/**
 * New-user questionnaire.
 *
 * Runs AFTER signup and BEFORE the tabs, gated in app/_layout.tsx on
 * `onboarded_at`. A user who reinstalls and logs back in skips it, because the
 * answer lives on the server, not in local storage.
 *
 * WHY ONE QUESTION PER SCREEN
 * A single long form asking gender, height, weight, peak weight, experience,
 * cardio, steps and goal reads as a medical intake and gets abandoned. One
 * question per screen with a visible step count is slower to click through and
 * far more likely to be finished — and it lets each question carry a sentence
 * explaining why we're asking, which is what makes the peak-weight question
 * land instead of feeling intrusive.
 *
 * ARITHMETIC LIVES ON THE SERVER. This screen collects answers and renders
 * what /api/onboarding/preview returns. It must never compute a calorie target
 * locally — two implementations of the same formula will drift, and the one on
 * the phone is the one nobody tests.
 */

import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn, FadeInDown, FadeOut } from 'react-native-reanimated';

import {
  Button,
  Cell,
  Choice,
  Field,
  Label,
  Plain,
  Rule,
  StepDots,
  Stepper,
} from '../../src/components/instrument';
import { Dial } from '../../src/components/dial';
import { api, ApiError, type OnboardingPlan } from '../../src/lib/api';
import { useAuth } from '../../src/state/useAuth';
import { useOnboarding } from '../../src/state/useOnboarding';
import { useSurfaces } from '../../src/state/useTheme';
import { motion, palette, space, type } from '../../src/theme';

// Steps are an ordered enum rather than magic numbers so inserting a question
// later is a one-line change instead of an off-by-one hunt.
//
// GOAL COMES FIRST, DELIBERATELY.
// It is the only interesting question in the set -- everything after it is
// data entry -- and choosing one is a small commitment that measurably
// predicts finishing the rest. Opening on "what's your email" asks for
// something with no payoff attached, which is where questionnaires lose
// people. It also means every later question can be framed against the goal
// the user just picked rather than asked in the abstract.
const STEPS = [
  'goal',
  'sex',
  'body',
  'peak',
  'experience',
  'training',
  'steps',
  'plan',
] as const;
type Step = (typeof STEPS)[number];

const LB_PER_KG = 2.20462;

