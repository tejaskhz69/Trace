/**
 * The line-icon set, transcribed path-for-path from the design artifact.
 *
 * 2px strokes on a 24x24 box, round caps and joins, no fills. They are drawn
 * rather than shipped as a font because the set is small and an icon font
 * would be a 2 MB dependency for a dozen glyphs.
 *
 * `size` and `color` are props rather than styles so an icon inherits the
 * accent from its caller — the active tab is the accent colour, everything
 * else is `textFaint`.
 */

import React, { memo } from 'react';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

export interface IconProps {
  size?: number;
  color?: string;
  /** Stroke weight. The artifact uses 1.7 at 24px. */
  strokeWidth?: number;
}

function make(
  name: string,
  render: (stroke: { stroke: string; strokeWidth: number }) => React.ReactNode,
) {
  const Comp = memo(function Icon({
    size = 22,
    color = '#8A97A3',
    strokeWidth = 1.7,
  }: IconProps) {
    return (
      <Svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {render({ stroke: color, strokeWidth })}
      </Svg>
    );
  });
  Comp.displayName = name;
  return Comp;
}

export const IconHome = make('IconHome', (s) => (
  <>
    <Path d="M3.5 16a8.5 8.5 0 0 1 17 0" {...s} />
    <Path d="M12 16l4.2-5.4" {...s} />
    <Circle cx="12" cy="16" r="1.5" {...s} />
    <Path d="M3.5 19.5h17" {...s} />
  </>
));

export const IconNutrition = make('IconNutrition', (s) => (
  <>
    <Path d="M7 3v6M10.5 3v6M8.75 9v12" {...s} />
    <Path d="M7 9h3.5" {...s} />
    <Path d="M17.5 3c1.6 2.2 1.6 6.3 0 8.4V21" {...s} />
  </>
));

export const IconTrainer = make('IconTrainer', (s) => (
  <Path d="M3 9.5v5M6.5 7v10M17.5 7v10M21 9.5v5M6.5 12h11" {...s} />
));

export const IconChart = make('IconChart', (s) => (
  <>
    <Path d="M4 19.5h16" {...s} />
    <Path d="M6.5 19.5v-6M11 19.5v-11M15.5 19.5v-7M20 19.5v-13" {...s} />
  </>
));

export const IconUser = make('IconUser', (s) => (
  <>
    <Circle cx="12" cy="8.4" r="3.4" {...s} />
    <Path d="M5 20.2a7 7 0 0 1 14 0" {...s} />
  </>
));

export const IconSearch = make('IconSearch', (s) => (
  <>
    <Circle cx="10.5" cy="10.5" r="6" {...s} />
    <Path d="M15 15l5 5" {...s} />
  </>
));

export const IconCamera = make('IconCamera', (s) => (
  <>
    <Path d="M3 8.5h3.5L8 6h8l1.5 2.5H21v11H3z" {...s} />
    <Circle cx="12" cy="13.5" r="3.6" {...s} />
  </>
));

export const IconBarcode = make('IconBarcode', (s) => (
  <Path d="M3 5v14M6.5 5v14M9.5 5v10M12.5 5v14M15.5 5v10M18.5 5v14M21 5v14" {...s} />
));

export const IconGear = make('IconGear', (s) => (
  <>
    <Circle cx="12" cy="12" r="3.2" {...s} />
    <Path
      d="M12 3v2.6M12 18.4V21M3 12h2.6M18.4 12H21M5.6 5.6l1.9 1.9M16.5 16.5l1.9 1.9M18.4 5.6l-1.9 1.9M7.5 16.5l-1.9 1.9"
      {...s}
    />
  </>
));

export const IconWatch = make('IconWatch', (s) => (
  <>
    <Rect x="7" y="6.5" width="10" height="11" rx="3" {...s} />
    <Path d="M9.5 6.5V3.5h5v3M9.5 17.5v3h5v-3" {...s} />
  </>
));

export const IconHeart = make('IconHeart', (s) => (
  <Path
    d="M12 20s-7.5-4.6-7.5-9.4A4.1 4.1 0 0 1 12 8a4.1 4.1 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z"
    {...s}
  />
));

