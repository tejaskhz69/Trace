/**
 * Exercise detail — illustration, cues, estimated 1RM, and the set logger.
 *
 * Ported from the artifact's INCLINE DB PRESS screen.
 *
 * THE SET LOGGER IS THE POINT OF THIS SCREEN
 * Everything above it is context; the reason a user opens it mid-workout is
 * to record a set. So the weight/reps steppers pre-fill from the last
 * session, and logging is one tap from there. That single behaviour is what
 * separates an app people use between sets from one they fill in afterwards
 * from memory — which is to say, badly.
 *
 * OPTIMISTIC, BUT HONEST
 * A logged set appears in the list immediately and is marked pending until
 * the server confirms. If the write fails the row is marked failed rather
 * than silently vanishing — losing a set someone believes they recorded is
 * far worse than making them wait.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  Button,
  Cell,
  Delta,
  Label,
  Panel,
  Plain,
  Readout,
  Rule,
  Stepper,
} from '../../src/components/instrument';
import { exerciseArt } from '../../src/components/exercise-art';
import { api, request } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

interface LoggedSet {
  key: string;
  index: number;
  weight_kg: number;
  reps: number;
  state: 'pending' | 'saved' | 'failed';
  /** Reps above the same set last session. null when there's no comparison. */
  repDelta: number | null;
}

/**
 * Epley. Duplicated from the server deliberately and ONLY for the optimistic
 * row -- the authoritative value is whatever the server returns. If these two
 * ever disagree, the server wins.
 */
function e1rm(weight: number, reps: number): number {
  return reps <= 1 ? weight : weight * (1 + reps / 30);
}

