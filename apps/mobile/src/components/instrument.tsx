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
// TextInput is imported separately further down, next to the Readout that
// animates it. Left there so that pairing stays obvious.
import Animated, {
  Easing,
  interpolate,
  useAnimatedProps,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, G, Line, Path, Rect, Text as SvgText } from 'react-native-svg';
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
// Primitives read the accent themselves rather than taking it as a prop, so a
// screen can never hardcode green while the user has chosen white.
import { useAccent } from '../state/useTheme';

/** Digits that don't jitter as they change. See design rule #2. */
const tabularNums = { fontVariant: ['tabular-nums' as const] };

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
  color,
  overColor = palette.warn,
  height = 8,
  ticks = [0.25, 0.5, 0.75],
}: GaugeProps) {
  // Undefined `color` means "use the accent". An explicit colour always wins,
  // which is how a macro gauge keeps its fixed channel colour.
  const accent = useAccent();
  const fill = color ?? accent.brand;
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
          { backgroundColor: fill, borderRadius: height / 2 },
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
  color,
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
  const accent = useAccent();
  const hi = color ?? accent.brand;
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
              backgroundColor: highlightLast && isLast ? hi : dimColor,
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
  const accent = useAccent();
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
      ? { backgroundColor: accent.brand, borderColor: accent.brand }
      : variant === 'outline'
        ? { backgroundColor: 'transparent', borderColor: palette.hairlineBright }
        : { backgroundColor: 'transparent', borderColor: 'transparent' };

  // brandInk, not palette.void: on the white accent, near-black-on-white is
  // the only legible pairing, and void happens to work only for green.
  const labelColor =
    variant === 'primary'
      ? accent.brandInk
      : variant === 'outline'
        ? palette.text
        : palette.textDim;

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

// `signal` is intentionally absent: it follows the user's accent and is built
// at render time from useAccent(). warn and danger are STATES, not preferences
// — an over-limit sodium bar must look the same in both accents.
const PLAIN_TONE: Record<
  Exclude<PlainTone, 'signal'>,
  { rule: string; tint: string; text: string }
> = {
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
  const accent = useAccent();
  const t =
    tone === 'signal'
      ? { rule: accent.brand, tint: accent.brandSoft, text: accent.plainText }
      : PLAIN_TONE[tone];
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

// ---------------------------------------------------------------------------
// Choice — a selectable option, for questionnaires
// ---------------------------------------------------------------------------

export interface ChoiceOption<T extends string | number> {
  value: T;
  label: string;
  /** Optional second line. Use it to say what the option MEANS, not to sell it. */
  detail?: string;
}

/**
 * A vertical list of mutually exclusive options.
 *
 * Selection is shown by a signal-coloured left rule plus a brighter border,
 * never by a filled background — a filled row at this size reads as a button
 * that has already been pressed, and users stop scanning the rest of the list.
 */
export const Choice = memo(function ChoiceBase<T extends string | number>({
  options,
  value,
  onChange,
  columns = 1,
}: {
  options: readonly ChoiceOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  columns?: 1 | 2 | 3;
}) {
  const accent = useAccent();
  return (
    <View style={[styles.choiceWrap, columns > 1 && styles.choiceGrid]}>
      {options.map((opt) => {
        const selected = opt.value === value;
        return (
          <Pressable
            key={String(opt.value)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={opt.label}
            onPress={() => {
              Haptics.selectionAsync();
              onChange(opt.value);
            }}
            style={[
              styles.choice,
              columns > 1 && { flexBasis: `${100 / columns}%`, flexGrow: 1 },
              selected && { borderColor: accent.brand },
            ]}
          >
            {selected ? (
              <View style={[styles.choiceKey, { backgroundColor: accent.brand }]} />
            ) : null}
            <Text
              style={[
                type.heading,
                { color: selected ? palette.text : palette.textDim },
              ]}
            >
              {opt.label}
            </Text>
            {opt.detail ? (
              <Text style={[type.caption, styles.choiceDetail]}>{opt.detail}</Text>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}) as <T extends string | number>(props: {
  options: readonly ChoiceOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  columns?: 1 | 2 | 3;
}) => React.ReactElement;

// ---------------------------------------------------------------------------
// Stepper — a bounded numeric input
// ---------------------------------------------------------------------------

/**
 * Minus / big number / plus.
 *
 * A free TextInput is the wrong control for "how many cardio sessions a week"
 * — it opens a keyboard, permits 900, and demands a dismiss gesture. Bounds
 * are enforced here so a screen can never submit an out-of-range answer that
 * the server would only reject after a round trip.
 */
export const Stepper = memo(function StepperBase({
  value,
  onChange,
  min = 0,
  max = 99,
  step = 1,
  unit,
  format,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  format?: (value: number) => string;
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, v));

  const nudge = (delta: number) => {
    const next = clamp(value + delta);
    if (next === value) return; // at a bound: no haptic, no re-render
    Haptics.selectionAsync();
    onChange(next);
  };

  return (
    <View style={styles.stepper}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Decrease"
        onPress={() => nudge(-step)}
        style={[styles.stepperBtn, value <= min && styles.stepperBtnOff]}
      >
        <Text style={styles.stepperSign}>–</Text>
      </Pressable>

      <View style={styles.stepperValue}>
        <Text style={[type.figure, { color: palette.text }]}>
          {format ? format(value) : value}
        </Text>
        {unit ? (
          <Text style={[type.label, { color: palette.textFaint }]}>{unit}</Text>
        ) : null}
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Increase"
        onPress={() => nudge(step)}
        style={[styles.stepperBtn, value >= max && styles.stepperBtnOff]}
      >
        <Text style={styles.stepperSign}>+</Text>
      </Pressable>
    </View>
  );
});

// ---------------------------------------------------------------------------
// LineChart — multi-series trend, with an optional target band
// ---------------------------------------------------------------------------

export interface LineSeries {
  label: string;
  color: string;
  values: (number | null)[];
  /** Draw the raw points as dots as well as the line (daily weigh-ins). */
  dots?: boolean;
  /** Dashed rather than solid — used for the raw series under a trend. */
  dashed?: boolean;
}

/**
 * A small multi-series line chart.
 *
 * DIRECT LABELS, NOT A COLOUR KEY. Each series is labelled at its own end
 * point, so identity never depends on colour alone — the rule that lets this
 * many hues coexist (design system #4) and the reason it still reads for the
 * ~8% of men with red-green colour blindness.
 *
 * `band` draws a target range behind everything. It is deliberately a flat
 * translucent fill rather than hatching: hatching at this size turns into
 * moiré on a phone screen.
 *
 * `null` in a series is a genuine gap — a week with no weigh-in — and the line
 * breaks rather than interpolating across it. Drawing a straight line through
 * missing data invents measurements the user never took.
 */
export const LineChart = memo(function LineChartBase({
  series,
  height = 150,
  band,
  xLabels,
  yTicks = 3,
  unit = '',
}: {
  series: LineSeries[];
  height?: number;
  /** Target corridor, as [low[], high[]] in the same units. */
  band?: { low: number[]; high: number[]; color?: string };
  xLabels?: [string, string];
  yTicks?: number;
  unit?: string;
}) {
  const [w, setW] = React.useState(0);

  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  if (band) all.push(...band.low, ...band.high);
  const lo = all.length ? Math.min(...all) : 0;
  const hi = all.length ? Math.max(...all) : 1;
  const pad = (hi - lo) * 0.12 || 1;
  const min = lo - pad;
  const max = hi + pad;

  const n = Math.max(...series.map((s) => s.values.length), band?.low.length ?? 0, 2);
  const LEFT = 30;
  const RIGHT = 46; // room for the end-point label
  const plotW = Math.max(0, w - LEFT - RIGHT);

  const x = (i: number) => LEFT + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
  const y = (v: number) => height - ((v - min) / (max - min)) * height;

  /** Break the path at nulls so a gap reads as a gap. */
  const path = (vals: (number | null)[]) => {
    let d = '';
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };

  const ticks = Array.from({ length: yTicks }, (_, i) => min + ((max - min) * (i + 0.5)) / yTicks);

  return (
    <View onLayout={(e) => setW(e.nativeEvent.layout.width)}>
      {w > 0 ? (
        <Svg width={w} height={height + 18}>
          {ticks.map((t, i) => (
            <React.Fragment key={i}>
              <Line
                x1={LEFT}
                y1={y(t)}
                x2={LEFT + plotW}
                y2={y(t)}
                stroke={palette.hairline}
                strokeWidth={HAIRLINE}
              />
              <SvgText
                x={LEFT - 6}
                y={y(t) + 3}
                fill={palette.textGhost}
                fontSize={9}
                textAnchor="end"
              >
                {Math.round(t)}
              </SvgText>
            </React.Fragment>
          ))}

          {band ? (
            <Path
              d={
                band.high.map((v, i) => `${i ? 'L' : 'M'}${x(i)} ${y(v)}`).join(' ') +
                ' ' +
                band.low
                  .map((v, i, a) => `L${x(a.length - 1 - i)} ${y(a[a.length - 1 - i])}`)
                  .join(' ') +
                ' Z'
              }
              fill={band.color ?? palette.hairlineBright}
              opacity={0.35}
            />
          ) : null}

          {series.map((s) => {
            // Explicit loop rather than reduce: reduce infers its accumulator
            // from the element type here, which is `number | null`, and the
            // index is never null.
            let lastIdx = -1;
            for (let i = 0; i < s.values.length; i++) {
              if (s.values[i] != null) lastIdx = i;
            }
            const lastVal = lastIdx >= 0 ? (s.values[lastIdx] as number) : null;
            return (
              <React.Fragment key={s.label}>
                <Path
                  d={path(s.values)}
                  stroke={s.color}
                  strokeWidth={2}
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeDasharray={s.dashed ? '3 3' : undefined}
                  opacity={s.dashed ? 0.7 : 1}
                />
                {s.dots
                  ? s.values.map((v, i) =>
                      v == null ? null : (
                        <Circle key={i} cx={x(i)} cy={y(v)} r={2} fill={s.color} opacity={0.55} />
                      ),
                    )
                  : null}
                {lastVal != null ? (
                  <>
                    <Circle cx={x(lastIdx)} cy={y(lastVal)} r={3.5} fill={s.color} />
                    {/* Directly labelled, so identity never needs the colour. */}
                    <SvgText
                      x={Math.min(x(lastIdx) + 7, w - 2)}
                      y={y(lastVal) + 3}
                      fill={s.color}
                      fontSize={9}
                      fontWeight="700"
                    >
                      {s.label}
                    </SvgText>
                  </>
                ) : null}
              </React.Fragment>
            );
          })}

          {xLabels ? (
            <>
              <SvgText x={LEFT} y={height + 14} fill={palette.textGhost} fontSize={9}>
                {xLabels[0]}
              </SvgText>
              <SvgText
                x={LEFT + plotW}
                y={height + 14}
                fill={palette.textGhost}
                fontSize={9}
                textAnchor="end"
              >
                {xLabels[1]}
              </SvgText>
            </>
          ) : null}
        </Svg>
      ) : (
        <View style={{ height: height + 18 }} />
      )}
      {unit ? <Text style={styles.chartUnit}>{unit}</Text> : null}
    </View>
  );
});

// ---------------------------------------------------------------------------
// Tile — a large tappable entry point
// ---------------------------------------------------------------------------

/**
 * Icon, name, and one line saying what it's for.
 *
 * The subtitle is not decoration. "AI scan" alone doesn't tell a new user that
 * it returns a range rather than one confident number, and that promise is the
 * product. Four tiles is the ceiling — a fifth stops the fastest path to
 * logging a meal from being obvious, which is the only job this grid has.
 */
export function Tile({
  icon,
  name,
  detail,
  onPress,
  disabled,
}: {
  icon: React.ReactNode;
  name: string;
  detail: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${name}. ${detail}`}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={[styles.tile, disabled && { opacity: 0.45 }]}
    >
      {icon}
      <Text style={styles.tileName}>{name}</Text>
      <Text style={styles.tileDetail}>{detail}</Text>
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// ItemRow — a logged meal or a recent food
// ---------------------------------------------------------------------------

/**
 * Title + subtitle on the left, a number and its uncertainty on the right.
 *
 * `plusMinus` renders as "±63" and exists because non-negotiable #2 applies
 * everywhere an estimate is shown, not only on the scan screen. A logged
 * photo estimate and a scanned barcode must not look equally certain — the
 * barcode says "verified", the estimate carries its band.
 */
export function ItemRow({
  title,
  subtitle,
  value,
  plusMinus,
  note,
  onPress,
  last,
}: {
  title: string;
  subtitle?: string;
  value: string | number;
  /** Half-width of the uncertainty interval, in the same unit as `value`. */
  plusMinus?: number | null;
  /** Shown instead of a band, e.g. "verified". */
  note?: string;
  onPress?: () => void;
  last?: boolean;
}) {
  const body = (
    <View style={[styles.itemRow, last && { borderBottomWidth: 0 }]}>
      <View style={styles.itemLeft}>
        <Text style={styles.itemTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.itemSub} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      <View style={styles.itemRight}>
        <Text style={styles.itemValue}>{value}</Text>
        {plusMinus != null ? (
          <Text style={styles.itemSub}>±{Math.round(plusMinus)}</Text>
        ) : note ? (
          <Text style={styles.itemSub}>{note}</Text>
        ) : null}
      </View>
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={title} onPress={onPress}>
      {body}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// SearchField — the magnifier input
// ---------------------------------------------------------------------------

/**
 * A search box. Distinct from `Field` because it has no label, carries a
 * leading glyph, and is the primary control on the screen rather than one row
 * of a form.
 *
 * `leading` is injected rather than imported so this file stays free of a
 * dependency on the icon set — instrument.tsx is the vocabulary, and it must
 * not need to know what a magnifier looks like.
 */
export function SearchField({
  value,
  onChangeText,
  placeholder = 'Search',
  leading,
  autoFocus,
}: {
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  leading?: React.ReactNode;
  autoFocus?: boolean;
}) {
  const accent = useAccent();
  const [focused, setFocused] = React.useState(false);
  return (
    <View style={[styles.searchBox, focused && { borderColor: accent.brandDim }]}>
      {leading}
      <TextInput
        value={value}
        onChangeText={onChangeText}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={placeholder}
        placeholderTextColor={palette.textGhost}
        selectionColor={accent.brand}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
        autoFocus={autoFocus}
        accessibilityLabel={placeholder}
        style={styles.searchInput}
      />
      {value.length > 0 ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Clear search"
          onPress={() => onChangeText('')}
          hitSlop={10}
        >
          <Text style={styles.searchClear}>×</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// GroupHeader — "CHEST · 26 EXERCISES"
// ---------------------------------------------------------------------------

export function GroupHeader({ label, count, unit = 'exercises' }: {
  label: string;
  count: number;
  unit?: string;
}) {
  return (
    <View style={styles.groupHeader}>
      <Label color={palette.textDim}>
        {label} · {count} {unit}
      </Label>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Delta — the ▲ 4.2% / ▼ 2.1% / — 0.0% trend chip
// ---------------------------------------------------------------------------

/**
 * A signed percentage with a direction glyph.
 *
 * The glyph is not decoration: red/green as a sole channel fails for roughly
 * 8% of men, and this is the single most colour-coded element in the app. The
 * arrow carries the meaning; the colour reinforces it.
 *
 * `null` renders as a dash, NOT as 0.0%. A week with no comparison data is
 * not a week of no progress, and showing "0.0%" invents a measurement.
 */
export const Delta = memo(function DeltaBase({
  pct,
  size = 11,
}: {
  pct: number | null | undefined;
  size?: number;
}) {
  if (pct === null || pct === undefined) {
    return <Text style={[styles.delta, { fontSize: size, color: palette.textGhost }]}>—</Text>;
  }
  const up = pct > 0.05;
  const down = pct < -0.05;
  const color = up ? palette.up : down ? palette.down : palette.flat;
  const glyph = up ? '▲' : down ? '▼' : '—';
  return (
    <Text style={[styles.delta, { fontSize: size, color }]}>
      {glyph} {Math.abs(pct).toFixed(1)}%
    </Text>
  );
});

// ---------------------------------------------------------------------------
// LedgerBar — a micronutrient row with a real over-limit state
// ---------------------------------------------------------------------------

/**
 * "SODIUM · 2,610 / 2,300 mg" with a bar underneath.
 *
 * The over state is the point of this component. When `value` exceeds
 * `target` the bar fills completely and everything — label, numbers, fill —
 * turns danger red. That is the MyFitnessPal behaviour the product brief
 * asked for, and it has to be unmissable: a bar that quietly sits at 100% is
 * indistinguishable from one that is exactly on target.
 *
 * Colour is never the only channel: the numbers are always shown, so "2,610 /
 * 2,300" reads as over even to someone who cannot see the red.
 */
export const LedgerBar = memo(function LedgerBarBase({
  label,
  value,
  target,
  unit,
  color = palette.seriesWeight,
  height = 7,
}: {
  label: string;
  value: number;
  target: number;
  unit: string;
  color?: string;
  height?: number;
}) {
  const over = value > target;
  const fraction = target > 0 ? Math.min(value / target, 1) : 0;
  const tone = over ? palette.danger : palette.textDim;

  return (
    <View style={styles.ledgerRow}>
      <View style={styles.ledgerHead}>
        <Text style={[type.labelSm, { color: tone }]}>{label}</Text>
        <Text
          style={[
            type.labelSm,
            styles.ledgerNums,
            { color: over ? palette.danger : palette.text },
          ]}
        >
          {value.toLocaleString()} / {target.toLocaleString()} {unit}
        </Text>
      </View>
      <View style={[styles.ledgerTrack, { height, borderRadius: height / 2 }]}>
        <View
          style={{
            width: `${fraction * 100}%`,
            height,
            borderRadius: height / 2,
            backgroundColor: over ? palette.danger : color,
          }}
        />
      </View>
    </View>
  );
});

// ---------------------------------------------------------------------------
// SetRow — a settings row
// ---------------------------------------------------------------------------

/**
 * Label on the left, current value on the right, optional chevron.
 *
 * The hairline is drawn as a bottom border and suppressed on the last row, so
 * a stack of these inside a `Panel` reads as one list rather than a pile of
 * separate rows.
 */
export function SetRow({
  label,
  value,
  icon,
  valueColor,
  chevron,
  last,
  onPress,
  right,
}: {
  label: string;
  value?: string;
  icon?: React.ReactNode;
  valueColor?: string;
  chevron?: boolean;
  last?: boolean;
  onPress?: () => void;
  /** Replaces the value entirely — used for an inline `Segmented`. */
  right?: React.ReactNode;
}) {
  const body = (
    <View style={[styles.setRow, last && { borderBottomWidth: 0 }]}>
      <View style={styles.setRowL}>
        {icon}
        <Text style={styles.setRowLabel}>{label}</Text>
      </View>
      <View style={styles.setRowR}>
        {right ?? (
          <Text style={[styles.setRowValue, valueColor ? { color: valueColor } : null]}>
            {value}
          </Text>
        )}
        {chevron ? <Text style={styles.setRowChev}>›</Text> : null}
      </View>
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress}>
      {body}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Segmented — the inline pill toggle
// ---------------------------------------------------------------------------

/**
 * Two or three mutually exclusive options in a pill. The selected segment is
 * filled with the accent, so this control demonstrates the very setting it
 * usually controls.
 */
export const Segmented = memo(function SegmentedBase<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const accent = useAccent();
  return (
    <View style={styles.segmented}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            accessibilityLabel={o.label}
            onPress={() => {
              if (on) return;
              Haptics.selectionAsync();
              onChange(o.value);
            }}
            style={[styles.segment, on && { backgroundColor: accent.brand }]}
          >
            <Text
              style={[
                styles.segmentText,
                on && { color: accent.brandInk },
              ]}
            >
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}) as <T extends string>(props: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) => React.ReactElement;

// ---------------------------------------------------------------------------
// Field — labelled text input
// ---------------------------------------------------------------------------

/**
 * NOTE: `app/(auth)/login.tsx` still carries a private copy of this. When that
 * screen is migrated, delete its local `Field` and import this one instead —
 * two inputs that drift apart is exactly the failure the design system exists
 * to prevent.
 */
export function Field({
  label,
  suffix,
  ...props
}: {
  label: string;
  /** A unit rendered inside the input, e.g. "kg". Not editable. */
  suffix?: string;
} & React.ComponentProps<typeof TextInput>) {
  const accent = useAccent();
  const [focused, setFocused] = React.useState(false);
  return (
    <View style={styles.fieldWrap}>
      <Label color={focused ? palette.text : palette.textFaint}>{label}</Label>
      <View style={[styles.fieldBox, focused && { borderColor: accent.brandDim }]}>
        <TextInput
          {...props}
          onFocus={(e) => {
            setFocused(true);
            props.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            props.onBlur?.(e);
          }}
          style={styles.fieldInput}
          placeholderTextColor={palette.textGhost}
          selectionColor={accent.brand}
          accessibilityLabel={label}
        />
        {suffix ? (
          <Text style={[type.label, { color: palette.textFaint }]}>{suffix}</Text>
        ) : null}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// StepDots — wizard progress
// ---------------------------------------------------------------------------

/** Where you are in a multi-step flow. Widths animate on the UI thread. */
export const StepDots = memo(function StepDotsBase({
  count,
  index,
}: {
  count: number;
  index: number;
}) {
  const accent = useAccent();
  return (
    <View style={styles.stepDots}>
      {Array.from({ length: count }, (_, i) => (
        <View
          key={i}
          style={[
            styles.stepDot,
            i === index && { width: 28, backgroundColor: accent.brand },
            i < index && { backgroundColor: accent.brandDim },
          ]}
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

  // --- Choice ------------------------------------------------------------
  choiceWrap: { gap: space.sm },
  choiceGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  choice: {
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    overflow: 'hidden',
  },
  // The 2px signal rule down the left edge. This is the whole selected state —
  // no fill, so the row still reads as scannable text.
  choiceKey: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 2,
    backgroundColor: palette.signal,
  },
  choiceDetail: { color: palette.textFaint, marginTop: space.xxs },

  // --- Stepper -----------------------------------------------------------
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
  },
  stepperBtn: {
    width: 56,
    height: 64,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperBtnOff: { opacity: 0.25 },
  stepperSign: {
    ...type.figure,
    color: palette.textDim,
    lineHeight: 36,
  },
  stepperValue: { alignItems: 'center', gap: space.xxs },

  chartUnit: { ...type.labelSm, color: palette.textGhost, marginTop: 2 },

  // --- Tile --------------------------------------------------------------
  tile: {
    flexBasis: '48%',
    flexGrow: 1,
    gap: space.xs,
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
    padding: space.lg,
  },
  tileName: { ...type.heading, color: palette.text, marginTop: space.xs },
  tileDetail: { ...type.caption, fontSize: 12, color: palette.textFaint },

  // --- ItemRow -----------------------------------------------------------
  itemRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: HAIRLINE,
    borderBottomColor: palette.hairline,
  },
  itemLeft: { flex: 1, gap: 2 },
  itemTitle: { ...type.body, fontSize: 14.5, color: palette.text },
  itemSub: { ...type.caption, fontSize: 11.5, color: palette.textFaint },
  itemRight: { alignItems: 'flex-end', gap: 1 },
  itemValue: { ...type.valueSm, fontSize: 16, color: palette.text },

  // --- SearchField -------------------------------------------------------
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
  searchInput: {
    ...type.body,
    color: palette.text,
    flex: 1,
    paddingVertical: space.md,
  },
  searchClear: { ...type.value, color: palette.textFaint, lineHeight: 22 },

  // --- GroupHeader -------------------------------------------------------
  groupHeader: {
    backgroundColor: palette.raised,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.sm,
  },

  // --- Delta -------------------------------------------------------------
  delta: { fontFamily: fontFamily.semibold, letterSpacing: 0.2, ...tabularNums },

  // --- LedgerBar ---------------------------------------------------------
  ledgerRow: { gap: 5 },
  ledgerHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: space.sm,
  },
  ledgerNums: { ...tabularNums },
  ledgerTrack: { backgroundColor: palette.hairline, overflow: 'hidden' },

  // --- SetRow ------------------------------------------------------------
  setRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: 11,
    borderBottomWidth: HAIRLINE,
    borderBottomColor: palette.hairline,
  },
  setRowL: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flexShrink: 1 },
  setRowLabel: { ...type.body, fontSize: 13.5, color: palette.text },
  setRowR: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  setRowValue: { ...type.caption, fontSize: 12.5, color: palette.textDim },
  setRowChev: { ...type.caption, fontSize: 16, color: palette.textFaint, lineHeight: 16 },

  // --- Segmented ---------------------------------------------------------
  segmented: {
    flexDirection: 'row',
    gap: 2,
    padding: 2,
    borderRadius: radius.pill,
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
  },
  segment: { paddingHorizontal: 11, paddingVertical: 5, borderRadius: radius.pill },
  segmentText: { ...type.labelSm, fontSize: 9.5, color: palette.textFaint },

  // --- Field -------------------------------------------------------------
  fieldWrap: { gap: space.sm },
  fieldBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
  },
  fieldInput: {
    ...type.value,
    color: palette.text,
    flex: 1,
    paddingVertical: space.md,
  },

  // --- StepDots ----------------------------------------------------------
  stepDots: { flexDirection: 'row', gap: space.xs, alignItems: 'center' },
  stepDot: {
    height: 2,
    width: 14,
    borderRadius: 1,
    backgroundColor: palette.hairlineBright,
  },
});
