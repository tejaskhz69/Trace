/* Static mock data for the workout-trainer prototype.
 *
 * NOTHING HERE IS REAL.
 *
 * Every number below was invented for this prototype. No value was read from
 * the trace database, from HealthKit, from Health Connect, from Strava, from
 * a watch, or from any user account. No sleep was measured. No route was
 * recorded. No model was called. The exercise ids are mock strings shaped
 * like ids so the AI-review screen can demonstrate validation -- they are not
 * catalogue ids and they resolve to nothing.
 *
 * SOURCE LABELS
 * Every sample record carries a `source` drawn from SOURCE below. That field
 * describes the provenance *within the fiction* -- what kind of record this
 * would be in a working app -- and the UI renders it verbatim next to a
 * SAMPLE tag, so the two claims never blur into one. `imported` rows are
 * illustrative: the Profile screen shows every external source as NOT
 * CONNECTED, because nothing was imported and nothing could have been.
 *
 * This is the ONLY file holding sample values. If the prototype were ever
 * wired to a real source, this is the file that would be deleted.
 */

/* eslint-disable */
'use strict';

const SOURCE = {
  DEMO: 'demo',
  MANUAL: 'manually recorded',
  IMPORTED: 'imported',
  ESTIMATED: 'estimated',
  UNAVAILABLE: 'unavailable',
};

