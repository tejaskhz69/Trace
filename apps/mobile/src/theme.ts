/**
 * Trace design system — "Instrument panel".
 *
 * The reference points are Whoop, Oura, and aircraft avionics, not consumer
 * wellness apps. The premise: this is measuring equipment, and it should look
 * like equipment. That's the visual argument for the positioning — every
 * competitor uses soft rounded cards and pastel rings, so looking like an
 * instrument is itself differentiation.
 *
 * THE RULES
 * ---------
 * 1. NEAR-BLACK, not dark grey. #07090B. Real contrast makes data pop and
 *    saves OLED battery on the screen users open ten times a day.
 * 2. TABULAR NUMERALS EVERYWHERE data appears. Proportional digits make a
 *    counting number visibly jitter as its glyph widths change — the single
 *    biggest tell of an amateur data UI.
 * 3. HAIRLINES, not shadows. 1px rules at low opacity. Shadows imply soft
 *    physical objects; instruments have edges.
 * 4. ONE ACCENT. Signal green. Everything else is greyscale plus semantic
 *    state colours. If three things are highlighted, nothing is.
 * 5. UPPERCASE MICRO-LABELS with wide tracking. This is what reads as
 *    "readout" rather than "paragraph".
 * 6. NO DECORATIVE COLOUR. Every colour carries meaning. Macro colours are
 *    consistent app-wide and colourblind-safe (blue/amber/violet, never
 *    red/green pairs).
 */

import { Platform } from 'react-native';

/**
 * Appearance modes. Only the SURFACE ramp differs between them -- text and
 * accents are identical, so the app reads as one product in either mode and
 * a screen only has to theme its backgrounds and borders.
 *
 *   dark  -- surfaces lifted off pure black so panels separate cleanly
 *   black -- true #000000 for OLED, where black pixels are simply off
 */
export type Mode = 'dark' | 'black';

export const surfaces = {
  dark: {
    void: '#07090B',
    surface: '#0E1216',
    raised: '#141A20',
    hairline: '#1C2126',
    hairlineBright: '#262D35',
  },
  black: {
    void: '#000000',
    surface: '#0A0D11',
    raised: '#12171D',
    hairline: '#191E24',
    hairlineBright: '#242B33',
  },
} as const;

export type Surfaces = (typeof surfaces)[Mode];

/**
 * Accent choice -- a real user setting, not a preview toggle. It lives in
 * Profile › Appearance.
 *
 * ONLY THE INTERACTION ACCENT CHANGES: buttons, the active tab, a selected
 * chip, the rule down the left of a callout. The chart series and the macro
 * channels below are IDENTICAL in both accents, because those carry data, and
 * data must not restyle on a preference -- a protein bar that is green in one
 * accent and grey in the other is no longer a legend the user can learn.
 *
 * That separation is the whole reason this is safe to ship as a toggle.
 */
export type Accent = 'green' | 'white';

export const accents = {
  green: {
    brand: '#3DDC84',
    brandDim: '#2A9A5C',
    /** Text drawn ON the accent. Must stay legible on the brand fill. */
    brandInk: '#06210F',
    brandSoft: 'rgba(61,220,132,0.08)',
    brandTint: 'rgba(61,220,132,0.14)',
    /** Body copy inside a callout, tinted toward the accent. */
    plainText: '#D6E2DC',
  },
  white: {
    brand: '#EDF1F6',
    brandDim: '#8A97A3',
    brandInk: '#07090B',
    brandSoft: 'rgba(237,241,246,0.06)',
    brandTint: 'rgba(237,241,246,0.12)',
    plainText: '#CFD7DD',
  },
} as const;

export type AccentTokens = (typeof accents)[Accent];

