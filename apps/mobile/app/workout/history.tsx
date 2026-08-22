/**
 * Every workout, newest first.
 *
 * WHY IT IS ITS OWN SCREEN
 * The Trainer tab answers "what am I doing now"; this answers "what have I
 * been doing". Mixing them makes the tab you open mid-workout scroll past
 * three months of history to reach the thing you came for.
 *
 * ONE REQUEST, NOT ONE PER ROW
 * `/api/workouts/sessions` aggregates sets, reps and volume per session in a
 * single grouped query. Fetching a session then its sets would be ~150 round
 * trips for a screen the user flicks through in two seconds.
 *
 * AN UNFINISHED SESSION IS THE FIRST ROW AND IT IS ACTIONABLE
 * People forget to hit Finish. Surfacing the open session as a resume banner
 * is what stops yesterday's workout silently absorbing today's sets.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { Label, Panel, Rule } from '../../src/components/instrument';
import { api, type SessionRow } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

export default function HistoryScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.workoutHistory(60);
      setRows(res.sessions);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load your history.');
      setRows([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + space.md, paddingBottom: insets.bottom + space.xxl },
      ]}
    >
      <View style={styles.head}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </Pressable>
      </View>
      <Text style={styles.title}>Workouts</Text>

      {rows === null ? (
        <ActivityIndicator color={accent.brand} style={styles.loading} />
      ) : rows.length === 0 ? (
        <Panel>
          <Text style={styles.empty}>
            {error ?? 'No workouts logged yet. Start one from the Trainer tab.'}
          </Text>
        </Panel>
      ) : (
        <Panel padded={false}>
          {rows.map((s, i) => (
            <Animated.View
              key={s.id}
              entering={FadeInDown.duration(motion.base).delay(Math.min(i, 8) * 30)}
            >
              {i > 0 ? <Rule /> : null}
              <Pressable
                accessibilityRole="button"
                onPress={() =>
                  router.push(
                    s.is_active
                      ? `/workout/${s.id}`
                      : `/workout/summary?session=${s.id}`,
                  )
                }
                style={({ pressed }) => [
                  styles.row,
                  pressed && { backgroundColor: accent.brandSoft },
                ]}
              >
                <View style={styles.rowMain}>
                  <View style={styles.rowHead}>
                    <Text style={styles.rowName}>
                      {s.routine_name || 'Workout'}
                    </Text>
                    {s.is_active ? (
                      <View
                        style={[styles.liveTag, { borderColor: accent.brandDim }]}
                      >
                        <Text style={[styles.liveText, { color: accent.brand }]}>
                          IN PROGRESS
                        </Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.rowDate}>{formatWhen(s.started_at)}</Text>
                </View>
                <View style={styles.rowStats}>
                  <Stat value={s.duration_min} unit="min" />
                  <Stat value={s.total_sets} unit="sets" />
                  <Stat
                    value={Math.round(s.volume_kg).toLocaleString('en-US')}
                    unit="kg"
                  />
                </View>
              </Pressable>
            </Animated.View>
          ))}
        </Panel>
      )}
    </ScrollView>
  );
}

function Stat({ value, unit }: { value: string | number; unit: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Label>{unit}</Label>
    </View>
  );
}

/**
 * Relative for the last week, absolute after that. "3 days ago" is how people
 * think about recent training; "14 days ago" is not — by then they want the
 * date so they can line it up against how they felt.
 */
function formatWhen(iso: string): string {
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days === 0) return `Today · ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: space.lg, gap: space.md },
  head: { flexDirection: 'row' },
  back: { ...type.caption, color: palette.textDim },
  title: { ...type.title, color: palette.text },
  loading: { marginTop: space.xxl },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.md,
  },
  rowMain: { flex: 1, gap: 2 },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowName: { ...type.heading, color: palette.text },
  rowDate: { ...type.labelSm, color: palette.textFaint },
  rowStats: { flexDirection: 'row', gap: space.md },
  stat: { alignItems: 'flex-end', minWidth: 40, gap: 1 },
  statValue: { ...type.valueSm, color: palette.text },

  liveTag: {
    borderWidth: 1,
    borderRadius: radius.xs,
    paddingHorizontal: space.xs,
    paddingVertical: 1,
  },
  liveText: { ...type.labelSm, fontSize: 8 },

  empty: { ...type.caption, color: palette.textFaint, lineHeight: 19 },
});
