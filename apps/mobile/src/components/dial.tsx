/**
 * A big draggable number. Drag a ruler under a fixed needle to set a value.
 *
 * WHY THIS INSTEAD OF A TEXT FIELD
 * Three reasons, in order of how much they matter:
 *
 *   TYPO-PROOF   A keyboard lets someone enter 7 kg or 700 kg. Both are
 *                accepted, and a wrong starting weight poisons the TDEE
 *                estimate for weeks before anyone notices. A dial physically
 *                cannot produce a value outside its range.
 *   FASTER       Nobody's weight is a surprise to them. Landing near the right
 *                number and nudging is quicker than typing and dismissing a
 *                keyboard, especially on the third question in a row.
 *   NO KEYBOARD  A keyboard covering half the screen during a questionnaire is
 *                the main reason people abandon one. The layout never moves.
 *
 * MOTION IS ALL ON THE UI THREAD
 * The ruler is a Reanimated shared value driven by a Gesture Handler pan.
 * React re-renders only when the ROUNDED value changes -- so dragging across
 * 40 kg fires ~40 renders, not one per frame. Driving this from setState was
 * the original source of jank in this app and is explicitly banned.
 *
 * ACCESSIBILITY
 * A drag-only control is unusable with a screen reader, so the value is also
 * an `adjustable` element with increment/decrement actions, and a long-press
 * on the readout opens a plain numeric entry as the escape hatch.
 */

import React, { memo, useCallback, useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { useAccent } from '../state/useTheme';
import { motion, palette, radius, space, type } from '../theme';

/** Pixels of drag per one `step`. Tuned so a full swipe covers ~20 steps. */
const PX_PER_STEP = 14;

/** Ruler ticks are drawn this far apart. */
const TICK_GAP = PX_PER_STEP;

export const Dial = memo(function DialBase({
  value,
  onChange,
  min,
  max,
  step = 0.5,
  unit,
  label,
  decimals = 1,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit: string;
  label?: string;
  decimals?: 0 | 1;
}) {
  const accent = useAccent();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  // The live, unrounded position. React never sees this change.
  const offset = useSharedValue(0);
  const start = useSharedValue(0);

  const clamp = useCallback(
    (v: number) => Math.min(max, Math.max(min, v)),
    [min, max],
  );

  /**
   * Called from the UI thread on every frame, but only ever with a value that
   * actually changed -- the worklet compares before it hops threads. Without
   * that guard this is a setState per frame, which is the exact pattern the
   * performance rules exist to prevent.
   */
  const commit = useCallback(
    (next: number) => {
      Haptics.selectionAsync();
      onChange(next);
    },
    [onChange],
  );

  const pan = Gesture.Pan()
    .onBegin(() => {
      start.value = value;
      offset.value = 0;
    })
    .onUpdate((e) => {
      offset.value = e.translationX;
      // Drag RIGHT to increase, which matches the ruler sliding leftward
      // under a fixed needle.
      const raw = start.value + (e.translationX / PX_PER_STEP) * step;
      const snapped = Math.min(max, Math.max(min, Math.round(raw / step) * step));
      if (snapped !== value) {
        runOnJS(commit)(snapped);
      }
    })
    .onFinalize(() => {
      offset.value = withTiming(0, { duration: motion.fast });
    });

  // The ruler translates with the finger, then settles back to centre once
  // the value has been committed -- so the needle always reads the truth.
  const rulerStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: offset.value % TICK_GAP }],
  }));

  const fmt = (v: number) => v.toFixed(decimals);

  const openEditor = () => {
    setDraft(fmt(value));
    setEditing(true);
  };

  const closeEditor = () => {
    const n = parseFloat(draft.replace(',', '.'));
    if (Number.isFinite(n)) onChange(clamp(Math.round(n / step) * step));
    setEditing(false);
  };

  return (
    <View style={styles.wrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}

      {editing ? (
        <View style={styles.editRow}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            keyboardType="decimal-pad"
            autoFocus
            selectTextOnFocus
            onBlur={closeEditor}
            onSubmitEditing={closeEditor}
            style={[styles.editInput, { borderColor: accent.brand }]}
          />
          <Text style={styles.unit}>{unit}</Text>
        </View>
      ) : (
        <Pressable
          onLongPress={openEditor}
          delayLongPress={350}
          accessibilityRole="adjustable"
          accessibilityLabel={label ?? 'Value'}
          accessibilityValue={{ text: `${fmt(value)} ${unit}` }}
          accessibilityHint="Swipe up or down to adjust. Long press to type a value."
          accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
          onAccessibilityAction={(e) => {
            const d = e.nativeEvent.actionName === 'increment' ? step : -step;
            onChange(clamp(value + d));
          }}
          style={styles.readoutRow}
        >
          <Text style={[styles.readout, { color: palette.text }]}>{fmt(value)}</Text>
          <Text style={styles.unit}>{unit}</Text>
        </Pressable>
      )}

      {/* ------------------------------------------------------ the ruler */}
      <GestureDetector gesture={pan}>
        <View style={styles.rulerBox} collapsable={false}>
          <Animated.View style={[styles.ruler, rulerStyle]}>
            {TICKS.map((i) => (
              <View
                key={i}
                style={[
                  styles.tick,
                  // Every fifth tick is taller, so the eye has something to
                  // track. A uniform comb reads as a texture, not a scale.
                  i % 5 === 0 ? styles.tickMajor : null,
                ]}
              />
            ))}
          </Animated.View>

          {/* The needle is fixed; the ruler moves under it. */}
          <View style={[styles.needle, { backgroundColor: accent.brand }]} />

          {/* Fade the ends so the ruler reads as continuous rather than as a
              bar that stops. Two overlays rather than a gradient dependency. */}
          <View style={styles.fadeL} pointerEvents="none" />
          <View style={styles.fadeR} pointerEvents="none" />
        </View>
      </GestureDetector>

      <Text style={styles.hint}>
        Drag to set{Platform.OS === 'ios' ? '' : ''} · hold the number to type it
      </Text>
    </View>
  );
});

/** Fixed-length comb. It scrolls modulo one gap, so it never needs more. */
const TICKS = Array.from({ length: 41 }, (_, i) => i);

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  label: { ...type.label, color: palette.textFaint },

  readoutRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  readout: { ...type.readout },
  unit: { ...type.title, color: palette.textFaint },

  editRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  editInput: {
    ...type.figure,
    color: palette.text,
    borderBottomWidth: 2,
    minWidth: 140,
    paddingVertical: space.xs,
  },

  rulerBox: {
    height: 56,
    justifyContent: 'center',
    overflow: 'hidden',
    marginTop: space.sm,
  },
  ruler: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: TICK_GAP - 2,
    paddingHorizontal: space.lg,
  },
  tick: { width: 2, height: 14, backgroundColor: palette.hairlineBright, borderRadius: 1 },
  tickMajor: { height: 26, backgroundColor: palette.textGhost },
  needle: {
    position: 'absolute',
    alignSelf: 'center',
    width: 3,
    height: 40,
    borderRadius: 2,
  },
  fadeL: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 40,
    backgroundColor: 'transparent',
  },
  fadeR: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    width: 40,
    backgroundColor: 'transparent',
  },
  hint: { ...type.labelSm, color: palette.textGhost },
});
