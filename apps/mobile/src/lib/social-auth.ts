/**
 * Native Google / Apple sign-in — the client half.
 *
 * WHAT THIS FILE'S JOB IS, EXACTLY
 * Get an **identity token** (a signed JWT) from the provider and hand it to
 * our own `POST /api/auth/social`, which verifies it and returns a Trace
 * session. This file never decides who the user is; it only fetches the
 * assertion. All of the trust lives on the server, because anything decided
 * here can be trivially faked by anyone running a modified client.
 *
 * WHY AN ID TOKEN AND NOT AN ACCESS TOKEN
 * An access token is a key to Google's APIs and says nothing verifiable about
 * identity — the server would have to call Google to find out who it belongs
 * to, adding a round trip and a dependency to every login. An ID token is
 * self-describing and signed, so the server verifies it offline.
 *
 * APPLE SENDS THE NAME EXACTLY ONCE
 * `credential.fullName` is populated on the very first authorization and is
 * null on every subsequent one — it is never in the token. If it is not
 * forwarded at that moment it is gone permanently, which is why
 * `displayName` is passed alongside the token rather than parsed out of it.
 *
 * WHY THE BUTTONS ASK THE SERVER FIRST
 * `configuredProviders()` hits `/api/auth/providers`. A button for a provider
 * the server cannot complete is worse than no button: the user taps,
 * authorises in a browser, and lands back in an app with no way to finish.
 */

import { Platform } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';

import { request } from './api';

// Required for the browser-based Google flow: without it the auth tab never
// hands control back and the promise hangs forever on Android.
WebBrowser.maybeCompleteAuthSession();

export type SocialProvider = 'apple' | 'google';

/**
 * A native Google app has a DIFFERENT client ID per platform, and the ID
 * token carries whichever one requested it. Configuring only the web ID is
 * the classic "works in the simulator, fails on my phone" — the token is
 * perfectly valid and then fails the server's audience check.
 */
export const GOOGLE_CLIENT_IDS = {
  ios: process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_IOS,
  android: process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_ANDROID,
  web: process.env.EXPO_PUBLIC_GOOGLE_CLIENT_ID_WEB,
};

export function googleConfigured(): boolean {
  return Boolean(
    GOOGLE_CLIENT_IDS.ios || GOOGLE_CLIENT_IDS.android || GOOGLE_CLIENT_IDS.web,
  );
}

/** Which providers the SERVER can actually complete. */
export async function configuredProviders(): Promise<SocialProvider[]> {
  try {
    const res = await request<{ providers: string[] }>('/api/auth/providers', {
      auth: false,
    });
    return res.providers.filter(
      (p): p is SocialProvider => p === 'google' || p === 'apple',
    );
  } catch {
    // Offline or the server is down. Show nothing rather than a button that
    // will strand the user halfway through a browser flow.
    return [];
  }
}

export async function appleAvailable(): Promise<boolean> {
  if (Platform.OS !== 'ios') return false;
  try {
    return await AppleAuthentication.isAvailableAsync();
  } catch {
    return false;
  }
}

export interface SocialAssertion {
  provider: SocialProvider;
  idToken: string;
  displayName?: string;
}

export class SocialCancelled extends Error {
  constructor() {
    super('cancelled');
    this.name = 'SocialCancelled';
  }
}

/**
 * Sign in with Apple.
 *
 * `identityToken` is the signed JWT the server verifies. `fullName` arrives
 * only the first time and is assembled here because Apple hands it back as
 * separate given/family fields, not a string.
 */
export async function signInWithApple(): Promise<SocialAssertion> {
  let credential: AppleAuthentication.AppleAuthenticationCredential;
  try {
    credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
    });
  } catch (e) {
    // Apple reports a user-cancelled sheet as a thrown error with this code.
    // Surfacing it as a failure would show an error message for something the
    // user did on purpose.
    if ((e as { code?: string })?.code === 'ERR_REQUEST_CANCELED') {
      throw new SocialCancelled();
    }
    throw e;
  }

  if (!credential.identityToken) {
    throw new Error('Apple did not return an identity token.');
  }

  const name = [credential.fullName?.givenName, credential.fullName?.familyName]
    .filter(Boolean)
    .join(' ')
    .trim();

  return {
    provider: 'apple',
    idToken: credential.identityToken,
    displayName: name || undefined,
  };
}

/**
 * The Google hook's config, for a screen to pass to `Google.useIdTokenAuthRequest`.
 *
 * Google's Expo integration is a HOOK, not a promise-returning function, so it
 * cannot live inside a zustand action — it has to be called at the top level
 * of a component. The screen owns the hook; this just centralises the config
 * so the client IDs are declared in one place.
 */
export function googleAuthConfig() {
  return {
    iosClientId: GOOGLE_CLIENT_IDS.ios,
    androidClientId: GOOGLE_CLIENT_IDS.android,
    webClientId: GOOGLE_CLIENT_IDS.web,
    // We want the identity assertion, not API access.
    scopes: ['openid', 'profile', 'email'],
  };
}

export { Google };
