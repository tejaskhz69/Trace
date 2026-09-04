/**
 * SESSION COMPLETE — what that hour in the gym actually proved.
 *
 * WHAT THIS SCREEN REFUSES TO DO
 * It does not tell you the session was "great". A single session cannot tell
 * anyone whether their training is working — that takes weeks, and the
 * adjudication engine owns that verdict. This screen reports what happened in
 * the room and stops there. Every congratulatory line here is tied to a
 * measurement that actually moved.
 *
 * PER-EXERCISE TREND
 * Each lift is compared against its best estimate from the previous six
 * weeks, EXCLUDING this session — otherwise every set is compared to itself
 * and nothing is ever progress. A lift with no history says FIRST TIME rather
 * than inventing a 0% change, because "no change" and "no comparison" are
 * different claims.
 *
 * MUSCLE SPLIT BY VOLUME, NOT SET COUNT
 * Set counts treat a 20 kg lateral raise and a 140 kg squat as equal work,
 * which is how a leg day ends up reading as "40% shoulders".
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { Button, Label, Panel, Rule } from '../../src/components/instrument';
import { api, type ExerciseTrend, type SessionSummary } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import {
  motion,
  palette,
  radius,
  space,
  strengthStateColor,
  SET_VERDICT_STATE,
  TREND_STATE,
  type,
} from '../../src/theme';

export default function SummaryScreen() {
  const { session } = useLocalSearchParams<{ session: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [data, setData] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session) return;
    try {
      // Finishing is idempotent -- it stamps ended_at only if unset -- so
      // landing here twice cannot rewrite the session's duration.
      setData(await api.finishSession(session));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this session.');
    }
  }, [session]);

  useEffect(() => {
    load();
  }, [load]);

  if (!data) {
    return (
      <View style={[styles.screen, styles.center, { backgroundColor: surfaces.void }]}>
        {error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <ActivityIndicator color={accent.brand} />
        )}
      </View>
    );
  }

  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + space.lg, paddingBottom: insets.bottom + space.xxl },
      ]}
    >
      <Animated.View entering={FadeInDown.duration(motion.base)}>
        <Label>Session complete</Label>
        <Text style={styles.headline}>{data.headline}</Text>
      </Animated.View>

      {/* ---------------------------------------------------- the totals */}
      <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
        <Panel padded={false}>
          <View style={styles.totals}>
            <Total label="Min" value={data.duration_min ?? '—'} />
            <Rule vertical />
            <Total label="Sets" value={data.total_sets} />
            <Rule vertical />
            <Total label="Reps" value={data.total_reps} />
            <Rule vertical />
            <Total
              label="Vol kg"
              value={Math.round(data.volume_kg).toLocaleString('en-US')}
            />
            <Rule vertical />
            <Total label="Avg RPE" value={data.avg_rpe ?? '—'} />
          </View>
        </Panel>
      </Animated.View>

      {/* ------------------------------------------------------ the lifts */}
      <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
        <Panel label="Lifts" padded={false}>
          {data.exercises.map((e, i) => {
            // Both estimates are already in the payload; the movement between
            // them is not, and it is the number a lifter can act on.
            const deltaKg =
              e.best_e1rm != null && e.previous_e1rm != null
                ? e.best_e1rm - e.previous_e1rm
                : null;
            return (
              <View key={e.exercise_id}>
                {i > 0 ? <Rule /> : null}
                <View style={styles.liftRow}>
                  <View style={styles.liftMain}>
                    <View style={styles.liftHead}>
                      <Text style={styles.liftIndex}>
                        {String(i + 1).padStart(2, '0')}
                      </Text>
                      <Text style={styles.liftName} numberOfLines={1}>
                        {e.name}
                      </Text>
                      <TrendChip trend={e.trend} deltaKg={deltaKg} />
                    </View>
                    <Text style={styles.liftMeta}>
                      {e.sets} set{e.sets === 1 ? '' : 's'} · top {e.top_weight_kg} kg ·{' '}
                      {Math.round(e.volume_kg).toLocaleString('en-US')} kg volume
                    </Text>
                    <ComparisonLine
                      trend={e.trend}
                      deltaKg={deltaKg}
                      deltaPct={e.delta_pct}
                    />
                    {/* One pip per working set, coloured by its verdict, from
                        the same map the chip above uses. The shape of a
                        session is visible before any number is read. */}
                    <View style={styles.pips}>
                      {e.set_verdicts.map((v, k) => (
                        <View
                          key={k}
                          style={[
                            styles.pip,
                            {
                              backgroundColor: strengthStateColor(
                                SET_VERDICT_STATE[v] ?? 'unrated',
                                accent.brand,
                              ),
                            },
                          ]}
                        />
                      ))}
                    </View>
                  </View>
                  <View style={styles.liftRight}>
                    <Text style={styles.liftE1rm}>
                      {e.best_e1rm ? `${e.best_e1rm}` : '—'}
                    </Text>
                    <Text style={styles.liftE1rmUnit}>KG EST.</Text>
                  </View>
                </View>
              </View>
            );
          })}
          {data.exercises.length === 0 ? (
            <Text style={styles.empty}>No sets were logged in this session.</Text>
          ) : null}
        </Panel>
      </Animated.View>

      {/* ---------------------------------------------------- muscle split */}
      {data.muscle_split.length > 0 ? (
        <Animated.View entering={FadeInDown.duration(motion.base).delay(120)}>
          <Panel label="Muscle split">
            <View style={styles.splitBar}>
              {data.muscle_split.map((m, i) => (
                <View
                  key={m.muscle}
                  style={{
                    flex: m.pct,
                    height: 8,
                    backgroundColor: SPLIT_TONES[i % SPLIT_TONES.length],
                  }}
                />
              ))}
            </View>
            <View style={styles.splitLegend}>
              {data.muscle_split.map((m, i) => (
                <View key={m.muscle} style={styles.splitItem}>
                  <View
                    style={[
                      styles.splitSwatch,
                      { backgroundColor: SPLIT_TONES[i % SPLIT_TONES.length] },
                    ]}
                  />
                  <Text style={styles.splitName}>{m.muscle}</Text>
                  <Text style={styles.splitPct}>{m.pct}%</Text>
                </View>
              ))}
            </View>
          </Panel>
        </Animated.View>
      ) : null}

      {/* --------------------------------------------------------- legend */}
      <View style={styles.legend}>
        <LegendRow
          color={strengthStateColor('up', accent.brand)}
          text="Raised your estimated max"
        />
        <LegendRow
          color={strengthStateColor('flat', accent.brand)}
          text="Held it — no change either way"
        />
        <LegendRow
          color={strengthStateColor('down', accent.brand)}
          text="Below your recent best"
        />
        <LegendRow
          color={strengthStateColor('unrated', accent.brand)}
          text="No history yet — nothing to compare"
        />
      </View>

      <Text style={styles.caveat}>
        One session cannot tell you whether your training is working. That takes
        weeks — the weekly verdict on Progress is the one that answers it.
      </Text>

      <Button label="Done" onPress={() => router.replace('/(tabs)/train')} />
    </ScrollView>
  );
}