export default function OnboardingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const surfaces = useSurfaces();
  // `restore` re-reads /api/auth/me, which is what refreshes `onboarded_at`
  // so the root layout's gate lets us through to the tabs.
  const refreshUser = useAuth((s) => s.restore);

  const signedIn = useAuth((st) => st.status) === 'signedIn';
  const stash = useOnboarding((st) => st.stash);

  const [stepIndex, setStepIndex] = useState(0);
  const step: Step = STEPS[stepIndex];

  const [sex, setSex] = useState<string | null>(null);
  const [useMetric, setUseMetric] = useState(true);
  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [everHeavier, setEverHeavier] = useState<'yes' | 'no' | 'skip' | null>(null);
  const [peakKg, setPeakKg] = useState('');
  const [experienceMonths, setExperienceMonths] = useState<number | null>(null);
  const [liftDays, setLiftDays] = useState(3);
  const [cardioDays, setCardioDays] = useState(2);
  const [dailySteps, setDailySteps] = useState(6000);
  const [goal, setGoal] = useState<'lose' | 'maintain' | 'gain' | 'recomp' | null>(null);

  const [plan, setPlan] = useState<OnboardingPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parse once, here, so every downstream check reads the same numbers. Height
  // and weight arrive as strings because the keyboard produces strings, and
  // "" must not silently become 0 — an empty field is incomplete, not zero.
  const parsed = useMemo(() => {
    const h = parseFloat(heightCm);
    const w = parseFloat(weightKg);
    const p = parseFloat(peakKg);
    const toKg = (v: number) => (useMetric ? v : v / LB_PER_KG);
    const toCm = (v: number) => (useMetric ? v : v * 2.54);
    return {
      height_cm: Number.isFinite(h) ? +toCm(h).toFixed(1) : NaN,
      weight_kg: Number.isFinite(w) ? +toKg(w).toFixed(1) : NaN,
      peak_kg: Number.isFinite(p) ? +toKg(p).toFixed(1) : NaN,
    };
  }, [heightCm, weightKg, peakKg, useMetric]);

  const answers = useCallback(
    () => ({
      sex,
      height_cm: parsed.height_cm,
      weight_kg: parsed.weight_kg,
      // Only send a peak weight if they actually gave one. `null` means "not
      // asked / declined", which the server treats differently from "never
      // been heavier" — it applies no adaptation either way, but it does not
      // claim a finding it doesn't have.
      highest_weight_kg:
        everHeavier === 'yes' && Number.isFinite(parsed.peak_kg)
          ? parsed.peak_kg
          : null,
      lifting_experience_months: experienceMonths ?? 0,
      lifting_sessions_per_week: liftDays,
      cardio_sessions_per_week: cardioDays,
      daily_steps: dailySteps,
      goal_type: goal ?? 'maintain',
    }),
    [sex, parsed, everHeavier, experienceMonths, liftDays, cardioDays, dailySteps, goal],
  );

  // Each step declares what "answered" means. A disabled Next with no
  // explanation is the most common onboarding dead end, so the button label
  // changes rather than the button silently doing nothing.
  const canAdvance = (): boolean => {
    switch (step) {
      case 'sex':
        return sex !== null;
      case 'body':
        return (
          Number.isFinite(parsed.height_cm) &&
          Number.isFinite(parsed.weight_kg) &&
          parsed.height_cm > 100 &&
          parsed.height_cm < 250 &&
          parsed.weight_kg > 25 &&
          parsed.weight_kg < 350
        );
      case 'peak':
        if (everHeavier === null) return false;
        if (everHeavier !== 'yes') return true;
        return Number.isFinite(parsed.peak_kg) && parsed.peak_kg > parsed.weight_kg;
      case 'experience':
        return experienceMonths !== null;
      case 'goal':
        return goal !== null;
      default:
        return true;
    }
  };

  const next = async () => {
    setError(null);
    // Entering the plan step means computing it. Preview is unauthenticated
    // and saves nothing, so a user can back out and change an answer.
    if (STEPS[stepIndex + 1] === 'plan') {
      setBusy(true);
      try {
        setPlan(await api.previewPlan(answers()));
        setStepIndex(stepIndex + 1);
      } catch (e) {
        setError(
          e instanceof ApiError
            ? e.message
            : 'Could not reach the server. Check your connection and try again.',
        );
      } finally {
        setBusy(false);
      }
      return;
    }
    setStepIndex(Math.min(STEPS.length - 1, stepIndex + 1));
  };

  /**
   * Finish the questionnaire.
   *
   * THE QUESTIONNAIRE NOW RUNS BEFORE THE ACCOUNT, so this has two exits.
   *
   *   SIGNED OUT  stash the answers and send them to create an account. They
   *               have already SEEN their target by this point, so the ask is
   *               "save this", not "sign up to find out" -- which is the
   *               entire reason for running the questionnaire first.
   *   SIGNED IN   the old path: save straight away and open the app.
   *
   * The answers are stashed rather than passed as params because they have to
   * survive a navigation and, on a bad day, the OS reclaiming the app while
   * the user is reading an SMS.
   */
  const finish = async () => {
    if (!signedIn) {
      await stash(answers(), plan);
      router.push('/(auth)/phone');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await api.submitOnboarding(answers());
      await refreshUser();
      router.replace('/(tabs)');
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Could not save your plan. Try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.screen, { backgroundColor: surfaces.void }]}>
      <View style={[styles.head, { paddingTop: insets.top + space.md }]}>
        <StepDots count={STEPS.length} index={stepIndex} />
        {/* Returning users must not be trapped in a questionnaire they have
            already answered. This is the only way out for them. */}
        {signedIn ? (
          <Text style={[type.labelSm, { color: palette.textFaint }]}>
            {stepIndex + 1} / {STEPS.length}
          </Text>
        ) : (
          <Pressable onPress={() => router.push('/(auth)/phone')} hitSlop={10}>
            <Text style={[type.labelSm, { color: palette.textFaint }]}>
              I HAVE AN ACCOUNT
            </Text>
          </Pressable>
        )}
      </View>
      <Rule />

      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
      >
        <Animated.View
          key={step}
          entering={FadeInDown.duration(motion.base)}
          exiting={FadeOut.duration(motion.fast)}
          style={styles.stepWrap}
        >
          {step === 'sex' && (
            <Question
              title="What's your biological sex?"
              why="Resting metabolism differs by roughly 150 kcal a day between males and females at the same size. It's the one place the formula needs it."
            >
              <Choice
                value={sex}
                onChange={setSex}
                options={[
                  { value: 'male', label: 'Male' },
                  { value: 'female', label: 'Female' },
                  {
                    value: 'other',
                    label: 'Prefer not to say',
                    detail: 'We use the male equation, then correct from your real data.',
                  },
                ]}
              />
            </Question>
          )}

          {step === 'body' && (
            <Question
              title="Your height and weight"
              why="The starting point for everything. Both get replaced by what you actually log."
            >
              <Choice
                columns={2}
                value={useMetric ? 'metric' : 'imperial'}
                onChange={(v) => setUseMetric(v === 'metric')}
                options={[
                  { value: 'metric', label: 'cm / kg' },
                  { value: 'imperial', label: 'in / lb' },
                ]}
              />
              <View style={styles.gap} />
              {/* Dials, not text fields. A keyboard accepts 7 kg and 700 kg
                  alike, and a wrong starting weight poisons the expenditure
                  estimate for weeks before anyone notices it. A dial cannot
                  produce a value outside its range, needs no keyboard, and
                  nobody's own weight is a surprise to them -- landing near it
                  and nudging is quicker than typing. */}
              <Dial
                label="Current weight"
                unit={useMetric ? 'kg' : 'lb'}
                value={parseFloat(weightKg) || (useMetric ? 70 : 154)}
                onChange={(v) => setWeightKg(String(v))}
                min={useMetric ? 30 : 66}
                max={useMetric ? 250 : 550}
                step={useMetric ? 0.5 : 1}
                decimals={useMetric ? 1 : 0}
              />
              <View style={styles.gap} />
              <Dial
                label="Height"
                unit={useMetric ? 'cm' : 'in'}
                value={parseFloat(heightCm) || (useMetric ? 178 : 70)}
                onChange={(v) => setHeightCm(String(v))}
                min={useMetric ? 120 : 47}
                max={useMetric ? 230 : 91}
                step={1}
                decimals={0}
              />
            </Question>
          )}

          {step === 'peak' && (
            <Question
              title="Have you ever weighed significantly more than you do now?"
              why="This is the question most apps don't ask. If you've dieted down from a much higher weight, you burn measurably less than your current size predicts — and being handed the textbook number is why people stall on day one."
            >
              <Choice
                value={everHeavier}
                onChange={setEverHeavier}
                options={[
                  { value: 'yes', label: 'Yes, I used to be heavier' },
                  { value: 'no', label: 'No, this is around my heaviest' },
                  { value: 'skip', label: "I'd rather not say" },
                ]}
              />
              {everHeavier === 'yes' && (
                <Animated.View entering={FadeIn.duration(motion.fast)}>
                  <View style={styles.gap} />
                  <Field
                    label="Heaviest you've been"
                    suffix={useMetric ? 'kg' : 'lb'}
                    value={peakKg}
                    onChangeText={setPeakKg}
                    keyboardType="decimal-pad"
                    placeholder={useMetric ? '91' : '200'}
                  />
                  {Number.isFinite(parsed.peak_kg) &&
                    parsed.peak_kg <= parsed.weight_kg && (
                      <>
                        <View style={styles.gap} />
                        <Plain tone="warn">
                          That's not higher than your current weight. Enter your
                          heaviest, or pick a different answer above.
                        </Plain>
                      </>
                    )}
                </Animated.View>
              )}
            </Question>
          )}

          {step === 'experience' && (
            <Question
              title="How long have you been lifting?"
              why="Newer lifters build muscle fast enough to justify a bolder surplus. Experienced lifters gaining at the same rate are mostly buying fat."
            >
              <Choice
                value={experienceMonths}
                onChange={setExperienceMonths}
                options={[
                  { value: 0, label: "I'm just starting", detail: 'Under 3 months' },
                  { value: 6, label: 'Under a year' },
                  { value: 24, label: '1–3 years' },
                  { value: 60, label: '3–8 years' },
                  { value: 120, label: 'Over 8 years' },
                ]}
              />
            </Question>
          )}

          {step === 'training' && (
            <Question
              title="A typical week"
              why="This sets which days get more carbohydrate. It does not add calories to your target — training days borrow from rest days, so the week totals the same."
            >
              <Label color={palette.textDim}>Lifting sessions</Label>
              <View style={styles.gapSm} />
              <Stepper value={liftDays} onChange={setLiftDays} min={0} max={7} unit="per week" />
              <View style={styles.gap} />
              <Label color={palette.textDim}>Cardio sessions</Label>
              <View style={styles.gapSm} />
              <Stepper
                value={cardioDays}
                onChange={setCardioDays}
                min={0}
                max={14}
                unit="per week"
              />
            </Question>
          )}

          {step === 'steps' && (
            <Question
              title="Roughly how many steps a day?"
              why="Daily movement explains more of the difference between two people's calorie burn than their gym sessions do. A rough number is fine — Trace corrects it from your weight trend."
            >
              <Stepper
                value={dailySteps}
                onChange={setDailySteps}
                min={0}
                max={30000}
                step={500}
                unit="steps a day"
                format={(v) => v.toLocaleString()}
              />
              <View style={styles.gap} />
              <Plain tone="signal">
                {dailySteps < 4000
                  ? 'Mostly seated — desk job, drives everywhere.'
                  : dailySteps < 7500
                    ? 'Lightly active — some walking built into the day.'
                    : dailySteps < 11000
                      ? 'Moderately active — you walk deliberately.'
                      : dailySteps < 15000
                        ? 'Very active — on your feet most of the day.'
                        : 'Extremely active — manual work or long daily walks.'}
              </Plain>
            </Question>
          )}

          {step === 'goal' && (
            <Question
              title="What are you here to do?"
              why="This sets the direction and the pace. You can change it whenever you like."
            >
              <Choice
                value={goal}
                onChange={setGoal}
                options={[
                  {
                    value: 'gain',
                    label: 'Build muscle',
                    detail: 'A controlled surplus. Expect the scale to rise slowly.',
                  },
                  {
                    value: 'lose',
                    label: 'Lose fat',
                    detail: 'A deficit with protein held high to protect muscle.',
                  },
                  {
                    value: 'recomp',
                    label: 'Recomp',
                    detail: 'Hold weight, change composition. The slowest route.',
                  },
                  {
                    value: 'maintain',
                    label: 'Maintain',
                    detail: 'Hold steady and keep training.',
                  },
                ]}
              />
            </Question>
          )}

          {step === 'plan' && plan && <PlanReview plan={plan} />}

          {error && (
            <>
              <View style={styles.gap} />
              <Plain tone="danger">{error}</Plain>
            </>
          )}
        </Animated.View>
      </ScrollView>

      <Rule />
      <View style={[styles.foot, { paddingBottom: insets.bottom + space.md }]}>
        {stepIndex > 0 && (
          <Button
            label="Back"
            variant="ghost"
            onPress={() => setStepIndex(stepIndex - 1)}
          />
        )}
        <View style={styles.flex} />
        <Button
          label={
            step !== 'plan'
              ? 'Continue'
              : signedIn
                ? 'Start tracking'
                : 'Save this — create account'
          }
          onPress={step === 'plan' ? finish : next}
          loading={busy}
          disabled={!canAdvance()}
        />
      </View>
    </View>
  );
}

