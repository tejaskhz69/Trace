/**
 * The ACTIVITIES half of the Trainer tab.
 *
 * WHAT WAS WRONG WITH THE OLD ONE
 * Nine chips that set a local `sport` variable, and nothing else. Tapping one
 * highlighted it and had no effect anywhere — no duration, no save, no list.
 * That is how it was reported: "there are very few activities and when I try
 * to click on it, nothing happens." Both halves of that were true.
 *
 * WHAT THIS IS
 * The artifact's screen, built for real:
 *
 *   WHAT DID YOU DO?   the full catalogue, grouped, searchable, 40 sports
 *   DURATION           a stepper, because a keyboard for "45" is absurd
 *   INTENSITY          one tap, and the biggest accuracy lever we have
 *   EST. BURN          a RANGE, live, recomputed as the inputs change
 *   LOG ACTIVITY       the thing the old screen was missing entirely
 *   ARRIVED ON THEIR OWN  everything the watch and Strava sent
 *
 * THE BURN NUMBER IS CONTEXT, NOT AN ALLOWANCE (non-negotiable #1). The
 * server sends `where_this_goes` — three rows ending in "Today's calorie
 * target: Unchanged" — and this screen renders that verbatim after a save
 * rather than paraphrasing it. The one thing a user must not conclude from
 * seeing "380 kcal" is that they have earned 380 kcal.
 *
 * THE RANGE IS NOT A HEDGE (non-negotiable #2). MET tables are population
 * averages and two people playing the same 45 minutes of badminton differ by
 * a lot, so ±25% is the honest width. Same rule as the photo scanner.
 */

import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  Button,
  Choice,
  GroupHeader,
  Label,
  Panel,
  Plain,
  Rule,
  SearchField,
  Skeleton,
  Stepper,
} from './instrument';
import { IconSearch, sportIcon } from './icons';
import {
  api,
  type Activity,
  type ActivityLogged,
  type Sport,
} from '../lib/api';
import { useAccent } from '../state/useTheme';
import { motion, palette, radius, space, type } from '../theme';

const INTENSITIES = [
  { value: 'easy' as const, label: 'Easy' },
  { value: 'moderate' as const, label: 'Moderate' },
  { value: 'hard' as const, label: 'Hard' },
];

type Intensity = 'easy' | 'moderate' | 'hard';

/** A local MET estimate, so the burn readout moves the instant a dial does.
 *
 *  WHY THE CLIENT DUPLICATES THE FORMULA
 *  A round trip per stepper tap would make the number lag the control by a
 *  few hundred milliseconds, which reads as broken. The SERVER's number is
 *  still the one that gets saved — this is a preview, and it uses the same
 *  MET the server sent down in the catalogue, so the two agree. */
function previewBurn(
  met: number,
  minutes: number,
  weightKg: number,
  intensity: Intensity,
): { point: number; band: number } {
  const factor = intensity === 'easy' ? 0.78 : intensity === 'hard' ? 1.28 : 1;
  const point = met * factor * (3.5 / 200) * weightKg * minutes;
  return { point: Math.round(point), band: Math.round(point * 0.25) };
}