export const IconLink = make('IconLink', (s) => (
  <>
    <Path d="M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.4l-1.7 1.7" {...s} />
    <Path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.6l1.7-1.7" {...s} />
  </>
));

export const IconChevron = make('IconChevron', (s) => (
  <Path d="M9.5 5.5L16 12l-6.5 6.5" {...s} />
));

export const IconLock = make('IconLock', (s) => (
  <>
    <Path d="M6.5 10.5h11V20h-11z" {...s} />
    <Path d="M8.8 10.5V7.8a3.2 3.2 0 0 1 6.4 0v2.7" {...s} />
  </>
));

// ---------------------------------------------------------------------------
// Equipment glyphs
// ---------------------------------------------------------------------------

/**
 * One glyph per equipment class, used as the fallback thumbnail for any
 * exercise without hand-drawn line art.
 *
 * There are 736 exercises and drawing each is not feasible, but an equipment
 * glyph is not a placeholder — it carries real information. "Cable" versus
 * "barbell" versus "machine" is exactly what a beginner scanning the list
 * needs to know to find the thing in front of them, and it keeps every row
 * in the same visual language instead of mixing photographs into a line-art
 * screen.
 */
export const IconBarbell = make('IconBarbell', (s) => (
  <Path d="M3 9.5v5M6.5 7v10M17.5 7v10M21 9.5v5M6.5 12h11" {...s} />
));

export const IconDumbbell = make('IconDumbbell', (s) => (
  <Path d="M4 8.5v7M7.5 6.5v11M16.5 6.5v11M20 8.5v7M7.5 12h9" {...s} />
));

export const IconCable = make('IconCable', (s) => (
  <>
    <Path d="M5 3.5v17" {...s} />
    <Path d="M5 5.5h7a3 3 0 0 1 3 3v4" {...s} />
    <Rect x="11.5" y="12.5" width="7" height="4" rx="1.4" {...s} />
  </>
));

export const IconMachine = make('IconMachine', (s) => (
  <>
    <Rect x="4" y="5" width="16" height="10" rx="2" {...s} />
    <Path d="M8 15v4.5M16 15v4.5M4.5 19.5h15" {...s} />
    <Path d="M8.5 9.5h7" {...s} />
  </>
));

export const IconBodyweight = make('IconBodyweight', (s) => (
  <>
    <Circle cx="12" cy="5.2" r="2.2" {...s} />
    <Path d="M12 7.4v6M12 13.4l-3.2 6M12 13.4l3.2 6M7.5 9.8h9" {...s} />
  </>
));

export const IconKettlebell = make('IconKettlebell', (s) => (
  <>
    <Path d="M9.3 8.2a3 3 0 0 1 5.4 0" {...s} />
    <Path d="M8.6 8.2a5.5 5.5 0 1 0 6.8 0z" {...s} />
  </>
));

/** Maps the `equipment` column onto a glyph. Unknown values get bodyweight. */
export const EQUIPMENT_ICON: Record<
  string,
  React.ComponentType<IconProps>
> = {
  barbell: IconBarbell,
  dumbbell: IconDumbbell,
  cable: IconCable,
  machine: IconMachine,
  smith: IconMachine,
  lever: IconMachine,
  bodyweight: IconBodyweight,
  band: IconCable,
  kettlebell: IconKettlebell,
  ez_bar: IconBarbell,
  trap_bar: IconBarbell,
};

export function equipmentIcon(
  equipment: string | null | undefined,
): React.ComponentType<IconProps> {
  return EQUIPMENT_ICON[(equipment ?? '').toLowerCase()] ?? IconBodyweight;
}

// ---------------------------------------------------------------------------
// Sport glyphs — the ACTIVITIES chips
// ---------------------------------------------------------------------------

export const IconCycling = make('IconCycling', (s) => (
  <>
    <Circle cx="5.5" cy="16.5" r="3.5" {...s} />
    <Circle cx="18.5" cy="16.5" r="3.5" {...s} />
    <Path d="M5.5 16.5l4-8h4l-2.5 8h7.5" {...s} />
    <Path d="M12.5 8.5h3" {...s} />
  </>
));

