/**
 * Unified health adapter: Apple HealthKit (iOS) + Health Connect (Android).
 *
 * IMPORTANT — THIS REQUIRES A DEVELOPMENT BUILD.
 * HealthKit is native code. It will NOT work in Expo Go. You need:
 *
 *   npx expo install @kingstinct/react-native-healthkit react-native-nitro-modules
 *   npx expo install react-native-health-connect          # Android
 *   npx expo run:ios     # or: eas build --profile development --platform ios
 *
 * ...plus the config plugin entries in app.json (already added).
 *
 * The modules are imported LAZILY inside each function. If you import them at
 * module scope, the whole app crashes on launch in Expo Go and on any build
 * where the native module is missing — which is a miserable way to discover
 * you forgot to rebuild.
 *
 * WHAT WE READ, AND WHY
 * ---------------------
 *   steps          -> NEAT drift detection. The single most useful signal.
 *   activeEnergy   -> reconciliation ONLY. Never added to the calorie target.
 *   restingEnergy  -> reconciliation.
 *   sleep          -> readiness; explains strength dips that aren't nutrition.
 *   workouts       -> activity context for external cardio.
 *   bodyMass       -> so a smart scale writing to Health flows in automatically.
 *
 * WHAT WE WRITE
 * -------------
 *   bodyMass, dietaryEnergy, protein/carbs/fat -- so Trace plays nicely with
 *   the rest of the user's health ecosystem. Write permission is requested
 *   separately and is genuinely optional.
 */

import { Platform } from 'react-native';

export type HealthPlatform = 'healthkit' | 'health_connect' | 'unavailable';

export interface ActivityDay {
  day: string; // YYYY-MM-DD
  steps?: number;
  active_energy_kcal?: number;
  resting_energy_kcal?: number;
  exercise_minutes?: number;
  distance_km?: number;
  flights_climbed?: number;
  resting_heart_rate?: number;
  hrv_ms?: number;
}

export interface SleepNight {
  night_of: string;
  asleep_hours: number;
  in_bed_hours?: number;
  deep_hours?: number;
  rem_hours?: number;
  awakenings?: number;
}

export interface ExternalWorkout {
  external_id: string;
  activity_type: string;
  started_at: string;
  ended_at?: string;
  duration_minutes: number;
  active_energy_kcal?: number;
  distance_km?: number;
  mean_heart_rate?: number;
}

export interface HealthSnapshot {
  activity: ActivityDay[];
  sleep: SleepNight[];
  workouts: ExternalWorkout[];
  weights: Array<{ day: string; weight_kg: number }>;
}

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

export function healthPlatform(): HealthPlatform {
  if (Platform.OS === 'ios') return 'healthkit';
  if (Platform.OS === 'android') return 'health_connect';
  return 'unavailable';
}

export async function isHealthAvailable(): Promise<boolean> {
  try {
    if (Platform.OS === 'ios') {
      const hk = await import('@kingstinct/react-native-healthkit');
      return hk.isHealthDataAvailable();
    }
    if (Platform.OS === 'android') {
      const hc = await import('react-native-health-connect');
      const status = await hc.getSdkStatus();
      return status === hc.SdkAvailabilityStatus.SDK_AVAILABLE;
    }
    return false;
  } catch (err) {
    // The native module isn't in this build. Almost always means Expo Go, or
    // a rebuild is needed after adding the dependency.
    console.warn(
      '[health] native module unavailable — you need a development build, ' +
        'not Expo Go. Run `npx expo run:ios`.',
      err,
    );
    return false;
  }
}

// ---------------------------------------------------------------------------
// Permissions
// ---------------------------------------------------------------------------

const IOS_READ = [
  'HKQuantityTypeIdentifierStepCount',
  'HKQuantityTypeIdentifierActiveEnergyBurned',
  'HKQuantityTypeIdentifierBasalEnergyBurned',
  'HKQuantityTypeIdentifierAppleExerciseTime',
  'HKQuantityTypeIdentifierDistanceWalkingRunning',
  'HKQuantityTypeIdentifierFlightsClimbed',
  'HKQuantityTypeIdentifierRestingHeartRate',
  'HKQuantityTypeIdentifierHeartRateVariabilitySDNN',
  'HKQuantityTypeIdentifierBodyMass',
  'HKCategoryTypeIdentifierSleepAnalysis',
  'HKWorkoutTypeIdentifier',
] as const;

