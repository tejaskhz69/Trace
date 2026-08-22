/**
 * Phone + one-time code — the primary sign-in path on mobile.
 *
 * WHY THIS IS THE DEFAULT AND EMAIL IS THE FALLBACK
 * Passwords are a Western convention. In India people log into Swiggy,
 * Zomato, HealthifyMe and every bank with a number and a code, and expect to.
 * A phone number is also a better identity key here: it is stable, it is the
 * thing people actually remember, and it removes an entire class of support
 * load — there is no "forgot password" flow because there is no password.
 *
 * SIGN-IN AND SIGN-UP ARE ONE ACTION
 * A verified number IS the account. Asking someone whether they are new is
 * asking them to remember something they should not have to, so there is no
 * such question anywhere in this flow.
 *
 * THE CODE SCREEN IS SIX BOXES, NOT ONE FIELD
 * One hidden input drives all six, which is what lets iOS and Android autofill
 * the code straight from the SMS notification. Six separate inputs look the
 * same and break autofill entirely — the user then has to leave the app to
 * read the message, which is exactly where people drop out.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { Button, Label, Rule } from '../../src/components/instrument';
import { api, ApiError } from '../../src/lib/api';
import { useAuth } from '../../src/state/useAuth';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

const CODE_LENGTH = 6;

/** Seconds before "Resend code" becomes tappable. */
const RESEND_AFTER_S = 30;