export const palette = {
  // --- Surfaces: the `dark` ramp, as the static default -----------------
  // Screens that theme themselves read these from useSurfaces() instead;
  // these keep un-migrated screens rendering correctly.
  void: surfaces.dark.void,
  surface: surfaces.dark.surface,
  raised: surfaces.dark.raised,
  hairline: surfaces.dark.hairline,
  hairlineBright: surfaces.dark.hairlineBright,

  // --- Text: four steps, no more ----------------------------------------
  text: '#F2F5F7',
  textDim: '#8A97A3',
  textFaint: '#5C6874',
  textGhost: '#3F4A55',

  // --- The single UI accent ----------------------------------------------
  // Signal green. This is the accent for INTERACTION only -- buttons, the
  // active tab, a ring, a selected chip. Data uses the series palette below.
  // Keeping those two jobs separate is what stops the screen turning green.
  signal: '#3DDC84',      // primary accent — active, confirm, focus
  signalDim: '#2A9A5C',   // focused borders
  signalInk: '#06210F',   // text ON the accent
  signalGlow: 'rgba(61,220,132,0.13)',

  // --- Semantic states ---------------------------------------------------
  warn: '#C2871F',
  danger: '#D9534F',
  info: '#2E86D9',        // also "on track" / synced

  // --- Chart series ------------------------------------------------------
  // Validated for a dark surface before use: lightness band, chroma floor,
  // colour-blind separation on adjacent pairs, contrast. Every series must
  // ALSO be directly labelled in the UI, so identity never depends on colour
  // alone -- that is the rule that lets this many hues coexist.
  seriesStrength: '#1FA862',
  seriesWeight: '#2E86D9',
  seriesEnergy: '#C2871F',
  seriesSleep: '#9A5FD0',
  // The fifth series. Used for the WIDEST / SHORTEST end of a scale -- a
  // quick-added meal in the certainty strip, a nutrient well under target.
  // Distinct from `danger` on purpose: this marks "least certain" or "most
  // short", which is information, not an alarm.
  seriesAlert: '#C4566B',

  // --- Progress direction ------------------------------------------------
  // Always paired with a ▲/▼/— glyph so the meaning survives for the ~8% of
  // men with red-green colour blindness, for whom this pair is the worst
  // possible choice as a sole channel.
  up: '#1FA862',
  down: '#C2871F',
  flat: '#5C6874',

  // --- Macro channels: fixed app-wide, colourblind-safe ------------------
  // Mapped onto the validated series set so a macro bar and a chart line of
  // the same quantity are the same colour everywhere in the app.
  protein: '#1FA862',
  carbs: '#2E86D9',
  fat: '#C2871F',
  fiber: '#6FB5AC',

  // --- Third-party brand -------------------------------------------------
  // The one licensed exception to "every colour carries meaning". Strava's
  // guidelines require their orange on the connect button and their mark.
  // Imported data itself renders in Trace's own colours.
  strava: '#FC5200',

  // --- Overlays ----------------------------------------------------------
  scrim: 'rgba(3,5,7,0.82)',
  glass: 'rgba(255,255,255,0.04)',

  // --- Camera chrome -------------------------------------------------------
  // Chrome drawn over a live camera feed, not an opaque panel -- it needs
  // true black/white with alpha so it reads against any background the
  // camera happens to be pointed at. The void/surface ramp above is for
  // panels on the app's own near-black background and doesn't apply here.
  cameraInk: '#000',
  cameraScrim: 'rgba(0,0,0,0.45)',
  cameraScrimStrong: 'rgba(0,0,0,0.7)',
  cameraPaper: '#fff',
  cameraPaperDim: 'rgba(255,255,255,0.85)',
  cameraPaperFaint: 'rgba(255,255,255,0.6)',

  // --- Legacy aliases ----------------------------------------------------
  // Screens not yet migrated to the instrument vocabulary still reference the
  // old names. Mapping rather than renaming lets the redesign land screen by
  // screen instead of as one 12-file breaking change. Delete these once
  // log/train/progress/scan-review are migrated.
  bg: surfaces.dark.void,
  surfaceRaised: surfaces.dark.raised,
  border: surfaces.dark.hairline,
  textMuted: '#8A97A3',
  primary: '#3DDC84',
  primaryDim: '#2A9A5C',
  primarySoft: 'rgba(61,220,132,0.13)',
  good: '#1FA862',
  caution: '#C2871F',
  bad: '#D9534F',
  neutral: '#8A97A3',
  overlay: 'rgba(0,0,0,0.82)',
} as const;

/** 4pt base grid. Instruments are gridded; nothing sits at an arbitrary offset. */
export const space = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

/**
 * Radii. Softened from the original tight set: a 16pt card reads as something
 * you can pick up, which is what makes the picture-led screens feel calm
 * rather than clinical. Still no shadows -- cards are flat, bordered regions.
 *
 *   sm  -- chips, small controls
 *   md  -- inner cells sitting inside a card
 *   lg  -- the card itself
 */
