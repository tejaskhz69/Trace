/**
 * Health sync: the glue between `lib/health.ts` (reads the phone) and
 * `POST /api/health/sync` (writes the server).
 *
 * Both ends already existed and nothing connected them. This is that wire.
 *
 * WHAT THIS IS NOT
 * It is not a calorie source. Everything synced here is for EXPLANATION and
 * reconciliation — NEAT drift, sleep debt, activity context. `active_energy`
 * never reaches a calorie target (CLAUDE.md non-negotiable #1, argued in full
 * in `services/activity.py`). If you find yourself adding a number from here
 * to a target, stop.
 *
 * THE WATERMARK
 * A first-ever sync can carry years of HealthKit history, and the server caps
 * each request at MAX_BATCH records per type. So we track how far we've
 * synced and only ever read forward from there, with a small overlap so a day
 * that was still accumulating when we last looked gets re-sent. Every upsert
 * server-side is keyed on a natural key, so re-sending is free.
 *
 * WHY PERMISSION STATE IS NOT A BOOLEAN
 * iOS deliberately refuses to tell you whether READ access was granted —
 * saying "denied" would itself leak health information. So there is no
 * "granted" to store. `status` tracks what we have OBSERVED: whether the
 * native module exists, whether we've asked, and whether a read returned
 * anything. "asked but empty" is genuinely ambiguous and is labelled as such.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import {
  healthPlatform,
  isHealthAvailable,
  readSnapshot,
  requestPermissions,
  type HealthPlatform,
} from '../lib/health';
import { request } from '../lib/api';

const WATERMARK_KEY = 'trace.health.syncedThrough';

/** The server rejects more than this per type, per request. */
const MAX_BATCH = 400;

/**
 * Re-read this many days before the watermark on every sync.
 *
 * Today's step count is still climbing when we sync at 2pm, and a workout
 * edited yesterday changes after we've already sent it. Without the overlap
 * those corrections would never arrive.
 */
const OVERLAP_DAYS = 3;

/** How much history to pull on the very first sync. */
const FIRST_SYNC_DAYS = 90;

export type HealthStatus =
  | 'unknown'        // haven't looked yet
  | 'unsupported'    // web, or a build with no native module (Expo Go)
  | 'unavailable'    // platform supports it, device/SDK doesn't
  | 'ready'          // asked for permission, module present
  | 'syncing'
  | 'error';

interface HealthSyncResponse {
  activity_days_written: number;
  sleep_nights_written: number;
  workouts_written: number;
  synced_through: string | null;
  message: string;
}

interface HealthState {
  platform: HealthPlatform;
  status: HealthStatus;
  /** ISO date we have synced through, or null if never. */
  syncedThrough: string | null;
  lastResult: HealthSyncResponse | null;
  error: string | null;
  /**
   * True when a sync completed but the phone returned nothing at all. On iOS
   * this is ambiguous by design — either permission was refused, or there is
   * genuinely no data. The UI must say both, not guess.
   */
  emptyAfterSync: boolean;

  init: () => Promise<void>;
  connect: () => Promise<boolean>;
  sync: (opts?: { full?: boolean }) => Promise<boolean>;
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function daysBetween(iso: string): number {
  const then = new Date(`${iso}T00:00:00Z`).getTime();
  if (Number.isNaN(then)) return FIRST_SYNC_DAYS;
  const diff = (Date.now() - then) / 86_400_000;
  return Math.max(1, Math.ceil(diff));
}

export const useHealth = create<HealthState>((set, get) => ({
  platform: healthPlatform(),
  status: 'unknown',
  syncedThrough: null,
  lastResult: null,
  error: null,
  emptyAfterSync: false,

  async init() {
    const platform = healthPlatform();
    if (platform === 'unavailable') {
      set({ platform, status: 'unsupported' });
      return;
    }

    const stored = await AsyncStorage.getItem(WATERMARK_KEY).catch(() => null);

    // `isHealthAvailable` returns false when the native module is missing,
    // which is the Expo Go case. That is "unsupported" (needs a development
    // build), not "unavailable" (device can't do it) — the fixes differ and
    // the UI tells the user which one they're looking at.
    const available = await isHealthAvailable();
    set({
      platform,
      syncedThrough: stored,
      status: available ? 'ready' : 'unsupported',
    });
  },

  async connect() {
    const { platform } = get();
    if (platform === 'unavailable') {
      set({ status: 'unsupported' });
      return false;
    }
    try {
      // On iOS the return value says nothing about READ access; treat it as
      // "the sheet was shown without throwing" and let the sync find out.
      await requestPermissions(true);
      set({ status: 'ready', error: null });
      return get().sync({ full: true });
    } catch (err) {
      set({
        status: 'error',
        error:
          err instanceof Error
            ? err.message
            : 'Could not open the health permission screen.',
      });
      return false;
    }
  },

  async sync(opts) {
    const { platform, syncedThrough, status } = get();
    if (platform === 'unavailable' || status === 'syncing') return false;

    set({ status: 'syncing', error: null });

    try {
      const days = opts?.full
        ? FIRST_SYNC_DAYS
        : syncedThrough
          ? daysBetween(syncedThrough) + OVERLAP_DAYS
          : FIRST_SYNC_DAYS;

      const snapshot = await readSnapshot(days);

      // Newest first, then truncate: if a first sync overflows the batch cap,
      // the days the user cares about are the recent ones. The rest arrive on
      // the next sync as the watermark walks backwards... which it doesn't —
      // so cap by taking the most recent, and accept that a very long history
      // is trimmed rather than dropping the sync entirely.
      const activity = [...snapshot.activity]
        .sort((a, b) => (a.day < b.day ? 1 : -1))
        .slice(0, MAX_BATCH);
      const sleep = [...snapshot.sleep]
        .sort((a, b) => (a.night_of < b.night_of ? 1 : -1))
        .slice(0, MAX_BATCH);
      const workouts = [...snapshot.workouts]
        .sort((a, b) => (a.started_at < b.started_at ? 1 : -1))
        .slice(0, MAX_BATCH);

      const empty =
        activity.length === 0 && sleep.length === 0 && workouts.length === 0;

      if (empty) {
        // Nothing to send. Don't POST an empty body — it would move the
        // watermark forward and hide the fact that we never got data.
        set({ status: 'ready', emptyAfterSync: true });
        return true;
      }

      const result = await request<HealthSyncResponse>('/api/health/sync', {
        method: 'POST',
        body: { source: platform, activity, sleep, workouts },
        timeoutMs: 30_000,
      });

      const mark = result.synced_through ?? daysAgo(0);
      await AsyncStorage.setItem(WATERMARK_KEY, mark).catch(() => undefined);

      set({
        status: 'ready',
        syncedThrough: mark,
        lastResult: result,
        emptyAfterSync: false,
      });
      return true;
    } catch (err) {
      set({
        status: 'error',
        error:
          err instanceof Error ? err.message : 'Health sync failed. Try again.',
      });
      return false;
    }
  },
}));

/** A one-line description of where sync stands, for the Profile row. */
export function healthSummary(s: HealthState): string {
  switch (s.status) {
    case 'unsupported':
      return 'Needs a development build';
    case 'unavailable':
      return 'Not available on this device';
    case 'syncing':
      return 'Syncing…';
    case 'error':
      return 'Tap to retry';
    case 'ready':
      if (s.emptyAfterSync) return 'No data shared yet';
      return s.syncedThrough ? `Synced ${s.syncedThrough}` : 'Connect';
    default:
      return 'Connect';
  }
}
