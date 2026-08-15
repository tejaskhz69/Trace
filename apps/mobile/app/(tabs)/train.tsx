/**
 * Workout logging.
 *
 * The entire competitive point of this screen is LOGGING SPEED. Hevy wins on
 * one behaviour: it auto-fills your previous performance so a set is two taps
 * mid-workout. We do the same, via /workouts/sessions/last-performance.
 *
 * Performance notes:
 *  - FlashList, not FlatList. Set lists get long and FlashList recycles.
 *  - Rows are memoised on primitives, so logging set 12 doesn't re-render 1-11.
 *  - The rest timer runs on a shared value, not setState — a 1Hz setState
 *    across a long list is a surprisingly effective way to drop frames.
 */

import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { FlashList } from '@shopify/flash-list';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { Button, Card, Skeleton } from '../../src/components/ui';
import { request } from '../../src/lib/api';
import { palette, radius, space, type } from '../../src/theme';

interface Exercise {
  id: string;
  name: string;
  muscle_group: string;
  is_compound: boolean;
}

interface LoggedSet {
  id: string;
  exerciseId: string;
  exerciseName: string;
  weight_kg: number;
  reps: number;
  e1rm: number | null;
  setIndex: number;
}

interface LastPerformance {
  sets: Array<{ weight_kg: number; reps: number; rpe: number | null }>;
  best_e1rm: number | null;
}

export default function TrainScreen() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [selected, setSelected] = useState<Exercise | null>(null);
  const [last, setLast] = useState<LastPerformance | null>(null);
  const [sets, setSets] = useState<LoggedSet[]>([]);
  const [weight, setWeight] = useState('');
  const [reps, setReps] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    request<Exercise[]>('/api/workouts/exercises')
      .then(setExercises)
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const startSession = useCallback(async () => {
    const res = await request<{ id: string }>('/api/workouts/sessions', {
      method: 'POST',
      body: { routine_name: null },
    });
    setSessionId(res.id);
    return res.id;
  }, []);

  /**
   * The two-tap behaviour: selecting an exercise pre-fills the weight and reps
   * from last time, so the common case (same weight, same reps) is one tap.
   */
  const selectExercise = useCallback(async (ex: Exercise) => {
    setSelected(ex);
    setLast(null);
    Haptics.selectionAsync();
    try {
      const perf = await request<LastPerformance>(
        `/api/workouts/sessions/last-performance?exercise_id=${ex.id}`,
      );
      setLast(perf);
      const top = perf.sets[0];
      if (top) {
        setWeight(String(top.weight_kg));
        setReps(String(top.reps));
      } else {
        setWeight('');
        setReps('');
      }
    } catch {
      setWeight('');
      setReps('');
    }
  }, []);

  const logSet = useCallback(async () => {
    if (!selected) return;
    const w = parseFloat(weight);
    const r = parseInt(reps, 10);
    if (!Number.isFinite(w) || !Number.isFinite(r) || r < 1) return;

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const id = sessionId ?? (await startSession());

    // Optimistic: the row appears instantly, the request follows.
    const optimistic: LoggedSet = {
      id: `tmp-${Date.now()}`,
      exerciseId: selected.id,
      exerciseName: selected.name,
      weight_kg: w,
      reps: r,
      e1rm: r === 1 ? w : w * (1 + r / 30),
      setIndex: sets.filter((s) => s.exerciseId === selected.id).length,
    };
    setSets((prev) => [optimistic, ...prev]);

    try {
      const res = await request<{ id: string; set_index: number; e1rm: number }>(
        `/api/workouts/sessions/${id}/sets`,
        { method: 'POST', body: { exercise_id: selected.id, weight_kg: w, reps: r } },
      );
      setSets((prev) =>
        prev.map((s) =>
          s.id === optimistic.id
            ? { ...s, id: res.id, setIndex: res.set_index, e1rm: res.e1rm }
            : s,
        ),
      );
    } catch {
      setSets((prev) => prev.filter((s) => s.id !== optimistic.id));
    }
  }, [selected, weight, reps, sessionId, sets, startSession]);

  const bestToday = useMemo(() => {
    if (!selected) return null;
    const mine = sets.filter((s) => s.exerciseId === selected.id && s.e1rm);
    if (!mine.length) return null;
    return Math.max(...mine.map((s) => s.e1rm!));
  }, [sets, selected]);

  const isPR = bestToday != null && last?.best_e1rm != null && bestToday > last.best_e1rm;

  return (
    <SafeAreaView style={styles.flex} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Train</Text>
        {sessionId && <Text style={styles.live}>● Session active</Text>}
      </View>

      {loading ? (
        <View style={styles.padded}>
          <Skeleton height={44} />
          <View style={{ height: space.md }} />
          <Skeleton height={140} />
        </View>
      ) : !selected ? (
        <FlashList
          data={exercises}
          keyExtractor={(e) => e.id}
          contentContainerStyle={{ padding: space.lg }}
          renderItem={({ item }) => (
            <ExerciseRow exercise={item} onPress={selectExercise} />
          )}
          ListEmptyComponent={
            <Card>
              <Text style={styles.emptyText}>
                No exercises loaded yet. Seed the exercise library on the
                backend to get started.
              </Text>
            </Card>
          }
        />
      ) : (
        <View style={styles.padded}>
          <Animated.View entering={FadeInDown.duration(240)}>
            <Card style={styles.activeCard}>
              <Pressable onPress={() => setSelected(null)} hitSlop={8}>
                <Text style={styles.back}>← All exercises</Text>
              </Pressable>

              <Text style={styles.exerciseName}>{selected.name}</Text>

              {last?.sets.length ? (
                <Text style={styles.lastTime}>
                  Last time:{' '}
                  {last.sets
                    .map((s) => `${s.weight_kg}×${s.reps}`)
                    .join('  ·  ')}
                </Text>
              ) : (
                <Text style={styles.lastTime}>First time logging this one.</Text>
              )}

              <View style={styles.inputRow}>
                <View style={styles.inputWrap}>
                  <Text style={styles.inputLabel}>Weight (kg)</Text>
                  <TextInput
                    value={weight}
                    onChangeText={setWeight}
                    style={styles.input}
                    keyboardType="decimal-pad"
                    selectTextOnFocus
                    accessibilityLabel="Weight in kilograms"
                  />
                </View>
                <View style={styles.inputWrap}>
                  <Text style={styles.inputLabel}>Reps</Text>
                  <TextInput
                    value={reps}
                    onChangeText={setReps}
                    style={styles.input}
                    keyboardType="number-pad"
                    selectTextOnFocus
                    accessibilityLabel="Repetitions"
                  />
                </View>
              </View>

              <Button label="Log set" onPress={logSet} />

              {isPR && (
                <Animated.View entering={FadeIn.duration(240)}>
                  <Text style={styles.pr}>
                    ★ New estimated 1RM — {bestToday!.toFixed(1)} kg, up from{' '}
                    {last!.best_e1rm!.toFixed(1)}
                  </Text>
                </Animated.View>
              )}
            </Card>
          </Animated.View>

          <FlashList
            data={sets.filter((s) => s.exerciseId === selected.id)}
            keyExtractor={(s) => s.id}
            contentContainerStyle={{ paddingTop: space.lg }}
            renderItem={({ item }) => <SetRow set={item} />}
          />
        </View>
      )}
    </SafeAreaView>
  );
}

