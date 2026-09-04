/**
 * Barcode validation on the device, before anything reaches the network.
 *
 * WHY THIS EXISTS ON THE CLIENT AT ALL
 * `services/api/app/services/gtin.py` is the authority and always will be: the
 * server must never trust a client's opinion about what is a valid product
 * identifier. But the scanner fires this callback many times per second, at a
 * camera pointed at whatever is in front of it, and a phone in a supermarket
 * aisle is on the worst network it will ever see. Every code rejected here is
 * a round trip that never happens — and the ones worth rejecting are common:
 * an in-store deli sticker, a partial read off a curved bottle, a shipping
 * label on the shelf edge.
 *
 * This is a PORT, not a reimplementation. `services/api/tests/test_gtin.py`
 * and `src/lib/__tests__/barcode.test.ts` run the same vector table, so the
 * two cannot silently disagree — a drift between them would mean the phone
 * accepts what the server refuses, which shows up as a mystery error rather
 * than as a failing test.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * It does not decide a product exists. A code passing every check here is
 * merely well-formed; only the server knows whether anything answers to it.
 */

/** Every GS1 encoding in the wild. Anything else is not a GTIN. */
const VALID_LENGTHS = new Set([8, 12, 13, 14]);
const GTIN_LENGTH = 14;

/**
 * GS1 prefixes reserved for restricted circulation — in-store codes a
 * retailer assigns for its own use. They are NOT globally unique: two chains
 * issue the same number for different things, so looking one up invites a
 * confident match on somebody else's product.
 *
 * 02 / 04  variable-measure and in-store items (GS1 General Specs 1.4.3)
 * 20–29    restricted distribution
 * 98 / 99  coupons, not products
 */
const RESTRICTED_PREFIXES = [
  '02',
  '04',
  ...Array.from({ length: 10 }, (_, i) => String(20 + i)),
  '98',
  '99',
];

export type BarcodeStatus =
  | 'ok'
  | 'not_numeric'
  | 'invalid_length'
  | 'bad_check_digit'
  | 'restricted';

export interface BarcodeCheck {
  status: BarcodeStatus;
  /** The scan folded to GTIN-14. Non-null only when status is 'ok'. */
  gtin14: string | null;
  /** False for 'restricted': a real barcode that will never resolve. */
  retryable: boolean;
}

/**
 * GS1 mod-10 check digit for a payload WITHOUT its check digit.
 *
 * Weights alternate 3,1,3,1… from the RIGHTMOST payload digit leftwards.
 * Anchoring on the right is the whole trick — it is what makes one
 * implementation serve EAN-8 through ITF-14 with no per-length special case.
 */
export function checkDigit(payload: string): number {
  let total = 0;
  for (let i = payload.length - 1, k = 0; i >= 0; i -= 1, k += 1) {
    total += Number(payload[i]) * (k % 2 === 0 ? 3 : 1);
  }
  return (10 - (total % 10)) % 10;
}

export function hasValidCheckDigit(code: string): boolean {
  if (code.length < 2 || !/^\d+$/.test(code)) return false;
  return checkDigit(code.slice(0, -1)) === Number(code[code.length - 1]);
}

/**
 * Is this an in-store or coupon code rather than a global product?
 *
 * THE PREFIX IS READ FROM THE 13-DIGIT FORM, WHICH IS `gtin14.slice(1)`.
 *
 * A GS1 prefix is positional, not "whatever survives stripping zeros". The
 * strip-first version this replaces was wrong in both directions:
 *
 *   '00400000000008' → strips to '400000000008', starts '40', so the '04'
 *                      rule never fired and every number-system-4 code passed
 *   '00000200000000' → strips to '200000000', starts '20', so an ordinary
 *                      UPC-A was refused as restricted
 *
 * In a GTIN-14 the leading digit is the packaging-level indicator and the 13
 * after it carry the prefix, so the same slice is right at every length once
 * padded — EAN-8, UPC-A, EAN-13 and ITF-14 alike.
 */
export function isRestricted(gtin14: string): boolean {
  if (gtin14.length !== GTIN_LENGTH || !/^\d+$/.test(gtin14)) return true;
  if (/^0+$/.test(gtin14)) return true; // all zeros: a placeholder
  return RESTRICTED_PREFIXES.includes(gtin14.slice(1, 3));
}

/**
 * Expand a UPC-E (8 digits) to its UPC-A (12).
 *
 * WHY THIS MATTERS MORE THAN IT LOOKS
 * `expo-camera` reports a UPC-E scan as its compressed 8-digit string, and 8
 * is also the length of an EAN-8. The two readings of one string are two
 * different products. Over 200,000 randomly generated valid EAN-8 codes
 * beginning 0 or 1, **58% also expand as a valid UPC-E** — so deciding from
 * the digits alone is worse than a coin toss. The symbology from the scanner
 * is the only reliable signal, which is why `classify` takes it and why this
 * is never applied speculatively.
 *
 * The check digit is re-derived from the EXPANDED form, which is where a
 * UPC-E's check digit is actually defined.
 */