export const radius = {
  xs: 4,
  sm: 8,
  md: 11,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

/**
 * Numeric font. Tabular figures are non-negotiable for any number that
 * changes — without them, digits visibly jitter as glyph widths shift.
 */
export const mono = Platform.select({
  ios: 'SF Mono',
  android: 'monospace',
  default: 'monospace',
}) as string;

/**
 * IBM Plex Sans, used app-wide rather than only for brand moments. Its
 * lining figures are genuinely tabular, which is what lets every changing
 * number in the app hold its column.
 *
 * Loaded via `useFonts` in `app/_layout.tsx`. RN will not synthesise weights
 * for a custom family, so each weight is its own registered face and styles
 * must name the exact one they want -- never a `fontWeight` on top of these.
 */
export const fontFamily = {
  light: 'IBMPlexSans_300Light',
  regular: 'IBMPlexSans_400Regular',
  medium: 'IBMPlexSans_500Medium',
  semibold: 'IBMPlexSans_600SemiBold',
  bold: 'IBMPlexSans_700Bold',
} as const;

// NOT `as const` -- RN's TextStyle requires a mutable string[] for fontVariant.
const tabular: { fontVariant: ('tabular-nums')[] } = {
  fontVariant: ['tabular-nums'],
};

/**
 * Every entry names an explicit IBM Plex Sans face and carries NO
 * `fontWeight` -- RN cannot synthesise a weight for a custom family, and
 * setting both makes Android fake-bold an already-bold face.
 *
 * Anything that displays a number is Bold + tabular: numbers are the
 * product, so they should read as the heaviest thing on the screen.
 */
export const type = {
  /** The one big number on a screen. Nothing else uses this size. */
  readout: {
    fontFamily: fontFamily.bold,
    fontSize: 64,
    letterSpacing: -3,
    lineHeight: 68,
    ...tabular,
  },
  /** Secondary large figures. */
  figure: {
    fontFamily: fontFamily.bold,
    fontSize: 34,
    letterSpacing: -1.2,
    lineHeight: 40,
    ...tabular,
  },
  /** Inline data values. */
  value: {
    fontFamily: fontFamily.bold,
    fontSize: 20,
    letterSpacing: -0.4,
    ...tabular,
  },
  valueSm: {
    fontFamily: fontFamily.bold,
    fontSize: 15,
    letterSpacing: -0.3,
    ...tabular,
  },
  title: { fontFamily: fontFamily.semibold, fontSize: 22, letterSpacing: -0.5 },
  heading: { fontFamily: fontFamily.semibold, fontSize: 16, letterSpacing: -0.2 },
  body: { fontFamily: fontFamily.regular, fontSize: 15, lineHeight: 22 },
  caption: { fontFamily: fontFamily.regular, fontSize: 13, lineHeight: 19 },
  /** The oversized light line on the login screen. */
  tagline: {
    fontFamily: fontFamily.light,
    fontSize: 28,
    letterSpacing: -0.8,
    lineHeight: 36,
  },
  /** The uppercase tracked label. This is the signature of the whole system. */
  label: {
    fontFamily: fontFamily.semibold,
    fontSize: 10,
    letterSpacing: 1.4,
    textTransform: 'uppercase' as const,
  },
  labelSm: {
    fontFamily: fontFamily.semibold,
    fontSize: 9,
    letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
  },

  // --- Legacy aliases (see palette note above) ---------------------------
  display: { fontFamily: fontFamily.bold, fontSize: 40, letterSpacing: -1 },
  bodyStrong: { fontFamily: fontFamily.semibold, fontSize: 15 },
  micro: { fontFamily: fontFamily.medium, fontSize: 11, letterSpacing: 0.3 },
} as const;

/**
 * Motion. Unchanged from the original spec because it was right: 200-300ms
 * ease-in-out, 100ms press. Every duration in the app comes from here.
 */
export const motion = {
  press: 100,
  fast: 180,
  base: 240,
  slow: 320,
  /** Ambient status pulses (a scanning reticle, a live-status dot) -- a
   * distinct, slower category from UI transition durations above. */
  pulse: 600,
  spring: { damping: 20, stiffness: 140, mass: 0.9 },
  /** Instruments settle; they don't bounce. Zero overshoot by design. */
  settle: { damping: 26, stiffness: 110, mass: 1 },
  pressScale: 0.97,
} as const;

/** 1px on any density. RN's hairlineWidth is device-correct. */
export const HAIRLINE = Platform.select({ ios: 0.5, default: 1 }) as number;

export const verdictStyle: Record<
  string,
  { color: string; label: string; glyph: string }
> = {
  lean_gain: { color: palette.signal, label: 'Lean gain', glyph: '▲' },
  recomposition: { color: palette.signal, label: 'Recomp', glyph: '◆' },
  clean_cut: { color: palette.signal, label: 'Clean cut', glyph: '▼' },
  fat_gain: { color: palette.warn, label: 'Fat gain', glyph: '▲' },
  muscle_loss_risk: { color: palette.danger, label: 'Muscle loss', glyph: '▼' },
  insufficient_data: { color: palette.textFaint, label: 'No read', glyph: '—' },
};

export const leverStyle: Record<string, { color: string; label: string }> = {
  sleep: { color: palette.info, label: 'Sleep' },
  activity: { color: palette.signal, label: 'Activity' },
  adherence: { color: palette.warn, label: 'Logging' },
  protein: { color: palette.protein, label: 'Protein' },
  training: { color: palette.fat, label: 'Training' },
  calories: { color: palette.warn, label: 'Calories' },
  none: { color: palette.textFaint, label: '' },
};
