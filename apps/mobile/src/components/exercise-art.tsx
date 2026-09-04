/**
 * Large line-art illustrations for the exercise detail screen.
 *
 * THE TIERING, AND WHY
 * There are 873 exercises. Hand-drawing all of them is not feasible, and
 * photographs would be a few hundred megabytes of assets that would also wreck
 * the near-black line-art language the rest of the app is built in.
 *
 * So there are three tiers, and each is a real answer rather than a
 * placeholder:
 *
 *   1. NAME MATCH   a hand-drawn figure for the specific movement.
 *   2. CATEGORY     the family figure — a stretch looks like a stretch, a
 *                   plyometric looks like a jump. Measured: this alone
 *                   rescues 76 of the 121 names that matched nothing, and
 *                   it is far more informative than a dumbbell glyph on
 *                   "Child's Pose".
 *   3. EQUIPMENT    the glyph. "Cable" versus "barbell" versus "machine" is
 *                   genuinely what tells a beginner where to walk.
 *
 * Exercise logging is brutally power-law — bench, squat, deadlift, press,
 * rows, pulldowns and curls are most logged sets — so the drawn set covers
 * most of what anyone opens, and the tiers below it stop the tail from
 * looking broken.
 *
 * COVERAGE IS MEASURED, NOT ASSUMED. `artifacts/art-coverage-misses.json` is
 * regenerated from the catalogue; the name tier alone was 752/873 (86.1%).
 * `drawn` in the return value stays honest about which tier answered.
 *
 * MATCHING is on keywords rather than exercise IDs, because the catalogue is
 * seeded from an external source and its IDs are not stable across re-seeds.
 * Order matters: the first pattern that matches wins, so more specific
 * patterns ("incline bench") must precede general ones ("bench").
 */

import React, { memo } from 'react';
import { View } from 'react-native';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

import { equipmentIcon } from './icons';
import { palette } from '../theme';

interface ArtProps {
  size?: number;
  color?: string;
}

const S = (color: string) => ({
  stroke: color,
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  fill: 'none' as const,
});

function art(render: (s: ReturnType<typeof S>) => React.ReactNode) {
  return memo(function Art({ size = 120, color = palette.textDim }: ArtProps) {
    return (
      <Svg width={size} height={size} viewBox="0 0 100 100">
        {render(S(color))}
      </Svg>
    );
  });
}

/**
 * Cardio. A crank and a wheel: the one shape shared by bike, elliptical and
 * rower, which is what the cardio rows in the catalogue actually have in
 * common. Treadmill names match the `Jump` runner instead.
 */
const Cardio = art((s) => (
  <>
    <Circle cx="30" cy="70" r="16" {...s} />
    <Circle cx="74" cy="70" r="9" {...s} />
    <Path d="M30 70 L42 50 H60" {...s} />
    <Path d="M60 50 L74 70" {...s} />
    <Path d="M52 50 L52 30 H68" {...s} />
    <Circle cx="30" cy="70" r="3" {...s} />
  </>
));

/** Incline press — the bench angle is the whole point of the drawing. */
const InclinePress = art((s) => (
  <>
    {/* bench at 30 degrees */}
    <Path d="M20 78 L64 52" {...s} />
    <Path d="M24 78 L24 88 M60 56 L60 88 M16 88 H68" {...s} />
    {/* torso along the bench */}
    <Circle cx="62" cy="44" r="6" {...s} />
    <Path d="M58 49 L32 68" {...s} />
    {/* arms pressing up */}
    <Path d="M54 54 L58 38 M46 60 L50 44" {...s} />
    {/* dumbbells */}
    <Path d="M53 36 h10 M53 42 h10 M45 42 h10 M45 48 h10" {...s} />
  </>
));

const FlatPress = art((s) => (
  <>
    <Path d="M18 66 H70 M24 66 V86 M64 66 V86 M14 86 H74" {...s} />
    <Circle cx="66" cy="58" r="6" {...s} />
    <Path d="M60 61 H32" {...s} />
    <Path d="M56 60 V40 M42 60 V40" {...s} />
    <Path d="M34 38 H64 M36 33 V45 M62 33 V45" {...s} />
  </>
));

const Squat = art((s) => (
  <>
    <Circle cx="50" cy="20" r="7" {...s} />
    <Path d="M28 32 H72 M30 27 V37 M70 27 V37" {...s} />
    <Path d="M50 27 V52" {...s} />
    <Path d="M50 52 L38 66 L38 84 M50 52 L62 66 L62 84" {...s} />
    <Path d="M32 84 H44 M56 84 H68" {...s} />
  </>
));