export default function PhoneAuthScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const accent = useAccent();
  const surfaces = useSurfaces();
  const completePhone = useAuth((s) => s.completePhone);

  const [stage, setStage] = useState<'number' | 'code'>('number');
  const [phone, setPhone] = useState('');
  const [masked, setMasked] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const [devCode, setDevCode] = useState<string | null>(null);

  const codeInput = useRef<TextInput>(null);

  // 10 digits is the national length in India; a country code typed with the
  // number is normalised server-side, so this is a nudge rather than a gate.
  const canSend = phone.replace(/\D/g, '').length >= 10;

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const send = useCallback(async () => {
    if (!canSend || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.phoneStart(phone);
      setMasked(res.phone);
      setDevCode(res.dev_code ?? null);
      setStage('code');
      setCode('');
      setCountdown(RESEND_AFTER_S);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      // The keyboard has to come up on its own; asking the user to tap the
      // boxes after they just tapped Send is a wasted interaction.
      setTimeout(() => codeInput.current?.focus(), 350);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : 'Could not send a code. Try again.',
      );
    } finally {
      setBusy(false);
    }
  }, [phone, canSend, busy]);

  const verify = useCallback(
    async (value: string) => {
      if (value.length !== CODE_LENGTH || busy) return;
      setBusy(true);
      setError(null);
      const ok = await completePhone(phone, value);
      setBusy(false);
      if (ok) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace('/(tabs)');
      } else {
        // Clear on failure. Making someone backspace six characters to retry
        // is a small cruelty on a screen they are already frustrated at.
        setCode('');
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        setError(useAuth.getState().error ?? 'That code was not right.');
      }
    },
    [phone, busy, completePhone, router],
  );

  const onCodeChange = (raw: string) => {
    const digits = raw.replace(/\D/g, '').slice(0, CODE_LENGTH);
    setCode(digits);
    setError(null);
    // Submit as soon as it is complete. A "Verify" button under a full code
    // is a tap that adds nothing.
    if (digits.length === CODE_LENGTH) verify(digits);
  };

  return (
    <KeyboardAvoidingView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + space.xl, paddingBottom: insets.bottom + space.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.brand}>
          <View style={[styles.dot, { backgroundColor: accent.brand }]} />
          <Text style={styles.brandText}>TRACE</Text>
        </View>
        <Rule style={styles.rule} />

        {stage === 'number' ? (
          <Animated.View entering={FadeInDown.duration(motion.base)}>
            <Text style={styles.headline}>
              <Text style={styles.headlineDim}>Know whether you&apos;re{'\n'}</Text>
              gaining muscle or fat.
            </Text>
            <Text style={styles.sub}>No password. We&apos;ll text you a code.</Text>

            <Label>Mobile number</Label>
            <View
              style={[
                styles.phoneField,
                {
                  backgroundColor: surfaces.raised,
                  borderColor: canSend ? accent.brand : surfaces.hairline,
                },
              ]}
            >
              <Text style={styles.cc}>+91</Text>
              <TextInput
                value={phone}
                onChangeText={(v) => {
                  setPhone(v);
                  setError(null);
                }}
                placeholder="98765 43210"
                placeholderTextColor={palette.textGhost}
                keyboardType="phone-pad"
                textContentType="telephoneNumber"
                autoComplete="tel"
                autoFocus
                maxLength={20}
                style={styles.phoneInput}
                onSubmitEditing={send}
              />
            </View>
            <Text style={styles.hint}>
              Enter a number from another country with its code, like
              +1 555 010 0000.
            </Text>

            <View style={styles.gap} />
            <Button
              label={busy ? 'Sending…' : 'Send code'}
              onPress={send}
              loading={busy}
              disabled={!canSend}
            />
          </Animated.View>
        ) : (
          <Animated.View entering={FadeInDown.duration(motion.base)}>
            <Text style={styles.headline}>
              <Text style={styles.headlineDim}>Enter the code{'\n'}</Text>
              we sent to {masked}.
            </Text>
            <Text style={styles.sub}>
              It expires in five minutes.{' '}
              <Text
                style={[styles.link, { color: accent.brand }]}
                onPress={() => {
                  setStage('number');
                  setCode('');
                  setError(null);
                }}
              >
                Wrong number?
              </Text>
            </Text>

            {/* One hidden input behind six boxes. Six real inputs look the
                same and break SMS autofill completely. */}
            <Pressable onPress={() => codeInput.current?.focus()}>
              <View style={styles.otpRow}>
                {Array.from({ length: CODE_LENGTH }).map((_, i) => {
                  const filled = i < code.length;
                  const active = i === code.length;
                  return (
                    <View
                      key={i}
                      style={[
                        styles.otpBox,
                        {
                          backgroundColor: surfaces.raised,
                          borderColor: filled || active
                            ? accent.brand
                            : surfaces.hairline,
                        },
                      ]}
                    >
                      <Text style={styles.otpChar}>
                        {filled ? code[i] : ''}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </Pressable>

            <TextInput
              ref={codeInput}
              value={code}
              onChangeText={onCodeChange}
              keyboardType="number-pad"
              // These two are what make the OS offer the code from the SMS
              // notification. Without them the user leaves the app to read it.
              textContentType="oneTimeCode"
              autoComplete="sms-otp"
              maxLength={CODE_LENGTH}
              autoFocus
              style={styles.hiddenInput}
              caretHidden
            />

            {devCode ? (
              <Animated.View entering={FadeIn}>
                <Text style={styles.devCode}>
                  DEV · no SMS provider configured · code is {devCode}
                </Text>
              </Animated.View>
            ) : null}

            <View style={styles.gap} />
            <Pressable
              onPress={countdown === 0 ? send : undefined}
              disabled={countdown > 0 || busy}
            >
              <Text
                style={[
                  styles.resend,
                  { color: countdown > 0 ? palette.textGhost : accent.brand },
                ]}
              >
                {countdown > 0 ? `Resend in ${countdown}s` : 'Resend code'}
              </Text>
            </Pressable>
          </Animated.View>
        )}

        {error ? (
          <Animated.Text entering={FadeIn.duration(motion.fast)} style={styles.error}>
            {error}
          </Animated.Text>
        ) : null}

        <View style={styles.flex} />
        <Pressable onPress={() => router.replace('/(auth)/login')}>
          <Text style={styles.footer}>
            Prefer email? <Text style={[styles.link, { color: accent.brand }]}>Use email instead</Text>
          </Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: space.lg },
  flex: { flex: 1, minHeight: space.xl },

  brand: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  brandText: { ...type.label, color: palette.text, letterSpacing: 2.4 },
  rule: { marginTop: space.md, marginBottom: space.xl },

  headline: { ...type.title, fontSize: 27, lineHeight: 32, color: palette.text },
  headlineDim: { color: palette.textDim, fontFamily: type.body.fontFamily },
  sub: {
    ...type.caption,
    color: palette.textDim,
    marginTop: space.sm,
    marginBottom: space.xl,
  },
  link: { fontFamily: type.heading.fontFamily },

  phoneField: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    marginTop: space.sm,
  },
  cc: { ...type.body, color: palette.textDim },
  phoneInput: {
    ...type.body,
    color: palette.text,
    flex: 1,
    paddingVertical: space.md + 2,
  },
  hint: { ...type.labelSm, color: palette.textGhost, marginTop: space.sm, textTransform: 'none', letterSpacing: 0 },

  otpRow: { flexDirection: 'row', gap: space.sm },
  otpBox: {
    flex: 1,
    aspectRatio: 0.87,
    borderWidth: 1,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  otpChar: { ...type.figure, fontSize: 24, color: palette.text },
  // Off-screen rather than display:none — a hidden-but-mounted input is what
  // keeps the keyboard and the autofill affordance alive.
  hiddenInput: { position: 'absolute', opacity: 0, height: 1, width: 1 },

  devCode: {
    ...type.labelSm,
    color: palette.warn,
    marginTop: space.md,
    textAlign: 'center',
  },
  resend: { ...type.label, textAlign: 'center' },
  gap: { height: space.lg },
  error: { ...type.caption, color: palette.danger, marginTop: space.lg },
  footer: { ...type.caption, color: palette.textFaint, textAlign: 'center' },
});
