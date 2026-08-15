/**
 * Auth store.
 *
 * `status` is a three-state machine, not a boolean. The bug that boolean
 * `isLoggedIn` always produces: on cold start the value is `false` for a few
 * hundred milliseconds while SecureStore is read, the router sees "logged
 * out" and kicks an already-authenticated user to the login screen. Users
 * report that as "it logs me out randomly".
 *
 *   'restoring'  -> we haven't read storage yet. Render nothing, redirect
 *                   nowhere.
 *   'signedOut'  -> confirmed no valid session.
 *   'signedIn'   -> confirmed session.
 */

import { create } from 'zustand';

import { ApiError, NetworkError, api, tokens, setUnauthorizedHandler } from '../lib/api';

export type AuthStatus = 'restoring' | 'signedOut' | 'signedIn';

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  is_pro: boolean;
  goal_type: string;
}

export type SocialProvider = 'apple' | 'google' | 'github';

/**
 * OAuth client IDs, inlined at BUILD time like every EXPO_PUBLIC_ var.
 *
 * All three are unset today, which is why `socialSignIn` reports the provider
 * as unconfigured instead of opening a broken browser flow. To finish it:
 *
 *   1. Register the app with each provider (Apple Developer, Google Cloud
 *      console, GitHub OAuth Apps) and put the client IDs in .env.
 *   2. Add a backend route that accepts the provider's identity token,
 *      verifies it against that provider's public keys, and returns a Trace
 *      session — mirroring what POST /api/auth/login already returns.
 *   3. Replace the guard below with expo-auth-session (Google/GitHub) and
 *      expo-apple-authentication (Apple).
 *
 * Until step 2 exists there is no way to turn a Google identity into a Trace
 * account, so shipping a button that opens a browser would strand the user
 * mid-flow.
 */
const OAUTH_CLIENT_IDS: Record<SocialProvider, string | undefined> = {
  apple: process.env.EXPO_PUBLIC_APPLE_CLIENT_ID,
  google: process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID,
  github: process.env.EXPO_PUBLIC_GITHUB_CLIENT_ID,
};

const PROVIDER_NAMES: Record<SocialProvider, string> = {
  apple: 'Apple',
  google: 'Google',
  github: 'GitHub',
};

interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  error: string | null;
  submitting: boolean;

  restore: () => Promise<void>;
  login: (email: string, password: string) => Promise<boolean>;
  socialSignIn: (provider: SocialProvider) => Promise<boolean>;
  register: (payload: {
    email: string;
    password: string;
    display_name?: string;
    height_cm?: number;
    weight_kg?: number;
    goal_type?: string;
  }) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
}

/** Turn any thrown value into something a human can act on. */
function messageFor(err: unknown): string {
  if (err instanceof NetworkError) {
    // Distinguish "can't reach the server" from "server said no". These look
    // identical to users and have completely different fixes.
    return (
      "Can't reach Trace right now. Check your connection — if it keeps " +
      'happening the server may be down.'
    );
  }
  if (err instanceof ApiError) {
    if (err.status === 409) return 'An account with that email already exists.';
    if (err.status === 401) return 'Incorrect email or password.';
    if (err.status === 422) return 'Please check the details you entered.';
    return err.message;
  }
  return 'Something went wrong. Please try again.';
}

export const useAuth = create<AuthState>((set, get) => ({
  status: 'restoring',
  user: null,
  error: null,
  submitting: false,

  async restore() {
    const token = await tokens.getAccess();
    if (!token) {
      set({ status: 'signedOut', user: null });
      return;
    }
    try {
      // Validate against the server rather than trusting a stored token. A
      // token can be present but revoked, expired, or signed with a
      // JWT_SECRET the server no longer has.
      const user = await api.me();
      set({ status: 'signedIn', user });
    } catch (err) {
      if (err instanceof NetworkError) {
        // Offline: keep the user signed in rather than destroying their
        // session because their train went into a tunnel.
        set({ status: 'signedIn', user: get().user });
        return;
      }
      await tokens.clear();
      set({ status: 'signedOut', user: null });
    }
  },

  async login(email, password) {
    set({ submitting: true, error: null });
    try {
      const res = await api.login(email, password);
      set({ status: 'signedIn', user: res.user, submitting: false });
      return true;
    } catch (err) {
      set({ error: messageFor(err), submitting: false });
      return false;
    }
  },

  async socialSignIn(provider) {
    if (!OAUTH_CLIENT_IDS[provider]) {
      // Deliberately explicit. A button that silently does nothing reads as a
      // broken app; this says which piece is missing.
      set({
        error: `${PROVIDER_NAMES[provider]} sign-in isn't set up yet. Use your email and password for now.`,
      });
      return false;
    }
    set({
      error: `${PROVIDER_NAMES[provider]} sign-in is configured but the server can't exchange its token yet.`,
    });
    return false;
  },

  async register(payload) {
    set({ submitting: true, error: null });
    try {
      const res = await api.register(payload);
      set({ status: 'signedIn', user: res.user, submitting: false });
      return true;
    } catch (err) {
      set({ error: messageFor(err), submitting: false });
      return false;
    }
  },

  async logout() {
    await api.logout();
    set({ status: 'signedOut', user: null, error: null });
  },

  clearError: () => set({ error: null }),
}));

/**
 * When a refresh fails deep inside some unrelated request, the API client
 * calls this. Without it the app sits on a screen quietly 401-ing forever.
 */
setUnauthorizedHandler(() => {
  useAuth.setState({ status: 'signedOut', user: null });
});
