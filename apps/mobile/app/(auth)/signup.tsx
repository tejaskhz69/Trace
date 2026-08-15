/**
 * Signup.
 *
 * Deliberately short: email, password, and the two numbers the adaptive TDEE
 * engine needs a prior for. Everything else can be asked later — every extra
 * field on this screen costs conversions, and Health & Fitness is a category
 * where 86% of paid conversions happen on day zero.
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

import { Button } from '../../src/components/ui';
import { useAuth } from '../../src/state/useAuth';
import { palette, radius, space, type } from '../../src/theme';

const GOALS = [
  { key: 'lose', label: 'Lose fat' },
  { key: 'recomp', label: 'Recomp' },
  { key: 'gain', label: 'Build muscle' },
] as const;

export default function SignupScreen() {
  const router = useRouter();
  const { register, submitting, error, clearError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [height, setHeight] = useState('');
  const [weight, setWeight] = useState('');
  const [goal, setGoal] = useState<string>('recomp');

  const canSubmit =
    email.includes('@') && password.length >= 8 && !!height && !!weight;

  async function onSubmit() {
    if (!canSubmit || submitting) return;
    const ok = await register({
      email,
      password,
      height_cm: parseFloat(height),
      weight_kg: parseFloat(weight),
      goal_type: goal,
    });
    if (ok) router.replace('/(tabs)');
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <Animated.View entering={FadeIn.duration(240)}>
          <Text style={styles.title}>Create your account</Text>
          <Text style={styles.subtitle}>
            Two numbers to start. I&apos;ll learn the rest from your data.
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInDown.duration(280).delay(60)} style={styles.form}>
          <Field
            label="Email"
            value={email}
            onChangeText={(t) => {
              if (error) clearError();
              setEmail(t);
            }}
            placeholder="you@example.com"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
          />

          <Field
            label="Password"
            value={password}
            onChangeText={setPassword}
            placeholder="At least 8 characters"
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="new-password"
            textContentType="newPassword"
          />

          <View style={styles.row}>
            <View style={styles.flex}>
              <Field
                label="Height (cm)"
                value={height}
                onChangeText={setHeight}
                placeholder="175"
                keyboardType="decimal-pad"
              />
            </View>
            <View style={styles.flex}>
              <Field
                label="Weight (kg)"
                value={weight}
                onChangeText={setWeight}
                placeholder="75"
                keyboardType="decimal-pad"
              />
            </View>
          </View>

          <View>
            <Text style={styles.label}>Goal</Text>
            <View style={styles.goalRow}>
              {GOALS.map((g) => (
                <Pressable
                  key={g.key}
                  onPress={() => setGoal(g.key)}
                  style={[styles.goal, goal === g.key && styles.goalActive]}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: goal === g.key }}
                >
                  <Text
                    style={[
                      styles.goalText,
                      goal === g.key && styles.goalTextActive,
                    ]}
                  >
                    {g.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Button
            label="Create account"
            onPress={onSubmit}
            loading={submitting}
            disabled={!canSubmit}
          />

          <View style={styles.footer}>
            <Text style={styles.footerText}>Already have an account? </Text>
            <Link href="/(auth)/login" style={styles.footerLink}>
              Sign in
            </Link>
          </View>
        </Animated.View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({
  label,
  ...props
}: { label: string } & React.ComponentProps<typeof TextInput>) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        {...props}
        style={styles.input}
        placeholderTextColor={palette.textFaint}
        accessibilityLabel={label}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.bg },
  scroll: { flexGrow: 1, justifyContent: 'center', padding: space.xl, gap: space.xl },
  title: { ...type.title, color: palette.text },
  subtitle: { ...type.body, color: palette.textMuted, marginTop: space.xs },

  form: { gap: space.lg },
  row: { flexDirection: 'row', gap: space.md },
  label: {
    ...type.micro,
    color: palette.textMuted,
    textTransform: 'uppercase',
    marginBottom: space.sm,
  },
  input: {
    height: 52,
    borderRadius: radius.md,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: space.lg,
    color: palette.text,
    ...type.body,
  },

  goalRow: { flexDirection: 'row', gap: space.sm },
  goal: {
    flex: 1,
    height: 44,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: palette.border,
    backgroundColor: palette.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  goalActive: { borderColor: palette.primary, backgroundColor: palette.primarySoft },
  goalText: { ...type.caption, color: palette.textMuted },
  goalTextActive: { color: palette.primary, fontWeight: '600' },

  error: { ...type.caption, color: palette.bad },
  footer: { flexDirection: 'row', justifyContent: 'center' },
  footerText: { ...type.caption, color: palette.textMuted },
  footerLink: { ...type.caption, color: palette.primary, fontWeight: '600' },
});
