/**
 * The five-tab bar from the design artifact: Home · Nutrition · Trainer ·
 * Progress · Profile.
 *
 * The route filenames keep their original names (index/log/train/progress) so
 * every existing link and redirect still resolves; only the titles and icons
 * follow the artifact. Renaming the files would be a breaking change across a
 * dozen call sites for no user-visible gain.
 *
 * The active tint follows the user's accent, so this bar is one of the places
 * the green/white switch is immediately visible.
 */

import React, { useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';

import {
  IconChart,
  IconHome,
  IconNutrition,
  IconPlus,
  IconTrainer,
  IconUser,
} from '../../src/components/icons';
import { LogSheet } from '../../src/components/log-sheet';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { palette, radius, space, type } from '../../src/theme';

export default function TabsLayout() {
  const surfaces = useSurfaces();
  const accent = useAccent();
  const insets = useSafeAreaInsets();
  const [logOpen, setLogOpen] = useState(false);

  const tint = (focused: boolean) => (focused ? accent.brand : palette.textFaint);

  return (
    <View style={styles.root}>
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: [
          styles.tabBar,
          { backgroundColor: surfaces.void, borderTopColor: surfaces.hairline },
        ],
        tabBarActiveTintColor: accent.brand,
        tabBarInactiveTintColor: palette.textFaint,
        tabBarLabelStyle: styles.tabLabel,
        // Lazy-mount so cold start only pays for the Home tab.
        lazy: true,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ focused }) => <IconHome color={tint(focused)} />,
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: 'Nutrition',
          tabBarIcon: ({ focused }) => <IconNutrition color={tint(focused)} />,
        }}
      />
      <Tabs.Screen
        name="train"
        options={{
          title: 'Trainer',
          tabBarIcon: ({ focused }) => <IconTrainer color={tint(focused)} />,
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ focused }) => <IconChart color={tint(focused)} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ focused }) => <IconUser color={tint(focused)} />,
        }}
      />
    </Tabs>

    {/*
      The quick-log button.

      It floats over the tab bar rather than living in it as a sixth tab,
      because it is not a destination -- it opens a sheet and the current
      screen stays where it was. Making it a Tabs.Screen would have expo-router
      mount a real route and steal the active-tab highlight from wherever the
      user actually is.

      Logging food happens four times a day from whichever screen is open, so
      the one control that starts it has to be reachable without first
      navigating somewhere.
    */}
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Log something"
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        setLogOpen(true);
      }}
      style={({ pressed }) => [
        styles.fab,
        {
          backgroundColor: accent.brand,
          bottom: (Platform.OS === 'ios' ? 92 : 74) + insets.bottom * 0.2,
          opacity: pressed ? 0.88 : 1,
          transform: [{ scale: pressed ? 0.96 : 1 }],
        },
      ]}
    >
      <IconPlus size={24} color={accent.brandInk} strokeWidth={2.2} />
    </Pressable>

    <LogSheet visible={logOpen} onClose={() => setLogOpen(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  fab: {
    position: 'absolute',
    right: space.lg,
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabBar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    height: Platform.OS === 'ios' ? 86 : 66,
    paddingTop: space.sm,
  },
  // 10px, tracked, matching `.tab` in the artifact.
  tabLabel: { ...type.labelSm, textTransform: 'none' },
});