export const IconRunning = make('IconRunning', (s) => (
  <>
    <Circle cx="14" cy="4.6" r="2" {...s} />
    <Path d="M9 20l2.6-4.6 1.4-3.4-3.4 1.6L8 17" {...s} />
    <Path d="M13 12l3 2.4.8 5" {...s} />
    <Path d="M13.6 8.4L10 10" {...s} />
  </>
));

export const IconSwimming = make('IconSwimming', (s) => (
  <>
    <Circle cx="16.5" cy="7.5" r="1.8" {...s} />
    <Path d="M4 13l3.5-2.6 4.5 2 3-2.4" {...s} />
    <Path d="M3 18.2c1.6 0 1.6 1.2 3.2 1.2s1.6-1.2 3.2-1.2 1.6 1.2 3.2 1.2 1.6-1.2 3.2-1.2 1.6 1.2 3.2 1.2" {...s} />
  </>
));

export const IconRacket = make('IconRacket', (s) => (
  <>
    <Path d="M13.4 10.6a4.6 5.8 0 1 0-3.2-3.2 4.6 5.8 0 0 0 3.2 3.2z" {...s} />
    <Path d="M10.4 10.8L5 19" {...s} />
  </>
));

export const IconRowing = make('IconRowing', (s) => (
  <>
    <Circle cx="7.5" cy="6" r="1.8" {...s} />
    <Path d="M3 17.5l6-3.5 4 2 5-6" {...s} />
    <Path d="M9.5 8.5l3.5 3" {...s} />
  </>
));

export const IconWalking = make('IconWalking', (s) => (
  <>
    <Circle cx="12.6" cy="4.6" r="2" {...s} />
    <Path d="M11 20l1.4-6.4M12.4 13.6l-2.4-4.2 3.4-1.6 2.2 3.2 2.4.8" {...s} />
    <Path d="M12.4 13.6l2.6 2.2.6 4.2" {...s} />
  </>
));

export const IconHiit = make('IconHiit', (s) => (
  <Path d="M13.5 2.5L5.5 13h5l-1 8.5L18.5 11h-5z" {...s} />
));

/* The catalogue grew from 9 sports to 40, and `sportIcon` fell back to the
   HIIT lightning bolt for everything it didn't know -- so thirty-odd chips
   rendered as the same glyph and the row read as a rendering bug rather than
   a list. These cover the rest by FAMILY rather than one-per-sport: a ball
   sport gets a ball, a racket sport gets a racket. Distinguishing squash from
   padel with 24px of line art is not possible and not useful; distinguishing
   a racket from a bicycle is both. */

export const IconBall = make('IconBall', (s) => (
  <>
    <Circle cx="12" cy="12" r="8.5" {...s} />
    <Path d="M12 3.5c2.6 2.4 2.6 14.6 0 17M3.9 9.2c3.4 1.4 12.8 1.4 16.2 0M3.9 14.8c3.4-1.4 12.8-1.4 16.2 0" {...s} />
  </>
));

export const IconHoop = make('IconHoop', (s) => (
  <>
    <Path d="M4 4.5h16v6H4z" {...s} />
    <Path d="M8.5 10.5h7l-1.4 5h-4.2z" {...s} />
    <Circle cx="12" cy="19.5" r="2" {...s} />
  </>
));

export const IconNet = make('IconNet', (s) => (
  <>
    <Path d="M3 8.5h18M3 8.5v9M21 8.5v9M3 17.5h18" {...s} />
    <Path d="M8 8.5v9M13 8.5v9M18 8.5v9M3 13h18" {...s} />
  </>
));

export const IconBat = make('IconBat', (s) => (
  <>
    <Path d="M14.5 3.2l6 6-8.4 8.4a2 2 0 0 1-2.8 0l-3.2-3.2a2 2 0 0 1 0-2.8z" {...s} />
    <Path d="M6.5 16.5L3.5 20.5" {...s} />
  </>
));

