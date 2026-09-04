/**
 * "Reduce Motion" — the OS accessibility setting, honoured.
 *
 * WHY THIS DID NOT EXIST BEFORE, AND WHY IT MATTERS HERE MOST
 * Nothing in this app consulted `AccessibilityInfo`. That is defensible for a
 * 180 ms panel fade and indefensible for the scanner: the reticle pulses on a
 * loop for as long as a lookup takes, filling the screen while the camera is
 * live. Looping, pulsing motion over a moving camera feed is the exact
 * combination that triggers vestibular symptoms, and it is the one animation
 * in the product a user cannot look away from — they are pointing the phone
 * at something.
 *
 * WHAT "REDUCED" MEANS HERE
 * Not "no feedback". A scanner with no visible state is a scanner that looks
 * broken, and removing the only signal that work is happening is a worse
 * accessibility outcome than the animation. Reduced motion swaps the LOOPING
 * TRANSFORM for a static frame plus the status text that was always there —
 * the information survives, the movement does not.
 *
 * Reads once and subscribes: the setting can be changed from Control Centre
 * without leaving the app, and a value captured at mount would be stale for
 * the rest of the session.
 */

import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let alive = true;

    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => {
        if (alive) setReduced(v);
      })
      // A platform that cannot answer is not a reason to crash a camera
      // screen. Defaulting to false keeps the existing behaviour.
      .catch(() => undefined);

    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', (v) => {
      if (alive) setReduced(v);
    });

    return () => {
      alive = false;
      sub?.remove();
    };
  }, []);

  return reduced;
}
