/**
 * Tab 2 · Nutrition — ported from the design artifact.
 *
 * Four ways in, then the day so far:
 *
 *   AI scan · Barcode · Search · My foods
 *   Today · N meals
 *   Recent (tap to repeat)
 *
 * WHY THE TILES ARE THE WHOLE TAB
 * The artifact's note is right and worth keeping: anything more here and the
 * fastest path to logging a meal stops being obvious. Search results, portion
 * pickers and the correction flow all live one screen deeper, because the job
 * of THIS screen is to answer "how do I get this meal in" in under a second.
 *
 * WHY SEARCH IS A TILE AND A BAR
 * The bar is for people who know what they want to type. The tile is for
 * people who don't yet know search exists. Both route to the same place.
 *
 * ESTIMATES CARRY THEIR BAND HERE TOO (non-negotiable #2). A meal logged from
 * a photo shows "444 ±63"; one scanned from a barcode shows "verified". They
 * must never look equally certain.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  ItemRow,
  Label,
  Panel,
  Plain,
  Rule,
  SearchField,
  Skeleton,
  Tile,
} from '../../src/components/instrument';
import {
  IconBarcode,
  IconCamera,
  IconSearch,
  IconUser,
} from '../../src/components/icons';
import {
  api,
  type DayUncertainty,
} from '../../src/lib/api';
import {
  CertaintyReadout,
  CertaintyStrip,
} from '../../src/components/certainty';
import { useAuth } from '../../src/state/useAuth';
import { useToday } from '../../src/state/useToday';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, space, type } from '../../src/theme';

/** Which meal the user is most likely logging right now. */
function mealNow(): string {
  const h = new Date().getHours();
  if (h < 11) return 'BREAKFAST';
  if (h < 16) return 'LUNCH';
  if (h < 21) return 'DINNER';
  return 'SNACK';
}

function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

interface LoggedMeal {
  id?: string;
  display_name?: string;
  calories?: number;
  grams?: number;
  serving_label?: string | null;
  meal_type?: string;
  kcal_low?: number | null;
  kcal_high?: number | null;
}

