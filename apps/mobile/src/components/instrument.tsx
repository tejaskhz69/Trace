/**
 * Instrument-panel primitives.
 *
 * These are the vocabulary of the redesign: Panel, Label, Readout, Gauge,
 * Sparkbar, Rule, StatCell. Screens compose these and add nothing bespoke —
 * that's what keeps twelve screens looking like one instrument.
 */

import React, { memo, useEffect } from 'react';
import {
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import Animated, {
  Easing,
  interpolate,
  useAnimatedProps,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, G, Line, Rect } from 'react-native-svg';
import * as Haptics from 'expo-haptics';

import {
  HAIRLINE,
  fontFamily,
  motion,
  palette,
  radius,
  space,
  type,
} from '../theme';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);
const AnimatedRect = Animated.createAnimatedComponent(Rect);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

// ---------------------------------------------------------------------------
// Rule — the primary structural element
// ---------------------------------------------------------------------------

export function Rule({
  vertical,
  bright,
  style,
}: {
  vertical?: boolean;
  bright?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View
      style={[
        {
          backgroundColor: bright ? palette.hairlineBright : palette.hairline,
          ...(vertical
            ? { width: HAIRLINE, alignSelf: 'stretch' }
            : { height: HAIRLINE, alignSelf: 'stretch' }),
        },
        style,
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Label — the uppercase tracked micro-label
// ---------------------------------------------------------------------------

export function Label({
  children,
  color = palette.textFaint,
  style,
}: {
  children: React.ReactNode;
  color?: string;
  style?: StyleProp<TextStyle>;
}) {
  return <Text style={[type.label, { color }, style]}>{children}</Text>;
}

// ---------------------------------------------------------------------------
// Panel — a bordered region, not a floating card
// ---------------------------------------------------------------------------

export function Panel({
  children,
  label,
  right,
  onPress,
  padded = true,
  style,
}: {
  children?: React.ReactNode;
  label?: string;
  right?: React.ReactNode;
  onPress?: () => void;
  padded?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const body = (
    <View style={[styles.panel, style]}>
      {(label || right) && (
        <>
          <View style={styles.panelHeader}>
            {label ? <Label>{label}</Label> : <View />}
            {right}
          </View>
          <Rule />
        </>
      )}
      <View style={padded ? styles.panelBody : undefined}>{children}</View>
    </View>
  );

  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} accessibilityRole="button">
      {body}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Readout — the one big number, animated on the UI thread
// ---------------------------------------------------------------------------

import { TextInput } from 'react-native';
const AnimatedTextInput = Animated.createAnimatedComponent(TextInput);

interface ReadoutProps {
  value: number;
  suffix?: string;
  prefix?: string;
  color?: string;
  size?: 'readout' | 'figure' | 'value';
  animate?: boolean;
}

/**
 * Counts up to its value on the UI thread via useAnimatedProps on a read-only
 * TextInput. React never re-renders during the count — the same technique as
 * the calorie ring, for the same reason.
 */
export const Readout = memo(function ReadoutBase({
  value,
  suffix,
  prefix,
  color = palette.text,
  size = 'readout',
  animate = true,
}: ReadoutProps) {
  const current = useSharedValue(animate ? 0 : value);

  useEffect(() => {
    current.value = withTiming(value, {
      duration: motion.slow,
      easing: Easing.out(Easing.cubic),
    });
  }, [value, current]);

  const text = useDerivedValue(() => {
    const n = Math.round(current.value);
    return `${prefix ?? ''}${n.toLocaleString('en-US')}${suffix ?? ''}`;
  });

  const animatedProps = useAnimatedProps(() => ({
    text: text.value,
    defaultValue: text.value,
  })) as never;

  return (
    <AnimatedTextInput
      editable={false}
      underlineColorAndroid="transparent"
      accessibilityRole="text"
      accessibilityLabel={`${prefix ?? ''}${value}${suffix ?? ''}`}
      style={[type[size], { color, padding: 0 }]}
      animatedProps={animatedProps}
    />
  );
});

// ---------------------------------------------------------------------------
// Gauge — a linear bar, the instrument alternative to a ring
// ---------------------------------------------------------------------------

interface GaugeProps {
  fraction: number;       // 0..1+, may exceed 1
  color?: string;
  overColor?: string;
  height?: number;
  /** Draw tick marks at these fractions, e.g. [0.25, 0.5, 0.75]. */
  ticks?: number[];
}

export const Gauge = memo(function GaugeBase({
  fraction,
  color = palette.signal,
  overColor = palette.warn,
  height = 8,
  ticks = [0.25, 0.5, 0.75],
}: GaugeProps) {
  const progress = useSharedValue(0);
  const clamped = Math.max(0, Math.min(fraction, 1));
  const over = Math.max(0, Math.min(fraction - 1, 0.5));

  useEffect(() => {
    progress.value = withTiming(clamped, {
      duration: motion.slow,
      easing: Easing.out(Easing.cubic),
    });
  }, [clamped, progress]);

  const fillStyle = useAnimatedStyle(() => ({
    width: `${progress.value * 100}%`,
  }));

  return (
    <View style={[styles.gaugeTrack, { height, borderRadius: height / 2 }]}>
      <Animated.View
        style={[
          styles.gaugeFill,
          { backgroundColor: color, borderRadius: height / 2 },
          fillStyle,
        ]}
      />
      {over > 0 && (
        <View
          style={[
            styles.gaugeOver,
            {
              backgroundColor: overColor,
              width: `${over * 100}%`,
              borderRadius: height / 2,
            },
          ]}
        />
      )}
      {/* Tick marks — the detail that reads as "instrument" rather than "bar". */}
      {ticks.map((t) => (
        <View
          key={t}
          pointerEvents="none"
          style={[styles.gaugeTick, { left: `${t * 100}%` }]}
        />
      ))}
    </View>
  );
});

// ---------------------------------------------------------------------------
// Sparkbar — a compact multi-day bar chart, e.g. 7 days of steps
// ---------------------------------------------------------------------------

export const Sparkbar = memo(function SparkbarBase({
  values,
  color = palette.signal,
  dimColor = palette.hairlineBright,
  height = 34,
  highlightLast = true,
}: {
  values: number[];
  color?: string;
  dimColor?: string;
  height?: number;
  highlightLast?: boolean;
}) {
  const max = Math.max(...values, 1);
  return (
    <View style={[styles.sparkbar, { height }]}>
      {values.map((v, i) => {
        const isLast = i === values.length - 1;
        const h = Math.max(2, (v / max) * height);
        return (
          <View
            key={i}
            style={{
              flex: 1,
              height: h,
              marginHorizontal: 1,
              borderRadius: 1,
              backgroundColor: highlightLast && isLast ? color : dimColor,
            }}
          />
        );
      })}
    </View>
  );
});

// ---------------------------------------------------------------------------
// StatCell — a label/value pair in a gridded row
// ---------------------------------------------------------------------------

export function StatCell({
  label,
  value,
  unit,
  color = palette.text,
  delta,
  align = 'left',
}: {
  label: string;
  value: string | number;
  unit?: string;
  color?: string;
  delta?: { value: string; positive: boolean } | null;
  align?: 'left' | 'center' | 'right';
}) {
  return (
    <View style={{ flex: 1, alignItems: align === 'left' ? 'flex-start' : align === 'right' ? 'flex-end' : 'center', gap: space.xs }}>
      <Label>{label}</Label>
      <View style={styles.statValueRow}>
        <Text style={[type.value, { color }]}>{value}</Text>
        {unit ? <Text style={styles.statUnit}>{unit}</Text> : null}
      </View>
      {delta ? (
        <Text
          style={[
            type.labelSm,
            { color: delta.positive ? palette.signal : palette.danger },
          ]}
        >
          {delta.value}
        </Text>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading,
  disabled,
  compact,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'outline' | 'ghost';
  loading?: boolean;
  disabled?: boolean;
  compact?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const pressed = useSharedValue(0);
  const isDisabled = disabled || loading;

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: interpolate(pressed.value, [0, 1], [1, motion.pressScale]) },
    ],
    opacity: interpolate(pressed.value, [0, 1], [1, 0.88]),
  }));

  const variantStyle =
    variant === 'primary'
      ? { backgroundColor: palette.signal, borderColor: palette.signal }
      : variant === 'outline'
        ? { backgroundColor: 'transparent', borderColor: palette.hairlineBright }
        : { backgroundColor: 'transparent', borderColor: 'transparent' };

  const labelColor =
    variant === 'primary' ? palette.void : variant === 'outline' ? palette.text : palette.textDim;

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      disabled={isDisabled}
      onPressIn={() => {
        pressed.value = withTiming(1, { duration: motion.press });
      }}
      onPressOut={() => {
        pressed.value = withTiming(0, { duration: motion.press });
      }}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={[
        styles.button,
        compact && styles.buttonCompact,
        variantStyle,
        isDisabled && { opacity: 0.4 },
        animatedStyle,
        style,
      ]}
    >
      <Text style={[type.label, { color: labelColor, letterSpacing: 1.6 }]}>
        {loading ? '···' : label}
      </Text>
    </AnimatedPressable>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

export function Skeleton({
  height,
  width = '100%',
  style,
}: {
  height: number;
  width?: number | `${number}%`;
  style?: StyleProp<ViewStyle>;
}) {
  const shimmer = useSharedValue(0.25);

  useEffect(() => {
    shimmer.value = withTiming(0.6, {
      duration: 800,
      easing: Easing.inOut(Easing.quad),
    });
    const id = setInterval(() => {
      shimmer.value = withTiming(shimmer.value > 0.4 ? 0.25 : 0.6, {
        duration: 800,
        easing: Easing.inOut(Easing.quad),
      });
    }, 800);
    return () => clearInterval(id);
  }, [shimmer]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: shimmer.value }));

  return (
    <Animated.View
      style={[
        { height, width, backgroundColor: palette.raised, borderRadius: radius.xs },
        animatedStyle,
        style,
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Ring — the calorie donut, segmented by macro
// ---------------------------------------------------------------------------

const RING_R = 52;
const RING_C = 2 * Math.PI * RING_R;

export interface RingSegment {
  /** Absolute value in the same unit as `total`, e.g. kcal from protein. */
  value: number;
  color: string;
}

/**
 * One arc. Its own component so each gets its own shared value and animates
 * on the UI thread without React re-rendering the ring.
 */
const Arc = memo(function ArcBase({
  fraction,
  offset,
  color,
  stroke,
}: {
  fraction: number;
  offset: number;
  color: string;
  stroke: number;
}) {
  const grow = useSharedValue(0);

  useEffect(() => {
    grow.value = withTiming(1, {
      duration: motion.slow,
      easing: Easing.out(Easing.cubic),
    });
  }, [fraction, offset, grow]);

  const animatedProps = useAnimatedProps(() => {
    const len = RING_C * fraction * grow.value;
    return {
      strokeDasharray: `${len} ${RING_C}`,
      strokeDashoffset: -RING_C * offset,
    };
  });

  return (
    <AnimatedCircle
      cx={0}
      cy={0}
      r={RING_R}
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="butt"
      animatedProps={animatedProps as never}
    />
  );
});

/**
 * A full circle whose arcs are each macro's share of the day's target, so the
 * segments sum to the target and the unfilled gap IS what's left. That makes
 * the ring honest: it can't show "on track" while the numbers disagree.
 *
 * The arcs are not self-labelling at this size -- pair it with a row of
 * `Cell`s keyed to the same colours, or the ring is decoration.
 */
export const Ring = memo(function RingBase({
  segments,
  total,
  size = 168,
  stroke = 17,
  children,
}: {
  segments: RingSegment[];
  /** The denominator. Arcs are drawn as value/total. */
  total: number;
  size?: number;
  stroke?: number;
  /** Centre content — normally a `Readout` and a `Label`. */
  children?: React.ReactNode;
}) {
  const safeTotal = total > 0 ? total : 1;

  // Cumulative offsets, computed once per render rather than inside each arc.
  let running = 0;
  const arcs = segments.map((s) => {
    const fraction = Math.max(0, Math.min(s.value / safeTotal, 1));
    const arc = { fraction, offset: running, color: s.color };
    running += fraction;
    return arc;
  });

  return (
    <View style={{ width: size, height: size, alignSelf: 'center' }}>
      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* -90deg so the first segment starts at twelve o'clock. */}
        <G transform={`translate(${size / 2}, ${size / 2}) rotate(-90)`}>
          <Circle
            cx={0}
            cy={0}
            r={RING_R}
            fill="none"
            stroke={palette.raised}
            strokeWidth={stroke}
          />
          {arcs.map((a, i) => (
            <Arc key={i} {...a} stroke={stroke} />
          ))}
        </G>
      </Svg>
      <View style={styles.ringCentre} pointerEvents="none">
        {children}
      </View>
    </View>
  );
});

// ---------------------------------------------------------------------------
// Plain — the plain-English sentence under a chart
// ---------------------------------------------------------------------------

export type PlainTone = 'signal' | 'warn' | 'danger';

const PLAIN_TONE: Record<PlainTone, { rule: string; tint: string; text: string }> = {
  signal: { rule: palette.signal, tint: palette.signalGlow, text: '#D6E2DC' },
  warn: { rule: palette.warn, tint: 'rgba(194,135,31,0.09)', text: '#E5D6BC' },
  danger: { rule: palette.danger, tint: 'rgba(217,83,79,0.09)', text: '#EBD2D1' },
};

/**
 * A chart states a fact; this says what to do about it. It is the single
 * biggest difference between the instrument redesign and the picture-led one,
 * and the reason the app reads as explaining rather than reporting.
 *
 * Keep it to one or two sentences. If it needs three, the chart above it is
 * doing too much.
 */
export function Plain({
  children,
  tone = 'signal',
  style,
}: {
  children: React.ReactNode;
  tone?: PlainTone;
  style?: StyleProp<ViewStyle>;
}) {
  const t = PLAIN_TONE[tone];
  return (
    <View style={[styles.plain, { backgroundColor: t.tint }, style]}>
      <View style={[styles.plainRule, { backgroundColor: t.rule }]} />
      <Text style={[styles.plainText, { color: t.text }]}>{children}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Cell — a rounded stat tile
// ---------------------------------------------------------------------------

/**
 * Replaces StatCell + vertical Rule. Cells sit on `raised` with a gap between
 * them rather than being divided by hairlines -- that is the whole visual
 * difference between the two design directions, expressed in one component.
 *
 * `keyColor` draws a top rule, which is what turns a row of cells into a
 * legend for the `Ring` above it.
 */
export function Cell({
  label,
  value,
  unit,
  sub,
  keyColor,
  subTone,
  style,
}: {
  label: string;
  value: string | number;
  unit?: string;
  sub?: string;
  keyColor?: string;
  subTone?: 'up' | 'down' | 'flat' | 'danger';
  style?: StyleProp<ViewStyle>;
}) {
  const subColor =
    subTone === 'up'
      ? palette.up
      : subTone === 'down'
        ? palette.down
        : subTone === 'danger'
          ? palette.danger
          : palette.textDim;

  return (
    <View
      style={[
        styles.cell,
        keyColor
          ? {
              borderTopWidth: 2,
              borderTopColor: keyColor,
              borderTopLeftRadius: radius.xs,
              borderTopRightRadius: radius.xs,
            }
          : null,
        style,
      ]}
    >
      <Label>{label}</Label>
      <View style={styles.cellValueRow}>
        <Text style={[type.value, { color: palette.text }]}>{value}</Text>
        {unit ? <Text style={styles.cellUnit}>{unit}</Text> : null}
      </View>
      {sub ? (
        <Text style={[styles.cellSub, { color: subColor }]}>{sub}</Text>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Series — the chart family
// ---------------------------------------------------------------------------

/**
 * A proportional two-part bar with its labels inside. Used for the
 * muscle-vs-fat split, which is the product's headline claim, so it gets to
 * be a component rather than an ad-hoc View.
 */
export const SplitBar = memo(function SplitBarBase({
  left,
  right,
  leftColor = palette.seriesStrength,
  rightColor = palette.seriesEnergy,
  leftLabel,
  rightLabel,
  height = 30,
}: {
  left: number;
  right: number;
  leftColor?: string;
  rightColor?: string;
  leftLabel: string;
  rightLabel: string;
  height?: number;
}) {
  const total = left + right;
  const leftPct = total > 0 ? (left / total) * 100 : 0;
  const grow = useSharedValue(0);

  useEffect(() => {
    grow.value = withTiming(1, {
      duration: motion.slow,
      easing: Easing.out(Easing.cubic),
    });
  }, [leftPct, grow]);

  const leftStyle = useAnimatedStyle(() => ({
    width: `${leftPct * grow.value}%`,
  }));

  return (
    <View style={[styles.splitTrack, { height, borderRadius: radius.sm }]}>
      <View style={[styles.splitFill, { backgroundColor: rightColor }]} />
      <Animated.View
        style={[styles.splitFill, { backgroundColor: leftColor }, leftStyle]}
      />
      <View style={styles.splitLabels} pointerEvents="none">
        <Text style={[styles.splitLabel, { color: palette.void }]} numberOfLines={1}>
          {leftLabel}
        </Text>
        <Text style={[styles.splitLabel, { color: palette.void }]} numberOfLines={1}>
          {rightLabel}
        </Text>
      </View>
    </View>
  );
});

/**
 * Day-by-day bars with a target line and one day called out. The callout is a
 * colour AND a value label, never colour alone.
 */
export const DayBars = memo(function DayBarsBase({
  values,
  labels,
  color = palette.seriesSleep,
  flagIndex,
  flagColor = palette.danger,
  flagNote,
  target,
  targetLabel,
  height = 96,
}: {
  values: number[];
  labels: string[];
  color?: string;
  /** Index to draw in `flagColor` — e.g. the night that fell short. */
  flagIndex?: number;
  flagColor?: string;
  flagNote?: string;
  /** Draws a dashed threshold line at this value. */
  target?: number;
  targetLabel?: string;
  height?: number;
}) {
  const max = Math.max(...values, target ?? 0, 1);
  const barArea = height - 18;

  return (
    <View style={{ gap: space.xs }}>
      <View style={[styles.dayBarsRow, { height }]}>
        {target != null && (
          <View
            pointerEvents="none"
            style={[
              styles.targetLine,
              { bottom: 18 + (target / max) * barArea, borderColor: color },
            ]}
          >
            {targetLabel ? (
              <Text style={[styles.targetLabel, { color }]}>{targetLabel}</Text>
            ) : null}
          </View>
        )}
        {values.map((v, i) => {
          const flagged = i === flagIndex;
          return (
            <View key={i} style={styles.dayBarCol}>
              <View
                style={{
                  height: Math.max(2, (v / max) * barArea),
                  alignSelf: 'stretch',
                  borderRadius: radius.xs,
                  backgroundColor: flagged ? flagColor : color,
                  opacity: flagged ? 1 : 0.85,
                }}
              />
              <Text
                style={[
                  styles.dayBarLabel,
                  flagged && { color: flagColor, fontFamily: fontFamily.bold },
                ]}
              >
                {labels[i]}
              </Text>
            </View>
          );
        })}
      </View>
      {flagNote ? (
        <Text style={[styles.dayBarNote, { color: flagColor }]}>{flagNote}</Text>
      ) : null}
    </View>
  );
});

/** One labelled row of a stacked breakdown, e.g. where your burn comes from. */
export function BreakdownRow({
  label,
  value,
  color,
  unit,
}: {
  label: string;
  value: number;
  color: string;
  unit?: string;
}) {
  return (
    <View style={styles.breakdownRow}>
      <View style={styles.breakdownLeft}>
        <View style={[styles.breakdownDot, { backgroundColor: color }]} />
        <Text style={styles.breakdownLabel}>{label}</Text>
      </View>
      <View style={styles.cellValueRow}>
        <Text style={[type.valueSm, { color: palette.text }]}>
          {value.toLocaleString('en-US')}
        </Text>
        {unit ? <Text style={styles.cellUnit}>{unit}</Text> : null}
      </View>
    </View>
  );
}

/**
 * A stacked proportional bar. Pair with `BreakdownRow`s beneath it -- the bar
 * shows relative size, the rows carry the identity, so meaning never depends
 * on colour alone.
 */
export const StackBar = memo(function StackBarBase({
  parts,
  height = 26,
}: {
  parts: { value: number; color: string }[];
  height?: number;
}) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <View style={[styles.stackBar, { height, borderRadius: radius.sm }]}>
      {parts.map((p, i) => (
        <View
          key={i}
          style={{
            flex: p.value / total,
            backgroundColor: p.color,
            marginRight: i < parts.length - 1 ? 2 : 0,
            borderRadius: radius.xs,
          }}
        />
      ))}
    </View>
  );
});

const styles = StyleSheet.create({
  panel: {
    backgroundColor: palette.surface,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  panelHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  panelBody: { padding: space.lg },

  gaugeTrack: {
    backgroundColor: palette.raised,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  gaugeFill: { position: 'absolute', left: 0, top: 0, bottom: 0 },
  gaugeOver: { position: 'absolute', left: 0, top: 0, bottom: 0, opacity: 0.9 },
  gaugeTick: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: HAIRLINE,
    backgroundColor: palette.void,
    opacity: 0.6,
  },

  sparkbar: { flexDirection: 'row', alignItems: 'flex-end' },

  statValueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
  statUnit: { ...type.labelSm, color: palette.textFaint },

  button: {
    height: 50,
    borderRadius: radius.sm,
    borderWidth: HAIRLINE,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  buttonCompact: { height: 38, paddingHorizontal: space.lg },

  // --- Ring --------------------------------------------------------------
  ringCentre: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // --- Plain -------------------------------------------------------------
  plain: {
    flexDirection: 'row',
    gap: space.md,
    padding: space.md,
    borderTopRightRadius: radius.sm,
    borderBottomRightRadius: radius.sm,
  },
  plainRule: { width: 3, borderRadius: 2, alignSelf: 'stretch' },
  plainText: { ...type.body, flex: 1, lineHeight: 21 },

  // --- Cell --------------------------------------------------------------
  cell: {
    flex: 1,
    backgroundColor: palette.raised,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.xs,
  },
  cellValueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
  cellUnit: { ...type.labelSm, color: palette.textFaint },
  cellSub: { ...type.caption, fontSize: 11 },

  // --- SplitBar ----------------------------------------------------------
  splitTrack: { overflow: 'hidden', backgroundColor: palette.raised },
  splitFill: { position: 'absolute', left: 0, top: 0, bottom: 0, right: 0 },
  splitLabels: {
    ...StyleSheet.absoluteFillObject,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.md,
  },
  splitLabel: { ...type.labelSm, letterSpacing: 0.6 },

  // --- DayBars -----------------------------------------------------------
  dayBarsRow: { flexDirection: 'row', alignItems: 'flex-end', gap: space.sm },
  dayBarCol: { flex: 1, alignItems: 'center', gap: space.xs },
  dayBarLabel: { ...type.labelSm, color: palette.textFaint },
  dayBarNote: { ...type.labelSm, textAlign: 'center' },
  targetLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    borderTopWidth: HAIRLINE,
    borderStyle: 'dashed',
    opacity: 0.7,
  },
  targetLabel: {
    ...type.labelSm,
    position: 'absolute',
    right: 0,
    top: -12,
  },

  // --- Breakdown ---------------------------------------------------------
  breakdownRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
  },
  breakdownLeft: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  breakdownDot: { width: 8, height: 8, borderRadius: 4 },
  breakdownLabel: { ...type.body, color: palette.textDim },
  stackBar: { flexDirection: 'row', overflow: 'hidden' },
});
