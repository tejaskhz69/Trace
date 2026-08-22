/**
 * Appearance: two independent axes.
 *
 *   mode   -- Dark (lifted surfaces) or Black (true #000000, OLED)
 *   accent -- Green or White, the INTERACTION accent only
 *
 * They are independent on purpose. Mode changes the ground the app is painted
 * on; accent changes what a button and an active tab look like. Neither
 * touches the chart series or the macro channels, because those carry data and
 * data must not restyle on a preference.
 *
 * Both are read from storage BEFORE the first paint (see `restore()`, called
 * from the root layout alongside the auth restore) so the app never flashes
 * the wrong ground or the wrong accent on cold start.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import { Accent, AccentTokens, Mode, Surfaces, accents, surfaces } from '../theme';

const MODE_KEY = 'trace.appearanceMode';
const ACCENT_KEY = 'trace.accent';

interface ThemeState {
  mode: Mode;
  accent: Accent;
  /** False until storage has been read; the root layout gates the splash on it. */
  ready: boolean;
  restore: () => Promise<void>;
  setMode: (mode: Mode) => void;
  toggle: () => void;
  setAccent: (accent: Accent) => void;
  toggleAccent: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  mode: 'dark',
  // Green is the default. The white accent is the alternative the user can
  // choose, matching the artifact's Profile › Appearance switch.
  accent: 'green',
  ready: false,

  async restore() {
    try {
      // One round trip rather than two sequential reads -- this sits on the
      // cold-start path and the splash is held until it resolves.
      const [[, storedMode], [, storedAccent]] = await AsyncStorage.multiGet([
        MODE_KEY,
        ACCENT_KEY,
      ]);
      set({
        mode: storedMode === 'black' || storedMode === 'dark' ? storedMode : 'dark',
        accent: storedAccent === 'white' || storedAccent === 'green' ? storedAccent : 'green',
        ready: true,
      });
    } catch {
      // A storage failure must never block the app from rendering.
      set({ ready: true });
    }
  },

  setMode(mode) {
    set({ mode });
    // Fire-and-forget: the UI has already switched, and a failed write only
    // means the preference doesn't survive a restart.
    AsyncStorage.setItem(MODE_KEY, mode).catch(() => undefined);
  },

  toggle() {
    get().setMode(get().mode === 'dark' ? 'black' : 'dark');
  },

  setAccent(accent) {
    set({ accent });
    AsyncStorage.setItem(ACCENT_KEY, accent).catch(() => undefined);
  },

  toggleAccent() {
    get().setAccent(get().accent === 'green' ? 'white' : 'green');
  },
}));

/** The active surface ramp. Re-renders only when the mode actually changes. */
export function useSurfaces(): Surfaces {
  return surfaces[useTheme((s) => s.mode)];
}

/**
 * The active accent tokens.
 *
 * Primitives call this themselves rather than taking an accent prop, so a
 * screen never has to thread it through — and so no screen can accidentally
 * hardcode green while the user has chosen white.
 */
export function useAccent(): AccentTokens {
  return accents[useTheme((s) => s.accent)];
}