function Question({
  title,
  why,
  children,
}: {
  title: string;
  why: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <Text style={[type.title, styles.qTitle]}>{title}</Text>
      <Text style={[type.caption, styles.qWhy]}>{why}</Text>
      {children}
    </>
  );
}

/**
 * The payoff screen. Every number here came from the server.
 *
 * Non-negotiable #2 applies: these are estimates, and the notes say so. The
 * week is shown as seven concrete days because "your target is 2,850" is not
 * something a beginner can act on, but "Monday: 3,140 kcal, 112 g protein" is.
 */
/**
 * The last screen is the TARGET, never a confirmation.
 *
 * "Account created ✓" is a receipt for something the user did not want. They
 * came for a number, so the flow ends on the number, at readout size, and the
 * button under it says "Start tracking" rather than "Done".
 *
 * THE SENTENCE ABOUT THE FIRST ADJUSTMENT IS DOING REAL WORK.
 * Week one's figure comes from a prediction equation, which carries roughly
 * ±10% error on an individual. In about two weeks the adaptive engine has
 * enough weigh-ins and logged days to REPLACE it with a measurement, and that
 * number will move -- sometimes by a couple of hundred kcal. A user who was
 * not told to expect that reads the change as the app being broken or
 * arbitrary, and stops trusting every number after it. Saying it here, before
 * it happens, turns the same event into the app working as promised.
 *
 * It is also just true, and it is the product's actual claim. Leading with it
 * is more honest than presenting the formula's guess as if it were measured.
 */
