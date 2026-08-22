/**
 * Recipes — your shelf, and everyone else's.
 *
 * Two scopes behind one Segmented, because they answer two different
 * questions: LIBRARY is "what do I cook", DISCOVER is "what could I cook".
 * Mixing them into one list would bury the six recipes a person actually
 * makes under everything anyone ever published.
 *
 * THE ONE THING THIS SCREEN INSISTS ON: a recipe with no measured cooked
 * weight is marked. It logs by serving and only by serving, and saying so on
 * the row is cheaper than letting someone discover it at the moment they are
 * trying to log 200 g of it.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Button,
  Label,
  Panel,
  Rule,
  SearchField,
  Segmented,
  Skeleton,
} from '../../src/components/instrument';
import { IconSearch } from '../../src/components/icons';
import { api, type RecipeSort, type RecipeSummary } from '../../src/lib/api';
import { useAccent } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

type Scope = 'library' | 'discover';

const SCOPES = [
  { value: 'library' as const, label: 'My library' },
  { value: 'discover' as const, label: 'Discover' },
];

const SORTS = [
  { value: 'popular' as const, label: 'Popular' },
  { value: 'recent' as const, label: 'New' },
  { value: 'protein' as const, label: 'Protein' },
];

export default function RecipesScreen() {
  const router = useRouter();
  const accent = useAccent();

  const [scope, setScope] = useState<Scope>('library');
  const [sort, setSort] = useState<RecipeSort>('popular');
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<RecipeSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    let alive = true;
    setFailed(false);
    const task = InteractionManager.runAfterInteractions(() => {
      const req =
        scope === 'library'
          ? api.myRecipes('all', q || undefined)
          : api.discoverRecipes({ q: q || undefined, sort });
      req
        .then((r) => alive && setRows(r.recipes))
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, [scope, sort, q]);

  useEffect(() => {
    setRows(null);
    return load();
  }, [load]);

  // Coming back from the builder must show the recipe that was just saved.
  useFocusEffect(useCallback(() => load(), [load]));

  const empty = rows !== null && rows.length === 0;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.masthead}>
        <View>
          <Label>Nutrition</Label>
          <Text style={styles.mastheadName}>Recipes</Text>
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

      <View style={styles.controls}>
        <Segmented options={SCOPES} value={scope} onChange={setScope} />
        <SearchField
          value={q}
          onChangeText={setQ}
          placeholder={scope === 'library' ? 'Search your recipes' : 'Search published recipes'}
          leading={<IconSearch size={16} color={palette.textFaint} />}
        />
        {scope === 'discover' ? (
          <Segmented options={SORTS} value={sort} onChange={setSort} />
        ) : null}
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {rows === null && !failed ? (
          <View style={{ gap: space.md }}>
            <Skeleton height={78} />
            <Skeleton height={78} />
            <Skeleton height={78} />
          </View>
        ) : null}

        {failed ? (
          <Panel label="Offline">
            <Text style={styles.muted}>
              Couldn&apos;t reach the server. Your recipes are safe — pull back in
              when you have a connection.
            </Text>
          </Panel>
        ) : null}

        {empty ? (
          <Panel label={scope === 'library' ? 'Nothing here yet' : 'No matches'}>
            <Text style={styles.muted}>
              {scope === 'library'
                ? 'Build a recipe once and logging it takes two taps forever after. Keep it private, or publish it when it is good.'
                : 'Nothing published matches that yet. Yours could be the first.'}
            </Text>
          </Panel>
        ) : null}

        {(rows ?? []).map((r, i) => (
          <Animated.View
            key={r.id}
            entering={FadeInDown.duration(motion.base).delay(Math.min(i, 8) * 40)}
          >
            <RecipeRow
              row={r}
              accent={accent.brand}
              onPress={() => router.push(`/recipes/${r.id}`)}
            />
          </Animated.View>
        ))}

        <View style={{ height: space.xxxl }} />
      </ScrollView>

      <View style={styles.footer}>
        <Rule />
        <View style={styles.footerInner}>
          <Button label="New recipe" onPress={() => router.push('/recipes/new')} />
        </View>
      </View>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------

const RecipeRow = React.memo(
  function RecipeRowBase({
    row,
    accent,
    onPress,
  }: {
    row: RecipeSummary;
    accent: string;
    onPress: () => void;
  }) {
    const byline = row.is_owner
      ? row.visibility === 'published'
        ? 'Published by you'
        : 'Private'
      : (row.author_name ?? 'Someone');

    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${row.name}, ${Math.round(row.calories_per_serving)} calories per serving`}
        onPress={onPress}
        style={styles.row}
      >
        <View style={styles.rowTop}>
          <Text style={styles.rowName} numberOfLines={1}>
            {row.name}
          </Text>
          {row.visibility === 'published' ? (
            <View style={[styles.chip, { borderColor: accent }]}>
              <Text style={[type.labelSm, { color: accent }]}>Public</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.rowStats}>
          <Stat value={Math.round(row.calories_per_serving)} unit="kcal" label="per serving" />
          <Rule vertical />
          <Stat value={Math.round(row.protein_per_serving_g)} unit="g" label="protein" />
          <Rule vertical />
          <Stat value={row.ingredient_count} label="ingredients" />
        </View>

        <Text style={styles.rowMeta} numberOfLines={1}>
          {byline}
          {row.servings > 1 ? ` · makes ${row.servings}` : ''}
          {/* Stated on the row, not discovered at logging time. */}
          {row.yield_estimated ? ' · by serving only' : ''}
          {row.save_count > 0 ? ` · ${row.save_count} saved` : ''}
        </Text>
      </Pressable>
    );
  },
  // Primitives only — the row re-renders when a number changes, not when the
  // parent list re-fetches an identical object.
  (a, b) =>
    a.row.id === b.row.id &&
    a.row.name === b.row.name &&
    a.row.visibility === b.row.visibility &&
    a.row.calories_per_serving === b.row.calories_per_serving &&
    a.row.save_count === b.row.save_count &&
    a.accent === b.accent,
);

function Stat({ value, unit, label }: { value: number; unit?: string; label: string }) {
  return (
    <View style={styles.stat}>
      <View style={styles.statValue}>
        <Text style={[type.valueSm, { color: palette.text }]}>{value}</Text>
        {unit ? <Text style={styles.statUnit}>{unit}</Text> : null}
      </View>
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
  controls: { paddingHorizontal: space.lg, gap: space.md, paddingBottom: space.md },
  body: { paddingHorizontal: space.lg, gap: space.md },
  muted: { ...type.body, color: palette.textDim },

  row: {
    borderWidth: 1,
    borderColor: palette.hairline,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
    backgroundColor: palette.surface,
  },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowName: { ...type.heading, color: palette.text, flex: 1 },
  chip: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs,
  },
  rowStats: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  stat: { flex: 1, gap: space.xxs },
  statValue: { flexDirection: 'row', alignItems: 'baseline', gap: space.xxs },
  statUnit: { ...type.labelSm, color: palette.textFaint },
  rowMeta: { ...type.caption, color: palette.textFaint },

  footer: { backgroundColor: palette.void },
  footerInner: { padding: space.lg },
});
