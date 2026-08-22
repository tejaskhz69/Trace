/**
 * The live set logger. This is the screen the app is actually used on.
 *
 * WHAT MAKES IT DIFFERENT FROM A SET LOG
 * Every other tracker asks for weight and reps and stores them. This one also
 * asks HOW MANY MORE YOU COULD HAVE DONE, and that single extra question is
 * what turns a diary entry into a measurement: 75 kg × 10 with five left and
 * 75 kg × 10 with nothing left are wildly different facts about the same
 * lifter, and an app that cannot tell them apart cannot tell you whether you
 * are getting stronger.
 *
 * So the moment a set is submitted, the screen answers the only question that
 * matters — did that maintain your strength, or move it — and names the two
 * concrete routes to beating it: one more rep, or the next loadable weight.
 *
 * WHY THE VERDICT ARRIVES WITH THE WRITE
 * `POST /sets` returns the assessment in the same response. The lifter is
 * standing at the bar with 90 seconds of rest; a second round trip to find
 * out what just happened is one too many.
 *
 * WHY RIR AND NOT RPE ON THE CONTROL
 * "How many more could you have done" is a question a beginner can answer
 * honestly. "Rate this 1-10" is jargon that gets guessed. We ask for RIR and
 * render RPE underneath for people who think in it.
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
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  Button,
  Label,
  Panel,
  Rule,
  Stepper,
} from '../../src/components/instrument';
import { api, type NextSet, type SetResult, type SetVerdict } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

/** How many reps in reserve the lifter can claim. 5+ collapses the tail. */
const RIR_CHOICES = [0, 1, 2, 3, 4, 5] as const;

