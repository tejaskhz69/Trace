/**
 * SIGN UP — email and password. Nothing else.
 *
 * WHAT THIS SCREEN USED TO ASK, AND WHY IT NO LONGER DOES
 * It used to collect height, weight and goal alongside the credentials. That
 * made sense when the account came first and the questionnaire did not exist.
 * It does now: `(onboarding)/index.tsx` runs BEFORE the account, asks those
 * questions properly — a draggable dial for weight rather than a keyboard —
 * and shows the user their calorie target before asking them to save it.
 *
 * So by the time anyone reaches this screen those three answers are already
 * stashed in `useOnboarding`, and asking again was asking twice. It also read
 * as a bug, which is exactly how it was reported: "the old login page comes
 * which has the weight age and gender part."
 *
 * The register endpoint still accepts those fields as optional, and the root
 * layout submits the stashed answers the moment the account exists. This
 * screen's only job is credentials.
 */

import React, { useState } from 'react';
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
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { Button, Label, Rule } from '../../src/components/instrument';
import { useAuth } from '../../src/state/useAuth';
import { useOnboarding } from '../../src/state/useOnboarding';
import { useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

export default function SignupScreen() {
  const router = useRouter();
  const { register, submitting, error, clearError } = useAuth();
  const surfaces = useSurfaces();

  // Only read, never asked for again. Its presence is what lets this screen
  // promise the plan is already waiting rather than saying "account created".
  const plan = useOnboarding((s) => s.plan);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [focused, setFocused] = useState<'email' | 'password' | null>(null);

  const canSubmit = email.trim().includes('@') && password.length >= 8;

  async function onSubmit() {
    if (!canSubmit || submitting) return;
    // Email is normalised on the client AND the server. iOS auto-capitalises
    // the first character even with autoCapitalize="none" in some keyboard
    // configurations, and a capitalised address is a different string.
    const ok = await register({
      email: email.trim().toLowerCase(),
      password,
    });
    // The root layout owns what happens next: it spends any stashed
    // onboarding answers and routes accordingly. Racing it from here is how
    // the questionnaire ends up submitted twice.
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
        <Animated.View entering={FadeIn.duration(motion.base)}>
          <Label color={palette.textFaint}>Last step</Label>
          <Text style={styles.title}>Save your plan</Text>
          <Rule style={{ marginVertical: space.lg }} />
          <Text style={styles.subtitle}>
            {plan
              ? `Your target of ${Math.round(plan.calorie_target)} kcal is ready. An account keeps it, and keeps the weekly adjustments.`
              : 'An account keeps your plan and your history across devices.'}
          </Text>
        </Animated.View>

        <Animated.View
          entering={FadeInDown.duration(motion.base).delay(60)}
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
            placeholder="At least 8 characters"
            focused={focused === 'password'}
            onFocus={() => setFocused('password')}
            onBlur={() => setFocused(null)}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="new-password"
            textContentType="newPassword"
            returnKeyType="go"
            onSubmitEditing={onSubmit}
          />

          {error ? (
            <Animated.View
              entering={FadeIn.duration(motion.fast)}
              style={styles.errorRow}
            >
              <View style={styles.errorBar} />
              <Text style={styles.errorText} accessibilityLiveRegion="polite">
                {error}
              </Text>
            </Animated.View>
          ) : null}

          <Button
            label="Create account"
            onPress={onSubmit}
            loading={submitting}
            disabled={!canSubmit}
            style={{ marginTop: space.xs }}
          />

          {/* Phone is offered here as well as on the login screen, because
              "create an account" and "I'd rather not invent a password" are
              the same moment for a lot of people. */}
          <Pressable
            onPress={() => router.push('/(auth)/phone')}
            hitSlop={8}
            style={styles.alt}
          >
            <Label color={palette.textDim}>Use a phone number instead</Label>
          </Pressable>

          <View style={styles.footer}>
            <Label color={palette.textGhost}>Already have an account?</Label>
            <Link href="/(auth)/login" asChild>
              <Pressable hitSlop={8}>
                <Label color={palette.text}>Sign in</Label>
              </Pressable>
            </Link>
          </View>
        </Animated.View>
      </ScrollView>
    </KeyboardAvoidingView>
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
      <Label color={focused ? palette.text : palette.textFaint}>{label}</Label>
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
  screen: { flex: 1 },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: space.xl,
    gap: space.xl,
  },
  title: { ...type.title, color: palette.text, marginTop: space.sm },
  subtitle: { ...type.body, color: palette.textDim, lineHeight: 22 },

  form: { gap: space.lg },
  field: { gap: space.xs },
  input: {
    height: 50,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: space.lg,
    color: palette.text,
    ...type.body,
  },

  errorRow: { flexDirection: 'row', gap: space.md, alignItems: 'center' },
  errorBar: { width: 2, alignSelf: 'stretch', backgroundColor: palette.danger },
  errorText: { ...type.caption, color: palette.danger, flex: 1, lineHeight: 19 },

  alt: { alignItems: 'center', paddingVertical: space.sm },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: space.sm,
  },
});
