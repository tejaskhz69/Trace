/**
 * One recipe: what's in it, what it costs you, and how to log it.
 *
 * THE PORTION CONTROL IS THE POINT OF THE SCREEN. Everything above it exists
 * to let someone decide how much of this they are about to eat, so the log
 * action sits pinned at the bottom and never scrolls away.
 *
 * WHY THE GRAMS TAB SOMETIMES ISN'T THERE: a recipe whose finished weight was
 * never measured has no honest per-100 g figure — the raw ingredient sum is
 * not what came out of the pan. Rather than show a grams field that produces
 * a quietly wrong number, the control collapses to servings, which is exact,
 * and says why in one line. The server rejects a grams payload for such a
 * recipe regardless; this is the UI agreeing with it rather than discovering
 * it via a 422.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Button,
  Label,
  Panel,
  Plain,
  Rule,
  Segmented,
  Skeleton,
  Stepper,
} from '../../src/components/instrument';
import { api, type PublishCheck, type Recipe } from '../../src/lib/api';
import { useAccent } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

type Unit = 'servings' | 'grams';

const MEALS = [
  { value: 'breakfast' as const, label: 'Breakfast' },
  { value: 'lunch' as const, label: 'Lunch' },
  { value: 'dinner' as const, label: 'Dinner' },
  { value: 'snack' as const, label: 'Snack' },
];

export default function RecipeDetailScreen() {
  const router = useRouter();
  const accent = useAccent();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [failed, setFailed] = useState(false);
  const [unit, setUnit] = useState<Unit>('servings');
  const [servings, setServings] = useState(1);
  const [grams, setGrams] = useState(100);
  const [mealType, setMealType] = useState<'breakfast' | 'lunch' | 'dinner' | 'snack'>(
    'lunch',
  );
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .recipe(id)
        .then((r) => {
          if (!alive) return;
          setRecipe(r);
          if (r.serving_grams) setGrams(Math.round(r.serving_grams));
        })
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, [id]);

  useEffect(() => load(), [load]);

  // The portion, computed locally so the numbers move with the stepper.
  const portion = useMemo(() => {
    if (!recipe) return null;
    if (unit === 'grams' && recipe.per_100g) {
      const f = grams / 100;
      return {
        calories: recipe.per_100g.calories * f,
        protein_g: recipe.per_100g.protein_g * f,
        carbs_g: recipe.per_100g.carbs_g * f,
        fat_g: recipe.per_100g.fat_g * f,
      };
    }
    const f = servings / (recipe.servings || 1);
    return {
      calories: recipe.total.calories * f,
      protein_g: recipe.total.protein_g * f,
      carbs_g: recipe.total.carbs_g * f,
      fat_g: recipe.total.fat_g * f,
    };
  }, [recipe, unit, servings, grams]);

  const logIt = useCallback(async () => {
    if (!recipe) return;
    setBusy(true);
    try {
      await api.logRecipe(recipe.id, {
        ...(unit === 'grams' && recipe.per_100g ? { grams } : { servings }),
        meal_type: mealType,
      });
      router.back();
    } catch (err) {
      Alert.alert(
        'Could not log it',
        err instanceof Error ? err.message : 'Something went wrong.',
      );
    } finally {
      setBusy(false);
    }
  }, [recipe, unit, grams, servings, mealType, router]);

  const togglePublish = useCallback(async () => {
    if (!recipe) return;
    const goingPublic = recipe.visibility === 'private';

    if (goingPublic) {
      // Dry-run first so the confirmation can state the real consequences
      // instead of a generic "are you sure".
      let check: PublishCheck;
      try {
        check = await api.recipePublishCheck(recipe.id);
      } catch {
        Alert.alert('Could not check', 'Try again in a moment.');
        return;
      }
      if (!check.ok) {
        Alert.alert('Not ready to publish', check.blockers.join('\n\n'));
        return;
      }
      const body = [
        'Anyone using Trace will be able to find, log and copy this recipe, with your name on it.',
        ...check.cautions,
        'You can take it back down later.',
      ].join('\n\n');
      Alert.alert('Publish this recipe?', body, [
        { text: 'Not yet', style: 'cancel' },
        { text: 'Publish', onPress: () => setVisibility('published') },
      ]);
      return;
    }

    Alert.alert(
      'Make this private?',
      'It disappears from search for everyone else. Anyone who already copied it keeps their copy — that is what copying means.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Make private', onPress: () => setVisibility('private') },
      ],
    );

    async function setVisibility(v: 'private' | 'published') {
      try {
        setRecipe(await api.setRecipeVisibility(recipe!.id, v));
      } catch (err) {
        Alert.alert(
          'Could not change it',
          err instanceof Error ? err.message : 'Something went wrong.',
        );
      }
    }
  }, [recipe]);

  const toggleSave = useCallback(async () => {
    if (!recipe) return;
    const wasSaved = recipe.is_saved;
    // Optimistic: this is a reversible one-tap action, and waiting on a round
    // trip to fill in a bookmark is the kind of latency people notice.
    setRecipe({ ...recipe, is_saved: !wasSaved });
    try {
      await (wasSaved ? api.unsaveRecipe(recipe.id) : api.saveRecipe(recipe.id));
    } catch {
      setRecipe({ ...recipe, is_saved: wasSaved });
    }
  }, [recipe]);

  const fork = useCallback(async () => {
    if (!recipe) return;
    try {
      const copy = await api.forkRecipe(recipe.id);
      router.replace(`/recipes/${copy.id}`);
    } catch {
      Alert.alert('Could not copy', 'Try again in a moment.');
    }
  }, [recipe, router]);

  const remove = useCallback(() => {
    if (!recipe) return;
    Alert.alert(
      `Delete ${recipe.name}?`,
      'Meals you have already logged from it stay in your history. This only removes the recipe.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.deleteRecipe(recipe.id);
              router.back();
            } catch {
              Alert.alert('Could not delete', 'Try again in a moment.');
            }
          },
        },
      ],
    );
  }, [recipe, router]);

  if (failed) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={{ padding: space.lg }}>
          <Panel label="Not found">
            <Text style={styles.muted}>
              This recipe is gone, or its author made it private.
            </Text>
          </Panel>
        </View>
      </SafeAreaView>
    );
  }

  if (!recipe || !portion) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={{ padding: space.lg, gap: space.md }}>
          <Skeleton height={44} />
          <Skeleton height={160} />
          <Skeleton height={220} />
        </View>
      </SafeAreaView>
    );
  }

  const canUseGrams = recipe.per_100g !== null;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.masthead}>
        <View style={{ flex: 1 }}>
          <Label>
            {recipe.is_owner
              ? recipe.visibility === 'published'
                ? 'Published by you'
                : 'Private recipe'
              : `By ${recipe.author_name ?? 'someone'}`}
          </Label>
          <Text style={styles.mastheadName} numberOfLines={2}>
            {recipe.name}
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={() => router.back()}
          hitSlop={12}
        >
          <Text style={styles.close}>×</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {/* ---- the portion being logged ----------------------------------- */}
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel label="This portion">
            <View style={styles.hero}>
              <Text style={[type.readout, { color: palette.text }]}>
                {Math.round(portion.calories)}
              </Text>
              <Text style={styles.unit}>kcal</Text>
            </View>
            <View style={styles.macroRow}>
              <Macro label="Protein" value={portion.protein_g} color={palette.protein} />
              <Rule vertical />
              <Macro label="Carbs" value={portion.carbs_g} color={palette.carbs} />
              <Rule vertical />
              <Macro label="Fat" value={portion.fat_g} color={palette.fat} />
            </View>
          </Panel>
        </Animated.View>

        {/* ---- how much ---------------------------------------------------- */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <Panel label="How much">
            <View style={{ gap: space.md }}>
              {canUseGrams ? (
                <Segmented
                  options={[
                    { value: 'servings' as const, label: 'Servings' },
                    { value: 'grams' as const, label: 'Grams' },
                  ]}
                  value={unit}
                  onChange={setUnit}
                />
              ) : null}

              {unit === 'grams' && canUseGrams ? (
                <Stepper
                  value={grams}
                  onChange={setGrams}
                  min={10}
                  max={2000}
                  step={10}
                  unit="g"
                />
              ) : (
                <Stepper
                  value={servings}
                  onChange={setServings}
                  min={0.5}
                  max={10}
                  step={0.5}
                  unit={servings === 1 ? 'serving' : 'servings'}
                  format={(v) => (Number.isInteger(v) ? String(v) : v.toFixed(1))}
                />
              )}

              {!canUseGrams ? (
                <Text style={styles.hint}>
                  Servings only — nobody weighed the finished dish, and the raw
                  ingredient weight is not what came out of the pan.
                  {recipe.is_owner ? ' Add the cooked weight to unlock grams.' : ''}
                </Text>
              ) : null}

              <Rule />
              <Segmented options={MEALS} value={mealType} onChange={setMealType} />
            </View>
          </Panel>
        </Animated.View>

        {recipe.warnings.length > 0 && recipe.is_owner ? (
          <Plain tone="warn">{recipe.warnings.join(' ')}</Plain>
        ) : null}

        {/* ---- the whole recipe -------------------------------------------- */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel
            label="Ingredients"
            right={<Label>{`Makes ${recipe.servings}`}</Label>}
            padded={false}
          >
            {recipe.ingredients.map((ing, i) => (
              <View
                key={ing.id}
                style={[
                  styles.ingRow,
                  i === recipe.ingredients.length - 1 && { borderBottomWidth: 0 },
                ]}
              >
                <Text style={styles.ingName} numberOfLines={1}>
                  {ing.display_name}
                </Text>
                <Text style={styles.ingGrams}>{Math.round(ing.grams)} g</Text>
              </View>
            ))}
          </Panel>
        </Animated.View>

        {recipe.steps.length > 0 ? (
          <Panel label="Method">
            <View style={{ gap: space.md }}>
              {recipe.steps.map((s, i) => (
                <View key={i} style={styles.stepRow}>
                  <Text style={styles.stepNum}>{i + 1}</Text>
                  <Text style={styles.stepText}>{s}</Text>
                </View>
              ))}
            </View>
          </Panel>
        ) : null}

        {/* ---- provenance --------------------------------------------------- */}
        <Panel label="The numbers">
          <Text style={styles.muted}>
            {recipe.sourced_fraction >= 0.99
              ? 'Every ingredient came from the food database.'
              : `${Math.round(recipe.sourced_fraction * 100)}% of the calories are traceable to the food database; the rest was entered by hand.`}
            {recipe.forked_from_id ? ' Copied from another recipe.' : ''}
          </Text>
        </Panel>

        {/* ---- owner / visitor actions -------------------------------------- */}
        <View style={{ gap: space.sm }}>
          {recipe.is_owner ? (
            <>
              <Button
                label="Edit recipe"
                variant="outline"
                onPress={() => router.push(`/recipes/new?id=${recipe.id}`)}
              />
              <Button
                label={recipe.visibility === 'published' ? 'Make private' : 'Publish'}
                variant="outline"
                onPress={togglePublish}
              />
              <Button label="Delete" variant="ghost" onPress={remove} />
            </>
          ) : (
            <>
              <Button
                label={recipe.is_saved ? 'Saved to your library' : 'Save to library'}
                variant="outline"
                onPress={toggleSave}
              />
              <Button label="Copy and edit" variant="ghost" onPress={fork} />
            </>
          )}
        </View>

        <View style={{ height: space.xxxl }} />
      </ScrollView>

      <View style={styles.footer}>
        <Rule />
        <View style={styles.footerInner}>
          <Button
            label={`Log ${
              unit === 'grams' && canUseGrams
                ? `${grams} g`
                : servings === 1
                  ? '1 serving'
                  : `${servings} servings`
            }`}
            onPress={logIt}
            loading={busy}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}

function Macro({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={{ flex: 1, gap: space.xxs, alignItems: 'center' }}>
      <Text style={[type.valueSm, { color }]}>{Math.round(value)}g</Text>
      <Label>{label}</Label>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.void },
  masthead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.md,
  },
  mastheadName: { ...type.title, color: palette.text, marginTop: space.xxs },
  close: { ...type.title, color: palette.textDim, lineHeight: 26 },
  body: { paddingHorizontal: space.lg, gap: space.md },

  hero: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  unit: { ...type.label, color: palette.textFaint },
  macroRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    marginTop: space.lg,
  },

  hint: { ...type.caption, color: palette.textDim },
  muted: { ...type.body, color: palette.textDim },

  ingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: palette.hairline,
  },
  ingName: { ...type.body, color: palette.text, flex: 1 },
  ingGrams: { ...type.valueSm, color: palette.textDim },

  stepRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  stepNum: { ...type.valueSm, color: palette.textFaint, width: 18 },
  stepText: { ...type.body, color: palette.text, flex: 1 },

  footer: { backgroundColor: palette.void },
  footerInner: { padding: space.lg },
});
