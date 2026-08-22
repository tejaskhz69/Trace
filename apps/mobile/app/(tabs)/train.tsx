/**
 * Tab 3 · Trainer — ported from the design artifact.
 *
 * Two modes behind one segmented control:
 *
 *   GYM         search + the exercise catalogue, grouped by muscle, each row
 *               carrying the user's own working weight and weekly trend
 *   ACTIVITIES  the full sport catalogue, session logging, and whatever
 *               Strava and the watch sent -- see components/activities.tsx
 *
 * WHY THE SEARCH BAR IS THE FIRST THING
 * There are 736 exercises. Scrolling to find "Incline Dumbbell Press" every
 * time you want to log a set is the difference between an app you use mid-
 * workout and one you don't. Search is the primary control here, not a
 * convenience.
 *
 * WHY ONE REQUEST FEEDS THE WHOLE LIST
 * `/api/workouts/catalogue` returns groups, counts, working weights and
 * deltas together. Fetching per-row history would be 737 round trips at
 * ~130 ms each against a database in another region — a minute and a half of
 * loading for one screen.
 *
 * ILLUSTRATIONS
 * Each row shows an equipment glyph rather than a drawing of the movement.
 * That is a deliberate tier-one choice, not a placeholder: 736 hand-drawn
 * SVGs is not feasible, photographs would wreck the line-art language, and
 * "cable vs barbell vs machine" is genuinely what a beginner scanning the
 * list needs in order to find the thing standing in front of them.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn } from 'react-native-reanimated';

import {
  Button,
  Delta,
  GroupHeader,
  Label,
  Panel,
  Plain,
  SearchField,
  Segmented,
  Skeleton,
} from '../../src/components/instrument';
import { ActivitiesPanel } from '../../src/components/activities';
import { MuscleBars, MuscleMap } from '../../src/components/muscle-map';
import { IconSearch, equipmentIcon } from '../../src/components/icons';
import { api, type CatalogueGroup, type VolumeReport } from '../../src/lib/api';
import { useAuth } from '../../src/state/useAuth';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

const MODES = [
  { value: 'gym' as const, label: 'Gym' },
  { value: 'activities' as const, label: 'Activities' },
];

function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim();
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return (parts[0]?.[0] ?? '?').concat(parts[1]?.[0] ?? '').toUpperCase();
}

export default function TrainerScreen() {
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  const accent = useAccent();
  const user = useAuth((s) => s.user);

  const [mode, setMode] = useState<'gym' | 'activities'>('gym');
  const [query, setQuery] = useState('');
  const [groups, setGroups] = useState<CatalogueGroup[] | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const router = useRouter();

  /**
   * Start a session, or hand back the one already open.
   *
   * Resuming rather than always starting fresh is what stops a forgotten
   * Finish from splitting one workout into four sessions -- which would make
   * every per-session summary wrong and the volume chart lumpy.
   */
  const startWorkout = useCallback(async () => {
    if (starting) return;
    setStarting(true);
    try {
      const id = activeSessionId ?? (await api.startSession('Workout')).id;
      setActiveSessionId(id);
      // No exercise chosen yet: the catalogue below IS the picker, so drop
      // the user back onto it with the session now live.
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start a workout.');
    } finally {
      setStarting(false);
    }
  }, [activeSessionId, starting]);

  const load = useCallback(async (q: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.exerciseCatalogue(q.trim() || undefined);
      setGroups(res.groups);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load exercises.');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      load('');
      // A session left open is the resume banner. Failing quietly is right
      // here: no banner is a fine degradation, a crashed tab is not.
      api
        .workoutHistory(5)
        .then((r) => setActiveSessionId(r.active_session_id))
        .catch(() => undefined);
    });
    return () => task.cancel();
  }, [load]);

  // Debounce: typing "incline" would otherwise fire six requests, and the
  // slowest one could land last and overwrite the right answer.
  useEffect(() => {
    const t = setTimeout(() => load(query), 280);
    return () => clearTimeout(t);
  }, [query, load]);

  const trained = useMemo(
    () =>
      (groups ?? []).reduce(
        (n, g) => n + g.exercises.filter((e) => e.working_weight_kg !== null).length,
        0,
      ),
    [groups],
  );

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.bar, { paddingTop: insets.top + space.sm }]}>
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>TRAINER</Text>
        </View>
        <View style={styles.barR}>
          <Text style={styles.stamp}>
            {mode === 'gym' ? `${total} EXERCISES` : 'THIS WEEK'}
          </Text>
          <View style={[styles.avatar, { borderColor: surfaces.hairlineBright }]}>
            <Text style={styles.avatarText}>
              {initials(user?.display_name ?? null, user?.email ?? '')}
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.modeWrap}>
        <Segmented options={MODES} value={mode} onChange={setMode} />
      </View>

      {mode === 'gym' ? (
        <>
          <View style={styles.searchWrap}>
            <SearchField
              value={query}
              onChangeText={setQuery}
              placeholder="Search exercises or a muscle"
              leading={<IconSearch size={17} color={palette.textFaint} />}
            />
          </View>

          <ScrollView
            contentContainerStyle={[
              styles.body,
              { paddingBottom: insets.bottom + space.xxl },
            ]}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            {/* The session controls sit above the catalogue, but only when
                the user is not searching -- someone typing "incline" is
                hunting for a row, and pushing it below a body map is exactly
                the friction the search bar exists to remove. */}
            {query.trim() === '' ? (
              <>
                <SessionBanner
                  activeId={activeSessionId}
                  onStart={startWorkout}
                  starting={starting}
                />
                <VolumePanel />
              </>
            ) : null}

            {groups === null ? (
              <View style={styles.gap}>
                <Skeleton height={44} />
                <Skeleton height={72} />
                <Skeleton height={72} />
                <Skeleton height={72} />
              </View>
            ) : error ? (
              <Plain tone="danger">{error}</Plain>
            ) : groups.length === 0 ? (
              <Plain tone="warn">
                Nothing matches &ldquo;{query}&rdquo;. Try a muscle name like
                &ldquo;chest&rdquo;, or the equipment you&apos;re standing at.
              </Plain>
            ) : (
              <>
                {busy ? (
                  <View style={styles.busyRow}>
                    <ActivityIndicator size="small" color={palette.textFaint} />
                  </View>
                ) : null}
                {groups.map((g) => (
                  <View key={g.muscle_group} style={styles.group}>
                    <GroupHeader
                      label={g.muscle_group.toUpperCase()}
                      count={g.count}
                    />
                    <View style={styles.rows}>
                      {g.exercises.map((e) => (
                        <ExerciseRow key={e.id} ex={e} sessionId={activeSessionId} />
                      ))}
                    </View>
                  </View>
                ))}

                {trained === 0 ? (
                  <Plain style={styles.gapT}>
                    Nothing logged yet, so no working weights to show. Log a set
                    and each exercise starts carrying{' '}
                    <Text style={styles.b}>your</Text> numbers and a weekly
                    trend.
                  </Plain>
                ) : null}
              </>
            )}
          </ScrollView>
        </>
      ) : (
        /* THE ACTIVITIES TAB, which used to be nine chips that set a local
           variable and did nothing at all. It now owns its own data and its
           own logging, so it lives in its own component rather than as a
           second body inside this screen's render. */
        <ActivitiesPanel bottomInset={insets.bottom} />
      )}
    </View>
  );
}