const Deadlift = art((s) => (
  <>
    <Circle cx="42" cy="24" r="7" {...s} />
    <Path d="M46 30 L58 46" {...s} />
    <Path d="M58 46 L54 68 L54 84" {...s} />
    <Path d="M48 34 L44 62" {...s} />
    <Path d="M24 62 H72 M28 55 V69 M68 55 V69" {...s} />
    <Path d="M46 84 H62" {...s} />
  </>
));

const OverheadPress = art((s) => (
  <>
    <Circle cx="50" cy="40" r="7" {...s} />
    <Path d="M50 47 V70 M50 70 L40 88 M50 70 L60 88" {...s} />
    <Path d="M44 50 L40 30 M56 50 L60 30" {...s} />
    <Path d="M26 26 H74 M30 20 V32 M70 20 V32" {...s} />
  </>
));

const Row = art((s) => (
  <>
    <Circle cx="34" cy="30" r="6" {...s} />
    <Path d="M38 34 L60 44 L60 84" {...s} />
    <Path d="M44 38 L44 56" {...s} />
    <Path d="M28 56 H62 M32 50 V62 M58 50 V62" {...s} />
    <Path d="M52 84 H70" {...s} />
  </>
));

const Pulldown = art((s) => (
  <>
    <Path d="M50 8 V30" {...s} />
    <Path d="M30 30 H70 M34 25 V35 M66 25 V35" {...s} />
    <Circle cx="50" cy="46" r="6" {...s} />
    <Path d="M44 34 L46 42 M56 34 L54 42" {...s} />
    <Path d="M50 52 V70" {...s} />
    <Rect x="36" y="70" width="28" height="6" rx="2" {...s} />
    <Path d="M42 76 V86 M58 76 V86" {...s} />
  </>
));

const Curl = art((s) => (
  <>
    <Circle cx="50" cy="22" r="7" {...s} />
    <Path d="M50 29 V62 M50 62 L42 86 M50 62 L58 86" {...s} />
    <Path d="M44 36 L36 50 L44 58" {...s} />
    <Path d="M38 56 H52 M40 51 V61 M50 51 V61" {...s} />
  </>
));

const Plank = art((s) => (
  <>
    <Circle cx="24" cy="46" r="6" {...s} />
    <Path d="M30 50 H72" {...s} />
    <Path d="M28 52 L26 70 M70 52 L74 70" {...s} />
    <Path d="M18 70 H32 M66 70 H80" {...s} />
    <Line x1="14" y1="74" x2="86" y2="74" {...s} strokeDasharray="4 4" />
  </>
));

const LegPress = art((s) => (
  <>
    <Rect x="18" y="58" width="30" height="18" rx="3" {...s} />
    <Circle cx="30" cy="50" r="6" {...s} />
    <Path d="M36 58 L60 44 M40 66 L64 52" {...s} />
    <Path d="M56 36 L78 26 L84 40 L62 50 Z" {...s} />
  </>
));

/* ==========================================================================
   TIER 1, CONTINUED.

   The original set was ten drawings, which covered 36% of the catalogue by
   name and left the other 563 exercises sharing an equipment glyph. That
   read exactly as reported: "only the first ten exercises have the
   illustration, all the others are literally the same."

   These are chosen against the ACTUAL word frequency in the 873 seeded
   names, not against a guess at what people lift. In the uncovered set:
   stretch appears 51 times, press 49, raise 38, extension 28, clean and
   snatch 38 between them, calf 20, crunch 19, push-up 21. Each drawing
   below buys back one of those blocks.
   ========================================================================== */

/** Static stretch — the single largest uncovered block, at 51 names. */
const Stretch = art((s) => (
  <>
    <Circle cx="30" cy="26" r="7" {...s} />
    <Path d="M30 33 V56" {...s} />
    {/* reaching forward over a straight front leg */}
    <Path d="M30 56 L62 66" {...s} />
    <Path d="M30 56 L36 78 L28 86" {...s} />
    <Path d="M32 38 L58 60" {...s} />
    <Path d="M18 86 H74" {...s} />
  </>
));

/** Overhead triceps extension. 'triceps' + 'extension' = 62 names. */
const TricepsExtension = art((s) => (
  <>
    <Circle cx="50" cy="30" r="7" {...s} />
    <Path d="M50 37 V64 M50 64 L42 86 M50 64 L58 86" {...s} />
    {/* upper arms vertical, forearms folded back behind the head */}
    <Path d="M44 42 L44 20 L58 14" {...s} />
    <Path d="M56 42 L56 20 L58 14" {...s} />
    <Path d="M52 10 h14 M54 6 v10 M64 6 v10" {...s} />
  </>
));

