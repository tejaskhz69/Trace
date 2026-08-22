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
import {
  SocialCancelled,
  signInWithApple,
  type SocialAssertion,
} from '../lib/social-auth';

export type AuthStatus = 'restoring' | 'signedOut' | 'signedIn';

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  is_pro: boolean;
  goal_type: string;
  /**
   * ISO timestamp, or null if the questionnaire hasn't been completed.
   *
   * The root layout routes on this. It comes from the server rather than local
   * storage on purpose: a reinstall, or signing in on a second device, must
   * not re-ask a user questions they have already answered.
   */
  onboarded_at?: string | null;
}

export type SocialProvider = 'apple' | 'google' | 'github';

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
  /** Hand a fetched provider token to the server. Used by the Google flow. */
  completeSocial: (assertion: SocialAssertion) => Promise<boolean>;
  /** Exchange a phone number and its one-time code for a session. */
  completePhone: (phone: string, code: string) => Promise<boolean>;
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

  /**
   * Exchange a provider identity token for a Trace session.
   *
   * THE CLIENT DOES NOT DECIDE WHO THE USER IS. It fetches a signed assertion
   * and hands it over; `POST /api/auth/social` verifies the signature and the
   * audience before it believes a single field. Anything decided here could
   * be faked by anyone running a modified build.
   *
   * The GOOGLE path is not here on purpose: Google's Expo integration is a
   * React hook, so it must be called from a component. The screen fetches the
   * token and calls `completeSocial` with it.
   */
  async socialSignIn(provider) {
    if (provider === 'github') {
      set({
        error: 'GitHub sign-in is not available. Use Google, Apple, or your email.',
      });
      return false;
    }
    if (provider === 'apple') {
      set({ submitting: true, error: null });
      try {
        const assertion = await signInWithApple();
        return await get().completeSocial(assertion);
      } catch (err) {
        // A cancelled sheet is not a failure. Showing an error for something
        // the user did on purpose is how an app feels broken.
        if (err instanceof SocialCancelled) {
          set({ submitting: false });
          return false;
        }
        set({ error: messageFor(err), submitting: false });
        return false;
      }
    }
    set({
      error: 'Start Google sign-in from the sign-in screen.',
    });
    return false;
  },

  async completeSocial(assertion) {
    set({ submitting: true, error: null });
    try {
      const res = await api.socialSignIn(
        assertion.provider,
        assertion.idToken,
        assertion.displayName,
      );
      set({ status: 'signedIn', user: res.user, submitting: false });
      return true;
    } catch (err) {
      set({ error: messageFor(err), submitting: false });
      return false;
    }
  },

  async completePhone(phone, code) {
    set({ submitting: true, error: null });
    try {
      const res = await api.phoneVerify(phone, code);
      set({ status: 'signedIn', user: res.user, submitting: false });
      return true;
    } catch (err) {
      // The server's message is the useful one here -- it counts down the
      // remaining attempts, which a generic string cannot.
      set({
        error: err instanceof ApiError ? err.message : messageFor(err),
        submitting: false,
      });
      return false;
    }
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
