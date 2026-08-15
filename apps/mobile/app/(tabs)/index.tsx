/**
 * HOME — instrument panel.
 *
 * Screen order is exactly as specified:
 *   1. CALORIES REMAINING  — the hero, correct at any hour of the day
 *   2. ACTIVITY TODAY      — what you've actually done
 *   3. COACH               — the one comment
 *
 * The calorie block leads with what's LEFT, not what's eaten, because that's
 * the number a user is actually asking for when they open the app at 3pm.
 * "2,847 eaten" requires mental arithmetic; "53 left" is the answer.
 *
 * Performance rules carried over unchanged: skeleton paints first, fetch
 * after InteractionManager, every animation on a shared value, nothing
 * animated via setState.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  InteractionManager,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import {
  Button,
  Gauge,
  Label,
  Panel,
  Readout,
  Rule,
  Skeleton,
  Sparkbar,
  StatCell,
} from '../../src/components/instrument';
import { useAuth } from '../../src/state/useAuth';
import { useToday } from '../../src/state/useToday';
import { useCoach } from '../../src/state/useCoach';
import {
  HAIRLINE,
  leverStyle,
  palette,
  radius,
  space,
  type,
} from '../../src/theme';

function clock(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export default function HomeScreen() {
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const { summary, loading, refreshing, load, refresh } = useToday();
  const { briefing, load: loadCoach } = useCoach();
  const [now, setNow] = useState(clock());

  useEffect(() => {
    const task = InteractionManager.runAfterInteractions(() => {
      load();
      loadCoach();
    });
    // The header clock is the only thing on this screen driven by an
    // interval, and it updates once a minute -- not once a second.
    const id = setInterval(() => setNow(clock()), 60_000);
    return () => {
      task.cancel();
      clearInterval(id);
    };
  }, [load, loadCoach]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const eaten = summary?.calories ?? 0;
  const target = summary?.calorie_target ?? null;
  const remaining = target != null ? Math.round(target - eaten) : null;
  const over = remaining != null && remaining < 0;
  const fraction = target && target > 0 ? eaten / target : 0;

  const activity = briefing?.activity_today ?? null;
  const stepHistory = useMemo(
    () => briefing?.step_history ?? [],
    [briefing?.step_history],
  );

  const showSkeleton = loading && !summary;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              refresh();
              loadCoach({ force: true });
            }}
            tintColor={palette.textFaint}
          />
        }
        removeClippedSubviews
        scrollEventThrottle={16}
      >
        {/* ---- Masthead ---------------------------------------------- */}
        <View style={styles.masthead}>
          <View>
            <Label color={palette.textGhost}>TRACE</Label>
            <Text style={styles.mastheadName}>
              {user?.display_name || user?.email?.split('@')[0] || 'Athlete'}
            </Text>
          </View>
          <View style={styles.mastheadRight}>
            <Text style={styles.clock}>{now}</Text>
            <Label color={palette.textGhost}>
              {new Date().toLocaleDateString('en-GB', {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
              })}
            </Label>
          </View>
        </View>

        {showSkeleton ? (
          <HomeSkeleton />
        ) : (
          <>
            {/* ============ 1. CALORIES REMAINING ==================== */}
            <Animated.View entering={FadeInDown.duration(240)}>
              <Panel padded={false}>
                <View style={styles.calBody}>
                  <View style={styles.calHeaderRow}>
                    <Label color={over ? palette.warn : palette.signal}>
                      {over ? 'Over budget' : 'Remaining today'}
                    </Label>
                    <Label color={palette.textGhost}>
                      {target ? `Target ${Math.round(target).toLocaleString()}` : 'No target yet'}
                    </Label>
                  </View>

                  <View style={styles.calReadoutRow}>
                    <Readout
                      value={remaining != null ? Math.abs(remaining) : eaten}
                      color={over ? palette.warn : palette.text}
                    />
                    <Text style={styles.calUnit}>kcal</Text>
                  </View>

                  <Text style={styles.calSub}>
                    {remaining == null
                      ? `${Math.round(eaten).toLocaleString()} eaten · log a few days and I'll set your target`
                      : over
                        ? `${Math.round(eaten).toLocaleString()} eaten · ${Math.abs(remaining)} over`
                        : `${Math.round(eaten).toLocaleString()} eaten of ${Math.round(target!).toLocaleString()}`}
                  </Text>

                  <View style={styles.gaugeWrap}>
                    <Gauge fraction={fraction} height={10} />
                  </View>
                </View>

                <Rule />

                {/* Macro strip */}
                <View style={styles.macroStrip}>
                  <MacroCell
                    label="Protein"
                    value={summary?.protein_g ?? 0}
                    target={summary?.protein_target_g ?? null}
                    color={palette.protein}
                  />
                  <Rule vertical />
                  <MacroCell
                    label="Carbs"
                    value={summary?.carbs_g ?? 0}
                    target={null}
                    color={palette.carbs}
                  />
                  <Rule vertical />
                  <MacroCell
                    label="Fat"
                    value={summary?.fat_g ?? 0}
                    target={null}
                    color={palette.fat}
                  />
                </View>

                <Rule />

                {/* Quick log */}
                <View style={styles.actionRow}>
                  <Button
                    label="Scan"
                    onPress={() => router.push('/scan')}
                    compact
                    style={styles.actionBtn}
                  />
                  <Button
                    label="Barcode"
                    variant="outline"
                    compact
                    onPress={() =>
                      router.push({ pathname: '/scan', params: { mode: 'barcode' } })
                    }
                    style={styles.actionBtn}
                  />
                  <Button
                    label="Search"
                    variant="outline"
                    compact
                    onPress={() => router.push('/(tabs)/log')}
                    style={styles.actionBtn}
                  />
                </View>
              </Panel>
            </Animated.View>

            {/* ============ 2. ACTIVITY TODAY ======================== */}
            <Animated.View entering={FadeInDown.duration(240).delay(50)}>
              <Panel
                label="Activity today"
                right={
                  activity?.synced_at ? (
                    <Label color={palette.textGhost}>SYNCED</Label>
                  ) : (
                    <Label color={palette.textGhost}>NO DATA</Label>
                  )
                }
              >
                {activity ? (
                  <View style={{ gap: space.lg }}>
                    <View style={styles.statRow}>
                      <StatCell
                        label="Steps"
                        value={(activity.steps ?? 0).toLocaleString()}
                        delta={
                          activity.steps_vs_baseline != null
                            ? {
                                value: `${activity.steps_vs_baseline >= 0 ? '+' : ''}${activity.steps_vs_baseline}%`,
                                positive: activity.steps_vs_baseline >= 0,
                              }
                            : null
                        }
                      />
                      <Rule vertical />
                      <StatCell
                        label="Active"
                        value={Math.round(activity.active_energy_kcal ?? 0)}
                        unit="kcal"
                        align="center"
                      />
                      <Rule vertical />
                      <StatCell
                        label="Training"
                        value={activity.sessions_today ?? 0}
                        unit={activity.sessions_today === 1 ? 'set' : 'sets'}
                        align="right"
                      />
                    </View>

                    {stepHistory.length > 2 && (
                      <View style={{ gap: space.sm }}>
                        <Sparkbar values={stepHistory} height={30} />
                        <View style={styles.sparkLegend}>
                          <Label color={palette.textGhost}>7 days</Label>
                          <Label color={palette.textGhost}>Today</Label>
                        </View>
                      </View>
                    )}

                    {/* The honesty note — active energy is context, not budget */}
                    <Text style={styles.footnote}>
                      Active energy is shown for context. It is not added to your
                      target — your weight trend already accounts for it.
                    </Text>
                  </View>
                ) : (
                  <View style={{ gap: space.md }}>
                    <Text style={styles.emptyText}>
                      Connect Apple Health to see steps, sleep, and workouts here.
                      It explains changes in your burn — it never changes your
                      calorie target.
                    </Text>
                    <Button
                      label="Connect health"
                      variant="outline"
                      compact
                      onPress={() => router.push('/(tabs)/progress')}
                    />
                  </View>
                )}
              </Panel>
            </Animated.View>

            {/* ============ 3. COACH ================================= */}
            <Animated.View entering={FadeInDown.duration(240).delay(100)}>
              <Panel
                label="Coach"
                right={
                  briefing?.primary ? (
                    <Label color={leverStyle[briefing.primary.lever]?.color ?? palette.textFaint}>
                      {leverStyle[briefing.primary.lever]?.label || ''}
                    </Label>
                  ) : null
                }
                onPress={() => router.push('/(tabs)/progress')}
              >
                {briefing?.primary ? (
                  <View style={{ gap: space.md }}>
                    <Text style={styles.coachHeadline}>
                      {briefing.primary.headline}
                    </Text>
                    <Text style={styles.coachDetail}>{briefing.primary.detail}</Text>

                    {briefing.primary.action ? (
                      <View style={styles.actionCallout}>
                        <View
                          style={[
                            styles.actionBar,
                            {
                              backgroundColor:
                                leverStyle[briefing.primary.lever]?.color ??
                                palette.signal,
                            },
                          ]}
                        />
                        <Text style={styles.actionText}>
                          {briefing.primary.action}
                        </Text>
                      </View>
                    ) : null}

                    {briefing.prompts.length > 0 && (
                      <>
                        <Rule />
                        <Text style={styles.promptText}>
                          {briefing.prompts[0]}
                        </Text>
                      </>
                    )}

                    <View style={styles.coachFooter}>
                      <Label color={palette.textGhost}>
                        {`Confidence ${Math.round(briefing.primary.confidence * 100)}%`}
                      </Label>
                      <Label color={palette.textGhost}>
                        {`Data ${Math.round(briefing.data_completeness * 100)}%`}
                      </Label>
                    </View>
                  </View>
                ) : (
                  <Text style={styles.emptyText}>
                    Keep logging. Once I have about two weeks of food, weight and
                    training, I&apos;ll tell you the one thing worth changing.
                  </Text>
                )}
              </Panel>
            </Animated.View>

            {/* ---- Today's meals, secondary ------------------------- */}
            {summary?.meals?.length ? (
              <Animated.View entering={FadeIn.duration(240).delay(150)}>
                <Panel label={`Logged · ${summary.meals.length}`} padded={false}>
                  {summary.meals.map((m, i) => (
                    <React.Fragment key={String(m.id)}>
                      {i > 0 && <Rule />}
                      <MealRow meal={m} />
                    </React.Fragment>
                  ))}
                </Panel>
              </Animated.View>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function MacroCell({
  label,
  value,
  target,
  color,
}: {
  label: string;
  value: number;
  target: number | null;
  color: string;
}) {
  return (
    <View style={styles.macroCell}>
      <Label color={palette.textFaint}>{label}</Label>
      <View style={styles.macroValueRow}>
        <Text style={[type.valueSm, { color: palette.text }]}>
          {Math.round(value)}
        </Text>
        <Text style={styles.macroUnit}>
          {target ? `/${Math.round(target)}g` : 'g'}
        </Text>
      </View>
      <View style={styles.macroBarTrack}>
        <View
          style={[
            styles.macroBarFill,
            {
              backgroundColor: color,
              width: `${Math.min(100, target ? (value / target) * 100 : Math.min(value / 2, 100))}%`,
            },
          ]}
        />
      </View>
    </View>
  );
}

function MealRow({ meal }: { meal: Record<string, unknown> }) {
  const low = meal.kcal_low as number | null;
  const high = meal.kcal_high as number | null;
  return (
    <View style={styles.mealRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.mealName} numberOfLines={1}>
          {String(meal.display_name ?? 'Meal')}
        </Text>
        <Label color={palette.textGhost}>
          {String(meal.serving_label ?? `${Math.round(Number(meal.grams ?? 0))} g`)}
        </Label>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={[type.valueSm, { color: palette.text }]}>
          {Math.round(Number(meal.calories ?? 0))}
        </Text>
        {low != null && high != null && (
          <Label color={palette.textGhost}>
            ±{Math.round((high - low) / 2)}
          </Label>
        )}
      </View>
    </View>
  );
}

function HomeSkeleton() {
  return (
    <View style={{ gap: space.md }}>
      <Skeleton height={260} />
      <Skeleton height={150} />
      <Skeleton height={170} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.void },
  scroll: {
    padding: space.lg,
    gap: space.md,
    paddingBottom: space.xxxl,
  },

  masthead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: space.xs,
  },
  mastheadName: { ...type.title, color: palette.text, marginTop: 2 },
  mastheadRight: { alignItems: 'flex-end', gap: 2 },
  clock: { ...type.valueSm, color: palette.textDim },

  // --- Calories ---------------------------------------------------------
  calBody: { padding: space.lg, gap: space.sm },
  calHeaderRow: { flexDirection: 'row', justifyContent: 'space-between' },
  calReadoutRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  calUnit: { ...type.heading, color: palette.textFaint },
  calSub: { ...type.caption, color: palette.textDim },
  gaugeWrap: { marginTop: space.sm },

  macroStrip: { flexDirection: 'row' },
  macroCell: { flex: 1, padding: space.md, gap: space.xs },
  macroValueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 2 },
  macroUnit: { ...type.labelSm, color: palette.textFaint },
  macroBarTrack: {
    height: 3,
    backgroundColor: palette.raised,
    borderRadius: 2,
    overflow: 'hidden',
    marginTop: 2,
  },
  macroBarFill: { height: '100%', borderRadius: 2 },

  actionRow: { flexDirection: 'row', gap: space.sm, padding: space.md },
  actionBtn: { flex: 1, paddingHorizontal: 0 },

  // --- Activity ---------------------------------------------------------
  statRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  sparkLegend: { flexDirection: 'row', justifyContent: 'space-between' },
  footnote: {
    ...type.caption,
    fontSize: 11,
    lineHeight: 16,
    color: palette.textGhost,
  },

  // --- Coach ------------------------------------------------------------
  coachHeadline: { ...type.heading, color: palette.text },
  coachDetail: { ...type.body, color: palette.textDim },
  actionCallout: { flexDirection: 'row', gap: space.md, alignItems: 'stretch' },
  actionBar: { width: 2, borderRadius: 1 },
  actionText: { ...type.body, color: palette.text, flex: 1, fontWeight: '500' },
  promptText: { ...type.caption, color: palette.textDim, paddingTop: space.md },
  coachFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: space.xs,
  },

  // --- Meals ------------------------------------------------------------
  mealRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  mealName: { ...type.body, color: palette.text, fontWeight: '500' },

  emptyText: { ...type.body, color: palette.textDim },
});