/**
 * Start, or resume, a workout.
 *
 * Resuming is offered because people forget to hit Finish, and a forgotten
 * session that keeps absorbing sets is worse than no session at all — it
 * makes every per-session number wrong.
 */
function SessionBanner({
  activeId,
  onStart,
  starting,
}: {
  activeId: string | null;
  onStart: () => void;
  starting: boolean;
}) {
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  return (
    <View style={[styles.banner, { borderColor: surfaces.hairlineBright }]}>
      <View style={styles.bannerL}>
        <Label>{activeId ? 'In progress' : 'Ready'}</Label>
        <Text style={styles.bannerTitle}>
          {activeId ? 'Resume workout' : 'Start a workout'}
        </Text>
        <Text style={styles.bannerSub}>
          {activeId
            ? 'Pick a lift below to log the next set.'
            : 'Then pick a lift below. Every set gets a verdict.'}
        </Text>
      </View>
      <View style={styles.bannerR}>
        {activeId ? (
          <Button
            label="Finish"
            variant="outline"
            compact
            onPress={() => router.push(`/workout/summary?session=${activeId}`)}
          />
        ) : (
          <Button
            label={starting ? '…' : 'Start'}
            compact
            loading={starting}
            onPress={onStart}
          />
        )}
        <Pressable onPress={() => router.push('/workout/history')} hitSlop={10}>
          <Text style={[styles.bannerLink, { color: accent.brand }]}>HISTORY</Text>
        </Pressable>
      </View>
    </View>
  );
}

/**
 * Muscles trained, and whether that was enough of them.
 *
 * The set count is the easy half. The half that matters is the verdict
 * underneath: most people under-train their back and over-train their arms
 * and have no idea, because a tally never made the imbalance visible.
 */
function VolumePanel() {
  const [days, setDays] = useState<'7' | '30'>('7');
  const [report, setReport] = useState<VolumeReport | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setReport(null);
    setFailed(false);
    api
      .muscleVolume(days === '7' ? 7 : 30)
      .then((r) => alive && setReport(r))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [days]);

  if (failed) return null;

  return (
    <Panel
      label="Muscles trained"
      right={
        <View style={styles.volToggle}>
          <Segmented
            options={[
              { value: '7' as const, label: '7 days' },
              { value: '30' as const, label: '30 days' },
            ]}
            value={days}
            onChange={setDays}
          />
        </View>
      }
    >
      {report === null ? (
        <Skeleton height={180} />
      ) : (
        <>
          <MuscleMap muscles={report.muscles} />
          <MuscleBars muscles={report.muscles} />
          {report.weakest ? (
            <Plain style={styles.gapT}>
              {report.muscles.find((m) => m.muscle === report.weakest)?.note}
            </Plain>
          ) : null}
        </>
      )}
    </Panel>
  );
}