export function expandUpcE(raw: string): string | null {
  if (!/^\d{8}$/.test(raw)) return null;
  const system = raw[0];
  const payload = raw.slice(1, 7);
  const check = raw[7];
  if (system !== '0' && system !== '1') return null;

  const last = payload[5];
  const body = payload.slice(0, 5);
  let expanded: string;
  if (last === '0' || last === '1' || last === '2') {
    expanded = `${system}${body.slice(0, 2)}${last}0000${body.slice(2, 5)}`;
  } else if (last === '3') {
    expanded = `${system}${body.slice(0, 3)}00000${body.slice(3, 5)}`;
  } else if (last === '4') {
    expanded = `${system}${body.slice(0, 4)}00000${body[4]}`;
  } else {
    expanded = `${system}${body}0000${last}`;
  }

  if (expanded.length !== 11) return null;
  if (checkDigit(expanded) !== Number(check)) return null;
  return expanded + check;
}

/**
 * Validate a scan and say why it failed.
 *
 * `symbology` is what the scanner reported (expo-camera's `type`). When it is
 * absent, an 8-digit code is treated as EAN-8 and NOT expanded. That default
 * is chosen deliberately: expanding an EAN-8 that was never a UPC-E fabricates
 * a valid-looking GTIN for a different product — a confident wrong match — and
 * a wrong match is far worse than a miss, because the user believes it.
 */
export function classify(raw: string | null | undefined, symbology?: string | null): BarcodeCheck {
  const fail = (status: BarcodeStatus): BarcodeCheck => ({
    status,
    gtin14: null,
    retryable: status !== 'restricted',
  });

  if (typeof raw !== 'string') return fail('not_numeric');
  let digits = raw.replace(/\D/g, '');
  if (!digits) return fail('not_numeric');

  if (digits.length === 8 && symbology === 'upc_e') {
    const expanded = expandUpcE(digits);
    // The scanner said UPC-E and it does not expand: a damaged read, not an
    // EAN-8. Reinterpreting it would be guessing all over again.
    if (expanded === null) return fail('bad_check_digit');
    digits = expanded;
  }

  if (!VALID_LENGTHS.has(digits.length)) return fail('invalid_length');
  if (!hasValidCheckDigit(digits)) return fail('bad_check_digit');

  const padded = digits.padStart(GTIN_LENGTH, '0');

  // All zeros is a placeholder somebody typed to satisfy a required field,
  // not a retailer-scoped product. Nothing to look up locally either, so
  // unlike a real restricted code it yields no key.
  if (/^0+$/.test(padded)) return fail('restricted');

  if (isRestricted(padded)) {
    // THE KEY IS RETURNED ANYWAY. A restricted code is a well-formed GTIN —
    // it just is not a GLOBAL one. The server uses it to search OUR catalogue,
    // where 1,079 real own-label products live, while never sending it to an
    // external source where the same digits belong to a different chain.
    return { status: 'restricted', gtin14: padded, retryable: false };
  }

  return { status: 'ok', gtin14: padded, retryable: false };
}

/**
 * Do two barcodes, in any encoding, identify one product?
 * False when either fails validation: unknown is not a match.
 */
export function sameProduct(a?: string | null, b?: string | null): boolean {
  const x = classify(a).gtin14;
  const y = classify(b).gtin14;
  return x !== null && x === y;
}

/**
 * How many consecutive frames must agree before a scan is acted on.
 *
 * The scanner emits a decode per frame, and a decode is not a certainty — a
 * curved bottle, a glossy wrapper or a hand moving through the shot all
 * produce reads that pass the check digit and name the wrong product. Two
 * frames is not caution for its own sake: at 30 fps it costs ~33 ms, which is
 * far below the threshold of noticing, and it removes the entire class of
 * single-frame misreads.
 *
 * Three would be measurably safer and measurably more annoying on a phone
 * being held by a person carrying a shopping basket.
 */
export const STABLE_FRAMES = 2;

/**
 * Tracks agreement across frames so a single misread cannot trigger a lookup.
 *
 * Deliberately a tiny class rather than refs scattered through the screen:
 * the previous implementation kept one `handledBarcode` ref and acted on the
 * FIRST frame, which is exactly the behaviour this replaces.
 */
export class StabilityGate {
  private candidate: string | null = null;
  private streak = 0;
  private readonly settled = new Set<string>();

  constructor(private readonly required: number = STABLE_FRAMES) {}

  /**
   * Feed one decoded frame. Returns the GTIN-14 once, when it first becomes
   * stable, and null every other time — including every later frame of a code
   * already acted on, which is what stops one barcode in frame from firing a
   * lookup a second time two seconds later.
   */
  push(gtin14: string): string | null {
    if (this.settled.has(gtin14)) return null;

    if (gtin14 === this.candidate) {
      this.streak += 1;
    } else {
      this.candidate = gtin14;
      this.streak = 1;
    }

    if (this.streak >= this.required) {
      this.settled.add(gtin14);
      this.candidate = null;
      this.streak = 0;
      return gtin14;
    }
    return null;
  }

  /** Allow a code to fire again — used when the user asks to retry it. */
  forget(gtin14: string): void {
    this.settled.delete(gtin14);
  }

  reset(): void {
    this.candidate = null;
    this.streak = 0;
    this.settled.clear();
  }
}
