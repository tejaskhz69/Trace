/**
 * Shared primitives: Button, Card, MacroBars, Skeleton, ConfidenceChip.
 *
 * Every interactive element uses the same 100ms / 0.96x press response, driven
 * on the UI thread. Consistency of timing is what makes an app feel "built"
 * rather than assembled -- and it's cheaper than any individual animation.
 */

import React, { memo, useEffect } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  StyleProp,
  ViewStyle,
} from 'react-native';
import Animated, {
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { motion, palette, radius, space, type } from '../theme';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  loading?: boolean;
  disabled?: boolean;
  haptic?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading,
  disabled,
  haptic = true,
  style,
}: ButtonProps) {
  const pressed = useSharedValue(0);

  // Scale runs on the UI thread, so the button still responds instantly even
  // while the JS thread is busy parsing an API response.
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: interpolate(pressed.value, [0, 1], [1, motion.pressScale]) },
    ],
    opacity: interpolate(pressed.value, [0, 1], [1, 0.9]),
  }));

  const isDisabled = disabled || loading;

  return (
    <AnimatedPressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!isDisabled, busy: !!loading }}
      accessibilityLabel={label}
      disabled={isDisabled}
      onPressIn={() => {
        pressed.value = withTiming(1, { duration: motion.press });
      }}
      onPressOut={() => {
        pressed.value = withTiming(0, { duration: motion.press });
      }}
      onPress={() => {
        if (haptic) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress();
      }}
      style={[
        styles.button,
        variantStyles[variant],
        isDisabled && styles.buttonDisabled,
        animatedStyle,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator
          color={variant === 'primary' ? '#062B0A' : palette.text}
        />
      ) : (
        <Text style={[styles.buttonLabel, variantLabelStyles[variant]]}>
          {label}
        </Text>
      )}
    </AnimatedPressable>
  );
}

const variantStyles: Record<string, ViewStyle> = {
  primary: { backgroundColor: palette.primary },
  secondary: {
    backgroundColor: palette.surfaceRaised,
    borderWidth: 1,
    borderColor: palette.border,
  },
  ghost: { backgroundColor: 'transparent' },
  danger: { backgroundColor: 'transparent', borderWidth: 1, borderColor: palette.bad },
};

const variantLabelStyles: Record<string, { color: string }> = {
  primary: { color: '#062B0A' },
  secondary: { color: palette.text },
  ghost: { color: palette.textMuted },
  danger: { color: palette.bad },
};

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

export function Card({
  children,
  style,
}: {
  children: React.ReactNode;
  // StyleProp, not ViewStyle — callers legitimately pass arrays like
  // `[styles.card, { borderColor }]` and a bare ViewStyle rejects them.
  style?: StyleProp<ViewStyle>;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

// ---------------------------------------------------------------------------
// Macro bars
// ---------------------------------------------------------------------------

interface MacroBarsProps {
  protein: number;
  carbs: number;
  fat: number;
  proteinTarget?: number | null;
}

function MacroBar({
  label,
  value,
  target,
  color,
  max,
}: {
  label: string;
  value: number;
  target: number | null;
  color: string;
  max: number;
}) {
  const width = useSharedValue(0);
  const fraction = target ? Math.min(value / target, 1) : value / max;

  useEffect(() => {
    width.value = withTiming(fraction, {
      duration: motion.base,
      easing: Easing.inOut(Easing.quad),
    });
  }, [fraction, width]);

  const animatedStyle = useAnimatedStyle(() => ({
    width: `${width.value * 100}%`,
  }));

  return (
    <View style={styles.macroRow}>
      <View style={styles.macroHeader}>
        <Text style={styles.macroLabel}>{label}</Text>
        <Text style={styles.macroValue}>
          {Math.round(value)}
          <Text style={styles.macroUnit}>g</Text>
          {target ? (
            <Text style={styles.macroTarget}> / {Math.round(target)}g</Text>
          ) : null}
        </Text>
      </View>
      <View style={styles.macroTrack}>
        <Animated.View
          style={[styles.macroFill, { backgroundColor: color }, animatedStyle]}
        />
      </View>
    </View>
  );
}

/**
 * When there's no target, bars scale relative to the largest macro so the
 * chart still communicates proportion instead of sitting near-empty.
 */
export const MacroBars = memo(function MacroBarsMemo({
  protein,
  carbs,
  fat,
  proteinTarget,
}: MacroBarsProps) {
  const rows = [
    { label: 'Protein', value: protein, target: proteinTarget ?? null, color: palette.protein },
    { label: 'Carbs', value: carbs, target: null, color: palette.carbs },
    { label: 'Fat', value: fat, target: null, color: palette.fat },
  ];
  const max = Math.max(protein, carbs, fat, 1);
  return (
    <View style={styles.macroWrap}>
      {rows.map((r) => (
        <MacroBar key={r.label} {...r} max={max} />
      ))}
    </View>
  );
});

// ---------------------------------------------------------------------------
// Skeleton -- the spec says skeleton screens, not spinners
// ---------------------------------------------------------------------------

export function Skeleton({
  width,
  height,
  style,
}: {
  width?: number | `${number}%`;
  height: number;
  style?: StyleProp<ViewStyle>;
}) {
  const shimmer = useSharedValue(0.4);

  useEffect(() => {
    shimmer.value = withRepeat(
      withSequence(
        withTiming(0.85, { duration: 700, easing: Easing.inOut(Easing.quad) }),
        withTiming(0.4, { duration: 700, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      false,
    );
  }, [shimmer]);

  const animatedStyle = useAnimatedStyle(() => ({ opacity: shimmer.value }));

  return (
    <Animated.View
      style={[
        styles.skeleton,
        { width: width ?? '100%', height },
        animatedStyle,
        style,
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Confidence chip
// ---------------------------------------------------------------------------

export function ConfidenceChip({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.8
      ? palette.good
      : confidence >= 0.6
        ? palette.caution
        : palette.bad;

  return (
    <View style={[styles.chip, { borderColor: color }]}>
      <View style={[styles.chipDot, { backgroundColor: color }]} />
      <Text style={[styles.chipText, { color }]}>{pct}% sure</Text>
    </View>
  );
}

export function Divider() {
  return <View style={styles.divider} />;
}

const styles = StyleSheet.create({
  button: {
    height: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  buttonDisabled: { opacity: 0.45 },
  buttonLabel: { ...type.bodyStrong },

  card: {
    backgroundColor: palette.surface,
    borderRadius: radius.lg,
    padding: space.lg,
    borderWidth: 1,
    borderColor: palette.border,
  },

  macroWrap: { gap: space.md },
  macroRow: { gap: space.xs },
  macroHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  macroLabel: { ...type.caption, color: palette.textMuted },
  macroValue: { ...type.bodyStrong, color: palette.text },
  macroUnit: { ...type.caption, color: palette.textMuted },
  macroTarget: { ...type.caption, color: palette.textFaint },
  macroTrack: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: palette.border,
    overflow: 'hidden',
  },
  macroFill: { height: '100%', borderRadius: radius.pill },

  skeleton: {
    backgroundColor: palette.surfaceRaised,
    borderRadius: radius.sm,
  },

  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
    paddingVertical: 3,
  },
  chipDot: { width: 6, height: 6, borderRadius: 3 },
  chipText: { ...type.micro },

  divider: { height: 1, backgroundColor: palette.border, marginVertical: space.md },
});
