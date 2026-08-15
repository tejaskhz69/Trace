/**
 * Appearance mode: Dark (lifted surfaces) or Black (true #000000, OLED).
 *
 * Only the surface ramp changes between modes -- text and accents are shared
 * -- so a screen themes itself by reading `useSurfaces()` for backgrounds and
 * borders and taking everything else from the static `palette`.
 *
 * The choice is read from storage BEFORE the first paint (see `restore()`,
 * called from the root layout alongside the auth restore) so the app never
 * flashes the wrong ground on cold start.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import { Mode, Surfaces, surfaces } from '../theme';

const KEY = 'trace.appearanceMode';

interface ThemeState {
  mode: Mode;
  /** False until storage has been read; the root layout gates the splash on it. */
  ready: boolean;
  restore: () => Promise<void>;
  setMode: (mode: Mode) => void;
  toggle: () => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  mode: 'dark',
  ready: false,

  async restore() {
    try {
      const stored = await AsyncStorage.getItem(KEY);
      set({
        mode: stored === 'black' || stored === 'dark' ? stored : 'dark',
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
    AsyncStorage.setItem(KEY, mode).catch(() => undefined);
  },

  toggle() {
    get().setMode(get().mode === 'dark' ? 'black' : 'dark');
  },
}));

/** The active surface ramp. Re-renders only when the mode actually changes. */
export function useSurfaces(): Surfaces {
  return surfaces[useTheme((s) => s.mode)];
}
