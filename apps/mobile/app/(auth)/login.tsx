/**
 * LOGIN — instrument panel.
 *
 * The design argument: a login screen is the only screen every user sees, and
 * it sets the expectation for everything after it. A generic centred logo and
 * two rounded inputs says "another wellness app". A boot sequence with a
 * status line says "this thing measures".
 *
 * Functionally unchanged from the version that fixed your login bug — all the
 * anti-case-mismatch props are still here, and so is the triple-tap
 * diagnostic. Redesigning must never quietly drop a bug fix.
 *
 * Social sign-in is UI-complete but NOT yet wired to a provider: each button
 * routes through `useAuth().socialSignIn`, which reports that the provider
 * has no credentials rather than failing silently. See the OAuth section in
 * src/state/useAuth.ts for exactly what has to be filled in.
 */

import React, { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Link, useRouter } from 'expo-router';
import Animated, {
  Easing,
  FadeIn,
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';

import { Button, Label, Rule } from '../../src/components/instrument';
import { useAuth, SocialProvider } from '../../src/state/useAuth';
import {
  Google,
  appleAvailable,
  configuredProviders,
  googleAuthConfig,
  googleConfigured,
} from '../../src/lib/social-auth';
import { useSurfaces } from '../../src/state/useTheme';
import { API_BASE_URL } from '../../src/lib/api';
import { HAIRLINE, motion, palette, radius, space, type } from '../../src/theme';

export default function LoginScreen() {
  const router = useRouter();
  const { login, socialSignIn, completeSocial, submitting, error, clearError } =
    useAuth();
  const surfaces = useSurfaces();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [focused, setFocused] = useState<'email' | 'password' | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  /**
   * Which social buttons to render.
   *
   * Asked of the SERVER, not inferred from local env vars. The client IDs and
   * the server's verification config can drift apart, and the failure that
   * causes is the worst kind: the browser flow completes, the user is
   * authorised with Google, and then the exchange 401s with nowhere to go.
   * The server is the one that knows whether it can finish the job.
   */
  const [providers, setProviders] = useState<string[] | null>(null);
  const [hasApple, setHasApple] = useState(false);

  useEffect(() => {
    let alive = true;
    configuredProviders().then((p) => alive && setProviders(p));
    appleAvailable().then((a) => alive && setHasApple(a));
    return () => {
      alive = false;
    };
  }, []);

  const canSubmit = email.trim().length > 3 && password.length >= 8;

  async function onSubmit() {
    if (!canSubmit || submitting) return;
    const ok = await login(email, password);
    if (ok) router.replace('/(tabs)');
  }

  async function onSocial(provider: SocialProvider) {
    if (submitting) return;
    const ok = await socialSignIn(provider);
    if (ok) router.replace('/(tabs)');
  }

  return (
    <KeyboardAvoidingView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        {/* ---- Identity block ---------------------------------------- */}
        <Animated.View entering={FadeIn.duration(motion.base)}>
          <View style={styles.markRow}>
            <StatusDot />
            <Pressable
              onPress={() => setShowDiagnostics((v) => !v)}
              hitSlop={12}
              accessibilityLabel="Show connection diagnostics"
            >
              <Text style={styles.wordmark}>TRACE</Text>
            </Pressable>
          </View>

          <Rule style={{ marginVertical: space.lg }} />

          <Text style={styles.tagline}>
            Know whether you&apos;re{'\n'}
            <Text style={styles.taglineAccent}>gaining muscle or fat.</Text>
          </Text>
        </Animated.View>

        {/* ---- Continue with … --------------------------------------- */}
        <Animated.View
          entering={FadeInDown.duration(motion.base).delay(60)}
          style={styles.oauth}
        >
          {/* Apple requires its button on iOS if you offer any other social
              login (App Store guideline 4.8), and it does not exist on
              Android, so it is iOS-only by design rather than by oversight.

              Every button here is gated on the SERVER reporting it can
              complete the exchange. A button that opens a browser and then
              cannot finish strands the user outside the app, which is worse
              than not offering the option at all. */}
          {providers?.includes('apple') && hasApple && (
            <SocialButton
              provider="apple"
              label="Continue with Apple"
              onPress={() => onSocial('apple')}
              disabled={submitting}
              primary
            />
          )}
          {/* Mounted ONLY when Google is genuinely configured. The hook
              inside it throws with no client id, and a hook cannot be called
              conditionally -- so the CONDITION HAS TO BE ON THE COMPONENT.
              Calling it unconditionally is what crashed this screen. */}
          {providers?.includes('google') && googleConfigured() ? (
            <GoogleButton disabled={submitting} />
          ) : null}
          {/* Always offered, and listed first among the alternatives: it is
              the path with no password to invent or forget, and the one this
              market actually expects. */}
          <SocialButton
            provider="phone"
            label="Continue with a phone number"
            onPress={() => router.push('/(auth)/phone')}
            disabled={submitting}
          />
          {providers?.length === 0 ? (
            <Text style={styles.noProviders}>
              Google and Apple sign-in aren&apos;t configured on this server
              yet. Use your phone number or your email below.
            </Text>
          ) : null}
        </Animated.View>

        <Animated.View
          entering={FadeIn.duration(motion.base).delay(100)}
          style={styles.orRow}
        >
          <Rule style={styles.orRule} />
          <Label color={palette.textGhost}>or</Label>
          <Rule style={styles.orRule} />
        </Animated.View>

        {/* ---- Credentials ------------------------------------------- */}
        <Animated.View
          entering={FadeInDown.duration(motion.base).delay(140)}
          style={styles.form}
        >
          <Field
            label="Email"
            value={email}
            onChangeText={(t) => {
              if (error) clearError();
              setEmail(t);
            }}
            placeholder="you@example.com"
            focused={focused === 'email'}
            onFocus={() => setFocused('email')}
            onBlur={() => setFocused(null)}
            // ---- The five props that prevent the case-mismatch bug ----
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
            // -----------------------------------------------------------
            returnKeyType="next"
          />

          <Field
            label="Password"
            value={password}
            onChangeText={(t) => {
              if (error) clearError();
              setPassword(t);
            }}
            placeholder="········"
            focused={focused === 'password'}
            onFocus={() => setFocused('password')}
            onBlur={() => setFocused(null)}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="current-password"
            textContentType="password"
            returnKeyType="go"
            onSubmitEditing={onSubmit}
          />

          {error ? (
            <Animated.View entering={FadeIn.duration(motion.fast)} style={styles.errorRow}>
              <View style={styles.errorBar} />
              <Text style={styles.errorText} accessibilityLiveRegion="polite">
                {error}
              </Text>
            </Animated.View>
          ) : null}

          <Button
            label="Sign in"
            onPress={onSubmit}
            loading={submitting}
            disabled={!canSubmit}
            style={{ marginTop: space.xs }}
          />

          <View style={styles.footer}>
            <Label color={palette.textGhost}>No account?</Label>
            <Link href="/(auth)/signup" asChild>
              <Pressable hitSlop={8}>
                <Label color={palette.text}>Create one</Label>
              </Pressable>
            </Link>
          </View>
        </Animated.View>

        {/* ---- Diagnostics (tap the wordmark) ------------------------- */}
        {showDiagnostics && (
          <Animated.View
            entering={FadeIn.duration(motion.fast)}
            style={[styles.diagnostics, { backgroundColor: surfaces.surface }]}
          >
            <View style={styles.diagRow}>
              <Label color={palette.textGhost}>Endpoint</Label>
              <Text style={styles.diagValue} numberOfLines={1}>
                {API_BASE_URL}
              </Text>
            </View>
            <Rule />
            <View style={styles.diagRow}>
              <Label color={palette.textGhost}>Transport</Label>
              <Text
                style={[
                  styles.diagValue,
                  {
                    color: API_BASE_URL.startsWith('https')
                      ? palette.info
                      : palette.warn,
                  },
                ]}
              >
                {API_BASE_URL.startsWith('https') ? 'TLS' : 'CLEARTEXT — will fail'}
              </Text>
            </View>
            <Text style={styles.diagHint}>
              If that isn&apos;t your Railway URL, EXPO_PUBLIC_API_URL is unset or
              stale. It&apos;s inlined at build time — restart with
              `npx expo start --clear`, and rebuild for release.
            </Text>
          </Animated.View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

/** A slow pulse on the status dot. Runs on the UI thread; costs nothing. */
function StatusDot() {
  const pulse = useSharedValue(0.35);

  useEffect(() => {
    pulse.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.quad) }),
        withTiming(0.35, { duration: 1400, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      false,
    );
  }, [pulse]);

  const style = useAnimatedStyle(() => ({ opacity: pulse.value }));

  return <Animated.View style={[styles.statusDot, style]} />;
}

type ButtonProvider = SocialProvider | 'phone';

const PROVIDER_PATHS: Record<ButtonProvider, string> = {
  phone:
    'M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm0 2v14h10V4H7zm5 15.2a1 1 0 1 0 0 2 1 1 0 0 0 0-2z',
  apple:
    'M16.4 12.8c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9s-1.8-.9-3-.8c-1.5 0-2.9.9-3.7 2.2-1.6 2.7-.4 6.8 1.1 9 .8 1.1 1.6 2.3 2.8 2.2 1.1 0 1.6-.7 2.9-.7s1.7.7 2.9.7 2-1.1 2.7-2.2c.9-1.2 1.2-2.5 1.2-2.5s-2.4-.9-2.4-3.5zM14.2 5.9c.6-.8 1-1.8.9-2.9-.9 0-2 .6-2.6 1.4-.6.7-1.1 1.7-1 2.7 1 .1 2-.5 2.7-1.2z',
  google:
    'M21.6 12.2c0-.6-.1-1.3-.2-1.9H12v3.6h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.2zM12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22zM6.4 14c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V7.4H3.1a10 10 0 0 0 0 9.2L6.4 14zM12 5.9c1.5 0 2.8.5 3.8 1.5l2.8-2.8A10 10 0 0 0 3.1 7.4L6.4 10c.8-2.3 3-4.1 5.6-4.1z',
  github:
    'M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.3-3.4-1.3-.4-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.9.8.1-.7.4-1.1.6-1.4-2.2-.2-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7 0-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 5 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.4 4.8-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 12 2z',
};

/**
 * Google sign-in, isolated behind its own mount.
 *
 * WHY THIS IS A SEPARATE COMPONENT AND NOT A FEW LINES IN THE SCREEN
 * `useIdTokenAuthRequest` throws when no client id is configured, and React
 * forbids calling a hook conditionally — so the only way to not call it is to
 * not render the thing that calls it. Inlining the hook in LoginScreen meant
 * every unconfigured install crashed the moment the login screen mounted,
 * which is exactly what happened.
 *
 * The parent decides whether Google is available; this component assumes it
 * is and does nothing else.
 */
function GoogleButton({ disabled }: { disabled?: boolean }) {
  const router = useRouter();
  const completeSocial = useAuth((s) => s.completeSocial);
  const [request, response, promptAsync] = Google.useIdTokenAuthRequest(
    googleAuthConfig(),
  );

  useEffect(() => {
    if (response?.type !== 'success') return;
    const idToken = response.params?.id_token;
    if (!idToken) return;
    completeSocial({ provider: 'google', idToken }).then((ok) => {
      if (ok) router.replace('/(tabs)');
    });
  }, [response, completeSocial, router]);

  return (
    <SocialButton
      provider="google"
      label="Continue with Google"
      onPress={() => promptAsync()}
      disabled={disabled || !request}
    />
  );
}

function SocialButton({
  provider,
  label,
  onPress,
  disabled,
  primary,
}: {
  provider: ButtonProvider;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  const surfaces = useSurfaces();
  const tint = primary ? palette.signalInk : palette.text;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={[
        styles.social,
        primary
          ? { backgroundColor: palette.signal, borderColor: palette.signal }
          : { borderColor: surfaces.hairlineBright },
        disabled && { opacity: 0.5 },
      ]}
    >
      <Svg viewBox="0 0 24 24" width={17} height={17}>
        <Path d={PROVIDER_PATHS[provider]} fill={tint} />
      </Svg>
      <Text style={[styles.socialLabel, { color: tint }]}>{label}</Text>
    </Pressable>
  );
}

function Field({
  label,
  focused,
  ...props
}: {
  label: string;
  focused: boolean;
} & React.ComponentProps<typeof TextInput>) {
  const surfaces = useSurfaces();
  return (
    <View style={styles.field}>
      <View style={styles.fieldHeader}>
        <Label color={focused ? palette.text : palette.textFaint}>{label}</Label>
      </View>
      <TextInput
        {...props}
        style={[
          styles.input,
          { backgroundColor: surfaces.raised, borderColor: surfaces.hairline },
          focused && { borderColor: palette.signalDim },
        ]}
        placeholderTextColor={palette.textGhost}
        selectionColor={palette.signal}
        accessibilityLabel={label}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  noProviders: {
    ...type.caption,
    color: palette.textFaint,
    textAlign: 'center',
    lineHeight: 19,
  },
  screen: { flex: 1 },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: space.xl,
    gap: space.xl,
  },

  markRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: palette.signal,
  },
  wordmark: { ...type.heading, letterSpacing: 5, color: palette.text },
  tagline: { ...type.tagline, color: palette.textDim },
  taglineAccent: { fontFamily: type.title.fontFamily, color: palette.text },

  oauth: { gap: space.sm },
  social: {
    height: 48,
    borderRadius: radius.sm,
    borderWidth: HAIRLINE,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
  },
  socialLabel: { ...type.body, fontFamily: type.bodyStrong.fontFamily },

  orRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  orRule: { flex: 1 },

  form: { gap: space.lg },
  field: { gap: space.sm },
  fieldHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  input: {
    height: 50,
    borderRadius: radius.sm,
    borderWidth: HAIRLINE,
    paddingHorizontal: space.lg,
    color: palette.text,
    fontFamily: type.body.fontFamily,
    fontSize: 15,
  },

  errorRow: { flexDirection: 'row', gap: space.md, alignItems: 'stretch' },
  errorBar: { width: 2, backgroundColor: palette.danger, borderRadius: 1 },
  errorText: { ...type.caption, color: palette.danger, flex: 1 },

  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.sm,
    marginTop: space.xs,
  },

  diagnostics: {
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  diagRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: space.md,
    gap: space.md,
  },
  diagValue: {
    fontSize: 11,
    color: palette.textDim,
    flexShrink: 1,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  diagHint: {
    ...type.caption,
    fontSize: 11,
    lineHeight: 16,
    color: palette.textGhost,
    padding: space.md,
    paddingTop: 0,
  },
});
