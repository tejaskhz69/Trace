/**
 * The quick-log sheet — one tap from anywhere to every way of logging.
 *
 * WHY A GRID AND NOT A MENU
 * There are eight ways into this app's two data streams, and a user who has
 * to remember which tab hides the barcode scanner will use the app less. A
 * 3×3 grid is scannable in one look and puts every route the same distance
 * from the thumb. The order is deliberate: the three fastest ways to log food
 * come first, because that is the thing people do four times a day.
 *
 * WHY IT IS NOT A NATIVE ACTION SHEET
 * A native sheet would inherit iOS chrome and break the instrument language
 * on the one surface the user sees most often. This is a scrim plus a
 * bordered panel, drawn from the same tokens as everything else.
 *
 * MOTION
 * The scrim fades and the panel translates up on the UI thread via Reanimated
 * shared values. Nothing here animates through setState.
 */

import React, { useEffect } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  IconBarcode,
  IconCamera,
  IconMic,
  IconSearch,
  IconTrainer,
  IconNutrition,
  IconChart,
  IconUser,
} from './icons';
import { useAccent, useSurfaces } from '../state/useTheme';
import { motion, palette, radius, space, type } from '../theme';

export interface LogAction {
  key: string;
  label: string;
  icon: React.ReactNode;
  route: string;
}

export function LogSheet({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(visible ? 1 : 0, {
      duration: motion.base,
      easing: Easing.out(Easing.cubic),
    });
  }, [visible, progress]);

  const scrimStyle = useAnimatedStyle(() => ({ opacity: progress.value }));
  const panelStyle = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [{ translateY: (1 - progress.value) * 24 }],
  }));

  const tint = palette.textDim;

  const actions: LogAction[] = [
    { key: 'scan', label: 'Scan a meal', icon: <IconCamera color={tint} />, route: '/scan' },
    {
      key: 'search',
      label: 'Food database',
      icon: <IconSearch color={tint} />,
      route: '/food-search',
    },
    {
      key: 'barcode',
      label: 'Barcode',
      icon: <IconBarcode color={tint} />,
      route: '/scan?mode=barcode',
    },
    {
      key: 'describe',
      label: 'Describe a meal',
      icon: <IconNutrition color={tint} />,
      route: '/food-search?describe=1',
    },
    {
      key: 'voice',
      label: 'Voice log',
      icon: <IconMic color={tint} />,
      route: '/workout/voice',
    },
    {
      key: 'workout',
      label: 'Log workout',
      icon: <IconTrainer color={tint} />,
      route: '/(tabs)/train',
    },
    {
      key: 'weight',
      label: 'Log weight',
      icon: <IconChart color={tint} />,
      route: '/(tabs)/progress?log=weight',
    },
    {
      key: 'history',
      label: 'Past workouts',
      icon: <IconUser color={tint} />,
      route: '/workout/history',
    },
  ];

  const go = (route: string) => {
    Haptics.selectionAsync();
    onClose();
    // Let the sheet's dismissal start before the push, so the new screen
    // does not slide in underneath a panel that is still on screen.
    requestAnimationFrame(() => router.push(route as never));
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <Animated.View style={[styles.scrim, scrimStyle]}>
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={onClose}
          accessibilityLabel="Close"
        />
      </Animated.View>

      <View style={styles.wrap} pointerEvents="box-none">
        <Animated.View
          style={[
            styles.panel,
            {
              backgroundColor: surfaces.surface,
              borderColor: surfaces.hairlineBright,
              marginBottom: insets.bottom + space.lg,
            },
            panelStyle,
          ]}
        >
          <View style={styles.head}>
            <Text style={styles.headLabel}>Log</Text>
            <Pressable onPress={onClose} hitSlop={12} accessibilityLabel="Close">
              <Text style={styles.close}>✕</Text>
            </Pressable>
          </View>

          <View style={styles.grid}>
            {actions.map((a) => (
              <Pressable
                key={a.key}
                accessibilityRole="button"
                accessibilityLabel={a.label}
                onPress={() => go(a.route)}
                style={({ pressed }) => [
                  styles.cell,
                  { borderColor: surfaces.hairline },
                  pressed && { backgroundColor: accent.brandSoft, borderColor: accent.brandDim },
                ]}
              >
                <View style={styles.cellIcon}>{a.icon}</View>
                <Text style={styles.cellLabel}>{a.label}</Text>
              </Pressable>
            ))}
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: palette.scrim },
  wrap: { flex: 1, justifyContent: 'flex-end', paddingHorizontal: space.md },
  panel: {
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.md,
    gap: space.md,
  },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.xs,
  },
  headLabel: { ...type.label, color: palette.textFaint },
  close: { ...type.caption, color: palette.textFaint },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  cell: {
    // Three per row: (100% - 2 gaps) / 3, expressed so it survives any
    // container width without a measured layout pass.
    width: '31.5%',
    aspectRatio: 1,
    borderWidth: 1,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.xs,
  },
  cellIcon: { opacity: 0.9 },
  cellLabel: {
    ...type.labelSm,
    color: palette.textDim,
    textAlign: 'center',
    textTransform: 'none',
    letterSpacing: 0,
  },
});