/** Lateral / front raise. 'raise' + 'lateral' = 51 names. */
const LateralRaise = art((s) => (
  <>
    <Circle cx="50" cy="24" r="7" {...s} />
    <Path d="M50 31 V62 M50 62 L42 86 M50 62 L58 86" {...s} />
    {/* arms straight out to the sides, at shoulder height */}
    <Path d="M44 38 H22 M56 38 H78" {...s} />
    <Path d="M16 34 v8 M28 34 v8 M72 34 v8 M84 34 v8" {...s} />
  </>
));

/** Cable pushdown — the other triceps shape, and a cable tell. */
const Pushdown = art((s) => (
  <>
    <Path d="M74 10 V84" {...s} />
    <Path d="M74 16 H56" {...s} />
    <Circle cx="42" cy="30" r="7" {...s} />
    <Path d="M42 37 V64 M42 64 L34 86 M42 64 L50 86" {...s} />
    <Path d="M48 42 L56 34 L56 16" {...s} />
    <Path d="M50 50 h14" {...s} />
  </>
));

/** Kettlebell swing. 34 names carry 'kettlebell'. */
const Swing = art((s) => (
  <>
    <Circle cx="46" cy="24" r="7" {...s} />
    <Path d="M46 31 L44 54" {...s} />
    <Path d="M44 54 L36 72 L36 86 M44 54 L56 70 L56 86" {...s} />
    {/* arms swinging the bell forward and up */}
    <Path d="M48 38 L70 46" {...s} />
    <Path d="M70 46 a7 7 0 0 1 8 6" {...s} />
    <Circle cx="76" cy="58" r="7" {...s} />
    <Path d="M20 86 H80" {...s} strokeDasharray="4 4" />
  </>
));

/** Olympic pull — clean, snatch, high pull. 38 names. */
const OlympicPull = art((s) => (
  <>
    <Circle cx="46" cy="18" r="7" {...s} />
    <Path d="M46 25 V46" {...s} />
    <Path d="M46 46 L38 66 L38 86 M46 46 L56 66 L56 86" {...s} />
    {/* bar caught high, elbows up */}
    <Path d="M40 32 L34 26 M52 32 L58 26" {...s} />
    <Path d="M24 26 H68 M28 19 V33 M64 19 V33" {...s} />
    <Path d="M22 86 H72" {...s} />
  </>
));

/** Push-up. 'push' + 'up' together account for 44 names. */
const PushUp = art((s) => (
  <>
    <Circle cx="26" cy="42" r="6" {...s} />
    <Path d="M32 46 L72 60" {...s} />
    {/* arms down to the floor, hips high enough to read as a plank */}
    <Path d="M34 48 V74 M28 46 V74" {...s} />
    <Path d="M70 60 L78 78" {...s} />
    <Path d="M22 74 H40 M70 78 H86" {...s} />
    <Path d="M14 82 H90" {...s} strokeDasharray="4 4" />
  </>
));

/** Standing calf raise. 20 names. */
const CalfRaise = art((s) => (
  <>
    <Circle cx="50" cy="18" r="7" {...s} />
    <Path d="M50 25 V54" {...s} />
    <Path d="M42 32 L42 50 M58 32 L58 50" {...s} />
    <Path d="M50 54 L44 74 M50 54 L56 74" {...s} />
    {/* heels lifted clear of the step -- the whole point of the drawing */}
    <Path d="M40 74 L36 68 M60 74 L64 68" {...s} />
    <Path d="M30 78 H70 V88 H30 Z" {...s} />
  </>
));

/** Crunch / sit-up. 19 names, plus most of the ab work. */
const Crunch = art((s) => (
  <>
    <Path d="M18 78 H82" {...s} strokeDasharray="4 4" />
    <Circle cx="36" cy="52" r="7" {...s} />
    <Path d="M42 56 L58 66" {...s} />
    {/* knees bent, feet planted */}
    <Path d="M58 66 L70 54 L78 68" {...s} />
    <Path d="M38 46 L44 40 M42 58 L48 50" {...s} />
    <Path d="M72 74 H84" {...s} />
  </>
));

