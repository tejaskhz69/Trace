/**
 * Tab 1 · Home — ported from the design artifact.
 *
 * Three cards, in this order:
 *   1. REMAINING TODAY  — the full ring, a macro strip, and a sentence
 *   2. WORTH WATCHING   — the micronutrient ledger, with a real over state
 *   3. ACTIVITY TODAY   — steps / sleep / trained, seven days, and a sentence
 *
 * WHY THE RING IS A FULL CIRCLE
 * Each arc is one macro's share of the day's calorie target, so the segments
 * sum to the target and THE GAP IS WHAT'S LEFT. That is why the centre number
 * and the gap always agree — they are the same quantity drawn two ways. An
 * arc-per-macro-progress ring can't make that promise.
 *
 * WHY EVERY CARD ENDS IN A SENTENCE
 * A chart states a fact; the sentence says what to do about it. That is the
 * voice of the redesign, and the reason the app reads as explaining rather
 * than reporting. `Plain` is the primitive; keep it to one or two sentences.
 *
 * Performance rules unchanged: skeleton paints first, fetch after
 * InteractionManager, animation on shared values, never setState.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  InteractionManager,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Cell,
  DayBars,
  Label,
  LedgerBar,
  Panel,
  Plain,
  Ring,
  Skeleton,
  type RingSegment,
} from '../../src/components/instrument';
import { api, type ProgressReport } from '../../src/lib/api';
import { StreakPanel } from '../../src/components/streak-panel';
import { useAuth } from '../../src/state/useAuth';
import { useToday } from '../../src/state/useToday';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, space, type } from '../../src/theme';

const KCAL_PER_G = { protein: 4, carbs: 4, fat: 9 } as const;

/** "FRI · 15 AUG", matching the artifact's masthead. */
function stamp(): string {
  const d = new Date();
  const day = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
  const mon = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
  return `${day} · ${d.getDate()} ${mon}`;
}

