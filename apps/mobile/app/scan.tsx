/**
 * Camera: photo scan + barcode, in one screen.
 *
 * Barcode is checked FIRST and locally — if there's a barcode in frame we
 * never spend an AI call on it. A barcode lookup is exact, free, and
 * sub-second; a vision call is an estimate that costs money. Preferring the
 * cheap exact path is both better data and better margin.
 */

import React, { useCallback, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeIn,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import * as ImageManipulator from 'expo-image-manipulator';

import { Button } from '../src/components/instrument';
import { useScan } from '../src/state/useScan';
import { api, type BarcodeLookup } from '../src/lib/api';
import { StabilityGate, classify, type BarcodeStatus } from '../src/lib/barcode';
import { useReducedMotion } from '../src/lib/motion-preference';
import { motion, palette, radius, space, type } from '../src/theme';

/**
 * What to say when the device itself refuses a scan, before any request.
 *
 * Each names a DIFFERENT next action, which is the whole reason for
 * distinguishing them. Collapsing them into "not found" is what makes a
 * scanner feel broken: the user re-scans a deli sticker forever because
 * nothing told them it is not the kind of barcode that can be looked up.
 *
 * These mirror `_REFUSAL_MESSAGES` in services/api/app/routers/foods.py. The
 * server sends its own copy for anything that reaches it; these cover the
 * codes that never leave the phone.
 */
const LOCAL_REFUSALS: Record<BarcodeStatus, string> = {
  ok: '',
  not_numeric: "That doesn't look like a product barcode. Try searching by name.",
  invalid_length:
    'That scan came out incomplete. Hold steady and try again, or search by name.',
  bad_check_digit:
    "That barcode didn't scan cleanly — it may be damaged or curved. Try again, or search by name.",
  restricted:
    "That's an in-store label, not a product barcode — it only means something inside that shop. Search by name, or snap the nutrition label instead.",
};

/** Distinguishes "no signal" from "the server said no". */
function isOffline(err: unknown): boolean {
  const msg = (err as Error)?.message ?? '';
  return /could not reach|network request failed/i.test(msg);
}

export default function ScanScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const { scan, scanning, error } = useScan();

  const [torch, setTorch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  /** The last code that failed in a way the user can act on. Drives Retry. */
  const [retryable, setRetryable] = useState<{ data: string; type?: string } | null>(
    null,
  );

  /**
   * Agreement across frames, plus a permanent per-session dedupe.
   *
   * REPLACES A SINGLE REF THAT ACTED ON THE FIRST FRAME AND RESET AFTER 2.5 s.
   * That had two failure modes, both common in a shop:
   *   - one misread frame off a curved or glossy pack triggered a lookup for
   *     the wrong product, and a check digit does not catch a decode that is
   *     internally consistent;
   *   - holding the camera on a pack for three seconds fired the SAME lookup
   *     again, because the guard had expired while the barcode was still in
   *     frame.
   * The gate settles a code once and never re-fires it unless the user asks.
   */
  const gate = useRef(new StabilityGate());

  /**
   * Codes already resolved this session, keyed by GTIN-14.
   *
   * Keyed on the NORMALISED form, so a product scanned as UPC-A and again as
   * EAN-13 is one entry rather than two. A hit here is the difference between
   * an instant result and a round trip on supermarket wifi.
   */
  const cache = useRef(new Map<string, BarcodeLookup>());

  /** Aborts a lookup the user has moved on from. */
  const inFlight = useRef<AbortController | null>(null);

  const lookup = useCallback(
    async (data: string, symbology?: string) => {
      // VALIDATE ON THE DEVICE FIRST. An in-store sticker, a partial read off
      // a curved bottle or a shipping label costs nothing to reject here and
      // a full round trip to reject at the server -- on the worst network the
      // app will ever see, standing in an aisle.
      const check = classify(data, symbology);
      if (check.status !== 'ok' || !check.gtin14) {
        setStatus(LOCAL_REFUSALS[check.status]);
        setRetryable(check.retryable ? { data, type: symbology } : null);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        return;
      }

      const hit = cache.current.get(check.gtin14);
      if (hit?.found && hit.item) {
        router.replace({ pathname: '/food-search', params: { barcode: data } });
        return;
      }

      // Cancel anything still running for an earlier code. Without this the
      // slower of two overlapping lookups wins whichever order they return in,
      // and the user lands on the product they were NOT pointing at.
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;

      setBusy(true);
      setRetryable(null);
      setStatus('Looking up barcode…');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      try {
        const res = await api.resolveBarcode(data, {
          symbology,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;

        if (res.found && res.item) {
          if (res.gtin14) cache.current.set(res.gtin14, res);
          // THE PORTION PICKER IS THE DESTINATION, not the Nutrition tab.
          // Food search already owns select -> portion -> log, so the barcode
          // result goes there rather than growing a second logging UI.
          //
          // `item` is handed over in the params so food-search does not
          // re-request the same barcode on arrival -- every successful scan
          // used to cost two identical lookups, one here and one there.
          router.replace({
            pathname: '/food-search',
            params: { barcode: data, prefetched: JSON.stringify(res.item) },
          });
          return;
        }

        // Only a genuine "nobody has catalogued this" is worth remembering.
        // An outage is not a missing product, and caching it as one would
        // teach the user their food does not exist.
        if (res.status === 'not_found' && res.gtin14) {
          cache.current.set(res.gtin14, res);
        }
        setStatus(res.message ?? 'Not found. Try the nutrition label instead.');
        // The server decides. A restricted code comes back retryable: false,
        // because scanning an in-store sticker again is a loop, not a recovery.
        setRetryable(res.retryable === false ? null : { data, type: symbology });
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') return;
        setStatus(
          isOffline(err)
            ? "You're offline. The lookup will work once you have signal."
            : "Couldn't look that up. Check your connection.",
        );
        setRetryable({ data, type: symbology });
      } finally {
        if (inFlight.current === controller) inFlight.current = null;
        setBusy(false);
      }
    },
    [router],
  );

  const onBarcode = useCallback(
    ({ data, type }: { data: string; type?: string }) => {
      if (busy) return;
      // Normalise before the stability gate so the same product decoded as
      // UPC-A on one frame and EAN-13 on the next still counts as agreement.
      const check = classify(data, type);
      if (!check.gtin14) {
        // Malformed reads are common while focusing; do not shout about every
        // frame. The gate below never settles them, so nothing fires.
        return;
      }
      if (gate.current.push(check.gtin14) === null) return;
      void lookup(data, type);
    },
    [busy, lookup],
  );

  const onRetry = useCallback(() => {
    if (!retryable) return;
    const check = classify(retryable.data, retryable.type);
    if (check.gtin14) {
      gate.current.forget(check.gtin14);
      cache.current.delete(check.gtin14);
    }
    void lookup(retryable.data, retryable.type);
  }, [retryable, lookup]);

  // Abandon any in-flight lookup when the screen goes away.
  React.useEffect(() => () => inFlight.current?.abort(), []);

  async function onCapture() {
    if (busy || scanning) return;
    setBusy(true);
    setStatus('Sharpening the photo…');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    try {
      const photo = await cameraRef.current?.takePictureAsync({
        quality: 0.7,
        imageType: 'jpg',
        skipProcessing: true,
      });
      if (!photo?.uri) throw new Error('no photo');

      // DOWNSCALE BEFORE UPLOADING, not after.
      //
      // The comment that used to sit on takePictureAsync said the server
      // downscales to 768px so sending the original "just costs upload time"
      // -- and then sent the original anyway. On a modern phone that is a
      // 12MP JPEG, two to four megabytes, which on mobile data is several
      // seconds of the user watching a spinner before the model has even
      // been asked. Resizing here makes the upload roughly a tenth the size
      // and throws away nothing the server would have kept.
      //
      // 1024 rather than the server's 768: it leaves headroom for the
      // server's own LANCZOS pass to work from, and the difference in upload
      // size between the two is negligible.
      const small = await ImageManipulator.manipulateAsync(
        photo.uri,
        [{ resize: { width: 1024 } }],
        { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG },
      );

      setStatus('Reading your plate…');
      const ok = await scan(small.uri);
      if (ok) router.replace('/scan-review');
    } catch {
      setStatus("Couldn't capture that. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!permission) return <View style={styles.flex} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.flex}>
        <View style={styles.permission}>
          <Text style={styles.permissionTitle}>Camera access</Text>
          <Text style={styles.permissionBody}>
            Trace needs your camera to identify food and scan barcodes. Photos
            are sent for analysis and aren&apos;t shared with anyone.
          </Text>
          <Button label="Allow camera" onPress={requestPermission} />
          <Button label="Not now" variant="ghost" onPress={() => router.back()} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <View style={styles.flex}>
      <CameraView
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        /* ONLY SYMBOLOGIES THAT CARRY A GTIN.
         *
         * `code128` was in this list and is not a product identifier: it is a
         * general-purpose symbology used for shipping labels, shelf-edge
         * tickets and internal SKUs. Decoding one and looking it up asks an
         * external database to identify a pallet.
         *
         * `itf14` is added because it is the case/outer-packaging GTIN, which
         * `services/gtin.py` has always normalised and the camera was never
         * asked to read.
         *
         * `upc_e` stays, and now matters: the callback's `type` is forwarded
         * so an 8-digit UPC-E is expanded rather than mistaken for an EAN-8.
         * The two readings of those digits name different products, and 58%
         * of valid EAN-8s beginning 0 or 1 also parse as a valid UPC-E. */
        barcodeScannerSettings={{
          barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'itf14'],
        }}
        onBarcodeScanned={onBarcode}
      />

      <SafeAreaView style={styles.overlay}>
        <View style={styles.topBar}>
          <IconButton glyph="✕" onPress={() => router.back()} label="Close" />
          <IconButton
            glyph={torch ? '☀' : '☾'}
            onPress={() => setTorch((t) => !t)}
            label="Toggle torch"
            active={torch}
          />
        </View>

        <View style={styles.reticleWrap}>
          <Reticle scanning={scanning || busy} />
          <Text style={styles.hint}>
            {params.mode === 'barcode'
              ? 'Point at a barcode'
              : 'Fill the frame with your plate'}
          </Text>
        </View>

        <View style={styles.bottom}>
          {(status || error) && (
            <Animated.View entering={FadeIn.duration(motion.fast)} style={styles.status}>
              <Text style={styles.statusText}>{error ?? status}</Text>
              {/* A MANUAL RETRY, offered only where retrying can work.
                  A restricted code and a malformed one are both dead ends for
                  the camera, so neither gets a button that implies otherwise —
                  the message already points at search or the label. */}
              {retryable && !busy ? (
                <Pressable
                  onPress={onRetry}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel="Try this barcode again"
                >
                  <Text style={styles.retryText}>TRY AGAIN</Text>
                </Pressable>
              ) : null}
            </Animated.View>
          )}

          <Pressable
            onPress={onCapture}
            disabled={busy || scanning}
            style={styles.shutterOuter}
            accessibilityRole="button"
            accessibilityLabel="Capture meal photo"
          >
            <View
              style={[
                styles.shutterInner,
                (busy || scanning) && styles.shutterBusy,
              ]}
            />
          </Pressable>

          <Text style={styles.shutterHint}>
            Barcodes scan automatically — no tap needed
          </Text>
        </View>
      </SafeAreaView>
    </View>
  );
}

/**
 * The scanning reticle. Pulses on the UI thread while a request is in flight,
 * so it keeps animating smoothly even while the JS thread is busy encoding
 * and uploading the image.
 */
function Reticle({ scanning }: { scanning: boolean }) {
  const pulse = useSharedValue(1);
  const reduced = useReducedMotion();

  React.useEffect(() => {
    // REDUCED MOTION: hold the frame still.
    //
    // This is the one looping animation in the product a user cannot look
    // away from — it runs over a live camera feed for as long as a lookup
    // takes, while they are pointing the phone at something. That is exactly
    // the combination that provokes vestibular symptoms.
    //
    // The signal is not removed, only the movement: the reticle still turns
    // the accent colour while work is in flight (below), and the status line
    // still says what is happening. A scanner with no visible state looks
    // broken, which would be a worse accessibility outcome than the pulse.
    if (scanning && !reduced) {
      pulse.value = withRepeat(
        withSequence(
          withTiming(1.04, { duration: motion.pulse }),
          withTiming(1, { duration: motion.pulse }),
        ),
        -1,
        false,
      );
    } else {
      pulse.value = withTiming(1, { duration: reduced ? 0 : motion.base });
    }
  }, [scanning, reduced, pulse]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    borderColor: palette.signal,
  }));

  return (
    <Animated.View
      style={[styles.reticle, animatedStyle, scanning && styles.reticleActive]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    />
  );
}

function IconButton({
  glyph,
  onPress,
  label,
  active,
}: {
  glyph: string;
  onPress: () => void;
  label: string;
  active?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.iconButton, active && styles.iconButtonActive]}
      hitSlop={10}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Text style={styles.iconGlyph}>{glyph}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.cameraInk },
  overlay: { flex: 1, justifyContent: 'space-between' },

  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: space.lg,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: palette.cameraScrim,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconButtonActive: { backgroundColor: palette.signal },
  iconGlyph: { color: palette.cameraPaper, fontSize: 17 },

  reticleWrap: { alignItems: 'center', gap: space.lg },
  reticle: {
    width: 280,
    height: 280,
    borderWidth: 2,
    borderRadius: radius.xl,
    borderColor: palette.signal,
  },
  /* Work in flight, without motion. This is what carries the signal when the
     pulse is suppressed for Reduce Motion — a thicker, brighter frame reads
     as "busy" while sitting perfectly still. */
  reticleActive: { borderWidth: 3 },
  hint: { ...type.caption, color: palette.cameraPaperDim },

  bottom: { alignItems: 'center', gap: space.md, paddingBottom: space.xl },
  status: {
    backgroundColor: palette.cameraScrimStrong,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    maxWidth: '85%',
  },
  statusText: { ...type.caption, color: palette.cameraPaper, textAlign: 'center' },
  retryText: {
    ...type.label,
    color: palette.signal,
    textAlign: 'center',
    marginTop: space.sm,
  },

  shutterOuter: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 4,
    borderColor: palette.cameraPaperDim,
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: palette.cameraPaper,
  },
  shutterBusy: { backgroundColor: palette.signal },
  shutterHint: { ...type.micro, color: palette.cameraPaperFaint },

  permission: {
    flex: 1,
    justifyContent: 'center',
    padding: space.xl,
    gap: space.lg,
    backgroundColor: palette.void,
  },
  permissionTitle: { ...type.title, color: palette.text },
  permissionBody: { ...type.body, color: palette.textDim, lineHeight: 22 },
});
