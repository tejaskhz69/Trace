/**
 * Tab 4 · Progress — ported from the design artifact.
 *
 *   IS IT WORKING?   the verdict, and the headline weight change
 *   WEIGHT           daily weigh-ins, the trend line, and the target corridor
 *   STRENGTH         the main lifts on one axis
 *
 * THIS TAB IS THE PRODUCT CLAIM
 * "We tell you whether you're gaining muscle or fat, not just whether the
 * scale moved" is answered here or nowhere. Which is exactly why the verdict
 * card must be willing to say INSUFFICIENT_DATA rather than guess: a confident
 * "mostly muscle" from two weigh-ins would be the single most damaging thing
 * this screen could print (non-negotiable #3).
 *
 * WHY THE RAW WEIGH-INS ARE STILL DRAWN
 * The trend line is what the engine acts on, but showing only the trend makes
 * the app look like it is hiding the noise. Drawing both — raw as faint dots,
 * trend as the solid line — is what teaches a user that a 0.8 kg jump
 * overnight is water, and it is the reason they stop panicking and stop
 * quitting.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { InteractionManager, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Cell,
  Delta,
  Label,
  LineChart,
  Panel,
  Plain,
  Readout,
  Skeleton,
  type LineSeries,
} from '../../src/components/instrument';
import { MaintenanceCard } from '../../src/components/maintenance-card';
import { api, request, type Maintenance, type WeightPoint } from '../../src/lib/api';
import { useAuth } from '../../src/state/useAuth';
import { useToday } from '../../src/state/useToday';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, space, type } from '../../src/theme';

const WEEKS = 10;

/** Fixed series colours. These are DATA, so they never follow the accent. */
const LIFT_COLORS = [
  palette.seriesStrength,
  palette.seriesWeight,
  palette.seriesSleep,
];

interface StrengthSeries {
  name: string;
  points: { week_start: string; e1rm: number }[];
  change_kg: number | null;
}

function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