export const IconStairs = make('IconStairs', (s) => (
  <Path d="M3 20.5h5v-5h5v-5h5v-5h3" {...s} />
));

export const IconRope = make('IconRope', (s) => (
  <>
    <Circle cx="12" cy="5" r="2" {...s} />
    <Path d="M12 7v6M12 13l-2.5 7M12 13l2.5 7" {...s} />
    <Path d="M6 8c-3 3-3 9 0 12M18 8c3 3 3 9 0 12" {...s} />
  </>
));

export const IconGlove = make('IconGlove', (s) => (
  <>
    <Path d="M5.5 9.5a4.5 4.5 0 0 1 9 0v3h1.5a2 2 0 0 1 0 4H14v2.5H6z" {...s} />
    <Path d="M5.5 13.5H14" {...s} />
  </>
));

export const IconLotus = make('IconLotus', (s) => (
  <>
    <Circle cx="12" cy="5.5" r="2" {...s} />
    <Path d="M12 8v4.5" {...s} />
    <Path d="M4.5 18.5c2.5-3.5 5-5 7.5-5s5 1.5 7.5 5" {...s} />
    <Path d="M4.5 18.5h15" {...s} />
  </>
));

export const IconMountain = make('IconMountain', (s) => (
  <>
    <Path d="M2.5 19.5l6.5-11 4 6.4 2.5-3.6 6 8.2z" {...s} />
    <Circle cx="17.5" cy="5.5" r="2" {...s} />
  </>
));

export const IconWave = make('IconWave', (s) => (
  <>
    <Path d="M3 16.5c2 0 2-1.6 4-1.6s2 1.6 4 1.6 2-1.6 4-1.6 2 1.6 4 1.6" {...s} />
    <Path d="M3 20c2 0 2-1.6 4-1.6s2 1.6 4 1.6 2-1.6 4-1.6 2 1.6 4 1.6" {...s} />
    <Path d="M7.5 12L17 3.5l1.5 5.5" {...s} />
  </>
));

export const IconPaddle = make('IconPaddle', (s) => (
  <>
    <Path d="M3.5 20.5L20.5 3.5" {...s} />
    <Path d="M16.5 3.5h4.5v4.5zM3 16.5v4.5h4.5z" {...s} />
  </>
));

export const IconFlag = make('IconFlag', (s) => (
  <>
    <Path d="M6 21V3.5" {...s} />
    <Path d="M6 4.5h11l-2.5 3.5L17 11.5H6z" {...s} />
  </>
));

export const IconHorse = make('IconHorse', (s) => (
  <>
    <Path d="M5 20.5c0-5 3-8 7-8.5l3.5-4.5 3 1.5-1.5 3.5c1.5 2 1.5 5.5 1 8" {...s} />
    <Path d="M15.5 7.5L13 4.5l3-.5 1 2" {...s} />
  </>
));

export const IconSkate = make('IconSkate', (s) => (
  <>
    <Path d="M6 3.5v9h6l4 3v3H4" {...s} />
    <Circle cx="7" cy="20.5" r="1.6" {...s} />
    <Circle cx="16" cy="20.5" r="1.6" {...s} />
  </>
));

export const IconDance = make('IconDance', (s) => (
  <>
    <Circle cx="14" cy="4.5" r="2" {...s} />
    <Path d="M14 6.5l-2 5 4 2-1 8" {...s} />
    <Path d="M12 11.5l-4.5 2M12 11.5l-2 9" {...s} />
    <Path d="M16 8.5l4-2" {...s} />
  </>
));

export const IconEllipse = make('IconEllipse', (s) => (
  <>
    <Path d="M3.5 17.5c0-3 3.5-6 8.5-6s8.5-3 8.5-3" {...s} />
    <Circle cx="4.5" cy="18.5" r="2" {...s} />
    <Circle cx="19.5" cy="7.5" r="2" {...s} />
  </>
));

export const IconHouse = make('IconHouse', (s) => (
  <>
    <Path d="M3.5 10.5L12 3.5l8.5 7" {...s} />
    <Path d="M5.5 12v8.5h13V12" {...s} />
    <Path d="M10 20.5v-5h4v5" {...s} />
  </>
));