/** Dip. */
const Dip = art((s) => (
  <>
    <Path d="M26 34 V86 M74 34 V86" {...s} />
    <Path d="M20 34 H36 M64 34 H80" {...s} />
    <Circle cx="50" cy="34" r="7" {...s} />
    <Path d="M50 41 V64" {...s} />
    <Path d="M44 40 L30 34 M56 40 L70 34" {...s} />
    <Path d="M50 64 L44 82 L52 88" {...s} />
  </>
));

/** Chest fly / pec deck. */
const Fly = art((s) => (
  <>
    <Path d="M18 68 H70 M24 68 V86 M64 68 V86 M14 86 H74" {...s} />
    <Circle cx="66" cy="60" r="6" {...s} />
    <Path d="M60 62 H34" {...s} />
    {/* arms wide in an arc, which is the whole difference from a press */}
    <Path d="M52 60 L34 44" {...s} />
    <Path d="M46 62 L30 50" {...s} />
    <Path d="M28 38 h12 M30 34 v10 M38 34 v10" {...s} />
    <Path d="M22 46 h12 M24 42 v10 M32 42 v10" {...s} />
  </>
));

/** Shrug. */
const Shrug = art((s) => (
  <>
    <Circle cx="50" cy="22" r="7" {...s} />
    {/* shoulders drawn high and square -- the movement is the shoulder line */}
    <Path d="M36 34 H64" {...s} />
    <Path d="M50 34 V60 M50 60 L42 86 M50 60 L58 86" {...s} />
    <Path d="M38 34 V62 M62 34 V62" {...s} />
    <Path d="M30 62 h16 M32 57 v10 M44 57 v10" {...s} />
    <Path d="M54 62 h16 M56 57 v10 M68 57 v10" {...s} />
  </>
));

/** Hip thrust / glute bridge. 'hip' appears 15 times. */
const HipThrust = art((s) => (
  <>
    <Path d="M14 62 H40 V80 H14 Z" {...s} />
    <Circle cx="26" cy="52" r="6" {...s} />
    {/* torso ramping up from the bench to a high hip */}
    <Path d="M32 56 L58 44" {...s} />
    <Path d="M58 44 L74 62 L74 84" {...s} />
    <Path d="M44 38 h26 M48 33 v10 M66 33 v10" {...s} />
    <Path d="M66 84 H84" {...s} />
  </>
));

/** Seated leg extension. */
const LegExtension = art((s) => (
  <>
    <Rect x="20" y="46" width="26" height="26" rx="3" {...s} />
    <Circle cx="33" cy="36" r="6" {...s} />
    <Path d="M46 58 H72" {...s} />
    <Path d="M72 52 v12" {...s} />
    <Path d="M46 68 H60" {...s} />
    <Path d="M26 72 V86 M40 72 V86" {...s} />
  </>
));

/** Lying leg curl — the mirror of the extension. */
const LegCurl = art((s) => (
  <>
    <Rect x="16" y="52" width="46" height="12" rx="3" {...s} />
    <Circle cx="22" cy="44" r="6" {...s} />
    <Path d="M62 58 L76 44" {...s} />
    <Path d="M72 40 h10" {...s} />
    <Path d="M22 64 V78 M56 64 V78" {...s} />
  </>
));

/** Face pull / rear delt — the cable-at-eye-level shape. */
const FacePull = art((s) => (
  <>
    <Path d="M84 12 V86" {...s} />
    <Path d="M84 30 H62" {...s} />
    <Circle cx="44" cy="30" r="7" {...s} />
    <Path d="M44 37 V62 M44 62 L36 86 M44 62 L52 86" {...s} />
    {/* elbows flared wide and high, which is the tell */}
    <Path d="M38 40 L26 26 M50 40 L62 26" {...s} />
    <Path d="M56 26 h10" {...s} />
  </>
));

/** Hanging leg raise. */
const HangingRaise = art((s) => (
  <>
    <Path d="M18 12 H82" {...s} />
    <Path d="M40 12 V26 M60 12 V26" {...s} />
    <Circle cx="50" cy="34" r="7" {...s} />
    <Path d="M50 41 V62" {...s} />
    {/* legs folded up to horizontal */}
    <Path d="M50 62 L72 58" {...s} />
    <Path d="M72 58 L78 66" {...s} />
    <Path d="M44 27 V16 M56 27 V16" {...s} />
  </>
));