export function ActivitiesPanel({ bottomInset }: { bottomInset: number }) {
  const accent = useAccent();

  const [catalogue, setCatalogue] = useState<Sport[] | null>(null);
  /** Body mass for the local preview. Null widens the band and says so. */
  const [weightKg, setWeightKg] = useState<number | null>(null);
  const [recent, setRecent] = useState<Activity[] | null>(null);
  const [query, setQuery] = useState('');

  const [sport, setSport] = useState<Sport | null>(null);
  const [minutes, setMinutes] = useState(45);
  const [intensity, setIntensity] = useState<Intensity>('moderate');

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<ActivityLogged | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Both fetches wait for the tab transition to finish.
   *
   * This panel mounts the instant the segmented control flips, and firing two
   * requests plus parsing a hundred-sport catalogue while the transition is
   * still animating drops frames on exactly the interaction the user is
   * looking at. `runAfterInteractions` is the house rule for this and it
   * applies here as much as to a screen -- the skeleton renders immediately
   * either way, so nothing is lost by waiting.
   */
  useEffect(() => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .sports()
        .then((res) => {
          if (!alive) return;
          setCatalogue(res.sports);
          setWeightKg(res.weight_kg);
        })
        .catch(() => alive && setCatalogue([]));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  /**
   * Returns its own cancel, so a screen the user swiped away from cannot
   * setState after unmount. React logs that as a warning rather than a crash,
   * which is exactly why it survives in shipped code.
   */
  const loadRecent = useCallback(() => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .activities(14)
        .then((r) => alive && setRecent(r))
        .catch(() => alive && setRecent([]));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  useEffect(loadRecent, [loadRecent]);

  /** Filter, then group in catalogue order so the groups keep their ranking. */
  const groups = useMemo(() => {
    if (!catalogue) return [];
    const q = query.trim().toLowerCase();
    const matched = q
      ? catalogue.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.group.toLowerCase().includes(q) ||
            s.key.replace(/_/g, ' ').includes(q),
        )
      : catalogue;

    const out: { group: string; sports: Sport[] }[] = [];
    for (const s of matched) {
      const last = out[out.length - 1];
      if (last && last.group === s.group) last.sports.push(s);
      else out.push({ group: s.group, sports: [s] });
    }
    return out;
  }, [catalogue, query]);

  const preview = useMemo(
    () =>
      sport
        ? previewBurn(sport.met, minutes, weightKg ?? 70, intensity)
        : null,
    [sport, minutes, weightKg, intensity],
  );

  const pick = useCallback((s: Sport) => {
    Haptics.selectionAsync();
    setSaved(null);
    setError(null);
    setSport((cur) => (cur?.key === s.key ? null : s));
  }, []);

  async function save() {
    if (!sport || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.logActivity({
        sport: sport.key,
        duration_minutes: minutes,
        intensity,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setSaved(res);
      setSport(null);
      loadRecent();
    } catch {
      setError("Couldn't save that session. Check your connection and retry.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={[
        styles.body,
        { paddingBottom: bottomInset + space.xxl },
      ]}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      {/* ---------------------------------------------- confirmation ----- */}
      {saved ? (
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel
            label="Logged"
            right={<Label color={accent.brand}>{saved.activity.name}</Label>}
          >
            <View style={styles.burnRow}>
              <Text style={[styles.burnBig, { color: palette.text }]}>
                {saved.activity.burn?.point ?? '—'}
                <Text style={styles.burnUnit}> kcal</Text>
              </Text>
              {saved.activity.burn ? (
                <Text style={styles.burnBand}>
                  ±{saved.activity.burn.band}
                </Text>
              ) : null}
            </View>

            <Rule style={styles.gapV} />

            {/* Rendered from the server's own words. This is the
                anti-double-counting explainer and it must not drift. */}
            {saved.where_this_goes.map(([k, v]) => (
              <View key={k} style={styles.goesRow}>
                <Text style={styles.goesK}>{k}</Text>
                <Text
                  style={[
                    styles.goesV,
                    {
                      color:
                        v === 'Unchanged' ? palette.textDim : accent.brand,
                    },
                  ]}
                >
                  {v.toUpperCase()}
                </Text>
              </View>
            ))}

            <Plain style={styles.gapV}>{saved.target_explainer}</Plain>
          </Panel>
        </Animated.View>
      ) : null}

      {/* ---------------------------------------------- the catalogue ---- */}
      <Panel
        label="What did you do?"
        right={
          <Label color={palette.textFaint}>
            {catalogue ? `${catalogue.length} sports` : '…'}
          </Label>
        }
      >
        <SearchField
          value={query}
          onChangeText={setQuery}
          placeholder="Search a sport"
          leading={<IconSearch size={17} color={palette.textFaint} />}
        />

        {catalogue === null ? (
          <View style={styles.gapV}>
            <Skeleton height={38} />
            <Skeleton height={38} />
          </View>
        ) : groups.length === 0 ? (
          <Plain tone="warn" style={styles.gapV}>
            Nothing matches &ldquo;{query}&rdquo;. Try &ldquo;racket&rdquo;,
            &ldquo;team&rdquo;, or log it as{' '}
            <Text style={styles.b}>Something else</Text>.
          </Plain>
        ) : (
          groups.map((g) => (
            <View key={g.group} style={styles.group}>
              <GroupHeader
                label={g.group.toUpperCase()}
                count={g.sports.length}
                unit="sports"
              />
              <View style={styles.chips}>
                {g.sports.map((s) => (
                  <SportChip
                    key={s.key}
                    sport={s}
                    selected={sport?.key === s.key}
                    onPress={pick}
                    accent={accent.brand}
                    accentSoft={accent.brandSoft}
                  />
                ))}
              </View>
            </View>
          ))
        )}
      </Panel>

      {/* ---------------------------------------------- the session ------ */}
      {sport ? (
        <Animated.View entering={FadeInDown.duration(motion.base)}>
          <Panel
            label={sport.name}
            right={<Label color={palette.textFaint}>{sport.group}</Label>}
          >
            <Label color={palette.textFaint}>Duration</Label>
            <Stepper
              value={minutes}
              onChange={setMinutes}
              min={5}
              max={300}
              step={5}
              unit="min"
            />

            <Rule style={styles.gapV} />

            <Label color={palette.textFaint}>How hard?</Label>
            <Choice
              options={INTENSITIES}
              value={intensity}
              onChange={setIntensity}
            />

            <Rule style={styles.gapV} />

            {/* THE RANGE, never a bare number. */}
            <View style={styles.burnRow}>
              <View>
                <Label color={palette.textFaint}>Estimated burn</Label>
                <Text style={styles.burnBig}>
                  {preview?.point ?? 0}
                  <Text style={styles.burnUnit}> kcal</Text>
                </Text>
              </View>
              <Text style={styles.burnBand}>±{preview?.band ?? 0}</Text>
            </View>

            <Plain style={styles.gapV}>
              {weightKg === null
                ? 'Estimated from a typical body weight, because yours isn’t on file yet — so this range is wider than it needs to be. Log a weigh-in and it narrows.'
                : sport.estimated
                  ? `A rougher estimate than most: ${sport.name.toLowerCase()} isn’t in the reference tables, so its intensity is interpolated from comparable sports.`
                  : 'A population average applied to one person, which is why it’s a range. It explains your burn — it does not add calories to eat.'}
            </Plain>

            {error ? <Plain tone="danger">{error}</Plain> : null}

            <Button
              label={saving ? 'Saving…' : 'Log activity'}
              onPress={save}
              loading={saving}
              style={styles.gapV}
            />
          </Panel>
        </Animated.View>
      ) : null}

      {/* ---------------------------------------------- what arrived ----- */}
      <Panel
        label="Arrived on their own"
        right={
          <Label color={palette.textFaint}>
            {recent === null
              ? '…'
              : recent.length === 0
                ? 'None yet'
                : `${recent.length} in 14 days`}
          </Label>
        }
        padded={recent !== null && recent.length > 0 ? false : undefined}
      >
        {recent === null ? (
          <Skeleton height={72} />
        ) : recent.length === 0 ? (
          <Plain>
            Sessions from Strava, Garmin and your watch land here automatically
            once you connect a source in Profile. Anything you log above shows
            up here too. Whatever they say,{' '}
            <Text style={styles.b}>
              none of it is added to your calorie target
            </Text>{' '}
            — it explains your burn, it doesn&apos;t inflate it.
          </Plain>
        ) : (
          recent.map((a, i) => (
            <ActivityRow key={a.id} activity={a} first={i === 0} />
          ))
        )}
      </Panel>
    </ScrollView>
  );
}

/**
 * One sport. memo'd on primitives because forty of these re-rendering on
 * every keystroke in the search box is exactly the jank the performance rules
 * exist to prevent.
 */
const SportChip = memo(
  function SportChipBase({
    sport,
    selected,
    onPress,
    accent,
    accentSoft,
  }: {
    sport: Sport;
    selected: boolean;
    onPress: (s: Sport) => void;
    accent: string;
    accentSoft: string;
  }) {
    const Icon = sportIcon(sport.key);
    return (
      <Pressable
        accessibilityRole="radio"
        accessibilityState={{ selected }}
        accessibilityLabel={sport.name}
        onPress={() => onPress(sport)}
        style={[
          styles.chip,
          selected && { borderColor: accent, backgroundColor: accentSoft },
        ]}
      >
        <Icon size={15} color={selected ? accent : palette.textFaint} />
        <Text style={[styles.chipText, selected && { color: accent }]}>
          {sport.name}
        </Text>
      </Pressable>
    );
  },
  (a, b) => a.sport.key === b.sport.key && a.selected === b.selected,
);

/** A logged or imported session. */
const ActivityRow = memo(
  function ActivityRowBase({
    activity,
    first,
  }: {
    activity: Activity;
    first: boolean;
  }) {
    const Icon = sportIcon(activity.sport);
    const when = new Date(activity.started_at);
    const day = when.toLocaleDateString(undefined, { weekday: 'short' });
    const mins = Math.round(activity.duration_minutes);
    const detail = [
      day,
      mins >= 60
        ? `${Math.floor(mins / 60)} h ${String(mins % 60).padStart(2, '0')}`
        : `${mins} min`,
      activity.distance_km ? `${activity.distance_km.toFixed(1)} km` : null,
    ]
      .filter(Boolean)
      .join(' · ');

    return (
      <Animated.View entering={FadeIn.duration(motion.fast)}>
        {first ? null : <Rule />}
        <View style={styles.actRow}>
          <View style={styles.actIcon}>
            <Icon size={18} color={palette.textDim} />
          </View>
          <View style={styles.actMid}>
            <Text style={styles.actName} numberOfLines={1}>
              {activity.name}
            </Text>
            <Text style={styles.actMeta} numberOfLines={1}>
              {detail}
            </Text>
          </View>
          <View style={styles.actRight}>
            {activity.burn ? (
              <>
                <Text style={styles.actKcal}>
                  {activity.burn.point}
                  <Text style={styles.actUnit}> kcal</Text>
                </Text>
                {/* A measured number and an estimated one must never look
                    equally certain. The band is the tell. */}
                <Text style={styles.actBand}>
                  {activity.burn.measured
                    ? 'MEASURED'
                    : `±${activity.burn.band}`}
                </Text>
              </>
            ) : (
              <Text style={styles.actKcal}>—</Text>
            )}
          </View>
        </View>
      </Animated.View>
    );
  },
  (a, b) => a.activity.id === b.activity.id && a.first === b.first,
);

const styles = StyleSheet.create({
  body: { paddingHorizontal: space.lg, gap: space.md },
  gapV: { marginTop: space.md },
  group: { marginTop: space.md, gap: space.xs },

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.hairlineBright,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  chipText: { ...type.body, fontSize: 13.5, color: palette.textDim },

  burnRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    marginTop: space.xs,
  },
  burnBig: { ...type.figure, color: palette.text },
  burnUnit: { ...type.labelSm, color: palette.textDim },
  burnBand: { ...type.valueSm, color: palette.textFaint },

  goesRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: space.sm,
  },
  goesK: { ...type.body, fontSize: 13.5, color: palette.textDim },
  goesV: { ...type.labelSm },

  actRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  actIcon: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: palette.raised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actMid: { flex: 1, gap: 2 },
  actName: { ...type.heading, color: palette.text },
  actMeta: { ...type.labelSm, color: palette.textFaint },
  actRight: { alignItems: 'flex-end', gap: 2 },
  actKcal: { ...type.valueSm, fontSize: 17, color: palette.text },
  actUnit: { ...type.labelSm, color: palette.textDim },
  actBand: { ...type.labelSm, color: palette.textFaint },

  b: { fontFamily: type.heading.fontFamily, color: palette.text },
});