export const IconBox = make('IconBox', (s) => (
  <>
    <Path d="M3.5 8L12 4l8.5 4v8L12 20l-8.5-4z" {...s} />
    <Path d="M3.5 8L12 12l8.5-4M12 12v8" {...s} />
  </>
));

export const IconBow = make('IconBow', (s) => (
  <>
    <Path d="M20.5 3.5C10 4.5 4.5 10 3.5 20.5" {...s} />
    <Path d="M20.5 3.5L12 12" {...s} />
    <Path d="M6.5 4.5C14 6 18 10 19.5 17.5" {...s} />
  </>
));

export const IconSail = make('IconSail', (s) => (
  <>
    <Path d="M12 2.5v13" {...s} />
    <Path d="M12 4.5l7 11h-7z" {...s} />
    <Path d="M3 18.5c2 0 2 1.5 4 1.5s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5" {...s} />
  </>
));

export const IconLeaf = make('IconLeaf', (s) => (
  <>
    <Path d="M4.5 19.5C4.5 11 10 5.5 19.5 4.5c1 9.5-4.5 15-13 15z" {...s} />
    <Path d="M19.5 4.5L9 15" {...s} />
  </>
));

export const SPORT_ICON: Record<string, React.ComponentType<IconProps>> = {
  // ---- racket ----------------------------------------------------------
  badminton: IconRacket,
  pickleball: IconRacket,
  tennis: IconRacket,
  table_tennis: IconRacket,
  squash: IconRacket,
  padel: IconRacket,
  // ---- team ------------------------------------------------------------
  cricket: IconBat,
  football: IconBall,
  soccer: IconBall,
  basketball: IconHoop,
  volleyball: IconNet,
  hockey: IconBat,
  kabaddi: IconNet,
  kho_kho: IconNet,
  bootcamp: IconHiit,
  ultimate: IconBall,
  // ---- endurance -------------------------------------------------------
  running: IconRunning,
  walking: IconWalking,
  hiking: IconMountain,
  cycling: IconCycling,
  virtual_cycling: IconCycling,
  ebike: IconCycling,
  swimming: IconSwimming,
  rowing: IconRowing,
  elliptical: IconEllipse,
  stair_climbing: IconStairs,
  skipping: IconRope,
  // ---- conditioning ----------------------------------------------------
  hiit: IconHiit,
  workout: IconHiit,
  circuit: IconHiit,
  crossfit: IconBarbell,
  weight_training: IconBarbell,
  boxing: IconGlove,
  martial_arts: IconGlove,
  // ---- mobility --------------------------------------------------------
  yoga: IconLotus,
  pilates: IconLotus,
  stretching: IconLotus,
  dancing: IconDance,
  // ---- outdoor ---------------------------------------------------------
  climbing: IconMountain,
  golf: IconFlag,
  skating: IconSkate,
  skiing: IconMountain,
  surfing: IconWave,
  kayaking: IconPaddle,
  horse_riding: IconHorse,
  other: IconHiit,
};

/**
 * Keyword fallbacks, most specific first.
 *
 * WHY THIS EXISTS RATHER THAN 104 MAP ENTRIES
 * The catalogue has a hundred-odd sports and many of them are variants of one
 * movement: `cycling`, `cycling_leisure`, `cycling_fast`, `mountain_biking`
 * and `spinning` are all a person on a bike. Enumerating every key means the
 * map silently falls out of date the moment a sport is added server-side —
 * which is exactly what happened before: the map knew nine sports, the tab
 * showed forty, and thirty-one of them rendered as the same lightning bolt.
 *
 * Matching on substrings means a new `cycling_commute` picks up the bicycle
 * without anyone touching this file. ORDER MATTERS: 'ski_erg' has to be
 * tested before 'ski', or a rowing-style machine gets a mountain.
 */
