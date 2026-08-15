/**
 * Today's data: daily summary + the current weekly verdict.
 *
 * Two things worth noting:
 *
 *  - `loading` and `refreshing` are separate. Pull-to-refresh must not blank
 *    the screen back to skeletons; that reads as a crash.
 *  - A failed verdict fetch is NOT an error state. The verdict legitimately
 *    doesn't exist until a user has ~3 weeks of data, and the API returns 422
 *    for that. Treating it as an error would show a scary banner to every new
 *    user for their first three weeks.
 */

import { create } from 'zustand';

import { ApiError, DailySummary, api } from '../lib/api';

export interface Verdict {
  id: string;
  verdict: string;
  headline: string;
  explanation: string;
  strength_index_delta_pct: number | null;
  weight_delta_pct_per_week: number | null;
  recommended_target: number | null;
  math_breakdown: Record<string, unknown>;
  guardrails_triggered: string[];
}

interface TodayState {
  summary: DailySummary | null;
  verdict: Verdict | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastLoadedAt: number | null;

  load: (opts?: { force?: boolean }) => Promise<void>;
  refresh: () => Promise<void>;
  applyOptimisticMeal: (kcal: number, p: number, c: number, f: number) => void;
}

const STALE_MS = 30_000;

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export const useToday = create<TodayState>((set, get) => ({
  summary: null,
  verdict: null,
  loading: false,
  refreshing: false,
  error: null,
  lastLoadedAt: null,

  async load(opts) {
    const { lastLoadedAt, loading } = get();
    if (loading) return;
    if (
      !opts?.force &&
      lastLoadedAt &&
      Date.now() - lastLoadedAt < STALE_MS
    ) {
      return; // avoid refetching on every tab focus
    }

    set({ loading: true, error: null });
    try {
      // Fire both together; the verdict must never block the summary.
      const [summary, verdict] = await Promise.allSettled([
        api.dailySummary(today()),
        api.weeklyVerdict(),
      ]);

      set({
        summary:
          summary.status === 'fulfilled' ? summary.value : get().summary,
        verdict:
          verdict.status === 'fulfilled'
            ? (verdict.value as unknown as Verdict)
            : // 422 = not enough data yet. That is normal, not an error.
              verdict.reason instanceof ApiError && verdict.reason.status === 422
              ? null
              : get().verdict,
        error:
          summary.status === 'rejected'
            ? 'Couldn&apos;t load today&apos;s data.'
            : null,
        loading: false,
        lastLoadedAt: Date.now(),
      });
    } catch {
      set({ loading: false, error: 'Something went wrong.' });
    }
  },

  async refresh() {
    set({ refreshing: true });
    await get().load({ force: true });
    set({ refreshing: false });
  },

  /**
   * Update the ring the instant a meal is logged, before the server responds.
   * The ring animates from the old value to the new one on the UI thread, so
   * this feels instant even on a slow connection.
   */
  applyOptimisticMeal(kcal, p, c, f) {
    const s = get().summary;
    if (!s) return;
    set({
      summary: {
        ...s,
        calories: s.calories + kcal,
        protein_g: s.protein_g + p,
        carbs_g: s.carbs_g + c,
        fat_g: s.fat_g + f,
      },
      lastLoadedAt: null, // force a real refetch next time
    });
  },
}));
