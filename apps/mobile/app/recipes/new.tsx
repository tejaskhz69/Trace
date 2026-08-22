/**
 * Build a recipe. Also edits one, via `?id=`.
 *
 * THE PANEL UPDATES AS YOU TYPE, and it is computed on the device with the
 * same arithmetic the server uses. Waiting for a round trip to find out that
 * your dal is 900 kcal a bowl makes the number feel like a verdict handed
 * down; watching it move as you adjust the ghee makes it feel like an
 * instrument. The server recomputes on save and is the authority — this is a
 * preview, and it is labelled as one.
 *
 * THE COOKED WEIGHT FIELD IS THE IMPORTANT ONE and is deliberately optional.
 * Leave it blank and the recipe logs by serving, which is exact. Fill it in
 * and per-100 g unlocks. What we never do is divide by the raw ingredient
 * weight and call it per-100 g — a dal loses ~15% of its mass as steam, and
 * that panel would under-report every gram logged against it.
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Button,
  Field,
  Label,
  Panel,
  Plain,
  Rule,
  SearchField,
  Segmented,
  Skeleton,
} from '../../src/components/instrument';
import { IconSearch } from '../../src/components/icons';
import {
  ApiError,
  api,
  type FoodItem,
  type RecipeDraftIngredient,
  type RecipeVisibility,
} from '../../src/lib/api';
import { useAccent } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

/** A line being edited. Carries its own panel so the preview needs no network. */
interface Line extends RecipeDraftIngredient {
  key: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
}

let seq = 0;
const nextKey = () => `line-${++seq}`;