export default function ExerciseDetail() {
  const params = useLocalSearchParams<{
    id: string;
    name?: string;
    equipment?: string;
    muscle?: string;
    secondary?: string;
    compound?: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();

  const name = params.name ?? 'Exercise';
  const equipment = params.equipment ?? 'barbell';
  const secondary = useMemo(
    () => (params.secondary ? params.secondary.split(',').filter(Boolean) : []),
    [params.secondary],
  );

  const { Art, drawn } = useMemo(
    () => exerciseArt(name, equipment),
    [name, equipment],
  );

  const [weight, setWeight] = useState(20);
  const [reps, setReps] = useState(8);
  const [sets, setSets] = useState<LoggedSet[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [lastSets, setLastSets] = useState<Array<{ weight_kg: number; reps: number }>>([]);
  const [bestE1rm, setBestE1rm] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-fill from the last session. This is the whole "two taps to log a set"
  // behaviour -- without it the user types four numbers between every set.
  useEffect(() => {
    let alive = true;
    api
      .lastPerformance(params.id)
      .then((res) => {
        if (!alive) return;
        setLastSets(res.sets);
        setBestE1rm(res.best_e1rm);
        if (res.sets.length > 0) {
          setWeight(Math.round(res.sets[0].weight_kg));
          setReps(res.sets[0].reps);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [params.id]);

  const logSet = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const index = sets.length + 1;
    const prior = lastSets[index - 1];
    const key = `${Date.now()}-${index}`;

    setSets((s) => [
      ...s,
      {
        key,
        index,
        weight_kg: weight,
        reps,
        state: 'pending',
        repDelta: prior ? reps - prior.reps : null,
      },
    ]);
    setError(null);
    setBusy(true);

    try {
      let sid = sessionId;
      if (!sid) {
        const created = await request<{ id: string }>('/api/workouts/sessions', {
          method: 'POST',
          body: { routine_name: null },
        });
        sid = created.id;
        setSessionId(sid);
      }
      await request(`/api/workouts/sessions/${sid}/sets`, {
        method: 'POST',
        body: { exercise_id: params.id, weight_kg: weight, reps },
      });
      setSets((s) =>
        s.map((x) => (x.key === key ? { ...x, state: 'saved' as const } : x)),
      );
    } catch (e) {
      // Mark it, don't remove it. A set that disappears is a set the user
      // believes they logged.
      setSets((s) =>
        s.map((x) => (x.key === key ? { ...x, state: 'failed' as const } : x)),
      );
      setError(
        e instanceof Error ? e.message : 'Set not saved. Check your connection.',
      );
    } finally {
      setBusy(false);
    }
  }, [sets.length, lastSets, weight, reps, sessionId, params.id]);

  const topE1rm = useMemo(() => {
    const mine = sets.length
      ? Math.max(...sets.map((s) => e1rm(s.weight_kg, s.reps)))
      : 0;
    return Math.max(mine, bestE1rm ?? 0);
  }, [sets, bestE1rm]);

  const deltaPct =
    bestE1rm && bestE1rm > 0 && topE1rm > 0
      ? ((topE1rm - bestE1rm) / bestE1rm) * 100
      : null;

  const targetSets = Math.max(lastSets.length, 4);

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Back"
          onPress={() => router.back()}
          hitSlop={12}
          style={styles.brand}
        >
          <Text style={styles.back}>‹</Text>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText} numberOfLines={1}>
            {name.toUpperCase()}
          </Text>
        </Pressable>
        <Text style={styles.stamp}>
          {(params.muscle ?? '').toUpperCase()} · {equipment.replace(/_/g, ' ').toUpperCase()}
        </Text>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.body,
          { paddingBottom: insets.bottom + space.xxl },
        ]}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* ------------------------------------------------ illustration */}
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel>
            <View style={styles.artWrap}>
              <Art size={132} color={palette.textDim} />
            </View>

            <View style={styles.chips}>
              <View style={[styles.chip, { borderColor: accent.brand }]}>
                <Text style={[styles.chipText, { color: accent.brand }]}>
                  {(params.muscle ?? 'target').toUpperCase()}
                </Text>
              </View>
              {secondary.slice(0, 3).map((m) => (
                <View key={m} style={styles.chip}>
                  <Text style={styles.chipText}>{m.toUpperCase()}</Text>
                </View>
              ))}
            </View>

            {!drawn ? (
              <Plain style={styles.gapT}>
                No illustration drawn for this movement yet — the glyph shows the
                equipment. The muscle chips and cue below still apply.
              </Plain>
            ) : null}
          </Panel>
        </Animated.View>

        {/* -------------------------------------------------------- cue */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
          <Panel>
            <View style={styles.cueRow}>
              <View style={styles.cueNum}>
                <Text style={styles.cueNumText}>1</Text>
              </View>
              <View style={styles.flex}>
                <Text style={styles.cueTitle}>{cueTitle(name, equipment)}</Text>
                <Text style={styles.cueBody}>{cueBody(name, equipment)}</Text>
              </View>
            </View>
          </Panel>
        </Animated.View>

        {/* -------------------------------------------------- estimated 1RM */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
          <Panel
            label="Estimated 1RM"
            right={
              deltaPct === null ? (
                <Label color={palette.textFaint}>No history</Label>
              ) : (
                <Delta pct={deltaPct} />
              )
            }
          >
            {topE1rm > 0 ? (
              <>
                <View style={styles.readoutRow}>
                  <Readout value={Math.round(topE1rm * 10) / 10} size="readout" />
                  <Text style={styles.readoutUnit}>kg</Text>
                </View>
                <Text style={styles.readoutSub}>
                  {bestE1rm
                    ? `best logged ${bestE1rm.toFixed(1)} kg`
                    : 'from today’s sets'}
                </Text>
              </>
            ) : (
              <Plain>
                Log a set and Trace estimates your one-rep max from it. That
                estimate, not the scale, is how it tells{' '}
                <Text style={styles.b}>muscle from fat</Text>.
              </Plain>
            )}
          </Panel>
        </Animated.View>

        {/* ------------------------------------------------- the set logger */}
        <Animated.View entering={FadeInDown.duration(motion.base).delay(120)}>
          <Panel
            label="Today"
            right={
              <Label color={palette.textFaint}>
                Set {sets.length + 1} of {targetSets}
              </Label>
            }
          >
            <Label color={palette.textDim}>Weight</Label>
            <View style={styles.gapSm} />
            <Stepper
              value={weight}
              onChange={setWeight}
              min={0}
              max={500}
              step={2.5}
              unit="kg"
              format={(v) => (Number.isInteger(v) ? `${v}` : v.toFixed(1))}
            />

            <View style={styles.gap} />
            <Label color={palette.textDim}>Reps</Label>
            <View style={styles.gapSm} />
            <Stepper value={reps} onChange={setReps} min={1} max={50} unit="reps" />

            <View style={styles.gap} />
            <Button
              label={busy ? 'Saving' : `Log set ${sets.length + 1}`}
              onPress={logSet}
              loading={busy}
            />

            {sets.length > 0 ? (
              <>
                <View style={styles.gap} />
                <Rule />
                <View style={styles.gapSm} />
                {sets.map((s) => (
                  <Animated.View
                    key={s.key}
                    entering={FadeIn.duration(motion.fast)}
                    style={styles.setRow}
                  >
                    <Text style={styles.setIndex}>Set {s.index}</Text>
                    <View style={styles.setRight}>
                      <Text style={styles.setValue}>
                        {s.weight_kg} kg × {s.reps}
                      </Text>
                      {s.repDelta !== null && s.repDelta !== 0 ? (
                        <Text
                          style={[
                            styles.setDelta,
                            { color: s.repDelta > 0 ? palette.up : palette.down },
                          ]}
                        >
                          {s.repDelta > 0 ? '▲' : '▼'} {Math.abs(s.repDelta)}
                        </Text>
                      ) : null}
                      <Text
                        style={[
                          styles.setState,
                          {
                            color:
                              s.state === 'failed'
                                ? palette.danger
                                : s.state === 'pending'
                                  ? palette.textGhost
                                  : accent.brand,
                          },
                        ]}
                      >
                        {s.state === 'failed' ? '!' : s.state === 'pending' ? '·' : '✓'}
                      </Text>
                    </View>
                  </Animated.View>
                ))}
              </>
            ) : null}

            {error ? (
              <>
                <View style={styles.gapSm} />
                <Plain tone="danger">{error}</Plain>
              </>
            ) : null}
          </Panel>
        </Animated.View>

        {/* ------------------------------------------------ last session */}
        {lastSets.length > 0 ? (
          <Animated.View entering={FadeInDown.duration(motion.base).delay(160)}>
            <Panel label="Last session" right={<Label>{lastSets.length} sets</Label>}>
              <View style={styles.cells}>
                {lastSets.slice(0, 4).map((s, i) => (
                  <Cell
                    key={i}
                    label={`Set ${i + 1}`}
                    value={s.weight_kg}
                    unit="kg"
                    sub={`${s.reps} reps`}
                  />
                ))}
              </View>
            </Panel>
          </Animated.View>
        ) : null}
      </ScrollView>
    </View>
  );
}

/**
 * Form cues.
 *
 * Keyword-matched, and deliberately few: a wrong cue is worse than none. The
 * full per-exercise instruction set comes from free-exercise-db (public
 * domain) once that import lands; these cover the movements where the single
 * most common beginner error is well established.
 */
function cueTitle(name: string, equipment: string): string {
  const n = name.toLowerCase();
  if (n.includes('incline')) return 'Set the bench to 30°';
  if (n.includes('squat')) return 'Break at the hips first';
  if (n.includes('deadlift')) return 'Bar stays against your legs';
  if (n.includes('bench')) return 'Keep your shoulder blades pinned';
  if (n.includes('row')) return 'Pull to your stomach, not your chest';
  if (n.includes('curl')) return 'Elbows stay at your sides';
  if (n.includes('press')) return 'Brace before you push';
  return `Control the weight both ways`;
}

function cueBody(name: string, equipment: string): string {
  const n = name.toLowerCase();
  if (n.includes('incline'))
    return 'Any steeper and your shoulders take the work instead of your chest.';
  if (n.includes('squat'))
    return 'Sitting back before bending the knees keeps the load on your legs rather than your lower back.';
  if (n.includes('deadlift'))
    return 'Letting the bar drift forward turns a leg exercise into a lower-back one.';
  if (n.includes('bench'))
    return 'Squeezing them together gives your shoulders a stable base and adds range you can actually press from.';
  if (n.includes('row'))
    return 'Pulling high shifts the work to your traps and away from the mid-back you meant to train.';
  if (n.includes('curl'))
    return 'Once your elbows drift forward, your front delts are doing the lifting.';
  if (n.includes('press'))
    return 'A tight midsection is what stops the weight moving you instead of the other way round.';
  return 'The lowering half builds as much as the lifting half — do not let it drop.';
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  flex: { flex: 1 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 7, flexShrink: 1 },
  back: { ...type.title, color: palette.textDim, marginRight: 2 },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
  brandText: {
    ...type.label,
    fontSize: 11,
    letterSpacing: 1.6,
    color: palette.text,
    flexShrink: 1,
  },
  stamp: { ...type.labelSm, color: palette.textFaint },

  body: { padding: space.lg, gap: space.md },

  artWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.md,
    backgroundColor: palette.raised,
    borderRadius: radius.md,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.hairlineBright,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 6,
  },
  chipText: { ...type.labelSm, color: palette.textDim },

  cueRow: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  cueNum: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.hairlineBright,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cueNumText: { ...type.labelSm, color: palette.textDim },
  cueTitle: { ...type.heading, color: palette.text, marginBottom: 4 },
  cueBody: { ...type.caption, color: palette.textDim },

  readoutRow: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  readoutUnit: { ...type.value, color: palette.textDim },
  readoutSub: { ...type.caption, color: palette.textFaint, marginTop: 2 },

  gap: { height: space.lg },
  gapSm: { height: space.sm },
  gapT: { marginTop: space.md },

  setRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
  },
  setIndex: { ...type.body, color: palette.textDim },
  setRight: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  setValue: { ...type.valueSm, color: palette.text },
  setDelta: { ...type.labelSm },
  setState: { ...type.labelSm, width: 10, textAlign: 'right' },

  cells: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
