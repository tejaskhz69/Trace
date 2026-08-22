/**
 * Voice workout logging — say the set, confirm what was heard.
 *
 *     "three sets of bench press at sixty kilos, ten to fifteen reps"
 *
 * WHY THIS EXISTS
 * Typing four numbers per set with chalk on your hands, between sets, is the
 * reason most people stop logging by week three. Speaking a set takes four
 * seconds and one hand.
 *
 * WHY THERE IS A REVIEW STEP AND IT IS NOT OPTIONAL
 * The model can mishear "sixty" as "sixteen". That set would enter the
 * training history, move the estimated max, and quietly corrupt the strength
 * verdict — which is half of what this product claims to know. So the server
 * returns a PROPOSAL and writes nothing; this screen shows what was heard,
 * what was understood, and requires a tap per entry. One tap is a cheap price
 * for the feature being trustworthy.
 *
 * WHAT THE MODEL IS AND IS NOT ALLOWED TO DO
 * It transcribes and extracts numbers. It does NOT pick which of the 736
 * catalogue exercises this is — that match is a deterministic, tested pure
 * function on the server, so it cannot drift when the model changes. When the
 * match is weak the entry arrives with alternatives and no selection, and
 * this screen makes the user choose rather than guessing on their behalf.
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
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import Animated, {
  Easing,
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { Button, Label, Panel, Rule, Stepper } from '../../src/components/instrument';
import { IconMic } from '../../src/components/icons';
import { api, type VoiceEntry } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

/** Below this the match is a guess, and the UI says so rather than pretending. */
const SHAKY_MATCH = 0.85;

type Draft = VoiceEntry & { reps: number; saved: boolean; chosenId: string | null };