export default function LiveSetScreen() {
  const { session, exercise } = useLocalSearchParams<{
    session: string;
    exercise: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [data, setData] = useState<NextSet | null>(null);
  const [weight, setWeight] = useState(0);
  const [reps, setReps] = useState(8);
  const [rir, setRir] = useState(2);
  const [result, setResult] = useState<SetResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session || !exercise) return;
    try {
      const next = await api.nextSet(session, exercise);
      setData(next);
      // Pre-fill from the prescription. A brand-new lift has no weight to
      // suggest, so it lands on the smallest loadable increment rather than
      // on a number we invented.
      setWeight(next.prescription.weight_kg ?? next.weight_step_kg * 8);
      setReps(next.prescription.reps);
      setRir(next.prescription.target_rir);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this exercise.');
    }
  }, [session, exercise]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = useCallback(async () => {
    if (!session || !exercise || saving) return;
    setSaving(true);
    try {
      const res = await api.logSet(session, {
        exercise_id: exercise,
        weight_kg: weight,
        reps,
        rir,
      });
      setResult(res);
      // A set that moved the estimate deserves to be felt, not just read.
      Haptics.notificationAsync(
        res.verdict === 'PURPLE'
          ? Haptics.NotificationFeedbackType.Success
          : Haptics.NotificationFeedbackType.Warning,
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save that set.');
    } finally {
      setSaving(false);
    }
  }, [session, exercise, weight, reps, rir, saving, load]);

  if (!data) {
    return (
      <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
        <View style={styles.center}>
          {error ? (
            <Text style={styles.error}>{error}</Text>
          ) : (
            <ActivityIndicator color={accent.brand} />
          )}
        </View>
      </View>
    );
  }

  const { exercise: ex, prescription, reference_e1rm, weight_step_kg } = data;
  const working = data.sets_done.filter((s) => !s.is_warmup);
  const setNo = working.length + 1;
  const loadPct = reference_e1rm
    ? Math.round((weight / reference_e1rm) * 100)
    : null;

  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + space.md, paddingBottom: insets.bottom + space.xxl },
      ]}
      keyboardShouldPersistTaps="handled"
    >
      {/* ---------------------------------------------------- masthead */}
      <View style={styles.head}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Back</Text>
        </Pressable>
        <Pressable
          onPress={() => router.replace(`/workout/summary?session=${session}`)}
          hitSlop={12}
        >
          <Text style={[styles.finish, { color: accent.brand }]}>FINISH</Text>
        </Pressable>
      </View>

      <Animated.View entering={FadeInDown.duration(motion.base)}>
        <Text style={styles.title}>{ex.name}</Text>
        <View style={styles.subhead}>
          <Text style={styles.sub}>
            {reference_e1rm ? `1RM ${reference_e1rm} kg` : 'No reference yet'}
          </Text>
          <Text style={styles.subDot}>·</Text>
          <Text style={styles.sub}>
            {working.length}/{Math.max(setNo, 3)} done
          </Text>
        </View>
      </Animated.View>

      {/* ------------------------------------------------- sets already in */}
      {working.length > 0 ? (
        <Panel style={styles.panel} padded={false}>
          {working.map((s, i) => (
            <View key={s.set_index}>
              {i > 0 ? <Rule /> : null}
              <View style={styles.doneRow}>
                <View style={styles.doneL}>
                  <Text style={styles.doneCheck}>✓</Text>
                  <Text style={styles.doneLabel}>SET {i + 1}</Text>
                  <VerdictChip verdict={s.verdict} />
                </View>
                <Text style={styles.doneValue}>
                  {s.weight_kg} kg × {s.reps}
                  {s.rir != null ? `  ·  ${s.rir} RIR` : ''}
                </Text>
              </View>
            </View>
          ))}
        </Panel>
      ) : null}

      {/* ------------------------------------------------------ the entry */}
      <Panel style={styles.panel} label={`Set ${setNo}`} padded={false}>
        <View style={styles.entry}>
          <View style={styles.entryCol}>
            <Label>Kg</Label>
            <Stepper
              value={weight}
              onChange={setWeight}
              min={0}
              max={500}
              step={weight_step_kg || 2.5}
              format={(v) => `${v % 1 === 0 ? v : v.toFixed(1)}`}
            />
          </View>
          <View style={styles.entryCol}>
            <Label>Reps</Label>
            <Stepper value={reps} onChange={setReps} min={1} max={50} step={1} />
          </View>
        </View>

        <Rule />

        {/* The question that makes this a measurement rather than a diary. */}
        <View style={styles.rirBlock}>
          <Label>How many more could you have done?</Label>
          <View style={styles.rirRow}>
            {RIR_CHOICES.map((n) => {
              const on = n === rir;
              const isTarget = n === prescription.target_rir;
              return (
                <Pressable
                  key={n}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: on }}
                  accessibilityLabel={`${n} reps in reserve`}
                  onPress={() => {
                    Haptics.selectionAsync();
                    setRir(n);
                  }}
                  style={[
                    styles.rirCell,
                    { borderColor: surfaces.hairlineBright },
                    on && { backgroundColor: accent.brand, borderColor: accent.brand },
                  ]}
                >
                  <Text
                    style={[
                      styles.rirNum,
                      { color: on ? accent.brandInk : palette.text },
                    ]}
                  >
                    {n === 5 ? '5+' : n}
                  </Text>
                  {isTarget ? (
                    <Text
                      style={[
                        styles.rirTarget,
                        { color: on ? accent.brandInk : palette.textGhost },
                      ]}
                    >
                      TARGET
                    </Text>
                  ) : null}
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.rirHint}>
            {rir === 0
              ? 'Nothing left — that was a set to failure.'
              : `Selecting ${rir} means you could have done ${rir} more rep${rir === 1 ? '' : 's'}.`}
          </Text>
        </View>
      </Panel>

      {/* ------------------------------------------------- the last verdict */}
      {result ? (
        <Animated.View entering={FadeIn.duration(motion.fast)}>
          <VerdictPanel result={result} />
        </Animated.View>
      ) : (
        <Panel style={styles.panel}>
          <Label>Prescription</Label>
          <Text style={styles.note}>{prescription.note}</Text>
          {loadPct ? (
            <Text style={styles.loadPct}>
              EST. LOAD {loadPct}% OF YOUR 1RM
            </Text>
          ) : null}
        </Panel>
      )}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Button
        label={saving ? 'Saving…' : 'Submit set'}
        onPress={submit}
        loading={saving}
        style={styles.submit}
      />

      <Text style={styles.footer}>
        LEAVE {prescription.target_rir} IN THE TANK · RPE{' '}
        {10 - prescription.target_rir} · REST{' '}
        {Math.floor(prescription.rest_s / 60)}:
        {String(prescription.rest_s % 60).padStart(2, '0')}
      </Text>
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------

/**
 * The verdict chip.
 *
 * ONE ACCENT, and it is spent here on the only state worth celebrating. A set
 * that merely repeated what we already knew gets a neutral chip — if
 * everything on the screen is green, green stops meaning anything.
 */
function VerdictChip({ verdict }: { verdict: SetVerdict | null }) {
  const accent = useAccent();
  if (!verdict || verdict === 'UNRATED') return null;

  const tone =
    verdict === 'PURPLE'
      ? { bg: accent.brandTint, fg: accent.brand, text: 'NEW BEST' }
      : verdict === 'UNDER'
        ? { bg: 'rgba(194,135,31,0.14)', fg: palette.warn, text: 'UNDER' }
        : { bg: palette.glass, fg: palette.textDim, text: 'ON TARGET' };

  return (
    <View style={[styles.chip, { backgroundColor: tone.bg }]}>
      <Text style={[styles.chipText, { color: tone.fg }]}>{tone.text}</Text>
    </View>
  );
}

function VerdictPanel({ result }: { result: SetResult }) {
  const accent = useAccent();
  const isBest = result.verdict === 'PURPLE';
  const isUnder = result.verdict === 'UNDER';
  const edge = isBest ? accent.brand : isUnder ? palette.warn : palette.hairlineBright;

  return (
    <View style={[styles.verdict, { borderColor: edge }]}>
      <View style={styles.verdictHead}>
        <View style={[styles.dot, { backgroundColor: edge }]} />
        <Text style={[styles.verdictTitle, { color: edge }]}>
          {isBest ? 'NEW BEST' : result.headline}
        </Text>
        {result.e1rm ? (
          <Text style={styles.verdictE1rm}>{result.e1rm} kg EST.</Text>
        ) : null}
      </View>
      <Text style={styles.verdictBody}>{result.detail}</Text>
      {result.load_pct ? (
        <Text style={styles.loadPct}>
          EST. LOAD {Math.round(result.load_pct)}% OF YOUR 1RM
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: space.lg, gap: space.md },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  back: { ...type.caption, color: palette.textDim },
  finish: { ...type.label },

  title: { ...type.title, color: palette.text },
  subhead: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: space.xs },
  sub: { ...type.labelSm, color: palette.textFaint },
  subDot: { ...type.labelSm, color: palette.textGhost },

  panel: { marginTop: space.xs },

  doneRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  doneL: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  doneCheck: { ...type.labelSm, color: palette.textDim },
  doneLabel: { ...type.labelSm, color: palette.textDim },
  doneValue: { ...type.valueSm, color: palette.text },

  entry: { flexDirection: 'row', padding: space.lg, gap: space.lg },
  entryCol: { flex: 1, gap: space.sm },

  rirBlock: { padding: space.lg, gap: space.md },
  rirRow: { flexDirection: 'row', gap: space.sm },
  rirCell: {
    flex: 1,
    height: 52,
    borderRadius: radius.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  rirNum: { ...type.value },
  rirTarget: { ...type.labelSm, fontSize: 7, letterSpacing: 0.8 },
  rirHint: { ...type.caption, color: palette.textFaint },

  verdict: {
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.sm,
  },
  verdictHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  dot: { width: 6, height: 6, borderRadius: 3 },
  verdictTitle: { ...type.label, flex: 1 },
  verdictE1rm: { ...type.labelSm, color: palette.textDim },
  verdictBody: { ...type.body, color: palette.textDim },

  note: { ...type.body, color: palette.textDim, marginTop: space.sm },
  loadPct: { ...type.labelSm, color: palette.textGhost, marginTop: space.xs },

  chip: {
    paddingHorizontal: space.sm,
    paddingVertical: 2,
    borderRadius: radius.xs,
  },
  chipText: { ...type.labelSm, fontSize: 8 },

  submit: { marginTop: space.sm },
  footer: {
    ...type.labelSm,
    color: palette.textGhost,
    textAlign: 'center',
    marginTop: space.xs,
  },
  error: { ...type.caption, color: palette.danger, textAlign: 'center' },
});