/** Good morning / back extension — the hinge, without a bar on the floor. */
const Hinge = art((s) => (
  <>
    <Circle cx="28" cy="38" r="7" {...s} />
    <Path d="M34 42 L58 54" {...s} />
    <Path d="M58 54 L58 84" {...s} />
    <Path d="M22 30 H62 M26 24 V36 M58 24 V36" {...s} />
    <Path d="M32 44 L34 30" {...s} />
    <Path d="M50 84 H68" {...s} />
  </>
));

/** Russian twist / rotation. */
const Twist = art((s) => (
  <>
    <Circle cx="46" cy="36" r="7" {...s} />
    <Path d="M46 43 V60" {...s} />
    <Path d="M46 60 L64 70 L64 82" {...s} />
    {/* the arc is the rotation */}
    <Path d="M30 44 a20 20 0 0 1 34 4" {...s} strokeDasharray="4 3" />
    <Path d="M40 46 H62" {...s} />
    <Circle cx="66" cy="46" r="5" {...s} />
    <Path d="M56 82 H74" {...s} />
  </>
));

/** Jump / plyometric. 'jump' appears 15 times. */
const Jump = art((s) => (
  <>
    <Circle cx="50" cy="20" r="7" {...s} />
    <Path d="M50 27 V48" {...s} />
    <Path d="M50 34 L34 24 M50 34 L66 24" {...s} />
    {/* tucked legs, and the ground line well below the feet */}
    <Path d="M50 48 L38 60 L44 68 M50 48 L62 60 L56 68" {...s} />
    <Path d="M22 84 H78" {...s} strokeDasharray="4 4" />
    <Path d="M46 74 V80 M54 74 V80" {...s} />
  </>
));

/** Loaded carry — farmer's walk, suitcase carry. */
const Carry = art((s) => (
  <>
    <Circle cx="50" cy="20" r="7" {...s} />
    <Path d="M50 27 V58 M50 58 L42 84 M50 58 L58 84" {...s} />
    <Path d="M42 34 V56 M58 34 V56" {...s} />
    <Path d="M32 56 h20 M34 50 v12 M50 50 v12" {...s} />
    <Path d="M48 56 h20 M50 50 v12 M66 50 v12" {...s} />
    <Path d="M20 88 H80" {...s} strokeDasharray="4 4" />
  </>
));

/** Wrist / forearm work. */
const Wrist = art((s) => (
  <>
    <Path d="M18 58 H58" {...s} />
    <Path d="M22 58 V78 M52 58 V78" {...s} />
    <Path d="M32 52 L58 52" {...s} />
    <Path d="M58 52 L70 40" {...s} />
    <Path d="M62 34 h14 M64 30 v10 M74 30 v10" {...s} />
    <Circle cx="26" cy="44" r="6" {...s} />
  </>
));

/** Machine work we have no better drawing for: a seat and a stack. */
const Machine = art((s) => (
  <>
    <Rect x="20" y="26" width="22" height="52" rx="3" {...s} />
    <Path d="M24 34 h14 M24 42 h14 M24 50 h14 M24 58 h14" {...s} />
    <Path d="M42 30 H70" {...s} />
    <Circle cx="66" cy="42" r="6" {...s} />
    <Rect x="56" y="52" width="22" height="8" rx="2" {...s} />
    <Path d="M60 60 V80 M74 60 V80" {...s} />
    <Path d="M52 84 H84" {...s} />
  </>
));

/** Ab wheel / barbell rollout. */
const Rollout = art((s) => (
  <>
    <Path d="M14 84 H86" {...s} strokeDasharray="4 4" />
    <Circle cx="30" cy="48" r="6" {...s} />
    <Path d="M34 52 L34 74" {...s} />
    <Path d="M34 74 L22 82 M34 74 L44 82" {...s} />
    <Path d="M36 50 L62 62" {...s} />
    <Circle cx="70" cy="70" r="10" {...s} />
    <Path d="M60 70 h20" {...s} />
  </>
));

/** Sled push or drag. */
const Sled = art((s) => (
  <>
    <Path d="M14 84 H86" {...s} strokeDasharray="4 4" />
    <Circle cx="26" cy="34" r="7" {...s} />
    <Path d="M26 41 L34 60 L28 80" {...s} />
    <Path d="M34 60 L46 74 L46 82" {...s} />
    <Path d="M30 46 L58 50" {...s} />
    <Path d="M58 34 V74 M58 74 H84 M58 44 H80" {...s} />
    <Path d="M62 34 h16 M64 30 v8 M76 30 v8" {...s} />
  </>
));