export default function VoiceLogScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();

  // expo-audio, not expo-av: av was removed in SDK 54. The recorder is a
  // hook-owned native object, so there is no ref to unload by hand.
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [isRecording, setIsRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The pulse runs on the UI thread. Animating a recording indicator through
  // setState is how you get a dropped frame every 500ms while the mic is hot.
  const pulse = useSharedValue(0);
  useEffect(() => {
    pulse.value = isRecording
      ? withRepeat(
          withTiming(1, { duration: motion.pulse, easing: Easing.inOut(Easing.quad) }),
          -1,
          true,
        )
      : withTiming(0, { duration: motion.fast });
  }, [isRecording, pulse]);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + pulse.value * 0.12 }],
    opacity: 0.35 + pulse.value * 0.4,
  }));

  const start = useCallback(async () => {
    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setError('Microphone access is needed to log a set by voice.');
        return;
      }
      // Recording on iOS is silent unless the session is switched into a
      // recording category first; without this the file comes back empty.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setIsRecording(true);
      setError(null);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start recording.');
    }
  }, [recorder]);

  const stop = useCallback(async () => {
    if (!isRecording) return;
    setIsRecording(false);
    setBusy(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error('Nothing was recorded.');

      const res = await api.voiceLog(uri, 'kg');
      setTranscript(res.transcript);
      setDrafts(
        res.entries.map((e) => ({
          ...e,
          // Pre-fill the actual rep count from the LOW end of a spoken range.
          // Someone who said "ten to fifteen" described a target, not a
          // result; starting at the low end means an unedited confirm can
          // only under-claim, never inflate the training history.
          reps: e.reps_low,
          saved: false,
          chosenId: e.exercise_id,
        })),
      );
      if (res.entries.length === 0) {
        setError("Nothing that sounded like a set. Try: “three sets of bench press at sixty kilos, ten reps”.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read that clip.');
    } finally {
      setBusy(false);
    }
  }, [isRecording, recorder]);

  const saveEntry = useCallback(
    async (index: number) => {
      const d = drafts[index];
      if (!d || d.saved || !d.chosenId) return;
      try {
        let sid = sessionId;
        if (!sid) {
          sid = (await api.startSession('Voice log')).id;
          setSessionId(sid);
        }
        // One POST per set, because `sets: 3` means three sets happened and
        // the strength engine counts sets, not multipliers.
        for (let i = 0; i < d.sets; i += 1) {
          await api.logSet(sid, {
            exercise_id: d.chosenId,
            weight_kg: d.weight_kg ?? 0,
            reps: d.reps,
          });
        }
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setDrafts((prev) =>
          prev.map((x, i) => (i === index ? { ...x, saved: true } : x)),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not save that set.');
      }
    },
    [drafts, sessionId],
  );

  const update = (i: number, patch: Partial<Draft>) =>
    setDrafts((prev) => prev.map((d, k) => (k === i ? { ...d, ...patch } : d)));

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

      <Text style={styles.title}>Say your set</Text>
      <Text style={styles.hint}>
        “Three sets of bench press at sixty kilos, ten to fifteen reps.”
        Nothing is saved until you confirm it below.
      </Text>

      {/* ------------------------------------------------------- the mic */}
      <View style={styles.micWrap}>
        <Animated.View
          style={[styles.micPulse, { backgroundColor: accent.brand }, pulseStyle]}
          pointerEvents="none"
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={isRecording ? 'Stop recording' : 'Start recording'}
          onPress={isRecording ? stop : start}
          disabled={busy}
          style={[
            styles.mic,
            {
              backgroundColor: isRecording ? accent.brand : surfaces.raised,
              borderColor: isRecording ? accent.brand : surfaces.hairlineBright,
            },
          ]}
        >
          {busy ? (
            <ActivityIndicator color={accent.brand} />
          ) : (
            <IconMic
              size={30}
              color={isRecording ? accent.brandInk : palette.textDim}
            />
          )}
        </Pressable>
        <Text style={styles.micLabel}>
          {busy
            ? 'READING…'
            : isRecording
              ? 'TAP TO STOP'
              : 'TAP TO SPEAK'}
        </Text>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {/* -------------------------------------------------- what was heard */}
      {transcript ? (
        <Panel label="Heard">
          <Text style={styles.transcript}>“{transcript}”</Text>
        </Panel>
      ) : null}

      {/* --------------------------------------------------- the proposals */}
      {drafts.map((d, i) => (
        <Animated.View
          key={`${d.exercise_phrase}-${i}`}
          entering={FadeInDown.duration(motion.base).delay(i * 40)}
        >
          <Panel padded={false} style={styles.draft}>
            <View style={styles.draftHead}>
              <View style={styles.draftHeadL}>
                <Text style={styles.draftName}>
                  {d.exercise_name ?? d.exercise_phrase}
                </Text>
                {d.exercise_name && d.match_score < SHAKY_MATCH ? (
                  <Text style={styles.shaky}>
                    heard “{d.exercise_phrase}” — check this is right
                  </Text>
                ) : null}
              </View>
              {d.saved ? (
                <Text style={[styles.savedTag, { color: accent.brand }]}>SAVED</Text>
              ) : null}
            </View>

            <Rule />

            {/* No match: make the user choose. Guessing here is exactly the
                failure mode the review screen exists to prevent. */}
            {!d.chosenId ? (
              <View style={styles.pick}>
                <Label>Which exercise?</Label>
                {d.alternatives.map((alt) => (
                  <Pressable
                    key={alt.id}
                    onPress={() => {
                      Haptics.selectionAsync();
                      update(i, { chosenId: alt.id, exercise_name: alt.name });
                    }}
                    style={[styles.altRow, { borderColor: surfaces.hairline }]}
                  >
                    <Text style={styles.altText}>{alt.name}</Text>
                  </Pressable>
                ))}
                {d.alternatives.length === 0 ? (
                  <Text style={styles.hint}>
                    No close match. Find it in the Trainer tab and log it there.
                  </Text>
                ) : null}
              </View>
            ) : (
              <>
                <View style={styles.fields}>
                  <View style={styles.field}>
                    <Label>Sets</Label>
                    <Stepper
                      value={d.sets}
                      onChange={(v) => update(i, { sets: v })}
                      min={1}
                      max={20}
                    />
                  </View>
                  <View style={styles.field}>
                    <Label>Kg</Label>
                    <Stepper
                      value={d.weight_kg ?? 0}
                      onChange={(v) => update(i, { weight_kg: v })}
                      min={0}
                      max={500}
                      step={2.5}
                      format={(v) => `${v % 1 === 0 ? v : v.toFixed(1)}`}
                    />
                  </View>
                  <View style={styles.field}>
                    <Label>Reps</Label>
                    <Stepper
                      value={d.reps}
                      onChange={(v) => update(i, { reps: v })}
                      min={1}
                      max={100}
                    />
                  </View>
                </View>

                {d.reps_low !== d.reps_high ? (
                  <Text style={styles.rangeNote}>
                    You said {d.reps_low}–{d.reps_high} reps. Set the number you
                    actually hit.
                  </Text>
                ) : null}

                {d.warnings.map((w) => (
                  <Text key={w} style={styles.warning}>
                    {w}
                  </Text>
                ))}

                <View style={styles.confirm}>
                  <Button
                    label={d.saved ? 'Saved' : `Save ${d.sets} set${d.sets === 1 ? '' : 's'}`}
                    onPress={() => saveEntry(i)}
                    disabled={d.saved}
                    variant={d.saved ? 'outline' : 'primary'}
                  />
                </View>
              </>
            )}
          </Panel>
        </Animated.View>
      ))}

      {drafts.some((d) => d.saved) ? (
        <Button
          label="Done"
          variant="outline"
          onPress={() => router.replace('/(tabs)/train')}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: space.lg, gap: space.md },
  head: { flexDirection: 'row' },
  back: { ...type.caption, color: palette.textDim },

  title: { ...type.title, color: palette.text },
  hint: { ...type.caption, color: palette.textFaint, lineHeight: 19 },

  micWrap: { alignItems: 'center', gap: space.md, paddingVertical: space.xl },
  micPulse: { position: 'absolute', top: space.xl, width: 96, height: 96, borderRadius: 48 },
  mic: {
    width: 88,
    height: 88,
    borderRadius: 44,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  micLabel: { ...type.label, color: palette.textFaint },

  transcript: { ...type.body, color: palette.textDim, fontStyle: 'italic' },

  draft: { marginTop: space.xs },
  draftHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: space.lg,
    gap: space.sm,
  },
  draftHeadL: { flex: 1, gap: 2 },
  draftName: { ...type.heading, color: palette.text },
  shaky: { ...type.labelSm, color: palette.warn, textTransform: 'none', letterSpacing: 0 },
  savedTag: { ...type.labelSm },

  fields: { flexDirection: 'row', gap: space.md, padding: space.lg },
  field: { flex: 1, gap: space.sm },
  rangeNote: {
    ...type.caption,
    color: palette.textFaint,
    paddingHorizontal: space.lg,
  },
  warning: {
    ...type.caption,
    color: palette.warn,
    paddingHorizontal: space.lg,
    paddingTop: space.xs,
  },
  confirm: { padding: space.lg },

  pick: { padding: space.lg, gap: space.sm },
  altRow: {
    borderWidth: 1,
    borderRadius: radius.md,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
  },
  altText: { ...type.body, color: palette.text },

  error: { ...type.caption, color: palette.danger, textAlign: 'center' },
});