export default function ProgressScreen() {
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();
  const user = useAuth((s) => s.user);
  const verdict = useToday((s) => s.verdict);
  const loadToday = useToday((s) => s.load);

  const [weights, setWeights] = useState<WeightPoint[] | null>(null);
  const [strength, setStrength] = useState<{
    series: StrengthSeries[];
    headline: string | null;
  } | null>(null);
  const [maintenance, setMaintenance] = useState<Maintenance | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => setReady(true));
    return () => task.cancel();
  }, []);

  const load = useCallback(async () => {
    loadToday();
    // Independent: a missing strength history must not blank the weight chart.
    const [w, s, m] = await Promise.allSettled([
      api.weightTrend(WEEKS * 7),
      request<{ series: StrengthSeries[]; headline: string | null }>(
        `/api/workouts/strength/overview?weeks=${WEEKS}`,
      ),
      api.maintenance(),
    ]);
    setWeights(w.status === 'fulfilled' ? w.value : []);
    setStrength(s.status === 'fulfilled' ? s.value : { series: [], headline: null });
    setMaintenance(m.status === 'fulfilled' ? m.value : null);
  }, [loadToday]);

  useFocusEffect(
    useCallback(() => {
      if (ready) load();
    }, [ready, load]),
  );

  const weightChart = useMemo(() => {
    if (!weights || weights.length === 0) return null;
    const raw = weights.map((p) => p.raw_kg);
    const trend = weights.map((p) => p.trend_kg);
    const first = trend[0];
    const last = trend[trend.length - 1];
    const change = last - first;
    const perWeek = weights.length > 7 ? change / (weights.length / 7) : null;

    const series: LineSeries[] = [
      {
        label: '',
        color: palette.textGhost,
        values: raw,
        dots: true,
        dashed: true,
      },
      { label: 'TREND', color: palette.seriesWeight, values: trend },
    ];
    return { series, change, perWeek, last, count: weights.length };
  }, [weights]);

  const strengthChart = useMemo(() => {
    if (!strength || strength.series.length === 0) return null;
    // Align every lift onto one week axis, leaving gaps where a lift was not
    // trained that week rather than joining across the hole.
    const allWeeks = Array.from(
      new Set(strength.series.flatMap((s) => s.points.map((p) => p.week_start))),
    ).sort();
    const series: LineSeries[] = strength.series.map((s, i) => {
      const by = new Map(s.points.map((p) => [p.week_start, p.e1rm]));
      return {
        label:
          s.change_kg == null
            ? s.name.slice(0, 8).toUpperCase()
            : `${s.name.slice(0, 8).toUpperCase()} ${s.change_kg > 0 ? '+' : ''}${s.change_kg}`,
        color: LIFT_COLORS[i % LIFT_COLORS.length],
        values: allWeeks.map((w) => by.get(w) ?? null),
      };
    });
    return { series, weeks: allWeeks.length };
  }, [strength]);

  if (!ready) {
    return (
      <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
        <View style={{ height: insets.top + 44 }} />
        <View style={styles.body}>
          <Skeleton height={180} />
          <Skeleton height={220} />
          <Skeleton height={220} />
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>PROGRESS</Text>
        </View>
        <View style={styles.barR}>
          <Text style={styles.stamp}>{WEEKS} WEEKS</Text>
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
      >
        {/* ---------------------------------------- measured maintenance
            Placed above the verdict because it is the number the user came
            for, and because the verdict below only makes sense once you know
            what expenditure it is being judged against. */}
        {maintenance ? (
          <Animated.View entering={FadeInDown.duration(motion.base)}>
            <MaintenanceCard data={maintenance} />
          </Animated.View>
        ) : null}

        {/* -------------------------------------------- is it working? */}
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel
            label="Is it working?"
            right={
              verdict ? (
                <Label color={accent.brand}>{verdictLabel(verdict.verdict)}</Label>
              ) : (
                <Label color={palette.textFaint}>Not yet</Label>
              )
            }
          >
            {weightChart && weightChart.count >= 2 ? (
              <>
                <View style={styles.readoutRow}>
                  <Text
                    style={[
                      styles.sign,
                      { color: weightChart.change >= 0 ? palette.up : palette.down },
                    ]}
                  >
                    {weightChart.change >= 0 ? '+' : '−'}
                  </Text>
                  <Readout
                    value={Math.abs(Math.round(weightChart.change * 10) / 10)}
                    size="readout"
                    color={weightChart.change >= 0 ? palette.up : palette.down}
                  />
                  <Text style={styles.readoutUnit}>kg</Text>
                </View>
                <Text style={styles.readoutSub}>
                  over the last {Math.round(weightChart.count / 7)} weeks
                </Text>
              </>
            ) : (
              <Text style={styles.readoutSub}>Not enough weigh-ins yet.</Text>
            )}

            <View style={styles.gapT}>
              {verdict ? (
                <Plain>{verdict.headline}</Plain>
              ) : (
                <Plain tone="warn">
                  Trace needs about{' '}
                  <Text style={styles.b}>three weeks of weigh-ins and food logs</Text>{' '}
                  before it will call muscle from fat. Until then it says so
                  rather than guessing — a confident verdict from two weeks of
                  data would be worse than none.
                </Plain>
              )}
            </View>
          </Panel>
        </Animated.View>

        {/* --------------------------------------------------- weight */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <Panel
            label="Weight"
            right={
              weightChart?.perWeek != null ? (
                <Label color={palette.textDim}>
                  {weightChart.perWeek >= 0 ? '+' : ''}
                  {weightChart.perWeek.toFixed(2)} kg / wk
                </Label>
              ) : (
                <Label color={palette.textFaint}>—</Label>
              )
            }
          >
            {weights === null ? (
              <Skeleton height={150} />
            ) : weightChart ? (
              <>
                <LineChart
                  series={weightChart.series}
                  height={150}
                  xLabels={[`${WEEKS}W AGO`, 'NOW']}
                />
                <View style={styles.legend}>
                  <LegendDot color={palette.textGhost} label="Daily weigh-in" />
                  <LegendDot color={palette.seriesWeight} label="Trend" />
                </View>
                <Plain style={styles.gapT}>
                  The dots jump; the line doesn&apos;t. Day-to-day swings are
                  water and gut contents —{' '}
                  <Text style={styles.b}>the trend is the only line worth
                  reacting to</Text>.
                </Plain>
              </>
            ) : (
              <Plain>
                No weigh-ins yet. Log your weight a few mornings a week and this
                chart starts telling you something the scale alone can&apos;t.
              </Plain>
            )}
          </Panel>
        </Animated.View>

        {/* ------------------------------------------------- strength */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel
            label="Strength"
            right={
              <Label color={strength?.headline ? accent.brand : palette.textFaint}>
                {strength?.headline ?? 'No lifts yet'}
              </Label>
            }
          >
            {strength === null ? (
              <Skeleton height={150} />
            ) : strengthChart ? (
              <>
                <LineChart
                  series={strengthChart.series}
                  height={150}
                  xLabels={['WK 1', `WK ${strengthChart.weeks}`]}
                />
                <View style={styles.cells}>
                  {strength.series.map((s, i) => (
                    <Cell
                      key={s.name}
                      label={s.name.slice(0, 14)}
                      value={s.points[s.points.length - 1]?.e1rm ?? 0}
                      unit="kg"
                      keyColor={LIFT_COLORS[i % LIFT_COLORS.length]}
                      sub={s.change_kg == null ? 'first week' : `${s.change_kg > 0 ? '+' : ''}${s.change_kg} kg`}
                      subTone={s.change_kg != null && s.change_kg < 0 ? 'danger' : 'up'}
                    />
                  ))}
                </View>
                <Plain style={styles.gapT}>
                  Rising lifts while the scale climbs is the signal that says{' '}
                  <Text style={styles.b}>the weight you&apos;re gaining is
                  mostly muscle</Text>. That pairing is the whole verdict.
                </Plain>
              </>
            ) : (
              <Plain>
                Log a few sessions and your main lifts appear here as estimated
                one-rep maxes. Strength is the half of the verdict the scale
                can&apos;t give you.
              </Plain>
            )}
          </Panel>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendSwatch, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

function verdictLabel(v: string): string {
  switch (v) {
    case 'lean_gain':
      return 'Mostly muscle';
    case 'fat_gain':
      return 'Mostly fat';
    case 'recomposition':
      return 'Recomping';
    case 'clean_cut':
      return 'Clean cut';
    case 'muscle_loss_risk':
      return 'Muscle at risk';
    default:
      return 'Not enough data';
  }
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

  readoutRow: { flexDirection: 'row', alignItems: 'baseline', gap: 2 },
  sign: { ...type.readout, fontSize: 44 },
  readoutUnit: { ...type.value, color: palette.textDim, marginLeft: 4 },
  readoutSub: { ...type.caption, color: palette.textFaint, marginTop: 2 },

  legend: { flexDirection: 'row', gap: space.lg, marginTop: space.sm },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendSwatch: { width: 10, height: 2, borderRadius: 1 },
  legendText: { ...type.caption, fontSize: 11.5, color: palette.textFaint },

  cells: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  gapT: { marginTop: space.md },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
