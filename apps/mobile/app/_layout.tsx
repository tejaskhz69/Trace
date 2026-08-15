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

import { useAuth } from '../src/state/useAuth';
import { useSurfaces, useTheme } from '../src/state/useTheme';
import { motion, palette, type } from '../src/theme';

export default function RootLayout() {
  const status = useAuth((s) => s.status);
  const restore = useAuth((s) => s.restore);
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
  }, [restore, restoreTheme]);

  const booted = status !== 'restoring' && fontsLoaded && themeReady;

  useEffect(() => {
    if (!booted) return; // <- the important line

    const inAuthGroup = segments[0] === '(auth)';

    if (status === 'signedOut' && !inAuthGroup) {
      router.replace('/(auth)/login');
    } else if (status === 'signedIn' && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [booted, status, segments, router]);

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
          <Stack.Screen
            name="scan"
            options={{ presentation: 'fullScreenModal', animation: 'fade' }}
          />
          <Stack.Screen
            name="scan-review"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
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
