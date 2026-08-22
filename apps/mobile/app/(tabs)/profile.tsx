/**
 * Tab 5 · Profile — account, connected sources, goal, appearance.
 *
 * Ported from the design artifact. The copy is the artifact's, verbatim, in
 * the places where it explains a rule: the accent callout and the Strava
 * disconnect warning both say something true that a shorter label wouldn't.
 *
 * This is where the green/white accent switch lives, per the artifact's
 * "Profile › Appearance". Putting it here rather than behind a debug gesture
 * matters — it is a real user setting, not a preview toggle.
 */

import React, { useEffect } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Label,
  Panel,
  Plain,
  Segmented,
  SetRow,
} from '../../src/components/instrument';
import { IconHeart, IconLink } from '../../src/components/icons';
import { useAuth } from '../../src/state/useAuth';
import { healthSummary, useHealth } from '../../src/state/useHealth';
import { useAccent, useSurfaces, useTheme } from '../../src/state/useTheme';
import { motion, palette, space, type } from '../../src/theme';

const ACCENT_OPTIONS = [
  { value: 'green' as const, label: 'Green' },
  { value: 'white' as const, label: 'White' },
];

const SURFACE_OPTIONS = [
  { value: 'dark' as const, label: 'Dark' },
  { value: 'black' as const, label: 'Black' },
];

function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);

  const mode = useTheme((s) => s.mode);
  const setMode = useTheme((s) => s.setMode);
  const accentName = useTheme((s) => s.accent);
  const setAccent = useTheme((s) => s.setAccent);

  const health = useHealth();
  useEffect(() => {
    health.init();
    // Once on mount. `init` is stable on the store, and re-running it on every
    // render would re-probe the native module continuously.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const healthOn = health.status === 'ready' && !!health.syncedThrough;
  const connectedCount = healthOn ? 1 : 0;

  const who = user?.display_name ?? user?.email?.split('@')[0] ?? 'Athlete';
  const mark = initials(user?.display_name ?? null, user?.email ?? '');

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>PROFILE</Text>
        </View>
        <View style={[styles.avatar, { borderColor: surfaces.hairlineBright }]}>
          <Text style={styles.avatarText}>{mark}</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + space.xxl }]}
        showsVerticalScrollIndicator={false}
      >
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel>
            <View style={styles.identity}>
              <View style={[styles.avatarLg, { borderColor: surfaces.hairlineBright }]}>
                <Text style={styles.avatarLgText}>{mark}</Text>
              </View>
              <View style={styles.flexShrink}>
                <Text style={styles.name}>{who}</Text>
                <Text style={styles.email}>{user?.email}</Text>
              </View>
            </View>
          </Panel>
        </Animated.View>

        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <Panel
            label="Connected"
            right={<Label>{connectedCount} of 3</Label>}
            padded={false}
          >
            <SetRow
              label={health.platform === 'health_connect' ? 'Health Connect' : 'Apple Health'}
              icon={<IconHeart size={16} color={healthOn ? accent.brand : palette.textDim} />}
              value={healthSummary(health)}
              valueColor={
                health.status === 'error'
                  ? palette.danger
                  : healthOn
                    ? accent.brand
                    : undefined
              }
              chevron={health.status !== 'syncing'}
              onPress={health.status === 'syncing' ? undefined : health.connect}
            />
            <SetRow
              label="Strava"
              icon={<IconLink size={16} color={palette.strava} />}
              value="Not yet available"
            />
            <SetRow
              label="Garmin"
              icon={<IconLink size={16} color={palette.textFaint} />}
              value="Via Apple Health"
              last
            />
            <View style={styles.panelFoot}>
              {health.status === 'unsupported' ? (
                <Plain tone="warn">
                  Health data needs a development build — it can&apos;t work in
                  Expo Go, because the native module isn&apos;t in that app.
                </Plain>
              ) : health.emptyAfterSync ? (
                <Plain tone="warn">
                  Connected, but nothing came back. Either no data has been
                  shared with Trace, or permission was declined —{' '}
                  <Text style={styles.b}>your phone won&apos;t tell us which</Text>.
                  Check Trace under Health &rsaquo; Sharing.
                </Plain>
              ) : (
                <Plain>
                  Garmin and Strava both write into{' '}
                  {health.platform === 'health_connect' ? 'Health Connect' : 'Apple Health'},
                  so connecting this one picks up both.{' '}
                  <Text style={styles.b}>None of it is added to your calorie
                  target</Text> — it explains your burn, it doesn&apos;t inflate it.
                </Plain>
              )}
            </View>
          </Panel>
        </Animated.View>

        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel label="Goal" padded={false}>
            <SetRow label="Aim" value={goalLabel(user?.goal_type)} chevron />
            <SetRow label="Units" value="kg · cm · kcal" chevron />
            <SetRow
              label="Surface"
              right={
                <Segmented options={SURFACE_OPTIONS} value={mode} onChange={setMode} />
              }
            />
            <SetRow
              label="Accent"
              last
              right={
                <Segmented
                  options={ACCENT_OPTIONS}
                  value={accentName}
                  onChange={setAccent}
                />
              }
            />
            <View style={styles.panelFoot}>
              <Plain>
                Accent changes buttons, the active tab and the ring&apos;s centre —{' '}
                <Text style={styles.b}>never a chart</Text>. Data colours mean
                something, so they stay put whichever you pick.
              </Plain>
            </View>
          </Panel>
        </Animated.View>

        <Animated.View entering={FadeInDown.duration(motion.base).delay(120)}>
          <Panel label="Account" padded={false}>
            <SetRow label="Sign out" value="" last onPress={logout} chevron />
          </Panel>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

function goalLabel(goal: string | undefined): string {
  switch (goal) {
    case 'gain':
      return 'Lean gain';
    case 'lose':
      return 'Fat loss';
    case 'recomp':
      return 'Recomp';
    default:
      return 'Maintain';
  }
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  flexShrink: { flexShrink: 1 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
  brandText: { ...type.label, fontSize: 11, letterSpacing: 2, color: palette.text },
  avatar: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: palette.raised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { ...type.labelSm, fontSize: 10.5, color: palette.textDim },
  body: { padding: space.lg, gap: space.md },

  identity: { flexDirection: 'row', alignItems: 'center', gap: 13 },
  avatarLg: {
    width: 46,
    height: 46,
    borderRadius: 23,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: palette.raised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarLgText: { ...type.valueSm, color: palette.text },
  name: { ...type.heading, color: palette.text },
  email: { ...type.caption, fontSize: 12, color: palette.textFaint, marginTop: 2 },

  panelFoot: {
    padding: space.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: palette.hairline,
  },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