const SPORT_KEYWORDS: Array<[string, React.ComponentType<IconProps>]> = [
  ['ski_erg', IconRowing],
  ['row', IconRowing],
  ['cycl', IconCycling],
  ['bik', IconCycling],
  ['spin', IconCycling],
  ['swim', IconSwimming],
  ['water', IconSwimming],
  ['open_water', IconSwimming],
  ['run', IconRunning],
  ['sprint', IconRunning],
  ['treadmill', IconRunning],
  ['triathlon', IconRunning],
  ['walk', IconWalking],
  ['hik', IconMountain],
  ['trek', IconMountain],
  ['climb', IconMountain],
  ['boulder', IconMountain],
  ['ski', IconMountain],
  ['snow', IconMountain],
  ['tennis', IconRacket],
  ['racquet', IconRacket],
  ['badminton', IconRacket],
  ['squash', IconRacket],
  ['padel', IconRacket],
  ['pickle', IconRacket],
  ['ball', IconBall],
  ['futsal', IconBall],
  ['rugby', IconBall],
  ['lacrosse', IconBall],
  ['hockey', IconBat],
  ['cricket', IconBat],
  ['box', IconGlove],
  ['kick', IconGlove],
  ['wrestl', IconGlove],
  ['bjj', IconGlove],
  ['martial', IconGlove],
  ['fenc', IconGlove],
  ['yoga', IconLotus],
  ['pilates', IconLotus],
  ['barre', IconLotus],
  ['stretch', IconLotus],
  ['tai_chi', IconLotus],
  ['foam', IconLotus],
  ['danc', IconDance],
  ['zumba', IconDance],
  ['aerobic', IconDance],
  ['bharat', IconDance],
  ['stair', IconStairs],
  ['skip', IconRope],
  ['rope', IconRope],
  ['kettle', IconBarbell],
  ['sled', IconBarbell],
  ['calisthenic', IconBarbell],
  ['crossfit', IconBarbell],
  ['weight', IconBarbell],
  ['golf', IconFlag],
  ['skat', IconSkate],
  ['board', IconSkate],
  ['surf', IconWave],
  ['sail', IconSail],
  ['paddle', IconPaddle],
  ['kayak', IconPaddle],
  ['canoe', IconPaddle],
  ['horse', IconHorse],
  ['equestr', IconHorse],
  ['archery', IconBow],
  ['garden', IconLeaf],
  ['house', IconHouse],
  ['cook', IconHouse],
  ['child', IconHouse],
  ['standing', IconHouse],
  ['shop', IconBox],
  ['moving', IconBox],
  ['labour', IconBox],
  ['dog', IconWalking],
  ['elliptic', IconEllipse],
  ['net', IconNet],
  ['hoop', IconHoop],
  ['basket', IconHoop],
];

export function sportIcon(
  sport: string | null | undefined,
): React.ComponentType<IconProps> {
  const key = (sport ?? '').toLowerCase();
  const exact = SPORT_ICON[key];
  if (exact) return exact;
  for (const [word, Icon] of SPORT_KEYWORDS) {
    if (key.includes(word)) return Icon;
  }
  // The bolt is the honest answer for "some other conditioning work", which
  // is what an unmatched key almost always is.
  return IconHiit;
}

// ---------------------------------------------------------------------------
// Quick-log sheet
// ---------------------------------------------------------------------------

export const IconMic = make('IconMic', (s) => (
  <>
    <Rect x="9" y="2.5" width="6" height="11" rx="3" {...s} />
    <Path d="M5.5 11a6.5 6.5 0 0 0 13 0" {...s} />
    <Path d="M12 17.5v4" {...s} />
  </>
));

export const IconPlus = make('IconPlus', (s) => (
  <>
    <Path d="M12 5v14" {...s} />
    <Path d="M5 12h14" {...s} />
  </>
));

/** A balance scale — weigh-ins, not body weight generally. */
export const IconScale = make('IconScale', (s) => (
  <>
    <Rect x="3" y="7" width="18" height="14" rx="3" {...s} />
    <Path d="M8 12h8" {...s} />
    <Path d="M12 7V3.5" {...s} />
  </>
));

export const IconClock = make('IconClock', (s) => (
  <>
    <Circle cx="12" cy="12" r="8.5" {...s} />
    <Path d="M12 7.5V12l3 1.8" {...s} />
  </>
));
