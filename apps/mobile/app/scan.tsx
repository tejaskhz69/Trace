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
import { api } from '../src/lib/api';
import { motion, palette, radius, space, type } from '../src/theme';

export default function ScanScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const { scan, scanning, error } = useScan();

  const [torch, setTorch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  // Guard against the barcode callback firing dozens of times per second.
  const handledBarcode = useRef<string | null>(null);

  const onBarcode = useCallback(
    async ({ data }: { data: string }) => {
      if (handledBarcode.current || busy) return;
      handledBarcode.current = data;
      setBusy(true);
      setStatus('Looking up barcode…');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      try {
        const res = await api.resolveBarcode(data);
        if (res.found && res.item) {
          // THE PORTION PICKER IS THE DESTINATION, not the Nutrition tab.
          // This used to hand `barcodeItemId` to /(tabs)/log, which never
          // read the param -- so a successful scan navigated away and
          // silently dropped the product. It looked exactly like the
          // scanner failing to recognise anything, which is what it was
          // reported as. Food search already owns select -> portion -> log,
          // so the barcode result goes there rather than growing a second
          // logging UI.
          router.replace({
            pathname: '/food-search',
            params: { barcode: data },
          });
          return;
        }
        setStatus(res.message ?? 'Not found. Try the nutrition label instead.');
      } catch {
        setStatus("Couldn't look that up. Check your connection.");
      } finally {
        setBusy(false);
        // Allow a retry after a moment rather than locking the scanner.
        setTimeout(() => {
          handledBarcode.current = null;
        }, 2500);
      }
    },
    [busy, router],
  );

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
        barcodeScannerSettings={{
          barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e', 'code128'],
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

  React.useEffect(() => {
    if (scanning) {
      pulse.value = withRepeat(
        withSequence(
          withTiming(1.04, { duration: motion.pulse }),
          withTiming(1, { duration: motion.pulse }),
        ),
        -1,
        false,
      );
    } else {
      pulse.value = withTiming(1, { duration: motion.base });
    }
  }, [scanning, pulse]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulse.value }],
    borderColor: palette.signal,
  }));

  return <Animated.View style={[styles.reticle, animatedStyle]} />;
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