/** Resistance band. */
const Band = art((s) => (
  <>
    <Circle cx="50" cy="22" r="7" {...s} />
    <Path d="M50 29 V60 M50 60 L42 84 M50 60 L58 84" {...s} />
    <Path d="M44 38 H24 M56 38 H76" {...s} />
    {/* the band itself, drawn slack then stretched */}
    <Path d="M24 38 q26 14 52 0" {...s} strokeDasharray="5 3" />
    <Path d="M20 33 v10 M80 33 v10" {...s} />
  </>
));

/** Joint circles and other warm-up rotations. */
const Circles = art((s) => (
  <>
    <Circle cx="50" cy="24" r="7" {...s} />
    <Path d="M50 31 V60 M50 60 L42 84 M50 60 L58 84" {...s} />
    <Path d="M44 38 H28" {...s} />
    <Circle cx="24" cy="38" r="12" {...s} strokeDasharray="4 3" />
    <Path d="M56 38 H72" {...s} />
    <Circle cx="76" cy="38" r="12" {...s} strokeDasharray="4 3" />
  </>
));

/** Side bend / lateral flexion. */
const SideBend = art((s) => (
  <>
    <Circle cx="42" cy="22" r="7" {...s} />
    <Path d="M44 29 L52 58" {...s} />
    <Path d="M52 58 L46 84 M52 58 L62 84" {...s} />
    {/* one arm overhead, torso tipped -- the shape IS the movement */}
    <Path d="M46 34 L58 18" {...s} />
    <Path d="M50 42 L52 62" {...s} />
    <Path d="M46 62 h14 M48 57 v10 M58 57 v10" {...s} />
  </>
));

/** Pullover. */
const Pullover = art((s) => (
  <>
    <Path d="M20 62 H72 M26 62 V82 M66 62 V82 M16 82 H76" {...s} />
    <Circle cx="34" cy="54" r="6" {...s} />
    <Path d="M40 56 H66" {...s} />
    {/* arms swept back past the head */}
    <Path d="M40 54 L24 38" {...s} />
    <Path d="M18 32 h14 M20 28 v10 M30 28 v10" {...s} />
  </>
));

/** Hip abduction / adduction. */
const Abduction = art((s) => (
  <>
    <Rect x="34" y="30" width="26" height="24" rx="3" {...s} />
    <Circle cx="47" cy="20" r="6" {...s} />
    <Path d="M38 54 L22 76" {...s} />
    <Path d="M56 54 L72 76" {...s} />
    <Path d="M14 76 h16 M64 76 h16" {...s} />
    <Path d="M30 66 h34" {...s} strokeDasharray="4 3" />
  </>
));

/** Crawl / bear crawl. */
const Crawl = art((s) => (
  <>
    <Path d="M14 84 H86" {...s} strokeDasharray="4 4" />
    <Circle cx="26" cy="40" r="6" {...s} />
    <Path d="M32 44 H64" {...s} />
    <Path d="M34 46 V80 M28 44 V80" {...s} />
    <Path d="M62 46 L70 62 L70 80" {...s} />
    <Path d="M56 46 L58 64 L58 80" {...s} />
  </>
));

/** Neck work. */
const Neck = art((s) => (
  <>
    <Circle cx="50" cy="34" r="12" {...s} />
    <Path d="M50 46 V64" {...s} />
    <Path d="M32 64 H68" {...s} />
    <Path d="M38 30 a14 14 0 0 1 -6 8" {...s} strokeDasharray="3 3" />
    <Path d="M62 30 a14 14 0 0 0 6 8" {...s} strokeDasharray="3 3" />
    <Path d="M44 72 V84 M56 72 V84" {...s} />
  </>
));

/** Isometric hold. */
const Hold = art((s) => (
  <>
    <Circle cx="50" cy="22" r="7" {...s} />
    <Path d="M50 29 V52" {...s} />
    <Path d="M50 52 L38 66 L38 84 M50 52 L62 66 L62 84" {...s} />
    <Path d="M44 36 L34 46 M56 36 L66 46" {...s} />
    <Path d="M30 84 H70" {...s} />
    {/* the stopwatch is what says "hold", not "move" */}
    <Circle cx="76" cy="20" r="10" {...s} />
    <Path d="M76 14 V20 L81 23 M76 8 v4" {...s} />
  </>
));

/**
 * Keyword patterns, most specific first. A movement matches when EVERY word in
 * its pattern appears in the exercise name.
 */
