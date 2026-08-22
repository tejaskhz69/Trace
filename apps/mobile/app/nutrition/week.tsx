/**
 * The weekly budget.
 *
 * THE BET: the daily target is what makes people quit at 8pm. You are 300
 * over, the day is "ruined", and the rational response — eat a little less
 * tomorrow — is invisible because the app resets to a fresh verdict at
 * midnight.
 *
 * A week-level budget matches how eating actually works. 300 over on Tuesday
 * is 300 borrowed from Thursday. Dinner out on Saturday is something you
 * SCHEDULE, and the app moves the calories before it happens rather than
 * scoring you afterwards.
 *
 * THE PROMISE AT THE BOTTOM IS NOT DECORATION. `carries_forward` comes off the
 * wire and is always zero, and the card says so in words. A budget that rolls
 * a deficit forward is a debt, and a user who starts Monday 900 in the hole
 * has been handed a reason to quit that the app invented.
 *
 * Flagged days are held on THIS screen and sent up as a query param rather
 * than persisted: flagging is a planning gesture, and a plan you made three
 * weeks ago silently reshaping this week would be worse than no memory at all.
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
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { Label, Panel, Plain, Rule, Skeleton } from '../../src/components/instrument';
import { api, type BudgetDay, type WeekBudget } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

const DOW = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const STATUS_LABEL: Record<string, string> = {
  on_pace: 'ON PACE',
  ahead: 'AHEAD',
  behind: 'BEHIND',
  blown: 'LET IT GO',
};

export default function WeekBudgetScreen() {
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [week, setWeek] = useState<WeekBudget | null>(null);
  const [flagged, setFlagged] = useState<string[]>([]);
  const [failed, setFailed] = useState(false);

  const load = useCallback((days: string[]) => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .weekBudget(days)
        .then((w) => alive && setWeek(w))
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  useEffect(() => load(flagged), [load, flagged]);

  const toggleFlag = useCallback((day: BudgetDay) => {
    // A past day cannot be planned around — the calories are already spent,
    // and pretending otherwise would rewrite numbers the user already saw.
    if (day.is_past) return;
    Haptics.selectionAsync();
    setFlagged((cur) =>
      cur.includes(day.day)
        ? cur.filter((d) => d !== day.day)
        : [...cur, day.day],
    );
  }, []);

  const statusColor = useMemo(() => {
    if (!week) return palette.textFaint;
    if (week.status === 'on_pace') return accent.brand;
    if (week.status === 'ahead') return palette.info;
    if (week.status === 'blown') return palette.seriesAlert;
    return palette.warn;
  }, [week, accent.brand]);

  /** Tallest bar sets the scale, so a big day doesn't clip. */
  const scale = useMemo(() => {
    if (!week) return 1;
    const vals = week.days.flatMap((d) => [
      d.planned_kcal,
      d.logged_kcal ?? 0,
    ]);
    return Math.max(week.daily_target, ...vals) * 1.1;
  }, [week]);

  return (
    <SafeAreaView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      edges={['top']}
    >
      <View style={styles.head}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Label color={palette.textDim}>← Nutrition</Label>
        </Pressable>
        <Label color={palette.textFaint}>
          {week ? `${week.days_left} days left` : 'This week'}
        </Label>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {failed ? (
          <Plain tone="danger">
            Couldn&apos;t load this week. Pull back and try again.
          </Plain>
        ) : !week ? (
          <>
            <Skeleton height={190} />
            <Skeleton height={120} />
          </>
        ) : (
          <>
            {/* ---------------------------------------- the budget ------ */}
            <Animated.View entering={FadeInDown.duration(motion.base)}>
              <Panel
                label="Budget remaining"
                right={
                  <Label color={statusColor}>
                    {STATUS_LABEL[week.status] ?? '—'}
                  </Label>
                }
              >
                <View style={styles.heroRow}>
                  <Text style={styles.hero}>
                    {Math.round(week.remaining).toLocaleString()}
                  </Text>
                  <Text style={styles.heroUnit}>kcal</Text>
                </View>
                <Text style={styles.sub}>{week.detail}</Text>

                {/* ---- the seven days ---- */}
                <View style={styles.chart}>
                  {week.days.map((d, i) => (
                    <DayBar
                      key={d.day}
                      day={d}
                      dow={DOW[i]}
                      scale={scale}
                      target={week.daily_target}
                      brand={accent.brand}
                      onPress={toggleFlag}
                    />
                  ))}
                </View>

                <View style={styles.legend}>
                  <LegendDot color={accent.brand} label="Logged" />
                  <LegendDot color={palette.hairlineBright} label="Planned" />
                  <Label color={palette.textFaint}>TAP A DAY TO FLAG IT</Label>
                </View>
              </Panel>
            </Animated.View>

            {/* ------------------------------------- redistribution ----- */}
            {week.days.some((d) => d.flagged && !d.is_past) ? (
              <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
                <Panel
                  label="Planned around"
                  right={<Label color={accent.brand}>MOVED</Label>}
                >
                  {week.days
                    .filter((d) => d.flagged && !d.is_past)
                    .map((d) => (
                      <View key={d.day} style={styles.shiftRow}>
                        <Text style={styles.shiftDay}>
                          {new Date(d.day).toLocaleDateString(undefined, {
                            weekday: 'long',
                          })}
                        </Text>
                        <Text style={[styles.shiftVal, { color: accent.brand }]}>
                          +{Math.round(d.shift)}
                          <Text style={styles.shiftUnit}> kcal</Text>
                        </Text>
                      </View>
                    ))}
                  <Rule style={styles.gap} />
                  <Plain style={styles.gap}>{week.notes[0]}</Plain>
                </Panel>
              </Animated.View>
            ) : (
              <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
                <Panel label="Eating out this week?">
                  <Plain>
                    Tap any upcoming day to flag it. Trace moves calories into
                    it from the rest of the week, so the meal costs you nothing
                    — the week still lands on target.
                  </Plain>
                </Panel>
              </Animated.View>
            )}

            {/* --------------------------------------- the promise ------ */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
              <Panel
                label="Next week"
                right={
                  <Label color={accent.brand}>
                    +{Math.round(week.carries_forward)} CARRIED
                  </Label>
                }
              >
                <Plain>
                  {week.notes[week.notes.length - 1]}
                </Plain>
              </Panel>
            </Animated.View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

/**
 * One day.
 *
 * Two bars in one column: the plan (hairline) and what was actually eaten
 * (solid). Overlaying them rather than pairing them side by side keeps seven
 * days legible on a phone, and makes over/under a matter of which bar is
 * taller rather than a number to read.
 */
const DayBar = React.memo(
  function DayBarBase({
    day,
    dow,
    scale,
    target,
    brand,
    onPress,
  }: {
    day: BudgetDay;
    dow: string;
    scale: number;
    target: number;
    brand: string;
    onPress: (d: BudgetDay) => void;
  }) {
    const H = 96;
    const plannedH = Math.max(2, (day.planned_kcal / scale) * H);
    const loggedH =
      day.logged_kcal !== null ? Math.max(2, (day.logged_kcal / scale) * H) : 0;
    const targetY = (target / scale) * H;

    const over = day.delta !== null && day.delta > 0;

    return (
      <Pressable
        onPress={() => onPress(day)}
        disabled={day.is_past}
        accessibilityRole="button"
        accessibilityLabel={`${dow}, ${Math.round(day.planned_kcal)} planned`}
        accessibilityState={{ selected: day.flagged, disabled: day.is_past }}
        style={styles.dayCol}
      >
        <View style={[styles.barArea, { height: H }]}>
          {/* target line */}
          <View style={[styles.targetLine, { bottom: targetY }]} />
          <View
            style={[
              styles.plannedBar,
              {
                height: plannedH,
                borderColor: day.flagged ? brand : palette.hairlineBright,
                backgroundColor: day.flagged ? `${brand}18` : 'transparent',
              },
            ]}
          />
          {day.logged_kcal !== null ? (
            <View
              style={[
                styles.loggedBar,
                {
                  height: loggedH,
                  backgroundColor: over ? palette.warn : brand,
                  opacity: day.is_past ? 0.55 : 1,
                },
              ]}
            />
          ) : null}
        </View>
        <Text
          style={[
            styles.dow,
            day.is_today && { color: palette.text },
            day.flagged && { color: brand },
          ]}
        >
          {dow}
        </Text>
      </Pressable>
    );
  },
  (a, b) =>
    a.day.day === b.day.day &&
    a.day.planned_kcal === b.day.planned_kcal &&
    a.day.logged_kcal === b.day.logged_kcal &&
    a.day.flagged === b.day.flagged &&
    a.scale === b.scale,
);

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
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

  heroRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  hero: { ...type.readout, fontSize: 44, color: palette.text },
  heroUnit: { ...type.labelSm, color: palette.textDim },
  sub: { ...type.body, fontSize: 13, color: palette.textDim, marginTop: space.xs, lineHeight: 19 },

  chart: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.lg,
  },
  dayCol: { alignItems: 'center', flex: 1, gap: space.xs },
  barArea: { width: 26, justifyContent: 'flex-end' },
  targetLine: {
    position: 'absolute',
    left: -3,
    right: -3,
    height: StyleSheet.hairlineWidth,
    backgroundColor: palette.hairlineBright,
  },
  plannedBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.sm,
  },
  loggedBar: {
    position: 'absolute',
    left: 4,
    right: 4,
    bottom: 0,
    borderRadius: radius.sm,
  },
  dow: { ...type.labelSm, color: palette.textFaint },

  legend: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    marginTop: space.md,
    flexWrap: 'wrap',
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 2 },
  legendText: { ...type.labelSm, color: palette.textDim, letterSpacing: 0.4 },

  shiftRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    paddingVertical: space.xs,
  },
  shiftDay: { ...type.heading, color: palette.text },
  shiftVal: { ...type.value },
  shiftUnit: { ...type.labelSm, color: palette.textDim },

  gap: { marginTop: space.md },
});
