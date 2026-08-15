/**
 * The weekly verdict card. This is the product.
 *
 * Design intent: it must read as a considered judgement, not a notification.
 * Three rules:
 *
 *  1. The headline is a SENTENCE, not a metric. "You're gaining mostly lean
 *     mass" beats "Lean gain: +4.2%".
 *  2. The two signals (weight, strength) are always shown together, because
 *     the whole claim is that neither means anything alone.
 *  3. "Show the math" is always available. MacroFactor's cult loyalty comes
 *     from showing its work; this costs a day of engineering and buys the
 *     "this app is honest" review sentiment no ad budget can.
 */

import React, { useState } from 'react';
import { LayoutAnimation, Platform, Pressable, StyleSheet, Text, UIManager, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { Card, Divider } from './ui';
import type { Verdict } from '../state/useToday';
import { motion, palette, radius, space, type, verdictStyle } from '../theme';

if (
  Platform.OS === 'android' &&
  UIManager.setLayoutAnimationEnabledExperimental
) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Props {
  verdict: Verdict;
  compact?: boolean;
  onPress?: () => void;
  onAccept?: () => void;
}

export function VerdictCard({ verdict, compact, onPress, onAccept }: Props) {
  const [showMath, setShowMath] = useState(false);
  const style = verdictStyle[verdict.verdict] ?? verdictStyle.insufficient_data;

  const strength = verdict.strength_index_delta_pct;
  const weight = verdict.weight_delta_pct_per_week;

  const body = (
    <Card style={[styles.card, { borderColor: `${style.color}44` }]}>
      <View style={styles.headerRow}>
        <View style={[styles.badge, { backgroundColor: `${style.color}22` }]}>
          <Text style={[styles.badgeIcon, { color: style.color }]}>
            {style.glyph}
          </Text>
        </View>
        <View style={styles.flex}>
          <Text style={styles.eyebrow}>This week</Text>
          <Text style={styles.headline}>{verdict.headline}</Text>
        </View>
      </View>

      {/* The two signals, always together. */}
      <View style={styles.signals}>
        <Signal
          label="Strength"
          value={strength != null ? `${strength >= 0 ? '+' : ''}${strength.toFixed(1)}%` : '—'}
          tone={
            strength == null
              ? 'neutral'
              : strength > 0.5
                ? 'good'
                : strength < -0.5
                  ? 'bad'
                  : 'neutral'
          }
        />
        <View style={styles.signalDivider} />
        <Signal
          label="Weight / wk"
          value={weight != null ? `${weight >= 0 ? '+' : ''}${weight.toFixed(2)}%` : '—'}
          tone="neutral"
        />
      </View>

      {!compact && (
        <>
          <Text style={styles.explanation}>{verdict.explanation}</Text>

          {verdict.recommended_target != null && (
            <View style={styles.targetRow}>
              <Text style={styles.targetLabel}>New target</Text>
              <Text style={styles.targetValue}>
                {Math.round(verdict.recommended_target)} kcal
              </Text>
            </View>
          )}

          <Divider />

          <Pressable
            onPress={() => {
              LayoutAnimation.configureNext(
                LayoutAnimation.create(
                  motion.base,
                  LayoutAnimation.Types.easeInEaseOut,
                  LayoutAnimation.Properties.opacity,
                ),
              );
              setShowMath((v) => !v);
            }}
            accessibilityRole="button"
            hitSlop={8}
          >
            <Text style={styles.mathToggle}>
              {showMath ? 'Hide the math' : 'Show the math'}
            </Text>
          </Pressable>

          {showMath && (
            <Animated.View entering={FadeIn.duration(motion.fast)}>
              <MathBreakdown verdict={verdict} />
            </Animated.View>
          )}

          {onAccept && verdict.recommended_target != null && (
            <Pressable
              onPress={onAccept}
              style={[styles.accept, { backgroundColor: style.color }]}
              accessibilityRole="button"
            >
              <Text style={styles.acceptText}>Accept new target</Text>
            </Pressable>
          )}
        </>
      )}

      {compact && (
        <Text style={styles.tapHint}>Tap for the full breakdown →</Text>
      )}
    </Card>
  );

  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} accessibilityRole="button">
      {body}
    </Pressable>
  );
}

function Signal({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'good' | 'bad' | 'neutral';
}) {
  const color =
    tone === 'good' ? palette.good : tone === 'bad' ? palette.bad : palette.text;
  return (
    <View style={styles.signal}>
      <Text style={styles.signalLabel}>{label}</Text>
      <Text style={[styles.signalValue, { color }]}>{value}</Text>
    </View>
  );
}

/**
 * The transparency panel. Renders whatever the server sent rather than a fixed
 * shape, so adding a term to the algorithm surfaces here automatically.
 */
