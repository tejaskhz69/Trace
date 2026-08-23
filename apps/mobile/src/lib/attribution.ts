/**
 * Data-source attribution for a food record.
 *
 * WHY THIS IS PER ROW AND NOT A GLOBAL NOTICE
 * The catalogue mixes three provenances: Open Food Facts (ODbL), USDA FoodData
 * Central (public domain) and our own curated dishes. A single blanket
 * "powered by Open Food Facts" line would misattribute the majority of rows and
 * would credit ODbL data to sources that had nothing to do with it. So each
 * record states its own source, and a screen showing several records can show
 * several different notices at once.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 * It states facts already recorded in the database (`source`, `source_licence`)
 * and nothing more. It does not assert licence compatibility, does not claim
 * the app satisfies any share-alike obligation, and invents no legal wording.
 * See `services/api/review/README.md` for what still needs human review.
 *
 * There are no links here on purpose: the app has no external-link
 * affordance anywhere else, so attribution stays text-only rather than
 * introducing a new interaction pattern for a compliance string.
 */

/** The subset of a food record this module needs. */
export type Attributable = {
  source?: string | null;
  source_licence?: string | null;
  verification_tier?: number | null;
};

export type Attribution = {
  /** Short tag for a dense list row, e.g. 'OPEN FOOD FACTS'. */
  tag: string | null;
  /** One factual sentence for a detail view. */
  detail: string | null;
  /** Licence shorthand as stored, e.g. 'odbl'. Null when unknown. */
  licence: string | null;
  /** Screen-reader text; never abbreviated. */
  accessibilityLabel: string | null;
  /** True when the row needs a visible attribution notice. */
  required: boolean;
};

const NONE: Attribution = {
  tag: null,
  detail: null,
  licence: null,
  accessibilityLabel: null,
  required: false,
};

/** Display names, keyed by the `source` values the API actually returns. */
const SOURCE_NAMES: Record<string, string> = {
  openfoodfacts: 'Open Food Facts',
  usda_fdc: 'USDA FoodData Central',
  ifct: 'Indian Food Composition Tables',
  curated: 'Trace',
  user: 'You',
};

/** Licence shorthand -> human phrase. Only what the database records. */
const LICENCE_PHRASES: Record<string, string> = {
  odbl: 'Open Database License (ODbL)',
  'public-domain': 'public domain',
  proprietary: 'used under licence',
  owned: 'created for Trace',
  user: 'created for Trace',
  unknown: 'licence not recorded',
};

/**
 * Attribution for one record.
 *
 * Returns `required: false` for our own curated and user-created rows: there
 * is no third party to credit, and tagging them would be the specific error of
 * labelling non-Open-Food-Facts data as Open Food Facts.
 */
export function attributionFor(item: Attributable | null | undefined): Attribution {
  if (!item || !item.source) return NONE;

  const source = String(item.source);
  const name = SOURCE_NAMES[source];

  // An unrecognised source is reported as unknown rather than guessed at.
  if (!name) {
    return {
      tag: 'SOURCE UNKNOWN',
      detail: 'Source not recorded for this item.',
      licence: item.source_licence ?? null,
      accessibilityLabel: 'Data source not recorded for this item.',
      required: true,
    };
  }

  if (source === 'curated' || source === 'user') {
    return { ...NONE, licence: item.source_licence ?? null };
  }

  const licence = item.source_licence ?? null;
  // `unknown` is the fail-closed default in the database. Say so plainly
  // rather than implying a licence the row does not actually carry.
  const phrase = licence ? LICENCE_PHRASES[licence] ?? null : null;

  return {
    tag: name.toUpperCase(),
    detail: phrase
      ? `Nutrition data from ${name}, ${phrase}.`
      : `Nutrition data from ${name}.`,
    licence,
    accessibilityLabel: phrase
      ? `Nutrition data from ${name}, ${phrase}.`
      : `Nutrition data from ${name}.`,
    required: true,
  };
}

/**
 * The distinct notices needed for a list of records, in stable order.
 *
 * Used by the profile screen so a user can see every source the app draws on
 * without one screen implying all data shares one licence.
 */
export function attributionsFor(items: readonly Attributable[]): Attribution[] {
  const seen = new Map<string, Attribution>();
  for (const item of items) {
    const a = attributionFor(item);
    if (a.required && a.detail && !seen.has(a.detail)) seen.set(a.detail, a);
  }
  return [...seen.values()].sort((x, y) =>
    (x.detail ?? '').localeCompare(y.detail ?? ''),
  );
}

/**
 * How confident we are in this record's numbers, from `verification_tier`
 * (1 best .. 7 worst). Returns null when unrecorded, so the UI shows nothing
 * rather than an invented claim.
 */
export function confidenceLabel(tier: number | null | undefined): string | null {
  if (tier == null || !Number.isFinite(tier)) return null;
  if (tier <= 2) return 'LAB VERIFIED';
  if (tier <= 4) return 'REFERENCE DATA';
  if (tier <= 6) return 'COMMUNITY DATA';
  return 'ESTIMATE';
}
