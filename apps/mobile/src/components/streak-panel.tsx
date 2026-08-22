/**
 * Consistency, and whether the phase it powers is actually working.
 *
 * WHY THESE TWO THINGS SHARE ONE PANEL
 * A streak on its own is a slot machine. Forty diligent days on a bulk that
 * has added nothing but fat is not an achievement, and an app that shows the
 * 40 in large type and says nothing else is congratulating someone for
 * failing carefully.
 *
 * So the verdict is not optional decoration underneath the number — it is the
 * second half of the same sentence, and the server returns both from one
 * endpoint precisely so this component cannot render one without the other.
 *
 * WHY THE STREAK IS WORTH SHOWING AT ALL
 * Because adherence IS the intervention here. Adaptive TDEE derives
 * expenditure from intake against weight trend, so a week with four logged
 * days produces a materially worse number than a week with seven. The bar
 * under the streak is `data_confidence` — how much the engine has to work
 * with — which is what makes this a readout rather than a sticker.
 *
 * The honest number and the motivating number sit side by side: the streak
 * counts days you showed up, the percentage says what share of the month that
 * really was. Showing both is what stops the motivating one from lying.
 */

import React, { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Gauge, Label, Panel, Plain, Rule } from './instrument';
import type { ProgressReport } from '../lib/api';
import { useAccent } from '../state/useTheme';
import { palette, space, type } from '../theme';

const VERDICT_LABEL: Record<string, string> = {
  on_track: 'ON TRACK',
  too_fast: 'TOO FAST',
  too_slow: 'TOO SLOW',
  wrong_way: 'WRONG WAY',
  insufficient_data: 'TOO EARLY',
};

const GOAL_NOUN: Record<string, string> = {
  gain: 'Bulk',
  lose: 'Cut',
  recomp: 'Recomp',
  maintain: 'Maintenance',
};

export const StreakPanel = memo(function StreakPanelBase({
  report,
}: {
  report: ProgressReport;
}) {
  const accent = useAccent();
  const { consistency: c, phase } = report;

  // `warn` for the two states that need action, `signal` for on track, and a
  // muted tone for "too early" -- which is not a failure, just not an answer
  // yet. Non-negotiable #3: refusing to judge is a legitimate result.
  const tone =
    phase.verdict === 'on_track'
      ? accent.brand
      : phase.verdict === 'insufficient_data'
        ? palette.textFaint
        : phase.verdict === 'too_slow'
          ? palette.warn
          : palette.danger;

  return (
    <Panel
      label="Consistency"
      right={
        <Label color={c.logged_today ? accent.brand : palette.textFaint}>
          {c.logged_today ? 'TODAY DONE' : 'TODAY OPEN'}
        </Label>
      }
    >
      {/* ---- the streak, and the honest number beside it ---------------- */}
      <View style={styles.top}>
        <View>
          <Text style={styles.streak}>
            {c.current_streak}
            <Text style={styles.streakUnit}>
              {' '}
              day{c.current_streak === 1 ? '' : 's'}
            </Text>
          </Text>
          <Label color={palette.textFaint}>
            {c.days_logged} of last {c.window_days} ·{' '}
            {Math.round(c.consistency_pct * 100)}%
          </Label>
        </View>

        <View style={styles.best}>
          <Label color={palette.textFaint}>Best</Label>
          <Text style={styles.bestValue}>{c.longest_streak}</Text>
        </View>
      </View>

      {/* The bar is data confidence, NOT progress toward a badge. What it
          measures is how much the engine has to work with. */}
      <View style={styles.gaugeWrap}>
        <Gauge fraction={c.data_confidence} color={accent.brand} />
        <View style={styles.gaugeRow}>
          <Label color={palette.textFaint}>Data the engine can use</Label>
          {c.next_milestone && c.days_to_next ? (
            <Label color={palette.textFaint}>
              {c.days_to_next} to {c.next_milestone.toLowerCase()}
            </Label>
          ) : null}
        </View>
      </View>

      <Plain style={styles.gap}>{c.headline}</Plain>

      <Rule style={styles.gap} />

      {/* ---- and whether any of it is working --------------------------- */}
      <View style={styles.phaseHead}>
        <Label color={palette.textFaint}>
          {GOAL_NOUN[phase.goal] ?? 'Phase'}
          {phase.weeks_elapsed >= 1
            ? ` · week ${Math.max(1, Math.round(phase.weeks_elapsed))}`
            : ''}
        </Label>
        <Label color={tone}>{VERDICT_LABEL[phase.verdict] ?? '—'}</Label>
      </View>

      <View style={styles.phaseRow}>
        <Text style={styles.phaseHeadline}>{phase.headline}</Text>
        {phase.total_change_kg !== null ? (
          <Text style={[styles.phaseChange, { color: tone }]}>
            {phase.total_change_kg > 0 ? '+' : ''}
            {phase.total_change_kg.toFixed(1)}
            <Text style={styles.phaseUnit}> kg</Text>
          </Text>
        ) : null}
      </View>

      {phase.rate_kg_per_week !== null &&
      phase.target_rate_kg_per_week !== null ? (
        <View style={styles.rates}>
          <Rate label="Actual" value={phase.rate_kg_per_week} />
          <Rate label="Planned" value={phase.target_rate_kg_per_week} muted />
        </View>
      ) : null}

      {phase.notes.length > 0 ? (
        <Plain
          tone={
            phase.verdict === 'on_track'
              ? 'signal'
              : phase.verdict === 'insufficient_data'
                ? 'signal'
                : 'warn'
          }
          style={styles.gap}
        >
          {phase.notes[0]}
        </Plain>
      ) : (
        <Plain style={styles.gap}>{phase.detail}</Plain>
      )}
    </Panel>
  );
});

function Rate({
  label,
  value,
  muted,
}: {
  label: string;
  value: number;
  muted?: boolean;
}) {
  return (
    <View style={styles.rateCell}>
      <Label color={palette.textFaint}>{label}</Label>
      <Text
        style={[
          styles.rateValue,
          muted && { color: palette.textDim },
        ]}
      >
        {value > 0 ? '+' : ''}
        {value.toFixed(2)}
        <Text style={styles.rateUnit}> kg/wk</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  top: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  streak: { ...type.figure, color: palette.text },
  streakUnit: { ...type.labelSm, color: palette.textDim },
  best: { alignItems: 'flex-end', gap: 2 },
  bestValue: { ...type.valueSm, fontSize: 17, color: palette.textDim },

  gaugeWrap: { marginTop: space.md, gap: space.xs },
  gaugeRow: { flexDirection: 'row', justifyContent: 'space-between' },

  gap: { marginTop: space.md },

  phaseHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.md,
  },
  phaseRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    marginTop: space.xs,
  },
  phaseHeadline: { ...type.heading, color: palette.text, flex: 1 },
  phaseChange: { ...type.value },
  phaseUnit: { ...type.labelSm, color: palette.textDim },

  rates: { flexDirection: 'row', marginTop: space.md },
  rateCell: { flex: 1, gap: 2 },
  rateValue: { ...type.valueSm, fontSize: 16, color: palette.text },
  rateUnit: { ...type.labelSm, color: palette.textDim },
});