function MathBreakdown({ verdict }: { verdict: Verdict }) {
  const m = verdict.math_breakdown ?? {};
  const expenditure = (m.expenditure ?? {}) as Record<string, unknown>;
  const strength = (m.strength ?? {}) as Record<string, unknown>;
  const perExercise =
    ((strength.strength_detail as Record<string, unknown>)?.per_exercise as
      | Array<Record<string, unknown>>
      | undefined) ?? [];

  return (
    <View style={styles.math}>
      {perExercise.length > 0 && (
        <>
          <Text style={styles.mathSection}>Strength index</Text>
          {perExercise.map((ex, i) => (
            <View key={i} style={styles.mathRow}>
              <Text style={styles.mathKey}>
                {String(ex.exercise)}{' '}
                <Text style={styles.mathWeight}>
                  ×{String(ex.weight)}
                </Text>
              </Text>
              <Text style={styles.mathValue}>
                {String(ex.e1rm_start)} → {String(ex.e1rm_now_smoothed)} kg (
                {Number(ex.pct_change) >= 0 ? '+' : ''}
                {String(ex.pct_change)}%)
              </Text>
            </View>
          ))}
        </>
      )}

      <Text style={styles.mathSection}>Expenditure</Text>
      <MathRow label="Starting estimate" value={expenditure.tdee_prior} unit=" kcal" />
      <MathRow label="What your data shows" value={expenditure.tdee_observed} unit=" kcal" />
      <MathRow label="Blended estimate" value={expenditure.tdee_blended} unit=" kcal" />
      <MathRow
        label="Confidence"
        value={
          expenditure.confidence != null
            ? `${Math.round(Number(expenditure.confidence) * 100)}%`
            : null
        }
      />
      <MathRow label="Days you logged food" value={expenditure.logged_days} />
      <MathRow label="Weigh-ins" value={expenditure.weigh_ins} />

      {verdict.guardrails_triggered?.length > 0 && (
        <>
          <Text style={styles.mathSection}>Caveats I applied</Text>
          {verdict.guardrails_triggered.map((g) => (
            <Text key={g} style={styles.guardrail}>
              • {humaniseGuardrail(g)}
            </Text>
          ))}
        </>
      )}
    </View>
  );
}

function MathRow({
  label,
  value,
  unit = '',
}: {
  label: string;
  value: unknown;
  unit?: string;
}) {
  if (value == null) return null;
  return (
    <View style={styles.mathRow}>
      <Text style={styles.mathKey}>{label}</Text>
      <Text style={styles.mathValue}>
        {typeof value === 'number' ? Math.round(value) : String(value)}
        {unit}
      </Text>
    </View>
  );
}

const GUARDRAIL_COPY: Record<string, string> = {
  novice_discount_applied:
    'You&apos;re new to lifting, so I discounted early strength gains — a lot of it is skill, not muscle.',
  program_changed:
    'Your routine changed mid-window, so lift-to-lift comparison isn&apos;t reliable.',
  low_food_logging__no_calorie_verdict:
    'Not enough food logging to make a calorie recommendation.',
  signals_within_noise_band: 'Both trends are still inside the noise band.',
  insufficient_data: 'Not enough sessions or weigh-ins yet.',
  no_strength_signal: 'No comparable lifts across two weeks yet.',
  observed_below_plausible_range__likely_underlogging:
    'Your numbers imply an implausibly low burn — you may be under-logging.',
  observed_above_plausible_range__check_weigh_in_consistency:
    'Your numbers imply an implausibly high burn — check your weigh-in consistency.',
  insufficient_logging: 'Too few logged days to adapt your target this week.',
};

function humaniseGuardrail(code: string): string {
  return GUARDRAIL_COPY[code] ?? code.replace(/_/g, ' ');
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  card: { gap: space.lg, borderWidth: 1 },

  headerRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  badge: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeIcon: { fontSize: 22, fontWeight: '700' },
  eyebrow: {
    ...type.micro,
    color: palette.textFaint,
    textTransform: 'uppercase',
  },
  headline: { ...type.heading, color: palette.text, marginTop: 2 },

  signals: {
    flexDirection: 'row',
    backgroundColor: palette.bg,
    borderRadius: radius.md,
    padding: space.md,
  },
  signal: { flex: 1, alignItems: 'center', gap: 2 },
  signalDivider: { width: 1, backgroundColor: palette.border },
  signalLabel: { ...type.micro, color: palette.textFaint },
  signalValue: { ...type.heading },

  explanation: { ...type.body, color: palette.textMuted, lineHeight: 22 },

  targetRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  targetLabel: { ...type.caption, color: palette.textMuted },
  targetValue: { ...type.title, color: palette.text },

  mathToggle: { ...type.caption, color: palette.primary, fontWeight: '600' },

  math: { gap: space.xs, marginTop: space.sm },
  mathSection: {
    ...type.micro,
    color: palette.textFaint,
    textTransform: 'uppercase',
    marginTop: space.md,
    marginBottom: space.xs,
  },
  mathRow: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  mathKey: { ...type.caption, color: palette.textMuted, flex: 1 },
  mathWeight: { color: palette.textFaint },
  mathValue: { ...type.caption, color: palette.text, fontWeight: '600' },
  guardrail: { ...type.caption, color: palette.textMuted, lineHeight: 20 },

  accept: {
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  acceptText: { ...type.bodyStrong, color: '#062B0A' },

  tapHint: { ...type.micro, color: palette.textFaint },
});