function PlanReview({ plan }: { plan: OnboardingPlan }) {
  const max = Math.max(...plan.week.days.map((d) => d.calories));
  return (
    <>
      <Label color={palette.textFaint}>Your daily target</Label>
      <View style={styles.gapSm} />
      <View style={styles.targetRow}>
        <Text style={styles.targetNumber}>
          {plan.week.daily_average.toLocaleString()}
        </Text>
        <Text style={styles.targetUnit}>kcal</Text>
      </View>

      <View style={styles.gapSm} />
      <Plain>
        This first number is a formula&apos;s best guess about you. Log for
        about two weeks and Trace replaces it with{' '}
        <Text style={styles.bold}>your</Text> real number, measured from what
        you ate and what your weight actually did. Expect it to move — that is
        the app working, not a glitch.
      </Plain>

      <View style={styles.gap} />
      <Text style={[type.caption, styles.qWhy]}>{plan.week.rationale}</Text>

      <View style={styles.summary}>
        <Cell label="Protein" value={`${plan.protein_target_g}`} unit="g" keyColor={palette.protein} />
        <Cell label="Carbs" value={`${plan.carb_target_g}`} unit="g" keyColor={palette.carbs} />
        <Cell label="Fat" value={`${plan.fat_target_g}`} unit="g" keyColor={palette.fat} />
      </View>

      <View style={styles.gap} />
      <Label color={palette.textDim}>The week</Label>
      <View style={styles.gapSm} />

      {plan.week.days.map((d) => (
        <View key={d.index} style={styles.dayRow}>
          <Text style={[type.labelSm, styles.dayName]}>{d.day}</Text>
          <View style={styles.dayBarTrack}>
            <View
              style={[
                styles.dayBar,
                {
                  width: `${(d.calories / max) * 100}%`,
                  backgroundColor:
                    d.day_type === 'training' ? palette.signal : palette.signalDim,
                },
              ]}
            />
          </View>
          <Text style={[type.valueSm, styles.dayKcal]}>
            {d.calories.toLocaleString()}
          </Text>
        </View>
      ))}

      <View style={styles.gap} />
      {plan.notes.map((n, i) => (
        <View key={i} style={styles.note}>
          <Plain tone={i === 0 && plan.adaptation_factor < 1 ? 'warn' : 'signal'}>
            {n}
          </Plain>
        </View>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  targetRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  targetNumber: { ...type.readout, color: palette.text },
  targetUnit: { ...type.title, color: palette.textFaint },
  bold: { fontFamily: type.heading.fontFamily },
  screen: { flex: 1 },
  flex: { flex: 1 },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
  },
  body: { padding: space.lg, paddingBottom: space.xxl },
  stepWrap: { flex: 1 },
  qTitle: { color: palette.text, marginBottom: space.sm },
  qWhy: { color: palette.textDim, marginBottom: space.xl },
  gap: { height: space.lg },
  gapSm: { height: space.sm },
  foot: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingTop: space.md,
  },

  summary: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },

  dayRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.xs,
  },
  dayName: { color: palette.textDim, width: 30 },
  dayBarTrack: { flex: 1, height: 10, backgroundColor: palette.raised },
  dayBar: { height: 10 },
  dayKcal: { color: palette.text, width: 52, textAlign: 'right' },

  note: { marginBottom: space.sm },
});
