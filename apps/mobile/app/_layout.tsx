/**
 * Root layout + auth gate.
 *
 * The redirect logic is deliberately conservative: while `status` is
 * 'restoring' we render a splash and navigate NOWHERE. Redirecting during
 * restore is what produces the "it logged me out on cold start" bug — the
 * router fires before SecureStore has answered.
 */

import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import Animated, { FadeIn } from 'react-native-reanimated';
import {
  useFonts,
  IBMPlexSans_300Light,
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
  IBMPlexSans_700Bold,
} from '@expo-google-fonts/ibm-plex-sans';

import { api } from '../src/lib/api';
import { useAuth } from '../src/state/useAuth';
import { useOnboarding } from '../src/state/useOnboarding';
import { useSurfaces, useTheme } from '../src/state/useTheme';
import { motion, palette, type } from '../src/theme';

export default function RootLayout() {
  const status = useAuth((s) => s.status);
  const user = useAuth((s) => s.user);
  const restore = useAuth((s) => s.restore);
  // `restore` re-reads the session and the user, which is what we need
  // after submitting onboarding: `onboarded_at` has just changed.
  const refreshUser = useAuth((s) => s.restore);
  const pendingAnswers = useOnboarding((s) => s.answers);
  const clearPending = useOnboarding((s) => s.clear);
  const hydratePending = useOnboarding((s) => s.hydrate);
  const themeReady = useTheme((s) => s.ready);
  const restoreTheme = useTheme((s) => s.restore);
  const surfaces = useSurfaces();
  const segments = useSegments();
  const router = useRouter();

  const [fontsLoaded] = useFonts({
    IBMPlexSans_300Light,
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexSans_700Bold,
  });

  useEffect(() => {
    restore();
    restoreTheme();
    hydratePending();
  }, [restore, restoreTheme, hydratePending]);

  const booted = status !== 'restoring' && fontsLoaded && themeReady;

  useEffect(() => {
    if (!booted) return; // <- the important line

    const inAuthGroup = segments[0] === '(auth)';
    const inOnboarding = segments[0] === '(onboarding)';

    // Three destinations, not two. The order matters: a signed-in user who
    // has never answered the questionnaire goes to onboarding, NOT to the
    // tabs — the Today screen has no calorie target to show them until they
    // do, and an empty dashboard is the worst possible first impression.
    //
    // `onboarded_at === undefined` (rather than null) means the field wasn't
    // in the response at all, which happens against an older server. Treating
    // that as "already onboarded" is the safe failure: it lets an existing
    // user into the app instead of trapping them in a wizard they can't
    // complete.
    const needsOnboarding =
      status === 'signedIn' && user !== null && user.onboarded_at === null;

    // Answers collected BEFORE the account existed. Submitting them here, in
    // one place, covers every way in -- phone, email, Google, Apple -- rather
    // than repeating the same block at four call sites.
    if (status === 'signedIn' && pendingAnswers && needsOnboarding) {
      api
        .submitOnboarding(pendingAnswers)
        .then(() => clearPending())
        .then(() => refreshUser())
        .catch(() => {
          // Keep the answers. A failed submit here must not silently discard
          // eight questions -- the onboarding screen will offer to retry.
        });
      return;
    }

    if (status === 'signedOut' && !inAuthGroup && !inOnboarding) {
      // A SIGNED-OUT USER GETS THE QUESTIONNAIRE, NOT A LOGIN WALL.
      // Asking someone to create an account before they have seen anything
      // is asking for a commitment with no payoff attached. They answer eight
      // questions, get a real calorie target computed from their own numbers,
      // and only then are asked to save it -- at which point the ask is worth
      // something. `/api/onboarding/preview` is unauthenticated precisely so
      // this is possible. "I have an account" on that screen is the way past
      // it for returning users.
      router.replace('/(onboarding)');
    } else if (needsOnboarding && !inOnboarding) {
      router.replace('/(onboarding)');
    } else if (status === 'signedIn' && !needsOnboarding && (inAuthGroup || inOnboarding)) {
      router.replace('/(tabs)');
    }
  }, [
    booted,
    status,
    user,
    segments,
    router,
    pendingAnswers,
    clearPending,
    refreshUser,
  ]);

  // Hold the splash until auth, fonts AND the appearance mode all resolve.
  // Painting before the mode is known would flash the wrong ground, and
  // painting before the font loads would repaint the wordmark a frame later.
  if (!booted) {
    return (
      <View style={[styles.splash, { backgroundColor: surfaces.void }]}>
        <Animated.Text entering={FadeIn.duration(motion.base)} style={styles.wordmark}>
          Trace
        </Animated.Text>
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={styles.flex}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: surfaces.void },
            // Slide, never a jarring cut. Matches the 200-300ms spec.
            animation: 'slide_from_right',
            animationDuration: motion.base,
          }}
        >
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="(auth)/login" />
          <Stack.Screen name="(auth)/signup" />
          {/* Phone + OTP is the primary sign-in path on mobile; email is
              the fallback for people who prefer it. */}
          <Stack.Screen name="(auth)/phone" />
          {/* No back gesture: leaving the questionnaire half-finished lands
              on a dashboard with no targets, which looks broken. */}
          <Stack.Screen name="(onboarding)/index" options={{ gestureEnabled: false }} />
          {/* Pushed from the Trainer list. Slides in so the back gesture
              returns to the exact scroll position the user left. */}
          <Stack.Screen name="exercise/[id]" />
          {/* Search lives one screen deeper than the Nutrition tab so the
              four entry tiles stay above the fold. */}
          <Stack.Screen name="food-search" />
          <Stack.Screen
            name="scan"
            options={{ presentation: 'fullScreenModal', animation: 'fade' }}
          />
          <Stack.Screen
            name="scan-review"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
          {/* The live set logger. No back gesture: a swipe mid-set would drop
              the lifter out of the session they are standing in, and the
              screen has its own explicit Back and Finish. */}
          <Stack.Screen name="workout/[session]" options={{ gestureEnabled: false }} />
          {/* The summary replaces the logger rather than stacking on it, so
              Back from here cannot walk into a session that just ended. */}
          <Stack.Screen name="workout/summary" options={{ gestureEnabled: false }} />
          <Stack.Screen
            name="workout/voice"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
          <Stack.Screen name="workout/history" />
        </Stack>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  splash: {
    // backgroundColor comes from the active mode at render time.
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // type.display already names the Bold face; no fontWeight on top of it.
  wordmark: { ...type.display, color: palette.text, letterSpacing: 6 },
});