const PATTERNS: Array<[string[], React.ComponentType<ArtProps>]> = [
  // ---- most specific first ------------------------------------------
  // A pattern matches when EVERY word in it appears in the name, so
  // ['leg','press'] must precede ['press'] or every leg press becomes a
  // bench press. Read this list as a decision tree, not a set.
  [['leg', 'press'], LegPress],
  [['leg', 'extension'], LegExtension],
  [['leg', 'curl'], LegCurl],
  [['leg', 'raise'], HangingRaise],
  [['hanging'], HangingRaise],
  [['calf'], CalfRaise],

  [['incline'], InclinePress],
  [['decline'], FlatPress],
  [['bench', 'press'], FlatPress],
  [['chest', 'press'], FlatPress],
  [['fly'], Fly],
  [['flye'], Fly],
  [['pec', 'deck'], Fly],

  [['pulldown'], Pulldown],
  [['pull', 'down'], Pulldown],
  [['pull', 'up'], Pulldown],
  [['chin', 'up'], Pulldown],
  [['lat', 'pull'], Pulldown],

  [['face', 'pull'], FacePull],
  [['rear', 'delt'], FacePull],
  [['reverse', 'fly'], FacePull],
  [['upright', 'row'], Shrug],
  [['shrug'], Shrug],

  [['overhead', 'press'], OverheadPress],
  [['shoulder', 'press'], OverheadPress],
  [['military'], OverheadPress],
  [['push', 'press'], OverheadPress],
  [['lateral', 'raise'], LateralRaise],
  [['front', 'raise'], LateralRaise],
  [['side', 'raise'], LateralRaise],
  [['raise'], LateralRaise],

  [['romanian'], Deadlift],
  [['deadlift'], Deadlift],
  [['good', 'morning'], Hinge],
  [['back', 'extension'], Hinge],
  [['hyperextension'], Hinge],
  [['hip', 'thrust'], HipThrust],
  [['glute', 'bridge'], HipThrust],
  [['bridge'], HipThrust],

  [['squat'], Squat],
  [['lunge'], Squat],
  [['step', 'up'], Squat],
  [['split'], Squat],

  [['clean'], OlympicPull],
  [['snatch'], OlympicPull],
  [['jerk'], OlympicPull],
  [['high', 'pull'], OlympicPull],
  [['swing'], Swing],
  [['kettlebell'], Swing],

  [['push', 'up'], PushUp],
  [['pushup'], PushUp],
  [['press', 'up'], PushUp],
  [['burpee'], Jump],
  [['jump'], Jump],
  [['box', 'jump'], Jump],
  [['hop'], Jump],

  [['pushdown'], Pushdown],
  [['push', 'down'], Pushdown],
  [['kickback'], Pushdown],
  [['skullcrusher'], TricepsExtension],
  [['skull', 'crusher'], TricepsExtension],
  [['triceps'], TricepsExtension],
  [['tricep'], TricepsExtension],
  [['extension'], TricepsExtension],

  [['dip'], Dip],
  [['row'], Row],
  [['wrist'], Wrist],
  [['forearm'], Wrist],
  [['curl'], Curl],

  [['plank'], Plank],
  [['crunch'], Crunch],
  [['sit', 'up'], Crunch],
  [['situp'], Crunch],
  [['twist'], Twist],
  [['russian'], Twist],
  [['woodchop'], Twist],
  [['rotation'], Twist],

  [['carry'], Carry],
  [['farmer'], Carry],

  [['rollout'], Rollout],
  [['roller'], Rollout],
  [['ab', 'wheel'], Rollout],
  [['sled'], Sled],
  [['drag'], Sled],
  [['prowler'], Sled],
  [['atlas'], Carry],
  [['band'], Band],
  [['circles'], Circles],
  [['side', 'bend'], SideBend],
  [['pullover'], Pullover],
  [['adductor'], Abduction],
  [['adduction'], Abduction],
  [['abduction'], Abduction],
  [['groin'], Abduction],
  [['crawl'], Crawl],
  [['neck'], Neck],
  [['isometric'], Hold],
  [['hold'], Hold],
  [['balance'], Hold],
  [['ropes'], Swing],
  [['battling'], Swing],
  [['sprint'], Jump],
  [['bound'], Jump],
  [['skater'], Jump],
  // ---- names the first pass missed, added after measuring -----------
  // Each of these was in the 121-name miss list. Grouped by the figure they
  // land on so the reasoning stays visible.
  //
  // Floor and anti-extension core. All of these are someone on their back or
  // in a plank; the crunch figure reads correctly for the whole family.
  [['dead', 'bug'], Crunch],
  [['flutter'], Crunch],
  [['heel', 'touch'], Crunch],
  [['cocoon'], Crunch],
  [['jackknife'], Crunch],
  [['pull-in'], Crunch],
  [['bottoms', 'up'], Crunch],
  [['leg', 'tuck'], Crunch],
  [['butt-up'], Crunch],
  [['body-up'], Crunch],
  [['otis'], Crunch],
  [['fallout'], Rollout],
  [['elbow', 'to', 'knee'], Crunch],
  [['leg', 'lift'], HangingRaise],
  // Hanging from a bar. Chins, muscle-ups and rope climbs are all vertical
  // pulls, which is what the pulldown figure shows.
  [['chin'], Pulldown],
  [['muscle', 'up'], Pulldown],
  [['rope', 'climb'], Pulldown],
  // Shoulder and rotator-cuff work: arms out to the side, loaded light.
  [['scaption'], LateralRaise],
  [['pronation'], LateralRaise],
  [['supination'], LateralRaise],
  [['side', 'lateral'], LateralRaise],
  [['around', 'the', 'world'], LateralRaise],
  [['iron', 'cross'], LateralRaise],
  [['car', 'driver'], LateralRaise],
  [['power', 'partial'], LateralRaise],
  // Barbell hinges and landmine work.
  [['landmine'], Twist],
  [['jammer'], OverheadPress],
  [['rack', 'pull'], Deadlift],
  [['rack', 'delivery'], OlympicPull],
  [['pull', 'through'], Hinge],
  [['stiff', 'leg'], Hinge],
  // Grip.
  [['pinch'], Wrist],
  [['hand', 'squeeze'], Wrist],
  [['spell', 'caster'], Twist],
  // Machine and assisted hamstring / hip.
  [['hamstring', 'slide'], LegCurl],
  [['manual', 'hamstring'], LegCurl],
  [['thigh', 'abductor'], Abduction],
  [['monster', 'walk'], Band],
  [['slam'], Swing],
  // Cardio equipment.
  [['air', 'bike'], Cardio],
  [['bicycl'], Cardio],
  [['elliptical'], Cardio],
  [['rowing'], Cardio],
  [['stationary'], Cardio],
  [['treadmill'], Jump],
  // ---- the big generic buckets, LAST --------------------------------
  // 'stretch' is the single largest block in the catalogue at 51 names,
  // and it is deliberately near the bottom: "standing hamstring stretch"
  // should match the stretch figure, but "stretch" appearing inside a
  // more specific movement's name must not beat that movement.
  [['stretch'], Stretch],
  [['smr'], Stretch],
  [['foam'], Stretch],
  [['mobility'], Stretch],
  [['machine'], Machine],
  [['cable'], Machine],
  [['press'], FlatPress],
];