const IOS_WRITE = [
  'HKQuantityTypeIdentifierBodyMass',
  'HKQuantityTypeIdentifierDietaryEnergyConsumed',
  'HKQuantityTypeIdentifierDietaryProtein',
  'HKQuantityTypeIdentifierDietaryCarbohydrates',
  'HKQuantityTypeIdentifierDietaryFatTotal',
] as const;

export async function requestPermissions(
  includeWrite = true,
): Promise<boolean> {
  try {
    if (Platform.OS === 'ios') {
      const hk = await import('@kingstinct/react-native-healthkit');
      await hk.requestAuthorization({
        toRead: IOS_READ as never,
        toShare: (includeWrite ? IOS_WRITE : []) as never,
      });
      // NOTE: iOS deliberately does NOT tell you whether READ permission was
      // granted — that would leak health information by omission. So never
      // branch on a "granted" boolean for reads. Try the query; empty results
      // mean either no permission or no data, and you cannot distinguish them.
      return true;
    }

    if (Platform.OS === 'android') {
      const hc = await import('react-native-health-connect');
      await hc.initialize();
      const granted = await hc.requestPermission([
        { accessType: 'read', recordType: 'Steps' },
        { accessType: 'read', recordType: 'ActiveCaloriesBurned' },
        { accessType: 'read', recordType: 'TotalCaloriesBurned' },
        { accessType: 'read', recordType: 'SleepSession' },
        { accessType: 'read', recordType: 'ExerciseSession' },
        { accessType: 'read', recordType: 'Distance' },
        { accessType: 'read', recordType: 'Weight' },
        { accessType: 'read', recordType: 'HeartRateVariabilityRmssd' },
        ...(includeWrite
          ? ([{ accessType: 'write', recordType: 'Weight' }] as const)
          : []),
      ] as never);
      return Array.isArray(granted) && granted.length > 0;
    }

    return false;
  } catch (err) {
    console.warn('[health] permission request failed', err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function dayRange(days: number): { start: Date; end: Date } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  start.setHours(0, 0, 0, 0);
  return { start, end };
}

/**
 * Read the last `days` of everything, bucketed by day.
 *
 * Deliberately returns a plain, serialisable snapshot that maps 1:1 onto the
 * /api/health/sync payload — no transformation needed at the call site.
 */
export async function readSnapshot(days = 90): Promise<HealthSnapshot> {
  const { start, end } = dayRange(days);

  if (Platform.OS === 'ios') return readHealthKit(start, end);
  if (Platform.OS === 'android') return readHealthConnect(start, end);
  return { activity: [], sleep: [], workouts: [], weights: [] };
}

async function readHealthKit(start: Date, end: Date): Promise<HealthSnapshot> {
  const hk = await import('@kingstinct/react-native-healthkit');

  const activityByDay = new Map<string, ActivityDay>();
  const bump = (day: string, patch: Partial<ActivityDay>) => {
    const existing = activityByDay.get(day) ?? { day };
    activityByDay.set(day, { ...existing, ...patch });
  };

  // --- Daily aggregates -------------------------------------------------
  // queryStatisticsCollection buckets on-device, which is far faster than
  // pulling raw samples and bucketing in JS. A year of step samples is tens
  // of thousands of records; the collection query returns ~365 numbers.
  const daily: Array<[string, keyof ActivityDay, number]> = [
    ['HKQuantityTypeIdentifierStepCount', 'steps', 1],
    ['HKQuantityTypeIdentifierActiveEnergyBurned', 'active_energy_kcal', 1],
    ['HKQuantityTypeIdentifierBasalEnergyBurned', 'resting_energy_kcal', 1],
    ['HKQuantityTypeIdentifierAppleExerciseTime', 'exercise_minutes', 1],
    ['HKQuantityTypeIdentifierDistanceWalkingRunning', 'distance_km', 0.001],
    ['HKQuantityTypeIdentifierFlightsClimbed', 'flights_climbed', 1],
  ];

  for (const [identifier, field, scale] of daily) {
    try {
      // Signature: (identifier, statistics[], anchorDate, intervalComponents, options?)
      // The anchor date pins bucket boundaries -- pass local midnight so days
      // line up with the user's calendar rather than UTC.
      const stats = await hk.queryStatisticsCollectionForQuantity(
        identifier as never,
        ['cumulativeSum'] as never,
        start,
        { day: 1 } as never,
        { filter: { startDate: start, endDate: end } } as never,
      );
      for (const bucket of (stats ?? []) as readonly unknown[] as Array<
        Record<string, unknown>
      >) {
        const value = (bucket.sumQuantity as { quantity?: number })?.quantity;
        const bucketStart = bucket.startDate as Date | string | undefined;
        if (value == null || bucketStart == null) continue;
        bump(isoDay(new Date(bucketStart)), {
          [field]: Math.round(value * scale * 100) / 100,
        } as Partial<ActivityDay>);
      }
    } catch {
      // A single missing metric must never fail the whole sync -- users
      // routinely deny one permission and grant the rest.
    }
  }

  // --- Sleep ------------------------------------------------------------
  const sleep: SleepNight[] = [];
  try {
    const samples = (await hk.queryCategorySamples(
      'HKCategoryTypeIdentifierSleepAnalysis' as never,
      { filter: { startDate: start, endDate: end } } as never,
    )) as readonly unknown[] as Array<Record<string, unknown>>;

    // Group by "night of": a session starting after noon belongs to that
    // date; one starting before noon belongs to the previous date. Without
    // this, a 1am bedtime lands on the wrong day and every sleep number is
    // off by one.
    const byNight = new Map<string, { asleep: number; inBed: number; deep: number; rem: number; wakes: number }>();

    for (const s of samples) {
      const from = new Date(s.startDate as string);
      const to = new Date(s.endDate as string);
      const hours = (to.getTime() - from.getTime()) / 3_600_000;
      if (hours <= 0 || hours > 24) continue;

      const night = new Date(from);
      if (from.getHours() < 12) night.setDate(night.getDate() - 1);
      const key = isoDay(night);

      const acc = byNight.get(key) ?? { asleep: 0, inBed: 0, deep: 0, rem: 0, wakes: 0 };
      const value = Number(s.value);

      // HKCategoryValueSleepAnalysis: 0 inBed, 1 asleepUnspecified,
      // 2 awake, 3 asleepCore, 4 asleepDeep, 5 asleepREM
      if (value === 0) acc.inBed += hours;
      else if (value === 2) acc.wakes += 1;
      else {
        acc.asleep += hours;
        if (value === 4) acc.deep += hours;
        if (value === 5) acc.rem += hours;
      }
      byNight.set(key, acc);
    }

    for (const [night, acc] of byNight) {
      if (acc.asleep <= 0) continue;
      sleep.push({
        night_of: night,
        asleep_hours: Math.round(acc.asleep * 100) / 100,
        in_bed_hours: acc.inBed > 0 ? Math.round(acc.inBed * 100) / 100 : undefined,
        deep_hours: acc.deep > 0 ? Math.round(acc.deep * 100) / 100 : undefined,
        rem_hours: acc.rem > 0 ? Math.round(acc.rem * 100) / 100 : undefined,
        awakenings: acc.wakes || undefined,
      });
    }
  } catch {
    /* sleep permission denied or no data */
  }

  // --- Workouts ---------------------------------------------------------
  const workouts: ExternalWorkout[] = [];
  try {
    const samples = (await hk.queryWorkoutSamples({
      filter: { startDate: start, endDate: end },
    } as never)) as readonly unknown[] as Array<Record<string, unknown>>;

    for (const w of samples) {
      const from = new Date(w.startDate as string);
      const to = new Date(w.endDate as string);
      workouts.push({
        external_id: String(w.uuid),
        activity_type: String(w.workoutActivityType ?? 'other'),
        started_at: from.toISOString(),
        ended_at: to.toISOString(),
        duration_minutes:
          Math.round(((to.getTime() - from.getTime()) / 60_000) * 10) / 10,
        active_energy_kcal:
          (w.totalEnergyBurned as { quantity?: number })?.quantity ?? undefined,
        distance_km: (w.totalDistance as { quantity?: number })?.quantity
          ? Math.round(((w.totalDistance as { quantity: number }).quantity / 1000) * 100) / 100
          : undefined,
      });
    }
  } catch {
    /* no workout permission */
  }

  // --- Weight (a smart scale writing to Health flows straight in) --------
  const weights: Array<{ day: string; weight_kg: number }> = [];
  try {
    const samples = (await hk.queryQuantitySamples(
      'HKQuantityTypeIdentifierBodyMass' as never,
      { filter: { startDate: start, endDate: end } } as never,
    )) as readonly unknown[] as Array<Record<string, unknown>>;
    for (const s of samples) {
      weights.push({
        day: isoDay(new Date(s.startDate as string)),
        weight_kg: Math.round(Number(s.quantity) * 100) / 100,
      });
    }
  } catch {
    /* no body mass permission */
  }

  return {
    activity: [...activityByDay.values()].sort((a, b) => a.day.localeCompare(b.day)),
    sleep: sleep.sort((a, b) => a.night_of.localeCompare(b.night_of)),
    workouts,
    weights,
  };
}

async function readHealthConnect(start: Date, end: Date): Promise<HealthSnapshot> {
  const hc = await import('react-native-health-connect');
  await hc.initialize();

  const timeRangeFilter = {
    operator: 'between',
    startTime: start.toISOString(),
    endTime: end.toISOString(),
  } as const;

  const activityByDay = new Map<string, ActivityDay>();
  const bump = (day: string, patch: Partial<ActivityDay>) => {
    const existing = activityByDay.get(day) ?? { day };
    const merged = { ...existing } as Record<string, number | string>;
    for (const [k, v] of Object.entries(patch)) {
      if (typeof v === 'number') {
        merged[k] = ((merged[k] as number) ?? 0) + v;
      } else if (v != null) {
        merged[k] = v;
      }
    }
    activityByDay.set(day, merged as unknown as ActivityDay);
  };

  const read = async (recordType: string) => {
    try {
      const res = await hc.readRecords(recordType as never, { timeRangeFilter });
      return (res as { records?: Array<Record<string, unknown>> }).records ?? [];
    } catch {
      return [];
    }
  };

  for (const r of await read('Steps')) {
    bump(isoDay(new Date(r.startTime as string)), { steps: Number(r.count) });
  }
  for (const r of await read('ActiveCaloriesBurned')) {
    bump(isoDay(new Date(r.startTime as string)), {
      active_energy_kcal:
        (r.energy as { inKilocalories?: number })?.inKilocalories ?? 0,
    });
  }
  for (const r of await read('Distance')) {
    bump(isoDay(new Date(r.startTime as string)), {
      distance_km: ((r.distance as { inMeters?: number })?.inMeters ?? 0) / 1000,
    });
  }

  const sleep: SleepNight[] = [];
  for (const r of await read('SleepSession')) {
    const from = new Date(r.startTime as string);
    const to = new Date(r.endTime as string);
    const hours = (to.getTime() - from.getTime()) / 3_600_000;
    if (hours <= 0 || hours > 24) continue;
    const night = new Date(from);
    if (from.getHours() < 12) night.setDate(night.getDate() - 1);
    sleep.push({
      night_of: isoDay(night),
      asleep_hours: Math.round(hours * 100) / 100,
    });
  }

  const workouts: ExternalWorkout[] = [];
  for (const r of await read('ExerciseSession')) {
    const from = new Date(r.startTime as string);
    const to = new Date(r.endTime as string);
    workouts.push({
      external_id: String((r.metadata as { id?: string })?.id ?? `${r.startTime}`),
      activity_type: String(r.exerciseType ?? 'other'),
      started_at: from.toISOString(),
      ended_at: to.toISOString(),
      duration_minutes:
        Math.round(((to.getTime() - from.getTime()) / 60_000) * 10) / 10,
    });
  }

  const weights: Array<{ day: string; weight_kg: number }> = [];
  for (const r of await read('Weight')) {
    weights.push({
      day: isoDay(new Date(r.time as string)),
      weight_kg:
        Math.round(((r.weight as { inKilograms?: number })?.inKilograms ?? 0) * 100) / 100,
    });
  }

  return {
    activity: [...activityByDay.values()].sort((a, b) => a.day.localeCompare(b.day)),
    sleep,
    workouts,
    weights,
  };
}

// ---------------------------------------------------------------------------
// Writing back
// ---------------------------------------------------------------------------

export async function writeWeight(weightKg: number, when = new Date()): Promise<void> {
  try {
    if (Platform.OS === 'ios') {
      const hk = await import('@kingstinct/react-native-healthkit');
      await hk.saveQuantitySample(
        'HKQuantityTypeIdentifierBodyMass' as never,
        'kg' as never,
        weightKg,
        when,
        when,
      );
    } else if (Platform.OS === 'android') {
      const hc = await import('react-native-health-connect');
      await hc.insertRecords([
        {
          recordType: 'Weight',
          time: when.toISOString(),
          weight: { value: weightKg, unit: 'kilograms' },
        },
      ] as never);
    }
  } catch (err) {
    // Writing is a nice-to-have. Never surface a failure to the user.
    console.warn('[health] failed to write weight', err);
  }
}
