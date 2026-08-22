/**
 * Does what you ate yesterday show up in today's session?
 *
 * THE BET: Trace already collects both sides. MacroFactor is two apps away
 * from the training data, Cal AI has no training at all, and LiftBite logs
 * both and links neither. This screen is the one insight only this app is
 * positioned to produce — and it turns the training log into a reason to keep
 * logging food, which is the retention problem every nutrition app has.
 *
 * MOST OF THIS SCREEN'S JOB IS REFUSING.
 * Four verdicts, and three of them decline to make a claim:
 *
 *   insufficient_data  fewer than eight matched days
 *   no_contrast        carbs barely vary, so there is nothing to compare
 *   none_found         a real answer: no relationship in your data
 *   positive           the only one that produces a suggestion
 *
 * `no_contrast` is the subtle one and the reason the screen is trustworthy.
 * Someone eating 290 g of carbs every day will produce a correlation
 * coefficient, and it will be noise. Reporting it would have the user eat
 * differently on the strength of nothing.
 *
 * THE SUGGESTION IS CALORIE-NEUTRAL BY CONSTRUCTION — carbs up, fat down, same
 * total — and `kcal_delta` is rendered so the user can see that it is zero.
 * Non-negotiable #1 is about not inventing calories, and a training-day
 * suggestion is exactly where one would sneak in.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Label,
  Panel,
  Plain,
  Rule,
  Skeleton,
  StatCell,
} from '../../src/components/instrument';
import { api, type FuelReport } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

const VERDICT_LABEL: Record<string, string> = {
  positive: 'A PATTERN',
  none_found: 'NO LINK',
  insufficient_data: 'NOT YET',
  no_contrast: 'NO CONTRAST',
};

export default function FuelScreen() {
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [report, setReport] = useState<FuelReport | null>(null);
  const [failed, setFailed] = useState(false);
  const [training, setTraining] = useState(false);

  const load = useCallback((trainingTomorrow: boolean) => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .fuelReport(trainingTomorrow)
        .then((r) => alive && setReport(r))
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  useEffect(() => load(training), [load, training]);

  const verdictColor =
    report?.verdict === 'positive'
      ? palette.info
      : report?.verdict === 'none_found'
        ? palette.textDim
        : palette.textFaint;

  return (
    <SafeAreaView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      edges={['top']}
    >
      <View style={styles.head}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Label color={palette.textDim}>← Nutrition</Label>
        </Pressable>
        <Label color={palette.textFaint}>Fuel vs training</Label>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {failed ? (
          <Plain tone="danger">Couldn&apos;t load this.</Plain>
        ) : !report ? (
          <>
            <Skeleton height={210} />
            <Skeleton height={140} />
          </>
        ) : (
          <>
            {/* ------------------------------------------ the finding --- */}
            <Animated.View entering={FadeInDown.duration(motion.base)}>
              <Panel
                label="Carbs the day before"
                right={
                  <Label color={verdictColor}>
                    {VERDICT_LABEL[report.verdict] ?? '—'}
                  </Label>
                }
              >
                <Text style={styles.headline}>{report.headline}</Text>
                <Text style={styles.detail}>{report.detail}</Text>

                {report.verdict === 'positive' &&
                report.high_carb_volume &&
                report.low_carb_volume ? (
                  <>
                    <Rule style={styles.gap} />
                    {/* The same fact twice: once as a coefficient for people
                        who want it, once as two averages for everyone else. */}
                    <View style={styles.compare}>
                      <VolumeBar
                        label={`After ${Math.round(report.carb_threshold_g ?? 0)} g+`}
                        value={report.high_carb_volume}
                        peak={report.high_carb_volume}
                        color={palette.info}
                      />
                      <VolumeBar
                        label="After a lower day"
                        value={report.low_carb_volume}
                        peak={report.high_carb_volume}
                        color={palette.hairlineBright}
                      />
                    </View>

                    <View style={styles.stats}>
                      <StatCell
                        label="Uplift"
                        value={`${report.uplift_pct?.toFixed(0)}%`}
                      />
                      <StatCell label="Sessions" value={String(report.pairs)} />
                      <StatCell
                        label="Strength"
                        value={report.rho ? report.rho.toFixed(2) : '—'}
                      />
                    </View>
                  </>
                ) : null}

                {report.notes.length > 0 ? (
                  <Plain style={styles.gap}>{report.notes[0]}</Plain>
                ) : null}
              </Panel>
            </Animated.View>

            {/* ------------------------------------- the suggestion ----- */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
              <Panel
                label="Training tomorrow?"
                right={
                  <Pressable
                    onPress={() => setTraining((t) => !t)}
                    hitSlop={10}
                    accessibilityRole="switch"
                    accessibilityState={{ checked: training }}
                  >
                    <Label color={training ? accent.brand : palette.textFaint}>
                      {training ? 'YES' : 'NO'}
                    </Label>
                  </Pressable>
                }
              >
                {report.suggestion ? (
                  <>
                    <Text style={styles.headline}>
                      {report.suggestion.headline}
                    </Text>

                    <View style={styles.shiftRow}>
                      <View style={styles.shiftCell}>
                        <Label color={palette.textFaint}>Carbs</Label>
                        <Text style={[styles.shiftVal, { color: palette.carbs }]}>
                          +{Math.round(report.suggestion.carbs_delta_g)}
                          <Text style={styles.shiftUnit}> g</Text>
                        </Text>
                      </View>
                      <View style={styles.shiftCell}>
                        <Label color={palette.textFaint}>Fat</Label>
                        <Text style={[styles.shiftVal, { color: palette.fat }]}>
                          {Math.round(report.suggestion.fat_delta_g)}
                          <Text style={styles.shiftUnit}> g</Text>
                        </Text>
                      </View>
                      <View style={styles.shiftCell}>
                        <Label color={palette.textFaint}>Calories</Label>
                        {/* Zero, and shown. This is the guard rendered. */}
                        <Text style={styles.shiftVal}>
                          {report.suggestion.kcal_delta === 0
                            ? '0'
                            : Math.round(report.suggestion.kcal_delta)}
                          <Text style={styles.shiftUnit}> kcal</Text>
                        </Text>
                      </View>
                    </View>

                    <Plain style={styles.gap}>{report.suggestion.detail}</Plain>
                  </>
                ) : training ? (
                  <Plain>
                    No suggestion — there&apos;s no pattern in your data to base
                    one on. Making one up would be worse than saying nothing.
                  </Plain>
                ) : (
                  <Plain>
                    Flip this on for a training day and, if your data supports
                    one, Trace will suggest a macro shift at the same calories.
                  </Plain>
                )}
              </Panel>
            </Animated.View>

            {/* ------------------------------------------- the caveat --- */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
              <Panel label="How this is worked out">
                <Plain>
                  Rank correlation between the carbs you ate on one day and the
                  volume you lifted the next. It needs at least{' '}
                  <Text style={styles.b}>eight matched sessions</Text> and a
                  real spread in your carb intake before it will say anything —
                  a pattern found in six days of similar eating is noise with a
                  number attached.
                </Plain>
              </Panel>
            </Animated.View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function VolumeBar({
  label,
  value,
  peak,
  color,
}: {
  label: string;
  value: number;
  peak: number;
  color: string;
}) {
  const frac = peak > 0 ? value / peak : 0;
  return (
    <View style={styles.volRow}>
      <Text style={styles.volLabel} numberOfLines={1}>
        {label}
      </Text>
      <View style={styles.volTrack}>
        <View
          style={[
            styles.volFill,
            { width: `${Math.max(3, frac * 100)}%`, backgroundColor: color },
          ]}
        />
      </View>
      <Text style={styles.volVal}>{Math.round(value).toLocaleString()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  body: { padding: space.lg, paddingTop: 0, gap: space.md, paddingBottom: space.xxl },

  headline: { ...type.title, fontSize: 19, color: palette.text },
  detail: {
    ...type.body,
    fontSize: 13,
    color: palette.textDim,
    marginTop: space.xs,
    lineHeight: 20,
  },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
  gap: { marginTop: space.md },

  compare: { marginTop: space.md, gap: space.sm },
  volRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  volLabel: { ...type.labelSm, color: palette.textDim, width: 104 },
  volTrack: {
    flex: 1,
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: palette.hairline,
    overflow: 'hidden',
  },
  volFill: { height: '100%', borderRadius: radius.pill },
  volVal: {
    ...type.valueSm,
    fontSize: 13,
    color: palette.text,
    width: 52,
    textAlign: 'right',
  },

  stats: { flexDirection: 'row', marginTop: space.lg },

  shiftRow: { flexDirection: 'row', marginTop: space.md },
  shiftCell: { flex: 1, gap: 3 },
  shiftVal: { ...type.value, color: palette.text },
  shiftUnit: { ...type.labelSm, color: palette.textDim },
});