/**
 * One exercise. Name and equipment on the left, the user's own numbers right.
 *
 * memo'd on primitives: this list renders several hundred rows and every one
 * of them re-rendering on a keystroke is exactly the jank the performance
 * rules exist to prevent.
 */
const ExerciseRow = React.memo(
  function ExerciseRowBase({
    ex,
    sessionId,
  }: {
    ex: CatalogueGroup['exercises'][number];
    sessionId: string | null;
  }) {
    const Icon = equipmentIcon(ex.equipment);
    const router = useRouter();

    // WITH a workout open, tapping a lift means "log a set on this" -- the
    // person is standing at the machine. WITHOUT one, it means "tell me about
    // this" and the detail screen is the right answer. Same row, and the
    // correct destination is entirely determined by whether a session is live.
    const open = () =>
      sessionId
        ? router.push({
            pathname: '/workout/[session]',
            params: { session: sessionId, exercise: ex.id },
          })
        : router.push({
            pathname: '/exercise/[id]',
            params: {
              id: ex.id,
              name: ex.name,
              equipment: ex.equipment,
              muscle: ex.muscle_group,
              secondary: ex.secondary_muscles.join(','),
              compound: ex.is_compound ? '1' : '0',
            },
          });

    return (
      <Animated.View entering={FadeIn.duration(motion.fast)}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={ex.name}
          onPress={open}
          style={styles.row}
        >
          <View style={styles.thumb}>
            <Icon size={22} color={palette.textDim} />
          </View>

          <View style={styles.rowMid}>
            <Text style={styles.rowName} numberOfLines={1}>
              {ex.name}
            </Text>
            <Text style={styles.rowMeta} numberOfLines={1}>
              {ex.equipment.replace(/_/g, ' ').toUpperCase()} ·{' '}
              {ex.is_compound ? 'COMPOUND' : 'ISOLATION'}
            </Text>
          </View>

          <View style={styles.rowRight}>
            {ex.working_weight_kg !== null ? (
              <Text style={styles.rowWeight}>
                {ex.working_weight_kg}
                <Text style={styles.rowUnit}> kg</Text>
              </Text>
            ) : (
              <Text style={styles.rowNever}>—</Text>
            )}
            <Delta pct={ex.delta_pct} />
          </View>
        </Pressable>
      </Animated.View>
    );
  },
  (a, b) =>
    a.ex.id === b.ex.id &&
    a.ex.working_weight_kg === b.ex.working_weight_kg &&
    a.ex.delta_pct === b.ex.delta_pct &&
    // Without this the rows keep the route they mounted with, and starting a
    // workout would leave every row still pointing at the detail screen.
    a.sessionId === b.sessionId,
);

const styles = StyleSheet.create({
  screen: { flex: 1 },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.md,
  },
  bannerL: { flex: 1, gap: 3 },
  bannerTitle: { ...type.heading, color: palette.text },
  bannerSub: { ...type.labelSm, color: palette.textFaint, textTransform: 'none', letterSpacing: 0 },
  bannerR: { alignItems: 'flex-end', gap: space.sm },
  bannerLink: { ...type.labelSm },
  volToggle: { minWidth: 150 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingBottom: space.sm,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
  brandText: { ...type.label, fontSize: 11, letterSpacing: 2, color: palette.text },
  barR: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  stamp: { ...type.labelSm, color: palette.textDim, letterSpacing: 1 },
  avatar: {
    width: 30, height: 30, borderRadius: 15,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: palette.raised,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { ...type.labelSm, fontSize: 10.5, color: palette.textDim },

  modeWrap: { paddingHorizontal: space.lg, paddingBottom: space.md },
  searchWrap: { paddingHorizontal: space.lg, paddingBottom: space.md },
  body: { paddingHorizontal: space.lg, gap: space.md },
  gap: { gap: space.sm },
  gapT: { marginTop: space.md },
  busyRow: { paddingVertical: space.sm, alignItems: 'center' },

  group: { gap: space.xs },
  rows: { gap: 1 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
  },
  thumb: {
    width: 44, height: 44, borderRadius: radius.sm,
    backgroundColor: palette.raised,
    alignItems: 'center', justifyContent: 'center',
  },
  rowMid: { flex: 1, gap: 2 },
  rowName: { ...type.heading, color: palette.text },
  rowMeta: { ...type.labelSm, color: palette.textFaint },
  rowRight: { alignItems: 'flex-end', gap: 3 },
  rowWeight: { ...type.valueSm, fontSize: 17, color: palette.text },
  rowUnit: { ...type.labelSm, color: palette.textDim },
  rowNever: { ...type.valueSm, fontSize: 17, color: palette.textGhost },

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.hairlineBright,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  chipText: { ...type.body, fontSize: 13.5, color: palette.textDim },

  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
