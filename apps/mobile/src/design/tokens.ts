/**
 * Trace — the session-summary visual system.
 *
 * Extracted from `design/trace-session-summary-reference.html`, which is the
 * newest screen and the one the rest of the app migrates toward. Values here
 * were read out of that file, not remembered.
 *
 * This module is ADDITIVE. `src/theme.ts` still drives every unmigrated
 * screen and is untouched. A half-migrated app is worse than an unmigrated
 * one, so a screen takes all of its values from here or none of them.
 *
 * ---------------------------------------------------------------------------
 * WHY THREE COLOURS AND A GREY
 * ---------------------------------------------------------------------------
 * The overload deck (revision 6) defines five verdicts and gives each its own
 * hue, including purple for "Building". That is one accent too many: purple
 * and green both read as good news, so the eye cannot rank them, and the
 * screen ends up as colourful as the competitor dashboards this product
 * exists to argue against.
 *
 * The mapping below collapses five verdicts onto three colours plus a
 * deliberate absence of colour:
 *
 *   Confirmed   >=8 sessions, smoothed trend up     GO, solid fill
 *   Building    beating bests, <8 sessions          GO, outline only
 *   Held        >=8 sessions, trend flat            HOLD
 *   Declining   >=8 sessions, trend down            BAD
 *   Not yet     <8 sessions, or a >4-week gap       DIM, no colour at all
 *
 * Solid means Trace will stand behind it. Outline means true about today but
 * not yet a trend. Grey means Trace does not know and will not pretend.
 *
 * GREY ROWS ARE A FEATURE. Four of nine movements sitting colourless is
 * correct behaviour, not an empty state to design away. Every competitor
 * paints ~89% of sets green, which is exactly why their green is worth
 * nothing.
 */

export const palette = {
  /** Page ground, behind the phone-width column. */
  bg: '#08090B',
  /** The column itself, one step lighter so its edges read without a border. */
  card: '#0F1114',

  /** Section rules. */
  line: 'rgba(237,237,240,.09)',
  /** Row rules — deliberately fainter than `line`; rows are not sections. */
  hairline: 'rgba(237,237,240,.055)',

  text: '#EDEDF0',
  /** Numerals, names, anything the eye should land on first. */
  bright: '#F6F8FA',
  /** Supporting prose and numeric detail. */
  muted: 'rgba(237,237,240,.55)',
  /**
   * Two jobs, and they are really the same job: mono labels, and the "not
   * yet" verdict. A label is chrome; an unknown verdict should read as chrome
   * too.
   */
  dim: 'rgba(237,237,240,.34)',

  go: '#5FD98C',
  hold: '#E9A13B',
  bad: '#DC4A4A',
} as const;

/** Tag and pill backgrounds. 11% of the hue, matching the reference file. */
export const tint = {
  go: 'rgba(95,217,140,.11)',
  hold: 'rgba(233,161,59,.11)',
  bad: 'rgba(220,74,74,.11)',
  dim: 'rgba(237,237,240,.06)',
} as const;

export type Verdict = 'confirmed' | 'building' | 'held' | 'declining' | 'not_yet';
export type Tone = 'go' | 'hold' | 'bad' | 'dim';

/**
 * The only place a verdict becomes a colour. Screens ask for a verdict and
 * get back how to draw it — they never pick a hex.
 *
 * `filled` is the whole point: confirmed and building share a colour and
 * differ only in whether it is filled in. That is the visual difference
 * between "this is a trend" and "this is one good day".
 */
export const VERDICT: Record<
  Verdict,
  { tone: Tone; filled: boolean; label: string }
> = {
  confirmed: { tone: 'go', filled: true, label: 'Confirmed' },
  building: { tone: 'go', filled: false, label: 'Building' },
  held: { tone: 'hold', filled: true, label: 'Held' },
  declining: { tone: 'bad', filled: true, label: 'Declining' },
  not_yet: { tone: 'dim', filled: false, label: 'Not yet' },
};

export const toneColour: Record<Tone, string> = {
  go: palette.go,
  hold: palette.hold,
  bad: palette.bad,
  dim: palette.dim,
};

export const toneTint: Record<Tone, string> = {
  go: tint.go,
  hold: tint.hold,
  bad: tint.bad,
  dim: tint.dim,
};

/**
 * MIN_SESSIONS. Below this a movement cannot be more than `building`, however
 * good the numbers look. The threshold is a product promise, not a constant
 * to tune for a nicer-looking screen — `services/programming.py` holds the
 * same number on the server and the two must not drift.
 */