function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();
  const user = useAuth((s) => s.user);

  const summary = useToday((s) => s.summary);
  const loading = useToday((s) => s.loading);
  const refreshing = useToday((s) => s.refreshing);
  const load = useToday((s) => s.load);
  const refresh = useToday((s) => s.refresh);

  const [ready, setReady] = useState(false);

  /**
   * Streak, consistency, and whether the phase is working.
   *
   * Fetched here rather than inside the panel so a failure degrades to
   * "no panel" instead of a broken card on the first screen of the app.
   */
  const [progress, setProgress] = useState<ProgressReport | null>(null);

  // Paint the skeleton first, fetch after the navigation animation settles.
  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      setReady(true);
      load();
    });
    return () => task.cancel();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      if (!ready) return;
      load();
      // Refetched on focus, not just on mount: logging a meal from the
      // Nutrition tab is exactly what flips "today open" to "today done",
      // and coming back to a stale streak would look like the log failed.
      let alive = true;
      api
        .progressReport()
        .then((r) => alive && setProgress(r))
        .catch(() => undefined);
      return () => {
        alive = false;
      };
    }, [ready, load]),
  );

  const ring = useMemo(() => {
    if (!summary) return null;
    const target = summary.calorie_target ?? 0;
    // Each arc is the macro's ENERGY contribution, not its gram count, so the
    // three arcs are directly comparable and sum to calories eaten.
    const segments: RingSegment[] = [
      { value: summary.protein_g * KCAL_PER_G.protein, color: palette.protein },
      { value: summary.carbs_g * KCAL_PER_G.carbs, color: palette.carbs },
      { value: summary.fat_g * KCAL_PER_G.fat, color: palette.fat },
    ];
    return { segments, target, left: Math.round(target - summary.calories) };
  }, [summary]);

  if (!ready || (loading && !summary)) {
    return (
      <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
        <View style={{ height: insets.top + 44 }} />
        <View style={styles.body}>
          <Skeleton height={300} />
          <Skeleton height={210} />
          <Skeleton height={230} />
        </View>
      </View>
    );
  }

  const target = summary?.calorie_target ?? null;
  const eaten = Math.round(summary?.calories ?? 0);
  const left = ring?.left ?? 0;
  const onTrack = target !== null && left >= 0;

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>TRACE</Text>
        </View>
        <View style={styles.barR}>
          <Text style={styles.stamp}>{stamp()}</Text>
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
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            tintColor={palette.textFaint}
          />
        }
      >
        {/* ---------------------------------------------- 1 · REMAINING */}
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel
            label="Remaining today"
            right={
              target === null ? (
                <Label color={palette.textFaint}>No target</Label>
              ) : (
                <Label color={onTrack ? accent.brand : palette.warn}>
                  {onTrack ? 'On track' : 'Over'}
                </Label>
              )
            }
          >
            {target === null ? (
              <Plain>
                You don&apos;t have a calorie target yet. Finish setup and
                Trace will build your week.
              </Plain>
            ) : (
              <>
                <View style={styles.ringWrap}>
                  <Ring segments={ring!.segments} total={target}>
                    <Text style={styles.ringNum}>{left.toLocaleString()}</Text>
                    <Text style={styles.ringUnit}>KCAL LEFT</Text>
                  </Ring>
                  <View style={styles.ringFeet}>
                    <Text style={styles.foot}>{eaten.toLocaleString()} EATEN</Text>
                    <Text style={styles.foot}>
                      {Math.round(target).toLocaleString()} TARGET
                    </Text>
                  </View>
                </View>

                {/* The ring can't label its own arcs at this size; the strip does. */}
                <View style={styles.row}>
                  <MacroCell
                    label="Protein"
                    value={summary!.protein_g}
                    target={summary!.protein_target_g}
                    color={palette.protein}
                  />
                  <MacroCell
                    label="Carbs"
                    value={summary!.carbs_g}
                    target={summary!.carb_target_g}
                    color={palette.carbs}
                  />
                  <MacroCell
                    label="Fat"
                    value={summary!.fat_g}
                    target={summary!.fat_target_g}
                    color={palette.fat}
                  />
                </View>

                <Plain style={styles.gapT} tone={onTrack ? 'signal' : 'warn'}>
                  {onTrack
                    ? `You've eaten ${eaten.toLocaleString()} today. About ${roomInFood(left)} worth of room left.`
                    : `You're ${Math.abs(left).toLocaleString()} kcal over today. One day doesn't decide the week — get back on target tomorrow.`}
                </Plain>
              </>
            )}
          </Panel>
        </Animated.View>

        {/* ------------------------------------------- 2 · CONSISTENCY
            The streak AND the phase verdict, together. See
            components/streak-panel.tsx for why they are never separated. */}
        {progress ? (
          <Animated.View entering={FadeInDown.duration(motion.base).delay(30)}>
            <StreakPanel report={progress} />
          </Animated.View>
        ) : null}

        {/* ------------------------------------------- 3 · WORTH WATCHING */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <WatchList summary={summary} />
        </Animated.View>

        {/* -------------------------------------------- 4 · ACTIVITY TODAY */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel
            label="Activity today"
            right={<Label color={palette.textFaint}>Not connected</Label>}
          >
            <View style={styles.row}>
              <Cell label="Steps" value="—" sub="connect a source" />
              <Cell label="Sleep" value="—" sub="connect a source" />
              <Cell label="Trained" value="—" sub="log a session" />
            </View>
            <DayBars
              values={[0, 0, 0, 0, 0, 0, 0]}
              labels={['S', 'M', 'T', 'W', 'T', 'F', 'S']}
              color={palette.seriesWeight}
              height={62}
            />
            <Plain style={styles.gapT}>
              Connect Apple Health, Strava or Garmin in Profile and your movement
              shows up here. Whatever it says,{' '}
              <Text style={styles.b}>you don&apos;t need to eat it back</Text> —
              it&apos;s already in your target.
            </Plain>
          </Panel>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

/**
 * One macro in the strip below the ring. The top rule is the ring's legend —
 * that colour and this colour are the same channel, which is the only reason
 * the ring is readable without labels on its arcs.
 */
function MacroCell({
  label,
  value,
  target,
  color,
}: {
  label: string;
  value: number;
  target: number | null;
  color: string;
}) {
  const g = Math.round(value);
  const left = target === null ? null : Math.round(target - value);
  return (
    <Cell
      label={label}
      value={g}
      unit="g"
      keyColor={color}
      sub={left === null ? 'no target' : left >= 0 ? `${left} g left` : `${-left} g over`}
      subTone={left !== null && left < 0 ? 'danger' : 'flat'}
    />
  );
}

/**
 * The micronutrient ledger.
 *
 * Bars are only rendered for nutrients we actually have data for. A day of
 * home-cooked food logged by hand will have no sodium figures at all, and an
 * empty bar reading "0 / 2,300" would be a lie in the reassuring direction.
 */
function WatchList({ summary }: { summary: ReturnType<typeof useToday.getState>['summary'] }) {
  if (!summary) return null;

  const rows = [
    {
      label: 'SODIUM',
      value: summary.sodium_mg,
      target: summary.sodium_limit_mg,
      unit: 'mg',
      color: palette.seriesWeight,
    },
    {
      label: 'POTASSIUM',
      value: summary.potassium_mg,
      target: summary.potassium_target_mg,
      unit: 'mg',
      color: palette.seriesWeight,
    },
    {
      label: 'SUGARS',
      value: summary.sugars_g,
      target: summary.sugars_limit_g,
      unit: 'g',
      color: palette.seriesEnergy,
    },
    {
      label: 'FIBRE',
      value: summary.fiber_g,
      target: summary.fiber_target_g,
      unit: 'g',
      color: palette.seriesStrength,
    },
  ];

  const known = rows.filter((r) => r.value !== null && r.target !== null);
  // Only sodium and sugars are ceilings. Potassium and fibre are floors to
  // reach, so exceeding them is good and must never be flagged as "over".
  const over = known.filter(
    (r) => (r.label === 'SODIUM' || r.label === 'SUGARS') && r.value! > r.target!,
  );

  return (
    <Panel
      label="Worth watching"
      right={
        known.length === 0 ? (
          <Label color={palette.textFaint}>No data</Label>
        ) : over.length > 0 ? (
          <Label color={palette.danger}>{over.length} over</Label>
        ) : (
          <Label color={palette.textFaint}>All under</Label>
        )
      }
    >
      {known.length === 0 ? (
        <Plain>
          None of today&apos;s foods carry sodium or sugar data yet. Scanning a
          barcode or picking from the database fills this in.
        </Plain>
      ) : (
        <>
          <View style={styles.ledger}>
            {known.map((r) => (
              <LedgerBar
                key={r.label}
                label={r.label}
                value={Math.round(r.value!)}
                target={Math.round(r.target!)}
                unit={r.unit}
                color={r.color}
              />
            ))}
          </View>
          {over.length > 0 ? (
            <Plain style={styles.gapT} tone="danger">
              {over[0].label === 'SODIUM' ? 'Sodium' : 'Sugars'} is{' '}
              <Text style={styles.b}>
                {Math.round(over[0].value! - over[0].target!).toLocaleString()}{' '}
                {over[0].unit} over
              </Text>
              . Restaurant gravies and packaged snacks carry most of it.
            </Plain>
          ) : (
            <Plain style={styles.gapT}>
              Everything&apos;s inside its limit today.
            </Plain>
          )}
        </>
      )}
    </Panel>
  );
}

/**
 * Turn a calorie gap into food, because "600 kcal" is not something most
 * people can picture and "two rotis and a bowl of dal" is.
 */
function roomInFood(kcal: number): string {
  if (kcal >= 900) return 'a full dinner';
  if (kcal >= 600) return 'two rotis and a bowl of dal';
  if (kcal >= 400) return 'a plate of rice and curry';
  if (kcal >= 250) return 'a bowl of curd and fruit';
  if (kcal >= 120) return 'a piece of fruit';
  return 'a cup of tea';
}

const styles = StyleSheet.create({
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

  ringWrap: { alignItems: 'center' },
  ringNum: { ...type.figure, fontSize: 42, color: palette.text },
  ringUnit: { ...type.labelSm, color: palette.textDim, marginTop: 2 },
  ringFeet: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignSelf: 'stretch',
    marginTop: space.xs,
  },
  foot: { ...type.labelSm, fontSize: 9.5, color: palette.textFaint },

  row: { flexDirection: 'row', gap: 9, marginTop: space.xs },
  ledger: { gap: 14 },
  gapT: { marginTop: space.md },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