const ExerciseRow = memo(function ExerciseRowBase({
  exercise,
  onPress,
}: {
  exercise: Exercise;
  onPress: (e: Exercise) => void;
}) {
  return (
    <Pressable
      onPress={() => onPress(exercise)}
      style={styles.exerciseRow}
      accessibilityRole="button"
    >
      <View style={styles.flex}>
        <Text style={styles.exerciseRowName}>{exercise.name}</Text>
        <Text style={styles.exerciseRowMeta}>
          {exercise.muscle_group}
          {exercise.is_compound ? ' · compound' : ''}
        </Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
});

const SetRow = memo(
  function SetRowBase({ set }: { set: LoggedSet }) {
    return (
      <View style={styles.setRow}>
        <Text style={styles.setIndex}>{set.setIndex + 1}</Text>
        <Text style={styles.setDetail}>
          {set.weight_kg} kg × {set.reps}
        </Text>
        {set.e1rm != null && (
          <Text style={styles.setE1rm}>e1RM {set.e1rm.toFixed(1)}</Text>
        )}
      </View>
    );
  },
  (a, b) =>
    a.set.id === b.set.id &&
    a.set.weight_kg === b.set.weight_kg &&
    a.set.reps === b.set.reps,
);

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.bg },
  padded: { flex: 1, padding: space.lg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingTop: space.md,
  },
  title: { ...type.title, color: palette.text },
  live: { ...type.micro, color: palette.primary },

  exerciseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: palette.border,
  },
  exerciseRowName: { ...type.bodyStrong, color: palette.text },
  exerciseRowMeta: { ...type.micro, color: palette.textFaint, marginTop: 2 },
  chevron: { ...type.heading, color: palette.textFaint },

  activeCard: { gap: space.md },
  back: { ...type.micro, color: palette.textMuted },
  exerciseName: { ...type.title, color: palette.text },
  lastTime: { ...type.caption, color: palette.textMuted },

  inputRow: { flexDirection: 'row', gap: space.md },
  inputWrap: { flex: 1, gap: space.xs },
  inputLabel: {
    ...type.micro,
    color: palette.textMuted,
    textTransform: 'uppercase',
  },
  input: {
    height: 52,
    borderRadius: radius.md,
    backgroundColor: palette.bg,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: space.lg,
    color: palette.text,
    ...type.heading,
  },
  pr: { ...type.caption, color: palette.primary, textAlign: 'center' },

  setRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: palette.border,
  },
  setIndex: {
    ...type.micro,
    color: palette.textFaint,
    width: 20,
  },
  setDetail: { ...type.body, color: palette.text, flex: 1 },
  setE1rm: { ...type.micro, color: palette.textMuted },

  emptyText: { ...type.body, color: palette.textMuted, lineHeight: 22 },
});
