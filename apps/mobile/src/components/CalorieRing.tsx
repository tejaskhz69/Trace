/**
 * The calorie ring.
 *
 * THIS IS ALMOST CERTAINLY WHERE YOUR JANK WAS.
 *
 * The naive implementation looks like this:
 *
 *     const [progress, setProgress] = useState(0);
 *     useEffect(() => {
 *       const id = setInterval(() => setProgress(p => p + 0.01), 16);
 *     }, []);
 *     <Circle strokeDashoffset={CIRC * (1 - progress)} />
 *
 * That runs a state update and a full React re-render every frame, on the JS
 * thread. The moment anything else touches the JS thread -- a navigation
 * transition, a list render, a fetch resolving -- frames drop. On a mid-range
 * Snapdragon it will never hold 60fps.
 *
 * This version:
 *   - drives the arc from a Reanimated SHARED VALUE, so the animation runs on
 *     the UI thread and is immune to JS-thread work entirely
 *   - uses useAnimatedProps on an Animated SVG Circle, so React never
 *     re-renders during the animation -- not once
 *   - is React.memo'd on primitives, so a parent re-render is free
 *   - animates with a spring (no overshoot) rather than a timing curve,
 *     because a ring that overshoots past the target reads as "you went over"
 *
 * The number in the middle is also driven on the UI thread, via
 * useAnimatedProps on a TextInput -- the standard trick for animating text
 * without re-rendering. Animating it with state would reintroduce exactly the
 * problem we just removed.
 */

import React, { memo, useEffect } from 'react';
import { StyleSheet, TextInput, View, Text } from 'react-native';
import Animated, {
  useAnimatedProps,
  useDerivedValue,
  useSharedValue,
  withSpring,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';

import { motion, palette, space, type } from '../theme';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);
const AnimatedTextInput = Animated.createAnimatedComponent(TextInput);

interface Props {
  consumed: number;
  target: number | null;
  size?: number;
  strokeWidth?: number;
}

function CalorieRingBase({
  consumed,
  target,
  size = 220,
  strokeWidth = 16,
}: Props) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Shared values live on the UI thread. Nothing here triggers a re-render.
  const progress = useSharedValue(0);

  const ratio = target && target > 0 ? consumed / target : 0;
  const clamped = Math.min(Math.max(ratio, 0), 1.35);
  const over = target ? consumed > target : false;

  useEffect(() => {
    progress.value = withSpring(clamped, motion.spring);
  }, [clamped, progress]);

  const animatedCircleProps = useAnimatedProps(() => ({
    // Runs entirely on the UI thread -- 'worklet' is implicit here.
    strokeDashoffset: circumference * (1 - Math.min(progress.value, 1)),
  }));

  // The overflow arc: only visible once you pass 100%.
  const animatedOverProps = useAnimatedProps(() => {
    const excess = Math.max(progress.value - 1, 0);
    return {
      strokeDashoffset: circumference * (1 - excess),
      opacity: excess > 0.001 ? 1 : 0,
    };
  });

  // Animate the number without re-rendering: drive a read-only TextInput's
  // `text` prop from the same shared value.
  const displayed = useDerivedValue(() => {
    const value = target ? progress.value * target : consumed;
    return `${Math.round(value)}`;
  });

  const animatedTextProps = useAnimatedProps(() => ({
    text: displayed.value,
    // `defaultValue` keeps TS happy about the TextInput contract.
    defaultValue: displayed.value,
  })) as never;

  const remaining = target ? Math.round(target - consumed) : null;

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <Svg width={size} height={size}>
        <Defs>
          <LinearGradient id="ringGradient" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor={palette.primary} />
            <Stop offset="1" stopColor="#7BD389" />
          </LinearGradient>
        </Defs>

        {/* Track */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={palette.border}
          strokeWidth={strokeWidth}
          fill="none"
        />

        {/* Progress */}
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#ringGradient)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={circumference}
          animatedProps={animatedCircleProps}
          // -90deg so the arc starts at 12 o'clock.
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />

        {/* Overflow */}
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={palette.caution}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={circumference}
          animatedProps={animatedOverProps}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>

      <View style={styles.center} pointerEvents="none">
        <AnimatedTextInput
          editable={false}
          underlineColorAndroid="transparent"
          style={styles.number}
          animatedProps={animatedTextProps}
        />
        <Text style={styles.unit}>kcal</Text>
        {remaining !== null && (
          <Text
            style={[
              styles.remaining,
              { color: over ? palette.caution : palette.textMuted },
            ]}
          >
            {over
              ? `${Math.abs(remaining)} over`
              : `${remaining} left`}
          </Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center' },
  center: { position: 'absolute', alignItems: 'center' },
  number: {
    ...type.display,
    color: palette.text,
    padding: 0,
    minWidth: 140,
    textAlign: 'center',
  },
  unit: {
    ...type.micro,
    color: palette.textFaint,
    textTransform: 'uppercase',
    marginTop: -2,
  },
  remaining: { ...type.caption, marginTop: space.sm },
});

/**
 * Memo on primitives only. The parent dashboard re-renders whenever any meal
 * is logged; without this the whole SVG tree reconciles on every one of those.
 */
export const CalorieRing = memo(
  CalorieRingBase,
  (a, b) =>
    a.consumed === b.consumed &&
    a.target === b.target &&
    a.size === b.size &&
    a.strokeWidth === b.strokeWidth,
);