/** Data colours, not the interaction accent — see theme.ts on that split. */
const SPLIT_TONES = [
  palette.seriesStrength,
  palette.seriesWeight,
  palette.seriesEnergy,
  palette.seriesSleep,
  palette.fiber,
];

function Total({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.total}>
      <Text style={styles.totalValue}>{value}</Text>
      <Label>{label}</Label>
    </View>
  );
}

/**
 * Status plus the movement, in kilograms.
 *
 * WHY KILOGRAMS AND NOT THE PERCENTAGE
 * The chip used to read "+2%". Two percent of what? A percentage of an
 * estimated one-rep max is a number nobody can act on — it does not tell you
 * what to put on the bar next week, and it makes a 2 kg move on a lateral
 * raise look identical to a 2.8 kg move on a squat. Kilograms are the unit the
 * gym is actually calibrated in. The percentage still earns its place on the
 * comparison line below, where it does the one job it is good at: making two
 * lifts of very different absolute loads comparable.
 *
 * Derived on the client from `best_e1rm - previous_e1rm`, both of which are
 * already in the payload. No API change, and nothing is shown that the server
 * did not measure: when either estimate is missing there is no comparison to
 * draw and the chip says so instead of rendering a zero.
 */
function TrendChip({
  trend,
  deltaKg,
}: {
  trend: ExerciseTrend;
  deltaKg: number | null;
}) {
  const accent = useAccent();
  const t = TREND_STATE[trend];
  const fg = strengthStateColor(t.state, accent.brand);
  return (
    <View style={styles.trendChip}>
      <Text style={[styles.trendText, { color: fg }]}>{t.label}</Text>
      {deltaKg != null && Math.abs(deltaKg) >= 0.05 ? (
        <Text style={[styles.trendDelta, { color: fg }]}>
          {deltaKg > 0 ? '+' : '−'}
          {Math.abs(deltaKg).toFixed(1)} KG
        </Text>
      ) : null}
    </View>
  );
}