/**
 * The category tier. Every row in the catalogue carries one of these, and a
 * family figure beats an equipment glyph every time: "Child's Pose" drawn as
 * a stretch is useful, drawn as a dumbbell is noise.
 */
const BY_CATEGORY: Record<string, React.ComponentType<ArtProps>> = {
  stretching: Stretch,
  plyometrics: Jump,
  strongman: Carry,
  cardio: Cardio,
  powerlifting: Deadlift,
  'olympic weightlifting': OlympicPull,
};

/** Which tier answered. Useful for measuring coverage, and for tests. */
export type ArtTier = 'name' | 'category' | 'equipment';

/**
 * Pick the illustration for an exercise.
 *
 * Returns a component rather than an element so the caller sizes and colours
 * it. `drawn` stays true for tiers 1 and 2 — both are real figures — and goes
 * false only for the equipment glyph, so a screen can still choose to treat
 * the glyph differently.
 */
export function exerciseArt(
  name: string,
  equipment: string | null | undefined,
  category?: string | null,
): { Art: React.ComponentType<ArtProps>; drawn: boolean; tier: ArtTier } {
  const n = name.toLowerCase();
  for (const [words, Comp] of PATTERNS) {
    if (words.every((w) => n.includes(w))) {
      return { Art: Comp, drawn: true, tier: 'name' };
    }
  }

  const byCat = category ? BY_CATEGORY[category.toLowerCase()] : undefined;
  if (byCat) return { Art: byCat, drawn: true, tier: 'category' };

  const Glyph = equipmentIcon(equipment);
  const Fallback = ({ size = 120, color = palette.textDim }: ArtProps) => (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Glyph size={size * 0.55} color={color} strokeWidth={1.4} />
    </View>
  );
  return { Art: Fallback, drawn: false, tier: 'equipment' };
}