export const MIN_SESSIONS = 8;

/** A gap this long and the old data no longer describes the person. */
export const STALE_AFTER_DAYS = 28;

/* -------------------------------------------------------------------------
 * TYPE
 * -------------------------------------------------------------------------
 * Two families, no third.
 *
 *   Inter          800 numerals and titles, 600 names, 400 prose
 *   JetBrains Mono 700 uppercase labels, 400 numeric detail
 *
 * Requires `@expo-google-fonts/inter` and `@expo-google-fonts/jetbrains-mono`,
 * neither of which is installed yet — the app currently loads IBM Plex Sans
 * and Space Grotesk. The family strings below are the names those packages
 * register once added.
 */
export const family = {
  sans: 'Inter_400Regular',
  sansMedium: 'Inter_600SemiBold',
  sansBold: 'Inter_800ExtraBold',
  mono: 'JetBrainsMono_400Regular',
  monoBold: 'JetBrainsMono_700Bold',
} as const;

/**
 * Spread into every style that renders a number. Proportional digits make a
 * counting number jitter as glyph widths change, which is the loudest tell of
 * an amateur data UI.
 */
export const tabular = { fontVariant: ['tabular-nums' as const] };

/**
 * The reference file scales everything from `clamp(8.2px, 1.2vh, 13.4px)` so
 * the screen fits one viewport on any phone. React Native has no `vh`, so the
 * caller passes usable height and gets the same behaviour.
 */
export function rootSize(viewportHeight: number): number {
  return Math.min(13.4, Math.max(8.2, viewportHeight * 0.012));
}

/** Multipliers on the root size, straight out of the reference stylesheet. */
export const scale = {
  statValue: 1.8,
  screenTitle: 1.02,
  exerciseName: 1.05,
  statKey: 0.7,
  headline: 0.78,
  label: 0.76,
  tag: 0.66,
  detail: 0.78,
  e1rmDelta: 0.76,
  e1rmEst: 0.72,
  legend: 0.7,
} as const;

/**
 * Tracking, in em. Negative on large sans, strongly positive on mono — that
 * contrast is what makes a mono label read as a readout rather than prose.
 */
export const tracking = {
  statValue: -0.035,
  exerciseName: -0.012,
  screenTitle: 0.03,
  mono: 0.15,
  monoTight: 0.13,
  monoWide: 0.17,
  monoDetail: 0.02,
} as const;

/**
 * Density, in root-size multiples. Rows are content-height and leftover space
 * collects ONCE at the bottom above the legend — never distributed between
 * rows, which is what makes a list look like a form.
 */
export const space = {
  gutter: 1.05,
  rowY: 0.62,
  withinRow: 0.3,
  sectionY: 0.7,
  idxWidth: 1.05,
  segWidth: 0.85,
  segHeight: 0.2,
  segGap: 0.2,
} as const;

/**
 * Per-set segment colour. ONE DASH PER SET, each coloured by that set's own
 * outcome — not one bar for the whole exercise.
 *
 * This is the honest part of the screen. An exercise whose headline says
 * "moved up" can still contain a set that went backwards, and the segment bar
 * is the only place a user sees that. Collapsing it to a single
 * exercise-level colour would hide exactly the detail worth showing.
 */
export type SetState = 'up' | 'flat' | 'down' | 'unknown';

export const SET_TONE: Record<SetState, Tone> = {
  up: 'go',
  flat: 'hold',
  down: 'bad',
  unknown: 'dim',
};

/**
 * Legend copy.
 *
 * DELIBERATELY NOT the reference file's wording. `design/vxs-reference/` holds
 * the competitor screen this layout descends from, and its legend reads
 * "PROGRESSING FASTER THAN EXPECTED / PROGRESSING AS EXPECTED / STRENGTH
 * DECLINE". The reference HTML carried the first and third of those over
 * close to verbatim. Layout is convention and nobody owns it; a sentence
 * reproduced word for word is not, so these say what our own thresholds mean
 * instead.
 *
 * The fourth line has no counterpart on the competitor screen at all, because
 * their system has no state for "we do not know yet".
 */
export const LEGEND: ReadonlyArray<{ tone: Tone; text: string }> = [
  { tone: 'go', text: 'Trend confirmed over 8+ sessions' },
  { tone: 'hold', text: 'Enough data, no movement' },
  { tone: 'bad', text: 'Trend down — worth looking at' },
  { tone: 'dim', text: 'Not enough sessions to say' },
];
