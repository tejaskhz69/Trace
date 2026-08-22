/**
 * Answers held across the signup boundary.
 *
 * WHY THIS STORE EXISTS
 * The questionnaire now runs BEFORE the account. Someone answers eight
 * questions, sees their calorie target, and only then is asked to create an
 * account — so between "here is your number" and "you are signed in" there is
 * a navigation, and the answers have to survive it.
 *
 * WHY IT IS PERSISTED RATHER THAN JUST IN MEMORY
 * The signup step is where a phone call comes in, the app gets backgrounded,
 * and iOS reclaims it. Losing eight answers at the exact moment someone
 * decided to commit is the worst possible time to lose them — they do not
 * start again, they leave. AsyncStorage costs one write and removes that
 * failure entirely.
 *
 * IT IS CLEARED THE MOMENT IT IS SPENT. `submitOnboarding` succeeding is the
 * signal; leaving stale answers behind would re-submit somebody else's plan
 * onto the next account created on the same device.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import type { OnboardingAnswers, OnboardingPlan } from '../lib/api';

const KEY = 'trace.pendingOnboarding';

interface OnboardingState {
  answers: OnboardingAnswers | null;
  plan: OnboardingPlan | null;
  hydrated: boolean;

  /** Stash what was answered, on the way to the account screen. */
  stash: (answers: OnboardingAnswers, plan: OnboardingPlan | null) => Promise<void>;
  /** Read it back after a cold start mid-signup. */
  hydrate: () => Promise<void>;
  clear: () => Promise<void>;
}

export const useOnboarding = create<OnboardingState>((set) => ({
  answers: null,
  plan: null,
  hydrated: false,

  async stash(answers, plan) {
    set({ answers, plan });
    try {
      await AsyncStorage.setItem(KEY, JSON.stringify({ answers, plan }));
    } catch {
      // A storage failure must not block signup. The in-memory copy still
      // carries the user through as long as the app is not killed.
    }
  },

  async hydrate() {
    try {
      const raw = await AsyncStorage.getItem(KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        set({ answers: parsed.answers ?? null, plan: parsed.plan ?? null });
      }
    } catch {
      // Corrupt payload: treat as nothing pending rather than crashing the
      // root layout, which would make the app unopenable.
    } finally {
      set({ hydrated: true });
    }
  },

  async clear() {
    set({ answers: null, plan: null });
    await AsyncStorage.removeItem(KEY).catch(() => undefined);
  },
}));
