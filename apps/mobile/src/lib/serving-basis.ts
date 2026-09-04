/**
 * Which basis a nutrition figure is on, and how confident we are in it.
 *
 * THE PROBLEM THIS SOLVES
 * Three bases meet on one screen and share one set of digits:
 *
 *   per 100 g / 100 ml   how the catalogue stores every row
 *   per serving          what the packet prints
 *   the scanned portion  what the user actually dialled in
 *
 * Nothing on screen said which. A user comparing a figure against the label
 * in their hand had no way to tell whether a disagreement was a data problem
 * or a units problem — and "silently mixing bases" is the exact failure that
 * makes a tracker untrustworthy, because every number stays plausible.
 *
 * PURE, SO IT CAN BE TESTED WITHOUT A RENDERER. This lived as an inline
 * template string inside the portion sheet, which meant the only way to check
 * "does a 250 ml drink say ml" was to render a screen that pulls in
 * expo-router, FlashList, Reanimated and three zustand stores. Extracting it
 * is what makes the fifteen cases below assertable at all.
 */

export type Basis = 'per_100' | 'per_serving' | 'portion' | 'estimate';

/** What the app is willing to claim about a row's numbers. */
export type QualityStatus =
  | 'verified'
  | 'estimated'
  | 'needs_review'
  | 'incomplete';

export interface BasisInput {
  /** True for drinks: the unit becomes ml, not g. */
  isLiquid?: boolean | null;
  /** Grams (or ml) the user has dialled in. */
  portionGrams?: number | null;
  /** Label of the chosen serving, e.g. "1 bar (45 g)". */
  servingName?: string | null;
  /** How many of that serving. */
  servingCount?: number | null;
  /** True when the figures came from a photo estimate rather than a source. */
  isEstimate?: boolean | null;
}

/** g or ml. Getting this wrong on a drink is a silent 1:1 volume/mass claim. */
export function unitFor(isLiquid?: boolean | null): 'g' | 'ml' {
  return isLiquid ? 'ml' : 'g';
}

/**
 * One line stating exactly what the figures above it describe.
 *
 * Never returns an empty string: a basis line that disappears when data is
 * missing is worse than one that says the basis is unknown, because the
 * reader assumes the previous line still applies.
 */
export function basisLabel(input: BasisInput): string {
  const unit = unitFor(input.isLiquid);
  const grams = input.portionGrams;

  if (input.isEstimate) {
    // An estimate has no serving to be "per". It describes the portion in
    // the photo and nothing else.
    return grams && grams > 0
      ? `Estimated for the portion in your photo (~${Math.round(grams)} ${unit})`
      : 'Estimated for the portion in your photo';
  }

  const hasServing = Boolean(input.servingName) && (input.servingCount ?? 0) > 0;
  if (hasServing && grams && grams > 0) {
    const count = input.servingCount as number;
    return `For ${count} × ${input.servingName} (${Math.round(grams)} ${unit}) · catalogue values are per 100 ${unit}`;
  }
  if (grams && grams > 0) {
    // No named serving — the user is working in raw weight.
    return `For ${Math.round(grams)} ${unit} · catalogue values are per 100 ${unit}`;
  }
  // MISSING SERVING SIZE. Say so rather than implying per-100 figures are a
  // portion; a row with no serving data is common in crowd-sourced records.
  return `Per 100 ${unit} · no serving size recorded for this food`;
}

/**
 * What the app may claim about a row's numbers.
 *
 * `verificationTier` is 1..7, lower is better evidence (services/licensing.py).
 * NO NUMERIC SCORE IS INVENTED: when the tier is absent and the row is not
 * flagged verified, the honest answer is "needs review", not a made-up
 * percentage.
 */
export function qualityStatus(input: {
  isVerified?: boolean | null;
  verificationTier?: number | null;
  isEstimate?: boolean | null;
  /** True when required nutrition fields are missing from the record. */
  incomplete?: boolean | null;
  /** True when the server flagged the values as not holding together. */
  reviewRequired?: boolean | null;
}): QualityStatus {
  // Order matters. Incompleteness and an explicit review flag both outrank a
  // `verified` boolean: a row can be from a trusted source AND be missing
  // half its panel, and the missing half is what the user needs to know.
  if (input.incomplete) return 'incomplete';
  if (input.reviewRequired) return 'needs_review';
  // AN ESTIMATE IS NEVER VERIFIED. Checked before `isVerified` so no
  // combination of flags can render a photo estimate as established fact.
  if (input.isEstimate) return 'estimated';
  if (input.isVerified) return 'verified';

  const tier = input.verificationTier;
  if (tier == null || !Number.isFinite(tier)) return 'needs_review';
  if (tier <= 2) return 'verified';
  if (tier <= 4) return 'verified';
  if (tier <= 6) return 'estimated';
  return 'needs_review';
}

/** Human wording for a status. Deliberately plain and non-clinical. */
export const QUALITY_LABEL: Record<QualityStatus, string> = {
  verified: 'VERIFIED',
  estimated: 'ESTIMATED',
  needs_review: 'NEEDS REVIEW',
  incomplete: 'INCOMPLETE DATA',
};

/**
 * Does this record have enough of a panel to be worth showing as complete?
 *
 * Calories alone is not nutrition data. A row with an energy figure and three
 * zeroed macros is what a bad crowd-sourced import looks like, and it will
 * otherwise render as a confident, complete-looking result.
 */
export function isIncomplete(item: {
  calories?: number | null;
  protein_g?: number | null;
  carbs_g?: number | null;
  fat_g?: number | null;
}): boolean {
  const kcal = item.calories ?? 0;
  if (kcal <= 0) return true;
  const macros = [item.protein_g, item.carbs_g, item.fat_g];
  if (macros.every((m) => m == null)) return true;
  // All three exactly zero alongside a real calorie figure is not a food.
  return macros.every((m) => (m ?? 0) === 0);
}
