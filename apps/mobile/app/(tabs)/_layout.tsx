import React from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { Tabs, useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';

import { palette, radius, space, type } from '../../src/theme';

/**
 * Simple glyph tab icons. Deliberately not an icon font -- a 2px-stroke line
 * icon set is the spec, and shipping one font file beats pulling in a 2MB
 * icon package for five glyphs.
 */
function TabIcon({ glyph, focused }: { glyph: string; focused: boolean }) {
  return (
    <Text
      style={[
        styles.icon,
        { color: focused ? palette.primary : palette.textFaint },
      ]}
    >
      {glyph}
    </Text>
  );
}

export default function TabsLayout() {
  const router = useRouter();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: palette.primary,
        tabBarInactiveTintColor: palette.textFaint,
        tabBarLabelStyle: styles.tabLabel,
        // Lazy-mount tabs so cold start only pays for the dashboard.
        lazy: true,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Today',
          tabBarIcon: ({ focused }) => <TabIcon glyph="◎" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="log"
        options={{
          title: 'Log',
          tabBarIcon: ({ focused }) => <TabIcon glyph="＋" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="train"
        options={{
          title: 'Train',
          tabBarIcon: ({ focused }) => <TabIcon glyph="▤" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ focused }) => <TabIcon glyph="↗" focused={focused} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: palette.surface,
    borderTopColor: palette.border,
    borderTopWidth: 1,
    height: Platform.OS === 'ios' ? 84 : 64,
    paddingTop: space.sm,
  },
  tabLabel: { ...type.micro },
  icon: { fontSize: 20, lineHeight: 24 },
});