export default function RecipeBuilderScreen() {
  const router = useRouter();
  const accent = useAccent();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const editing = typeof id === 'string' && id.length > 0;

  const [loading, setLoading] = useState(editing);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [servings, setServings] = useState('2');
  const [cookedWeight, setCookedWeight] = useState('');
  const [steps, setSteps] = useState<string[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [visibility, setVisibility] = useState<RecipeVisibility>('private');
  const [saving, setSaving] = useState(false);
  const [blockers, setBlockers] = useState<string[]>([]);

  React.useEffect(() => {
    if (!editing) return;
    let alive = true;
    api
      .recipe(id!)
      .then((r) => {
        if (!alive) return;
        setName(r.name);
        setDescription(r.description ?? '');
        setServings(String(r.servings));
        setCookedWeight(r.cooked_weight_g ? String(r.cooked_weight_g) : '');
        setSteps(r.steps);
        setVisibility(r.visibility);
        setLines(
          r.ingredients.map((ing) => ({
            key: nextKey(),
            food_item_id: ing.food_item_id,
            display_name: ing.display_name,
            grams: ing.grams,
            calories: ing.calories,
            protein_g: ing.protein_g,
            carbs_g: ing.carbs_g,
            fat_g: ing.fat_g,
            fiber_g: ing.fiber_g,
          })),
        );
      })
      .catch(() => Alert.alert('Could not open', 'That recipe would not load.'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [editing, id]);

  // --- the live panel -------------------------------------------------------
  //
  // Mirrors services/recipes.compose. Kept deliberately small: totals, per
  // serving, and NOTHING per-100 g unless a cooked weight was entered.
  const servingCount = Math.max(0.25, Number(servings) || 1);
  const cooked = cookedWeight.trim() ? Number(cookedWeight) : null;

  const preview = useMemo(() => {
    const usable = lines.filter((l) => l.grams > 0);
    const rawG = usable.reduce((s, l) => s + l.grams, 0);
    const acc = usable.reduce(
      (s, l) => {
        const f = l.grams / 100;
        return {
          calories: s.calories + l.calories * f,
          protein_g: s.protein_g + l.protein_g * f,
          carbs_g: s.carbs_g + l.carbs_g * f,
          fat_g: s.fat_g + l.fat_g * f,
        };
      },
      { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
    );
    const known = cooked !== null && Number.isFinite(cooked) && cooked > 0;
    return {
      rawG,
      total: acc,
      perServing: {
        calories: acc.calories / servingCount,
        protein_g: acc.protein_g / servingCount,
        carbs_g: acc.carbs_g / servingCount,
        fat_g: acc.fat_g / servingCount,
      },
      per100: known ? (acc.calories / cooked!) * 100 : null,
      servingGrams: known ? cooked! / servingCount : null,
    };
  }, [lines, servingCount, cooked]);

  // --- save -----------------------------------------------------------------
  const save = useCallback(async () => {
    if (!name.trim()) {
      Alert.alert('Name it first', 'A recipe needs a name you would recognise later.');
      return;
    }
    if (lines.length === 0) {
      Alert.alert('No ingredients', 'Add at least one ingredient.');
      return;
    }

    setSaving(true);
    setBlockers([]);
    const draft = {
      name: name.trim(),
      description: description.trim() || null,
      servings: servingCount,
      cooked_weight_g: cooked && Number.isFinite(cooked) ? cooked : null,
      steps: steps.filter((s) => s.trim()),
      tags: [],
      visibility,
      ingredients: lines.map((l) => ({
        food_item_id: l.food_item_id ?? null,
        display_name: l.display_name,
        grams: l.grams,
        calories: l.calories,
        protein_g: l.protein_g,
        carbs_g: l.carbs_g,
        fat_g: l.fat_g,
        fiber_g: l.fiber_g,
      })),
    };

    try {
      const saved = editing
        ? await api.updateRecipe(id!, draft)
        : await api.createRecipe(draft);
      router.replace(`/recipes/${saved.id}`);
    } catch (err) {
      // A refused publish comes back as the same PublishCheck shape the
      // dry-run endpoint returns, so it renders in the panel below rather
      // than as an alert the user has to dismiss to act on.
      const detail = err instanceof ApiError ? (err.detail as unknown) : null;
      const parsed =
        detail && typeof detail === 'object' && 'blockers' in detail
          ? ((detail as { blockers: string[] }).blockers ?? [])
          : [];
      if (parsed.length) setBlockers(parsed);
      else
        Alert.alert(
          'Could not save',
          err instanceof Error ? err.message : 'Something went wrong.',
        );
    } finally {
      setSaving(false);
    }
  }, [
    name, description, servingCount, cooked, steps, visibility, lines,
    editing, id, router,
  ]);

  if (loading) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={{ padding: space.lg, gap: space.md }}>
          <Skeleton height={44} />
          <Skeleton height={120} />
          <Skeleton height={200} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.masthead}>
        <View>
          <Label>{editing ? 'Editing' : 'New'}</Label>
          <Text style={styles.mastheadName}>Recipe</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cancel"
          onPress={() => router.back()}
          hitSlop={12}
        >
          <Text style={styles.close}>×</Text>
        </Pressable>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.body}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ---- the live panel ------------------------------------------ */}
          <Animated.View entering={FadeInDown.duration(motion.base)}>
            <Panel label="Per serving" right={<Label>Preview</Label>}>
              <View style={styles.previewTop}>
                <Text style={[type.figure, { color: palette.text }]}>
                  {Math.round(preview.perServing.calories)}
                </Text>
                <Text style={styles.unit}>kcal</Text>
              </View>
              <View style={styles.macroRow}>
                <Macro label="Protein" value={preview.perServing.protein_g} color={palette.protein} />
                <Rule vertical />
                <Macro label="Carbs" value={preview.perServing.carbs_g} color={palette.carbs} />
                <Rule vertical />
                <Macro label="Fat" value={preview.perServing.fat_g} color={palette.fat} />
              </View>
              <Rule />
              <Text style={styles.previewMeta}>
                {Math.round(preview.total.calories)} kcal total ·{' '}
                {Math.round(preview.rawG)} g of ingredients
                {preview.servingGrams
                  ? ` · ${Math.round(preview.servingGrams)} g a serving`
                  : ''}
              </Text>
            </Panel>
          </Animated.View>

          {blockers.length > 0 ? (
            <Plain tone="danger">
              {`Cannot publish yet. ${blockers.join(' ')}`}
            </Plain>
          ) : null}

          {/* ---- basics --------------------------------------------------- */}
          <Panel label="The dish">
            <View style={{ gap: space.md }}>
              <Field
                label="Name"
                value={name}
                onChangeText={setName}
                placeholder="Amma's dal tadka"
                autoCapitalize="sentences"
              />
              <Field
                label="Makes (servings)"
                value={servings}
                onChangeText={setServings}
                keyboardType="decimal-pad"
                suffix="servings"
              />
              <Field
                label="Cooked weight (optional)"
                value={cookedWeight}
                onChangeText={setCookedWeight}
                keyboardType="decimal-pad"
                suffix="g"
                placeholder="Weigh the finished dish"
              />
              <Text style={styles.hint}>
                {cooked
                  ? 'Logged by serving or by grams.'
                  : 'Without this, the recipe logs by serving only. Cooking changes the weight, so the raw ingredient total is not what came out of the pan.'}
              </Text>
            </View>
          </Panel>

          {/* ---- ingredients ---------------------------------------------- */}
          <Panel
            label="Ingredients"
            right={<Label>{`${lines.length}`}</Label>}
            padded={false}
          >
            {lines.map((line, i) => (
              <IngredientRow
                key={line.key}
                line={line}
                last={i === lines.length - 1}
                onChangeGrams={(g) =>
                  setLines((prev) =>
                    prev.map((l) => (l.key === line.key ? { ...l, grams: g } : l)),
                  )
                }
                onRemove={() =>
                  setLines((prev) => prev.filter((l) => l.key !== line.key))
                }
              />
            ))}
            {lines.length === 0 ? (
              <View style={{ padding: space.lg }}>
                <Text style={styles.hint}>
                  Search the food database below. Anything you add carries its
                  real nutrition, so the panel above is the actual dish.
                </Text>
              </View>
            ) : null}
          </Panel>

          <IngredientPicker
            onAdd={(item, grams) =>
              setLines((prev) => [
                ...prev,
                {
                  key: nextKey(),
                  food_item_id: item.id,
                  display_name: item.brand ? `${item.brand} ${item.name}` : item.name,
                  grams,
                  calories: item.calories,
                  protein_g: item.protein_g,
                  carbs_g: item.carbs_g,
                  fat_g: item.fat_g,
                  fiber_g: 0,
                },
              ])
            }
          />

          {/* ---- method ---------------------------------------------------- */}
          <Panel
            label="Method"
            right={
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Add a step"
                onPress={() => setSteps((s) => [...s, ''])}
                hitSlop={10}
              >
                <Text style={[type.label, { color: accent.brand }]}>+ Step</Text>
              </Pressable>
            }
          >
            <View style={{ gap: space.sm }}>
              {steps.map((s, i) => (
                <View key={i} style={styles.stepRow}>
                  <Text style={styles.stepNum}>{i + 1}</Text>
                  <TextInput
                    value={s}
                    onChangeText={(t) =>
                      setSteps((prev) => prev.map((v, j) => (j === i ? t : v)))
                    }
                    placeholder="What happens next"
                    placeholderTextColor={palette.textGhost}
                    selectionColor={accent.brand}
                    multiline
                    style={styles.stepInput}
                    accessibilityLabel={`Step ${i + 1}`}
                  />
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`Remove step ${i + 1}`}
                    onPress={() => setSteps((prev) => prev.filter((_, j) => j !== i))}
                    hitSlop={10}
                  >
                    <Text style={styles.remove}>×</Text>
                  </Pressable>
                </View>
              ))}
              {steps.length === 0 ? (
                <Text style={styles.hint}>
                  Optional, but a published recipe without a method is just a
                  shopping list.
                </Text>
              ) : null}
            </View>
          </Panel>

          {/* ---- visibility ------------------------------------------------ */}
          <Panel label="Who can see it">
            <View style={{ gap: space.md }}>
              <Segmented
                options={[
                  { value: 'private' as const, label: 'Private' },
                  { value: 'published' as const, label: 'Publish' },
                ]}
                value={visibility}
                onChange={setVisibility}
              />
              <Text style={styles.hint}>
                {visibility === 'private'
                  ? 'Only you. Nothing leaves your account, and you can publish it later.'
                  : 'Visible to everyone, with your name on it. You can take it back down at any time — though anyone who already copied it keeps their copy.'}
              </Text>
            </View>
          </Panel>

          <View style={{ height: space.xxxl }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <View style={styles.footer}>
        <Rule />
        <View style={styles.footerInner}>
          <Button
            label={editing ? 'Save changes' : 'Create recipe'}
            onPress={save}
            loading={saving}
            disabled={!name.trim() || lines.length === 0}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------

const IngredientRow = React.memo(
  function IngredientRowBase({
    line,
    last,
    onChangeGrams,
    onRemove,
  }: {
    line: Line;
    last: boolean;
    onChangeGrams: (grams: number) => void;
    onRemove: () => void;
  }) {
    const accent = useAccent();
    const kcal = Math.round((line.calories * line.grams) / 100);
    return (
      <View style={[styles.ingRow, last && { borderBottomWidth: 0 }]}>
        <View style={{ flex: 1, gap: space.xxs }}>
          <Text style={styles.ingName} numberOfLines={1}>
            {line.display_name}
          </Text>
          <Text style={styles.ingMeta}>
            {kcal} kcal
            {line.food_item_id ? '' : ' · hand-entered'}
          </Text>
        </View>
        <TextInput
          value={String(line.grams)}
          onChangeText={(t) => onChangeGrams(Number(t.replace(/[^0-9.]/g, '')) || 0)}
          keyboardType="decimal-pad"
          selectionColor={accent.brand}
          style={styles.gramsInput}
          accessibilityLabel={`Grams of ${line.display_name}`}
        />
        <Text style={styles.unitSm}>g</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Remove ${line.display_name}`}
          onPress={onRemove}
          hitSlop={10}
        >
          <Text style={styles.remove}>×</Text>
        </Pressable>
      </View>
    );
  },
  (a, b) =>
    a.line.key === b.line.key &&
    a.line.grams === b.line.grams &&
    a.line.display_name === b.line.display_name &&
    a.last === b.last,
);

/**
 * Search the catalogue and add a line.
 *
 * Debounced at 280 ms: the search hits Postgres trigram similarity and, on a
 * weak local result, fans out to Open Food Facts. Firing that per keystroke
 * would queue remote lookups nobody is waiting for any more.
 */
function IngredientPicker({
  onAdd,
}: {
  onAdd: (item: FoodItem, grams: number) => void;
}) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<FoodItem[]>([]);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback((text: string) => {
    setQ(text);
    if (timer.current) clearTimeout(timer.current);
    if (text.trim().length < 2) {
      setHits([]);
      return;
    }
    setBusy(true);
    timer.current = setTimeout(() => {
      api
        .searchFoods(text.trim())
        .then((r) => setHits(r.results.slice(0, 8)))
        .catch(() => setHits([]))
        .finally(() => setBusy(false));
    }, 280);
  }, []);

  React.useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return (
    <Panel label="Add an ingredient">
      <View style={{ gap: space.md }}>
        <SearchField
          value={q}
          onChangeText={search}
          placeholder="Search 578,000 foods"
          leading={<IconSearch size={16} color={palette.textFaint} />}
        />
        {busy ? <ActivityIndicator color={palette.textFaint} /> : null}
        {hits.map((item) => {
          const serving =
            item.serving_sizes?.find((s) => s.is_default)?.grams ?? 100;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="button"
              accessibilityLabel={`Add ${item.name}`}
              onPress={() => {
                onAdd(item, serving);
                setQ('');
                setHits([]);
              }}
              style={styles.hit}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.ingName} numberOfLines={1}>
                  {item.brand ? `${item.brand} ${item.name}` : item.name}
                </Text>
                <Text style={styles.ingMeta}>
                  {Math.round(item.calories)} kcal / 100 g
                  {item.is_verified ? ' · verified' : ''}
                </Text>
              </View>
              <Text style={styles.add}>+</Text>
            </Pressable>
          );
        })}
      </View>
    </Panel>
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
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.md,
  },
  mastheadName: { ...type.title, color: palette.text, marginTop: space.xxs },
  close: { ...type.title, color: palette.textDim, lineHeight: 26 },
  body: { paddingHorizontal: space.lg, gap: space.md, paddingTop: space.xs },

  previewTop: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.sm,
    marginBottom: space.md,
  },
  unit: { ...type.label, color: palette.textFaint },
  unitSm: { ...type.labelSm, color: palette.textFaint },
  macroRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    marginBottom: space.md,
  },
  previewMeta: { ...type.caption, color: palette.textFaint, marginTop: space.md },

  hint: { ...type.caption, color: palette.textDim },

  ingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: palette.hairline,
  },
  ingName: { ...type.body, color: palette.text },
  ingMeta: { ...type.caption, color: palette.textFaint },
  gramsInput: {
    ...type.valueSm,
    color: palette.text,
    minWidth: 54,
    textAlign: 'right',
    paddingVertical: space.xs,
  },
  remove: { ...type.title, color: palette.textFaint, lineHeight: 24 },
  add: { ...type.title, color: palette.textDim, lineHeight: 24 },

  hit: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: palette.hairline,
  },

  stepRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm },
  stepNum: {
    ...type.valueSm,
    color: palette.textFaint,
    width: 18,
    paddingTop: space.sm,
  },
  stepInput: {
    ...type.body,
    color: palette.text,
    flex: 1,
    borderWidth: 1,
    borderColor: palette.hairline,
    borderRadius: radius.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 40,
  },

  footer: { backgroundColor: palette.void },
  footerInner: { padding: space.lg },
});
