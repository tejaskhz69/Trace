/**
 * Coach + today's activity state.
 *
 * The coach briefing is deliberately non-blocking on the home screen: it
 * arrives after the calorie block and never gates it. A user opening the app
 * to check what they have left must never wait on a coaching computation.
 */

import { create } from 'zustand';

import { request } from '../lib/api';

export interface CoachInsight {
  key: string;
  urgency: number;
  lever: string;
  headline: string;
  detail: string;
  action: string | null;
  evidence: Record<string, unknown>;
  confidence: number;
}

export interface ActivityToday {
  steps: number | null;
  active_energy_kcal: number | null;
  exercise_minutes: number | null;
  sessions_today: number;
  steps_vs_baseline: number | null;
  synced_at: string | null;
}

export interface Briefing {
  for_date: string;
  primary: CoachInsight | null;
  secondary: CoachInsight[];
  prompts: string[];
  data_completeness: number;
  neat: Record<string, unknown> | null;
  sleep: Record<string, unknown> | null;
  energy_reconciliation: Record<string, unknown> | null;
  activity_today: ActivityToday | null;
  step_history: number[];
}

interface CoachState {
  briefing: Briefing | null;
  loading: boolean;
  lastLoadedAt: number | null;
  load: (opts?: { force?: boolean }) => Promise<void>;
}

const STALE_MS = 5 * 60_000; // the coach changes slowly; don't refetch on every focus

export const useCoach = create<CoachState>((set, get) => ({
  briefing: null,
  loading: false,
  lastLoadedAt: null,

  async load(opts) {
    const { loading, lastLoadedAt } = get();
    if (loading) return;
    if (!opts?.force && lastLoadedAt && Date.now() - lastLoadedAt < STALE_MS) {
      return;
    }

    set({ loading: true });
    try {
      const briefing = await request<Briefing>('/api/health/coach');
      set({ briefing, loading: false, lastLoadedAt: Date.now() });
    } catch {
      // A missing coach briefing is normal for a new user -- it is never an
      // error state and must never show an error banner.
      set({ loading: false, lastLoadedAt: Date.now() });
    }
  },
}));