const MOCK = {
  source: SOURCE.DEMO,

  /* --- The person ------------------------------------------------------ */
  user: {
    source: SOURCE.DEMO,
    name: 'Sam',
    initials: 'SM',
    goal: 'Muscle gain',
    phase: 'Lean bulk',
    daysPerWeek: 3,
    trainingAgeMonths: 4,
    equipment: ['Dumbbells', 'Bench', 'Mat'],
    preferredMinutes: 50,
    weightKg: 74.8,
    heightCm: 178,
  },

  /* --- Programme -------------------------------------------------------
     Beginner-safe on purpose: bodyweight and dumbbell only, no barbell
     prescription, and every suggested load is either a logged weight or an
     em dash. Mirrors WORKOUT_SCHEMA_DESIGN.md section 10.7. */
  programme: {
    source: SOURCE.DEMO,
    name: 'Foundations · Full Body A',
    split: 'Full body',
    week: 3,
    totalWeeks: 8,
    dayLabel: 'Day 1 of 3 this week',
    muscleGroups: ['Quads', 'Chest', 'Back', 'Hamstrings', 'Core'],
    adherencePct: 83,
    adherenceNote: '15 of 18 planned sessions done since week 1.',
    progressionRule:
      'Double progression. Hold the load until every prescribed set reaches the top of the rep range at the target reps in reserve, then add the smallest increment your equipment allows and return to the bottom of the range.',
    warmup: [
      { source: SOURCE.DEMO, label: 'General', detail: '5 min easy cycling or a brisk walk', working: false },
      { source: SOURCE.DEMO, label: 'Ramp set 1', detail: 'Goblet squat, about half the working load, 5 reps', working: false },
      { source: SOURCE.DEMO, label: 'Ramp set 2', detail: 'Goblet squat, about three-quarters, 3 reps', working: false },
    ],
  },

  /* --- Today's prescription -------------------------------------------- */
  exercises: [
    {
      source: SOURCE.DEMO,
      id: 'p1',
      name: 'Goblet Squat',
      equipment: 'Dumbbell',
      sets: 3,
      repLow: 8,
      repHigh: 12,
      rir: 2,
      restSec: 120,
      loadKg: 16,
      primary: ['Quads'],
      secondary: ['Glutes', 'Core'],
      pattern: 'Squat · knee-dominant',
      shape: 'squat',
      beginner:
        'You hold one dumbbell against your chest and sit down between your feet. Holding the weight in front keeps your torso upright, which makes this much easier to learn than a barbell squat.',
      cues: [
        'Hold the dumbbell vertically against your sternum, elbows tucked in.',
        'Push your knees out over your toes as you descend.',
        'Go as deep as you can while keeping your heels flat and your back neutral.',
        'Drive back up through mid-foot.',
      ],
      mistakes: [
        'Heels lifting — usually means going deeper than your ankles currently allow.',
        'Knees collapsing inward on the way up.',
        'Rounding the lower back at the bottom.',
      ],
      feel: 'Work across the front of the thighs and the glutes. A stretch at the bottom is normal.',
      easier: 'Bodyweight Squat to a Box — sit to a bench, stand up, no load to control.',
      harder: 'Dumbbell Split Squat — one leg at a time, roughly double the load per leg.',
      substitute: 'Bodyweight Squat to a Box',
      substituteWhy: 'Same movement pattern, no load to control while you learn the depth.',
      e1rm: [18.0, 18.5, 19.4, 19.4, 20.2, 21.0, 21.6, 22.4],
      history: [
        { source: SOURCE.DEMO, date: 'Fri 21 Aug', load: 16, reps: 10, rir: 2 },
        { source: SOURCE.DEMO, date: 'Tue 18 Aug', load: 16, reps: 9, rir: 2 },
        { source: SOURCE.DEMO, date: 'Sat 15 Aug', load: 14, reps: 11, rir: 2 },
        { source: SOURCE.DEMO, date: 'Wed 12 Aug', load: 14, reps: 10, rir: 3 },
      ],
      plateauStatus: 'progressing',
    },
    {
      source: SOURCE.DEMO,
      id: 'p2',
      name: 'Dumbbell Bench Press',
      equipment: 'Dumbbell · Bench',
      sets: 3,
      repLow: 8,
      repHigh: 12,
      rir: 2,
      restSec: 120,
      loadKg: 20,
      plateau: true,
      primary: ['Chest'],
      secondary: ['Front delts', 'Triceps'],
      pattern: 'Horizontal push',
      shape: 'press',
      beginner:
        'Lying on a bench, you press two dumbbells from chest height to arms-length. Dumbbells let each arm move on its own path, which is usually kinder on the shoulders than a bar.',
      cues: [
        'Set the bench flat, feet planted, shoulder blades pulled down and back.',
        'Start with the dumbbells just outside your chest, wrists stacked over elbows.',
        'Press up and very slightly together.',
        'Lower under control to about chest level.',
      ],
      mistakes: [
        'Flaring the elbows straight out to the sides.',
        'Bouncing the dumbbells off the chest.',
        'Letting the wrists bend back under the load.',
      ],
      feel: 'Work across the chest and the front of the shoulders, with the triceps helping at lockout.',
      easier: 'Incline Push-up — hands on the bench, load set by how high they are.',
      harder: 'Incline Dumbbell Press — bench at 30°, more work for the upper chest.',
      substitute: 'Push-up (feet elevated)',
      substituteWhy: 'Same pattern, no bench needed, load set by body position.',
      e1rm: [25.3, 26.0, 26.0, 25.3, 26.0, 26.0, 25.3, 26.0],
      history: [
        { source: SOURCE.DEMO, date: 'Sun 24 Aug', load: 20, reps: 9, rir: 2 },
        { source: SOURCE.DEMO, date: 'Wed 13 Aug', load: 20, reps: 8, rir: 2 },
        { source: SOURCE.DEMO, date: 'Tue 05 Aug', load: 20, reps: 9, rir: 2 },
        { source: SOURCE.DEMO, date: 'Tue 29 Jul', load: 20, reps: 9, rir: 2 },
      ],
      plateauStatus: 'confirmed',
    },
    {
      source: SOURCE.DEMO,
      id: 'p3',
      name: 'One-Arm Dumbbell Row',
      equipment: 'Dumbbell · Bench',
      sets: 3,
      repLow: 8,
      repHigh: 12,
      rir: 2,
      restSec: 90,
      loadKg: 18,
      unilateral: true,
      primary: ['Lats', 'Mid-back'],
      secondary: ['Biceps', 'Rear delts'],
      pattern: 'Horizontal pull',
      shape: 'row',
      beginner:
        'With one hand and one knee on a bench, you pull a dumbbell from arms-length up to your ribs. Bracing on the bench takes your lower back out of the equation.',
      cues: [
        'Flat back, hips square, opposite hand and knee supporting you.',
        'Let the arm hang and feel the shoulder blade reach forward.',
        'Pull the dumbbell toward your hip, leading with the elbow.',
        'Lower all the way down each rep.',
      ],
      mistakes: [
        'Twisting the torso to lift a heavier dumbbell.',
        'Shrugging the shoulder up toward the ear.',
        'Stopping short of a full stretch at the bottom.',
      ],
      feel: 'Work down the side of the back and through the mid-back, with the biceps assisting.',
      easier: 'Chest-Supported Dumbbell Row — the bench holds you up, so nothing to balance.',
      harder: 'Inverted Row — your own bodyweight, both sides at once.',
      substitute: 'Chest-Supported Dumbbell Row',
      substituteWhy: 'Removes the balance demand so both sides get the same position.',
      e1rm: [20.5, 21.0, 21.8, 22.4, 22.4, 23.1, 23.9, 24.6],
      history: [
        { source: SOURCE.DEMO, date: 'Fri 21 Aug', load: 18, reps: 10, rir: 2 },
        { source: SOURCE.DEMO, date: 'Tue 18 Aug', load: 18, reps: 9, rir: 2 },
        { source: SOURCE.DEMO, date: 'Sat 15 Aug', load: 16, reps: 11, rir: 2 },
        { source: SOURCE.DEMO, date: 'Wed 12 Aug', load: 16, reps: 10, rir: 2 },
      ],
      plateauStatus: 'progressing',
    },
    {
      source: SOURCE.DEMO,
      id: 'p4',
      name: 'Dumbbell Romanian Deadlift',
      equipment: 'Dumbbell',
      sets: 3,
      repLow: 10,
      repHigh: 12,
      rir: 3,
      restSec: 90,
      loadKg: 14,
      primary: ['Hamstrings'],
      secondary: ['Glutes', 'Lower back'],
      pattern: 'Hip hinge',
      shape: 'hinge',
      beginner:
        'You push your hips backward and let the dumbbells travel down your thighs, keeping your legs almost straight. It is a hip movement, not a squat.',
      cues: [
        'Soft knees, then push the hips back as far as they will go.',
        'Keep the dumbbells brushing your legs the whole way.',
        'Stop when you feel a strong stretch behind the thighs.',
        'Stand up by driving the hips forward.',
      ],
      mistakes: [
        'Bending the knees and turning it into a squat.',
        'Rounding the back to reach lower.',
        'Leaning back and over-squeezing at the top.',
      ],
      feel: 'A strong stretch through the back of the thighs. This one is deliberately kept at 3 reps in reserve.',
      easier: 'Glute Bridge — same hip extension, lying down, no spinal loading.',
      harder: 'Single-Leg Romanian Deadlift — one leg, which also demands balance.',
      substitute: 'Glute Bridge',
      substituteWhy: 'Trains the same hip extension with no spinal loading.',
      e1rm: [15.8, 16.2, 16.9, 17.5, 17.5, 18.2, 18.9, 19.6],
      history: [
        { source: SOURCE.DEMO, date: 'Fri 21 Aug', load: 14, reps: 12, rir: 3 },
        { source: SOURCE.DEMO, date: 'Tue 18 Aug', load: 14, reps: 11, rir: 3 },
        { source: SOURCE.DEMO, date: 'Sat 15 Aug', load: 12, reps: 12, rir: 3 },
        { source: SOURCE.DEMO, date: 'Wed 12 Aug', load: 12, reps: 11, rir: 3 },
      ],
      plateauStatus: 'progressing',
    },
    {
      source: SOURCE.DEMO,
      id: 'p5',
      name: 'Push-up',
      equipment: 'Bodyweight',
      sets: 2,
      repLow: 8,
      repHigh: 15,
      rir: 2,
      restSec: 60,
      loadKg: null,
      primary: ['Chest'],
      secondary: ['Triceps', 'Core'],
      pattern: 'Horizontal push',
      shape: 'press',
      beginner:
        'A moving plank. Your body stays in one straight line from head to heels while your arms bend and straighten.',
      cues: [
        'Hands slightly wider than the shoulders.',
        'Squeeze the glutes so the hips do not sag.',
        'Elbows travel back at roughly 45 degrees, not straight out.',
        'Touch the chest down, then press away from the floor.',
      ],
      mistakes: ['Hips sagging or piking up.', 'Only going halfway down.', 'Head dropping forward first.'],
      feel: 'Chest and triceps, with the midsection working to hold the line.',
      easier: 'Incline Push-up — the higher your hands, the lighter it is.',
      harder: 'Feet-Elevated Push-up — more of your weight over your hands.',
      substitute: 'Incline Push-up (hands on bench)',
      substituteWhy: 'The higher the hands, the lighter it is. The cleanest way to scale this movement.',
      e1rm: null,
      history: [
        { source: SOURCE.DEMO, date: 'Fri 21 Aug', load: null, reps: 13, rir: 2 },
        { source: SOURCE.DEMO, date: 'Tue 18 Aug', load: null, reps: 12, rir: 2 },
        { source: SOURCE.DEMO, date: 'Sat 15 Aug', load: null, reps: 11, rir: 2 },
        { source: SOURCE.DEMO, date: 'Wed 12 Aug', load: null, reps: 9, rir: 3 },
      ],
      plateauStatus: 'progressing',
    },
    {
      source: SOURCE.DEMO,
      id: 'p6',
      name: 'Dead Bug',
      equipment: 'Bodyweight · Mat',
      sets: 2,
      repLow: 8,
      repHigh: 10,
      rir: 3,
      restSec: 45,
      loadKg: null,
      unilateral: true,
      primary: ['Core'],
      secondary: ['Hip flexors'],
      pattern: 'Anti-extension',
      shape: 'core',
      beginner:
        'On your back, you lower one arm and the opposite leg while keeping your lower back pressed to the floor. The difficulty is in not letting the back arch.',
      cues: [
        'Press the lower back flat into the mat and keep it there.',
        'Move slowly — this is not a speed exercise.',
        'Breathe out as you extend.',
        'Stop the range where the back starts to lift.',
      ],
      mistakes: ['Letting the lower back arch off the mat.', 'Rushing the reps.', 'Holding the breath.'],
      feel: 'Deep in the front of the midsection. It should not be felt in the lower back.',
      easier: 'Bird Dog — same idea on hands and knees, easier to keep the back flat.',
      harder: 'Front Plank with reach — hold the line while one hand leaves the floor.',
      substitute: 'Front Plank',
      substituteWhy: 'Same anti-extension demand with no limb movement to coordinate.',
      e1rm: null,
      history: [
        { source: SOURCE.DEMO, date: 'Fri 21 Aug', load: null, reps: 10, rir: 3 },
        { source: SOURCE.DEMO, date: 'Tue 18 Aug', load: null, reps: 9, rir: 3 },
      ],
      plateauStatus: 'insufficient_data',
    },
  ],

  /* Extra exercises addable mid-session, and for the independent workout. */
  extraExercises: [
    { source: SOURCE.DEMO, id: 'x1', name: 'Dumbbell Lateral Raise', equipment: 'Dumbbell', sets: 2, repLow: 12, repHigh: 15, rir: 2, restSec: 60, loadKg: 6, primary: ['Side delts'] },
    { source: SOURCE.DEMO, id: 'x2', name: 'Dumbbell Curl', equipment: 'Dumbbell', sets: 2, repLow: 10, repHigh: 15, rir: 2, restSec: 60, loadKg: 10, primary: ['Biceps'] },
    { source: SOURCE.DEMO, id: 'x3', name: 'Calf Raise', equipment: 'Bodyweight', sets: 3, repLow: 12, repHigh: 20, rir: 2, restSec: 45, loadKg: null, primary: ['Calves'] },
    { source: SOURCE.DEMO, id: 'x4', name: 'Front Plank', equipment: 'Bodyweight · Mat', sets: 3, repLow: 20, repHigh: 45, rir: 2, restSec: 45, loadKg: null, primary: ['Core'] },
  ],

  substitutionPool: {
    p1: ['Bodyweight Squat to a Box', 'Dumbbell Split Squat', 'Leg Press'],
    p2: ['Push-up (feet elevated)', 'Incline Dumbbell Press', 'Machine Chest Press'],
    p3: ['Chest-Supported Dumbbell Row', 'Inverted Row', 'Seated Cable Row'],
    p4: ['Glute Bridge', 'Dumbbell Good Morning', 'Hamstring Curl'],
    p5: ['Incline Push-up (hands on bench)', 'Knee Push-up', 'Dumbbell Floor Press'],
    p6: ['Front Plank', 'Bird Dog', 'Pallof Press'],
  },

  muscleGroups: ['Chest', 'Back', 'Shoulders', 'Biceps', 'Triceps', 'Forearms', 'Quads', 'Hamstrings', 'Glutes', 'Calves', 'Core'],

  /* --- Readiness. Answers, not measurements. --------------------------- */
  readiness: {
    source: SOURCE.MANUAL,
    defaults: { sleepHours: 6.5, quality: 'Broken', energy: 3, soreness: 2, stress: 4 },
    trend: [
      { source: SOURCE.DEMO, day: 'Mon', score: 71 },
      { source: SOURCE.DEMO, day: 'Tue', score: 68 },
      { source: SOURCE.DEMO, day: 'Wed', score: 74 },
      { source: SOURCE.DEMO, day: 'Thu', score: 60 },
      { source: SOURCE.DEMO, day: 'Fri', score: 57 },
      { source: SOURCE.DEMO, day: 'Sat', score: 66 },
      { source: SOURCE.DEMO, day: 'Sun', score: 55 },
    ],
  },

  /* --- Sleep. NOT measured. Typed in, or absent. ------------------------ */
  sleep: {
    source: SOURCE.MANUAL,
    targetHours: 7.5,
    connection: { source: SOURCE.UNAVAILABLE, provider: 'HealthKit / Health Connect', connected: false, note: 'Not connected. No sleep has been imported, and no sleep permission has been requested.' },
    nights: [
      { source: SOURCE.MANUAL, day: 'Mon', date: '18 Aug', asleep: 7.2, inBed: 7.8, bedtime: '23:10', wake: '06:20', awakenings: 1, quality: 'Good' },
      { source: SOURCE.MANUAL, day: 'Tue', date: '19 Aug', asleep: 6.8, inBed: 7.4, bedtime: '23:45', wake: '06:35', awakenings: 2, quality: 'Good' },
      { source: SOURCE.ESTIMATED, day: 'Wed', date: '20 Aug', asleep: 7.5, inBed: 8.0, bedtime: '22:50', wake: '06:20', awakenings: 1, quality: 'Good' },
      { source: SOURCE.UNAVAILABLE, day: 'Thu', date: '21 Aug', asleep: null, inBed: null, bedtime: null, wake: null, awakenings: null, quality: null },
      { source: SOURCE.MANUAL, day: 'Fri', date: '22 Aug', asleep: 5.4, inBed: 6.1, bedtime: '01:05', wake: '06:30', awakenings: 3, quality: 'Poor' },
      { source: SOURCE.MANUAL, day: 'Sat', date: '23 Aug', asleep: 8.1, inBed: 8.6, bedtime: '23:30', wake: '07:40', awakenings: 0, quality: 'Good' },
      { source: SOURCE.MANUAL, day: 'Sun', date: '24 Aug', asleep: 6.4, inBed: 7.2, bedtime: '00:15', wake: '06:40', awakenings: 3, quality: 'Broken' },
    ],
  },

  /* --- Cardio. Invented. No GPS, nothing imported. ---------------------- */
  cardio: {
    source: SOURCE.DEMO,
    weekMinutes: 116,
    weekTargetMinutes: 150,
    weekSessions: 2,
    outdoor: {
      source: SOURCE.MANUAL,
      key: 'outdoor',
      label: 'Outdoor',
      title: 'Evening road ride',
      durationMin: 74,
      distanceKm: 24.6,
      avgSpeed: 19.9,
      elevationM: 212,
      intensity: 'Moderate · steady with two climbs',
      when: 'Yesterday, 18:10',
      energyKcal: 612,
      energyBasis: 'estimated',
      routeAvailable: true,
      effect:
        'Sample effect: leg volume trimmed by one set on the squat, and the Romanian deadlift kept at 3 reps in reserve rather than 2.',
    },
    indoor: {
      source: SOURCE.MANUAL,
      key: 'indoor',
      label: 'Indoor',
      title: 'Turbo trainer intervals',
      durationMin: 42,
      distanceKm: 18.1,
      avgSpeed: 25.9,
      elevationM: 0,
      intensity: 'Hard · 6 × 3 min at threshold',
      when: 'Yesterday, 06:40',
      energyKcal: 438,
      energyBasis: 'estimated',
      routeAvailable: false,
      effect:
        'Sample effect: squats moved after the pressing work so the legs are not the first thing under load, and the top rep-range target dropped by two.',
    },
    recent: [
      { source: SOURCE.MANUAL, title: 'Evening road ride', when: 'Sun · 74 min', distanceKm: 24.6, kind: 'Outdoor', energyKcal: 612 },
      { source: SOURCE.MANUAL, title: 'Turbo trainer intervals', when: 'Fri · 42 min', distanceKm: 18.1, kind: 'Indoor', energyKcal: 438 },
      { source: SOURCE.IMPORTED, title: 'Morning commute', when: 'Thu · 21 min', distanceKm: 7.4, kind: 'Outdoor', energyKcal: 178, illustrative: true },
    ],
  },

  /* --- Nutrition. Read-only mirror. Does not change food behaviour. ----- */
  nutrition: {
    source: SOURCE.DEMO,
    targetKcal: 2450,
    eatenKcal: 1850,
    protein: { eaten: 118, target: 165 },
    carbs: { eaten: 214, target: 300 },
    fat: { eaten: 58, target: 78 },
    watch: [
      { source: SOURCE.DEMO, name: 'Sodium', value: 2610, target: 2300, unit: 'mg', over: true },
      { source: SOURCE.DEMO, name: 'Fibre', value: 21, target: 34, unit: 'g', over: false },
    ],
    meals: [
      {
        source: SOURCE.DEMO, name: 'Breakfast', kcal: 486,
        items: [
          { source: SOURCE.MANUAL, name: 'Poha', portion: '1 bowl · 180 g', kcal: 270, kind: 'recorded', verification: 'verified', attribution: 'Curated by Trace' },
          { source: SOURCE.MANUAL, name: 'Eggs, boiled', portion: '2 medium', kcal: 156, kind: 'recorded', verification: 'verified', attribution: 'USDA FoodData Central' },
          { source: SOURCE.MANUAL, name: 'Coffee, black', portion: '1 cup', kcal: 5, kind: 'recorded', verification: 'verified', attribution: 'USDA FoodData Central' },
        ],
      },
      {
        source: SOURCE.DEMO, name: 'Lunch', kcal: 444, band: [381, 507],
        items: [
          { source: SOURCE.ESTIMATED, name: 'Puttu', portion: '2 pieces · 180 g', kcal: 248, band: [226, 270], kind: 'ai_estimate', verification: 'estimated', attribution: 'Photo estimate' },
          { source: SOURCE.ESTIMATED, name: 'Kadala curry', portion: '1 katori · 150 g', kcal: 196, band: [155, 237], kind: 'ai_estimate', verification: 'estimated', attribution: 'Photo estimate' },
        ],
      },
      {
        source: SOURCE.DEMO, name: 'Snack', kcal: 120,
        items: [
          { source: SOURCE.MANUAL, name: 'Whey isolate', portion: '1 scoop · 30 g', kcal: 120, kind: 'recorded', verification: 'verified', attribution: 'Open Food Facts' },
        ],
      },
    ],
  },

  /* --- Progress --------------------------------------------------------- */
  progress: {
    source: SOURCE.DEMO,
    sessionsThisWeek: 2,
    sessionsTarget: 3,
    streakWeeks: 5,
    weeks: [3, 2, 3, 3, 2, 3, 2, 2],
    weekLabels: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8'],
    composition: { source: SOURCE.ESTIMATED, gainedKg: 2.4, leanKg: 1.7, fatKg: 0.7, since: '5 July', verdict: 'Mostly muscle' },
    volume: [
      { source: SOURCE.DEMO, muscle: 'Chest', sets: 9, target: 12 },
      { source: SOURCE.DEMO, muscle: 'Back', sets: 11, target: 12 },
      { source: SOURCE.DEMO, muscle: 'Quads', sets: 8, target: 12 },
      { source: SOURCE.DEMO, muscle: 'Hamstrings', sets: 6, target: 10 },
      { source: SOURCE.DEMO, muscle: 'Shoulders', sets: 4, target: 8 },
      { source: SOURCE.DEMO, muscle: 'Core', sets: 5, target: 6 },
    ],
    lifts: [
      { source: SOURCE.DEMO, name: 'Goblet Squat', from: 12, to: 16, unit: 'kg', status: 'progressing' },
      { source: SOURCE.DEMO, name: 'One-Arm Dumbbell Row', from: 14, to: 18, unit: 'kg', status: 'progressing' },
      { source: SOURCE.DEMO, name: 'Dumbbell Bench Press', from: 20, to: 20, unit: 'kg', status: 'plateau' },
      { source: SOURCE.DEMO, name: 'Dumbbell Romanian Deadlift', from: 12, to: 14, unit: 'kg', status: 'progressing' },
      { source: SOURCE.DEMO, name: 'Push-up', from: 9, to: 13, unit: 'reps', status: 'progressing' },
    ],
    records: [
      { source: SOURCE.DEMO, name: 'Goblet Squat', detail: '16 kg × 10', when: '21 Aug' },
      { source: SOURCE.DEMO, name: 'One-Arm Dumbbell Row', detail: '18 kg × 10', when: '21 Aug' },
      { source: SOURCE.DEMO, name: 'Push-up', detail: 'Bodyweight × 13', when: '21 Aug' },
    ],
    fatigue: [
      { source: SOURCE.DEMO, week: 'W1', value: 28 },
      { source: SOURCE.DEMO, week: 'W2', value: 34 },
      { source: SOURCE.DEMO, week: 'W3', value: 31 },
      { source: SOURCE.DEMO, week: 'W4', value: 42 },
      { source: SOURCE.DEMO, week: 'W5', value: 48 },
      { source: SOURCE.DEMO, week: 'W6', value: 45 },
      { source: SOURCE.DEMO, week: 'W7', value: 56 },
      { source: SOURCE.DEMO, week: 'W8', value: 61 },
    ],
    sleepOverlay: [7.2, 6.8, 7.5, 6.9, 5.4, 8.1, 6.4, 6.6],
    cardioOverlay: [90, 40, 120, 75, 60, 145, 100, 116],
  },

  /* --- Plateau assessment ----------------------------------------------
     Shaped after the PlateauAssessment dataclass in section 14.4. Advisory
     only: nothing in this prototype applies a recommendation. */
  plateau: {
    source: SOURCE.DEMO,
    exercise: 'Dumbbell Bench Press',
    status: 'confirmed',
    statusLabel: 'Confirmed',
    confidence: 0.78,
    stalledMetric: 'Top-set estimated 1RM',
    windowDays: 26,
    baseline: '20 kg × 9 at 2 RIR · e1RM 26.0',
    current: '20 kg × 9 at 2 RIR · e1RM 26.0',
    reason:
      'Your dumbbell bench press has stayed at 20 kg for 4 qualifying sessions. You are still completing 8 to 9 reps at about 2 reps in reserve, so this looks like a progression plateau rather than a failed session.',
    evidence: [
      { source: SOURCE.DEMO, date: '29 Jul', load: 20, reps: 9, rir: 2, e1rm: 26.0, volume: 520, baseline: true },
      { source: SOURCE.DEMO, date: '05 Aug', load: 20, reps: 9, rir: 2, e1rm: 26.0, volume: 540 },
      { source: SOURCE.DEMO, date: '13 Aug', load: 20, reps: 8, rir: 2, e1rm: 25.3, volume: 480 },
      { source: SOURCE.DEMO, date: '24 Aug', load: 20, reps: 9, rir: 2, e1rm: 26.0, volume: 540 },
    ],
    checked: [
      'All 3 prescribed sets completed each session — this is not an execution problem.',
      'Same dumbbells, same flat bench, both arms. The sessions are comparable.',
      'No deload was active and no pain was recorded in the window.',
      'Load is not a kilogram-and-pound mix-up.',
    ],
    options: [
      { source: SOURCE.DEMO, id: 'reps', title: 'Keep 20 kg, aim for 10 reps', tradeoff: 'Cheapest option and the one double progression asks for first. Slower on paper than adding load.', recommended: true },
      { source: SOURCE.DEMO, id: 'micro', title: 'Smallest increment your dumbbells allow', tradeoff: 'Next rack step is 22.5 kg — a 12.5% jump. Reps will drop toward 6 for a week or two.' },
      { source: SOURCE.DEMO, id: 'set', title: 'Add a fourth set', tradeoff: 'More total work, but chest is already at 9 of 12 weekly sets and the session runs 6 minutes longer.' },
      { source: SOURCE.DEMO, id: 'variation', title: 'Review a temporary variation', tradeoff: 'Creates a new prescription. Your bench press history stays exactly as it is.' },
    ],
  },

  /* --- AI review --------------------------------------------------------
     The ids below are MOCK. `ex_mock_0000` fails validation on purpose,
     because section 10.3 says one bad id rejects the whole response. */
  aiDraft: {
    source: SOURCE.DEMO,
    model: 'sample-model (not called)',
    generatedFor: 'Full body · 45 minutes · dumbbells and bench',
    confidence: 0.0,
    dataCoverage: 0.0,
    items: [
      { source: SOURCE.DEMO, id: 'ex_mock_0142', name: 'Goblet Squat', sets: 3, repLow: 8, repHigh: 12, rir: 2, sub: 'Bodyweight Squat to a Box', valid: true },
      { source: SOURCE.DEMO, id: 'ex_mock_0087', name: 'Dumbbell Bench Press', sets: 3, repLow: 8, repHigh: 12, rir: 2, sub: 'Push-up (feet elevated)', valid: true },
      { source: SOURCE.DEMO, id: 'ex_mock_0311', name: 'One-Arm Dumbbell Row', sets: 3, repLow: 8, repHigh: 12, rir: 2, sub: 'Chest-Supported Dumbbell Row', valid: true },
      { source: SOURCE.DEMO, id: 'ex_mock_0000', name: 'Cable Crossover Machine', sets: 3, repLow: 12, repHigh: 15, rir: 1, sub: 'None offered', valid: false },
      { source: SOURCE.DEMO, id: 'ex_mock_0204', name: 'Dead Bug', sets: 2, repLow: 8, repHigh: 10, rir: 3, sub: 'Front Plank', valid: true },
    ],
  },

  /* --- Setup flow ------------------------------------------------------- */
  setup: {
    source: SOURCE.DEMO,
    goals: ['Muscle gain', 'Fat loss', 'Maintenance', 'Strength', 'General fitness'],
    phases: ['Lean bulk', 'Cut', 'Maintenance', 'Performance'],
    days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    equipment: ['Bodyweight', 'Dumbbells', 'Barbell', 'Bench', 'Cables', 'Machines', 'Bands', 'Mat', 'Pull-up bar'],
    cardioFrequency: ['None', '1 a week', '2 a week', '3 a week', '4+ a week'],
    exercisePreferences: ['Goblet Squat', 'Dumbbell Bench Press', 'One-Arm Dumbbell Row', 'Dumbbell Romanian Deadlift', 'Push-up', 'Dead Bug', 'Burpee'],
    sessionMinutes: [15, 20, 30, 45, 60, 75, 90],
  },

  /* --- Profile ---------------------------------------------------------- */
  profile: {
    source: SOURCE.DEMO,
    connections: [
      { source: SOURCE.UNAVAILABLE, name: 'Apple Health', state: 'Not connected' },
      { source: SOURCE.UNAVAILABLE, name: 'Health Connect', state: 'Not connected' },
      { source: SOURCE.UNAVAILABLE, name: 'Strava', state: 'Not connected' },
      { source: SOURCE.UNAVAILABLE, name: 'Garmin', state: 'Not connected' },
    ],
  },

  timeOptions: [15, 20, 30, 45, 60, 75, 90],
};