/**
 * The sentence that says what "CONFIRMED" was measured against.
 *
 * The screen has always compared each lift to its best estimate in the last
 * six weeks, excluding this session — it is in this file's docstring and in
 * `REFERENCE_WINDOW_DAYS = 42` on the server. It was never on screen. A trend
 * badge whose baseline is invisible is a verdict without evidence, which is
 * the one thing this product is not supposed to ship.
 */
function ComparisonLine({
  trend,
  deltaKg,
  deltaPct,
}: {
  trend: ExerciseTrend;
  deltaKg: number | null;
  deltaPct: number | null;
}) {
  if (trend === 'FIRST_TIME') {
    return (
      <Text style={styles.liftCompare}>
        First time logged — nothing to compare against yet.
      </Text>
    );
  }
  if (deltaKg == null || Math.abs(deltaKg) < 0.05) {
    return (
      <Text style={styles.liftCompare}>
        Level with your best estimate of the last 6 weeks.
      </Text>
    );
  }
  const verb = deltaKg > 0 ? 'above' : 'below';
  const pct = deltaPct != null ? ` (${deltaPct > 0 ? '+' : ''}${deltaPct}%)` : '';
  return (
    <Text style={styles.liftCompare}>
      {Math.abs(deltaKg).toFixed(1)} kg {verb} your best of the last 6 weeks
      {pct}.
    </Text>
  );
}

function LegendRow({ color, text }: { color: string; text: string }) {
  return (
    <View style={styles.legendRow}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center' },
  content: { paddingHorizontal: space.lg, gap: space.md },

  headline: { ...type.title, color: palette.text, marginTop: space.xs },

  totals: { flexDirection: 'row', paddingVertical: space.lg },
  total: { flex: 1, alignItems: 'center', gap: space.xs },
  totalValue: { ...type.value, color: palette.text },

  liftRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.md,
  },
  liftMain: { flex: 1, gap: space.xs },
  liftHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  liftIndex: { ...type.labelSm, color: palette.textGhost },
  liftName: { ...type.heading, color: palette.text, flexShrink: 1 },
  liftMeta: { ...type.labelSm, color: palette.textFaint },
  /* The baseline behind the badge. Sentence case, not a tracked label: it is
     a claim about evidence, and tracked caps read as a readout rather than as
     something to be read. */
  liftCompare: { ...type.caption, color: palette.textDim, marginTop: space.xxs },
  pips: { flexDirection: 'row', gap: 3, marginTop: 2 },
  pip: { width: 14, height: 3, borderRadius: 2 },
  liftRight: { alignItems: 'flex-end' },
  liftE1rm: { ...type.valueSm, color: palette.text },
  liftE1rmUnit: { ...type.labelSm, fontSize: 8, color: palette.textGhost },

  trendChip: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  trendText: { ...type.labelSm, fontSize: 8 },
  trendDelta: { ...type.labelSm, fontSize: 9 },

  splitBar: {
    flexDirection: 'row',
    height: 8,
    borderRadius: radius.xs,
    overflow: 'hidden',
    marginTop: space.sm,
  },
  splitLegend: { marginTop: space.md, gap: space.sm },
  splitItem: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  splitSwatch: { width: 8, height: 8, borderRadius: 2 },
  splitName: {
    ...type.caption,
    color: palette.textDim,
    flex: 1,
    textTransform: 'capitalize',
  },
  splitPct: { ...type.valueSm, color: palette.text },

  legend: { gap: space.xs, paddingHorizontal: space.xs },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  legendDot: { width: 10, height: 3, borderRadius: 2 },
  legendText: { ...type.labelSm, color: palette.textGhost },

  caveat: {
    ...type.caption,
    color: palette.textFaint,
    lineHeight: 18,
    paddingHorizontal: space.xs,
  },
  empty: { ...type.caption, color: palette.textFaint, padding: space.lg },
  error: { ...type.caption, color: palette.danger },
});