export default function NutritionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();
  const user = useAuth((s) => s.user);

  const summary = useToday((s) => s.summary);
  const loading = useToday((s) => s.loading);
  const load = useToday((s) => s.load);

  const [query, setQuery] = useState('');

  /**
   * How many foods we can actually search.
   *
   * Read from the server rather than hardcoded. The placeholder said
   * "Search 273,000 foods" as a literal, which was already wrong once (it
   * used to say 12,000) and will be wrong again after the next ingestion
   * run. The number is the single most persuasive thing on this screen, so
   * it should not be a string somebody has to remember to update.
   */
  const [catalogueSize, setCatalogueSize] = useState<number | null>(null);

  /**
   * The day as a RANGE, not a number (non-negotiable #2).
   *
   * Loaded separately from the summary because it fails independently: if the
   * uncertainty endpoint is down the tab still shows the day, just without
   * the band. Degrading to a missing panel beats degrading to a broken tab.
   */
  const [certainty, setCertainty] = useState<DayUncertainty | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .sourcesStatus()
      .then((s) => alive && setCatalogueSize(s.catalogue_size))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      let alive = true;
      api
        .dayUncertainty()
        .then((c) => alive && setCertainty(c))
        .catch(() => undefined);
      return () => {
        alive = false;
      };
    }, [load]),
  );

  const meals = useMemo(
    () => ((summary?.meals ?? []) as LoggedMeal[]).slice().reverse(),
    [summary],
  );

  const total = Math.round(summary?.calories ?? 0);

  const goSearch = useCallback(
    (q?: string) => router.push({ pathname: '/food-search', params: q ? { q } : {} }),
    [router],
  );

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>NUTRITION</Text>
        </View>
        <View style={styles.barR}>
          <Text style={styles.stamp}>{mealNow()}</Text>
          <View style={[styles.avatar, { borderColor: surfaces.hairlineBright }]}>
            <Text style={styles.avatarText}>
              {initials(user?.display_name ?? null, user?.email ?? '')}
            </Text>
          </View>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.body,
          { paddingBottom: insets.bottom + space.xxl },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <SearchField
          value={query}
          onChangeText={setQuery}
          placeholder={
            catalogueSize
              ? `Search ${catalogueSize.toLocaleString()} foods`
              : 'Search foods, brands, restaurants'
          }
          leading={<IconSearch size={17} color={palette.textFaint} />}
        />
        {query.trim().length > 1 ? (
          <Plain>
            <Text style={styles.b} onPress={() => goSearch(query.trim())}>
              Search &ldquo;{query.trim()}&rdquo; →
            </Text>
          </Plain>
        ) : null}

        {/* ---------------------------------------- the day, as a range
            This sits ABOVE the entry tiles on purpose. The first thing the
            Nutrition tab should say is how much room is left and how sure we
            are about it — the ways to log come second. */}
        {certainty && certainty.items.length > 0 ? (
          <>
            <Animated.View entering={FadeInDown.duration(motion.base)}>
              <CertaintyReadout report={certainty} />
            </Animated.View>
            <Animated.View entering={FadeInDown.duration(motion.base).delay(20)}>
              <CertaintyStrip report={certainty} />
            </Animated.View>
          </>
        ) : null}

        {/* ------------------------------------------------ four ways in */}
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel>
            <View style={styles.tiles}>
              <Tile
                icon={<IconCamera size={22} color={accent.brand} />}
                name="AI scan"
                detail="Point at the plate. Returns a range, never one confident number."
                onPress={() => router.push('/scan')}
              />
              <Tile
                icon={<IconBarcode size={22} color={palette.textDim} />}
                name="Barcode"
                detail="Packaged food, straight off the label."
                onPress={() => router.push({ pathname: '/scan', params: { mode: 'barcode' } })}
              />
              <Tile
                icon={<IconSearch size={22} color={palette.textDim} />}
                name="Search"
                detail="Indian brands and restaurant dishes included."
                onPress={() => goSearch()}
              />
              {/* Was a second route into Search, which made it a dead tile.
                  Recipes is the thing this slot was reaching for: the dishes
                  you actually cook, logged in one tap by serving. */}
              <Tile
                icon={<IconUser size={22} color={palette.textDim} />}
                name="Recipes"
                detail="Your own dishes. Keep them private, or publish them."
                onPress={() => router.push('/recipes')}
              />
            </View>
          </Panel>
        </Animated.View>

        {/* --------------------------------------------- go deeper
            Four screens, each answering a question the day view can't. They
            are links rather than sections because the tab's job is the
            fastest path to logging, and burying that under five analyses is
            exactly the mistake this tab was designed to avoid. */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(30)}>
          <Panel label="Go deeper" padded={false}>
            <DeepLink
              name="This week"
              detail="A budget, not a daily verdict. Flag a dinner out and it's paid for."
              onPress={() => router.push('/nutrition/week')}
              first
            />
            <DeepLink
              name="Protein"
              detail="When it landed, how short you are, and the cheapest way to fix it."
              onPress={() => router.push('/nutrition/protein')}
            />
            <DeepLink
              name="All nutrients"
              detail="26 tracked, and honest about the ones it can't see."
              onPress={() => router.push('/nutrition/nutrients')}
            />
            <DeepLink
              name="Fuel vs training"
              detail="Whether yesterday's carbs show up in today's session."
              onPress={() => router.push('/nutrition/fuel')}
            />
          </Panel>
        </Animated.View>

        {/* ------------------------------------------------ today's numbers
            Two rows, and the split between them is meaningful. The top row is
            the three macros, which are TARGETS to hit. The bottom row is
            fibre, sugar and sodium — of which fibre is a floor and the other
            two are ceilings, so their bars fill toward a limit rather than
            toward a goal. Putting them in one undifferentiated grid, which is
            what most apps do, teaches the wrong reading of half the numbers.

            An unknown stays unknown. A meal logged by hand carries no sodium
            figure at all, and rendering that as an empty bar would tell
            someone they are comfortably under a limit they may have blown. */}
        {summary ? (
          <Animated.View entering={FadeInDown.duration(motion.base).delay(20)}>
            <Panel label="Today">
              <View style={styles.macroRow}>
                <MacroCell
                  label="Protein"
                  value={summary.protein_g}
                  target={summary.protein_target_g}
                  color={palette.protein}
                />
                <MacroCell
                  label="Carbs"
                  value={summary.carbs_g}
                  target={summary.carb_target_g}
                  color={palette.carbs}
                />
                <MacroCell
                  label="Fat"
                  value={summary.fat_g}
                  target={summary.fat_target_g}
                  color={palette.fat}
                />
              </View>

              <Rule style={styles.microRule} />

              <View style={styles.macroRow}>
                <MacroCell
                  label="Fiber"
                  value={summary.fiber_g}
                  target={summary.fiber_target_g}
                  color={palette.fiber}
                />
                <MacroCell
                  label="Sugar"
                  value={summary.sugars_g}
                  target={summary.sugars_limit_g}
                  color={palette.seriesSleep}
                  ceiling
                />
                <MacroCell
                  label="Sodium"
                  value={summary.sodium_mg}
                  target={summary.sodium_limit_mg}
                  color={palette.warn}
                  unit="mg"
                  ceiling
                />
              </View>
            </Panel>
          </Animated.View>
        ) : null}

        {/* ------------------------------------------------- today so far */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <Panel
            label={`Today · ${meals.length} ${meals.length === 1 ? 'meal' : 'meals'}`}
            right={<Label color={palette.textDim}>{total.toLocaleString()} kcal</Label>}
            padded={false}
          >
            {loading && !summary ? (
              <View style={styles.pad}>
                <Skeleton height={44} />
              </View>
            ) : meals.length === 0 ? (
              <View style={styles.pad}>
                <Plain>
                  Nothing logged yet today. The fastest way in is the{' '}
                  <Text style={styles.b}>AI scan</Text> — point it at your plate
                  and correct what it gets wrong.
                </Plain>
              </View>
            ) : (
              meals.map((m, i) => (
                <ItemRow
                  key={m.id ?? i}
                  title={m.display_name ?? 'Meal'}
                  subtitle={[
                    m.meal_type ? cap(m.meal_type) : null,
                    m.serving_label ?? (m.grams ? `${Math.round(m.grams)} g` : null),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  value={Math.round(m.calories ?? 0)}
                  plusMinus={band(m)}
                  last={i === meals.length - 1}
                />
              ))
            )}
          </Panel>
        </Animated.View>

        {/* ----------------------------------------------------- recent */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel
            label="Recent"
            right={<Label color={palette.textFaint}>Tap to repeat</Label>}
            padded={false}
          >
            {meals.length === 0 ? (
              <View style={styles.pad}>
                <Plain>
                  Foods you log show up here so a repeat meal is one tap. Most
                  people eat the same twenty things.
                </Plain>
              </View>
            ) : (
              meals.slice(0, 4).map((m, i, arr) => (
                <ItemRow
                  key={`r-${m.id ?? i}`}
                  title={m.display_name ?? 'Meal'}
                  subtitle={
                    m.serving_label ?? (m.grams ? `${Math.round(m.grams)} g` : undefined)
                  }
                  value={Math.round(m.calories ?? 0)}
                  plusMinus={band(m)}
                  note={band(m) == null ? 'verified' : undefined}
                  last={i === arr.length - 1}
                  onPress={() => goSearch(m.display_name)}
                />
              ))
            )}
          </Panel>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

/**
 * Half-width of the logged estimate's interval, or null when the entry came
 * from a label and carries no uncertainty.
 */
function band(m: LoggedMeal): number | null {
  if (m.kcal_low == null || m.kcal_high == null) return null;
  return Math.max(0, (m.kcal_high - m.kcal_low) / 2);
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}


/**
 * One nutrient: how much, against what, and which direction is good.
 *
 * `ceiling` flips the meaning of the bar. A protein bar filling up is
 * progress; a sodium bar filling up is a warning, and it turns amber past the
 * limit rather than staying the same calm colour it had at 40%.
 *
 * A null value renders as "—", never as 0. "This food contains no sodium" and
 * "we have no sodium figure for this food" are different facts, and summing
 * unknowns as zero is how an app quietly under-reports a day.
 */
function MacroCell({
  label,
  value,
  target,
  color,
  unit = 'g',
  ceiling,
}: {
  label: string;
  value: number | null;
  target: number | null;
  color: string;
  unit?: string;
  ceiling?: boolean;
}) {
  const known = value != null;
  const frac = known && target ? Math.min(1, value / target) : 0;
  const over = known && target ? value > target : false;
  const tone = ceiling && over ? palette.warn : color;

  return (
    <View style={styles.macroCell}>
      <Label>{label}</Label>
      <View style={styles.macroVals}>
        <Text style={styles.macroValue}>
          {known ? Math.round(value) : '—'}
        </Text>
        <Text style={styles.macroUnit}>{unit}</Text>
      </View>
      <View style={styles.macroTrack}>
        <View
          style={[styles.macroFill, { width: `${frac * 100}%`, backgroundColor: tone }]}
        />
      </View>
      <Text style={[styles.macroTarget, over && ceiling ? { color: palette.warn } : null]}>
        {!known
          ? 'no data'
          : target
            ? ceiling
              ? over
                ? `over by ${Math.round(value - target)}`
                : `of ${Math.round(target)} max`
              : `of ${Math.round(target)}`
            : 'no target'}
      </Text>
    </View>
  );
}

/**
 * One row in "Go deeper". A push, made to look like one.
 *
 * NOTE for anyone adding a route here: expo-router's typed-route union is
 * GENERATED into .expo/types/router.d.ts, and only while the dev server is
 * running. A route added between two `expo start` runs will fail `tsc` even
 * though it bundles and navigates perfectly. Start Metro once and the error
 * disappears — it is a fact about the codegen, not about your route.
 */
function DeepLink({
  name,
  detail,
  onPress,
  first,
}: {
  name: string;
  detail: string;
  onPress: () => void;
  first?: boolean;
}) {
  return (
    <>
      {first ? null : <Rule />}
      <Pressable
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={name}
        style={styles.deepRow}
      >
        <View style={styles.deepMid}>
          <Text style={styles.deepName}>{name}</Text>
          <Text style={styles.deepDetail}>{detail}</Text>
        </View>
        <Text style={styles.deepChev}>›</Text>
      </Pressable>
    </>
  );
}

const styles = StyleSheet.create({
  deepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  deepMid: { flex: 1, gap: 2 },
  deepName: { ...type.heading, color: palette.text },
  deepDetail: { ...type.labelSm, color: palette.textFaint, textTransform: 'none', letterSpacing: 0 },
  deepChev: { ...type.value, color: palette.textGhost },

  macroRow: { flexDirection: 'row', gap: space.md },
  macroCell: { flex: 1, gap: space.xs },
  macroVals: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
  macroValue: { ...type.value, color: palette.text },
  macroUnit: { ...type.labelSm, color: palette.textFaint },
  macroTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: palette.hairline,
    overflow: 'hidden',
  },
  macroFill: { height: 4, borderRadius: 2 },
  macroTarget: { ...type.labelSm, fontSize: 8, color: palette.textGhost },
  microRule: { marginVertical: space.lg },
  screen: { flex: 1 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
  brandText: { ...type.label, fontSize: 11, letterSpacing: 2, color: palette.text },
  barR: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  stamp: { ...type.labelSm, color: palette.textDim, letterSpacing: 1 },
  avatar: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: palette.raised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { ...type.labelSm, fontSize: 10.5, color: palette.textDim },

  body: { padding: space.lg, gap: space.md },
  tiles: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  pad: { padding: space.lg },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
