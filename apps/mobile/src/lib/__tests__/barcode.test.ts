/**
 * Barcode validation on the device.
 *
 * The important half of this file is `TestSharedContract`: it runs the SAME
 * vector table as `services/api/tests/test_gtin.py`. A drift between the
 * device's validator and the server's would mean the phone accepts a code the
 * server refuses, or refuses one the server would have resolved — and both
 * present to a user as a mystery, not as a failing build. One table, two
 * implementations, one source of truth.
 *
 * The path below reaches across the monorepo on purpose. If it breaks, the
 * test fails loudly, which is the correct behaviour for a contract test.
 */

import vectors from '../../../../../services/api/tests/fixtures/barcode_vectors.json';
import {
  StabilityGate,
  checkDigit,
  classify,
  expandUpcE,
  hasValidCheckDigit,
  isRestricted,
  sameProduct,
  type BarcodeStatus,
} from '../barcode';

interface Vector {
  raw: string;
  symbology: string | null;
  status: string;
  gtin14: string | null;
  why: string;
}

const CASES = (vectors as { cases: Vector[] }).cases;

describe('shared contract with services/api/app/services/gtin.py', () => {
  it('has a table to check against', () => {
    expect(CASES.length).toBeGreaterThan(20);
  });

  it.each(CASES.map((c) => [c.why, c] as const))('%s', (_why, c) => {
    const got = classify(c.raw, c.symbology);
    expect(got.status).toBe(c.status as BarcodeStatus);
    expect(got.gtin14).toBe(c.gtin14);
  });

  it('covers every status the server can return', () => {
    const seen = new Set(CASES.map((c) => c.status));
    expect(seen).toEqual(
      new Set(['ok', 'not_numeric', 'invalid_length', 'bad_check_digit', 'restricted']),
    );
  });
});

describe('check digit', () => {
  it.each([
    ['01234567890', 5],
    ['001234567890', 5],
    ['400638133393', 1],
  ])('computes %s -> %i', (payload, expected) => {
    expect(checkDigit(payload as string)).toBe(expected);
  });

  it('anchors weights on the right, so one rule serves every length', () => {
    // The same product at two lengths must both validate. Left-anchoring
    // gives different answers and defeats the point of normalising.
    expect(hasValidCheckDigit('012345678905')).toBe(true);
    expect(hasValidCheckDigit('0012345678905')).toBe(true);
  });

  it('rejects a mistyped digit', () => {
    expect(hasValidCheckDigit('012345678906')).toBe(false);
  });
});

describe('the four GS1 lengths', () => {
  it('accepts a valid GTIN-14', () => {
    expect(classify('00012345678905').gtin14).toBe('00012345678905');
  });

  it('accepts a valid UPC-A and folds it to GTIN-14', () => {
    expect(classify('012345678905').gtin14).toBe('00012345678905');
  });

  it('accepts a valid EAN-8', () => {
    expect(classify('40063812').gtin14).toBe('00000040063812');
  });

  it('accepts a valid EAN-13', () => {
    expect(classify('8906136651951').gtin14).toBe('08906136651951');
  });

  it('folds UPC-A and EAN-13 of one product onto one key', () => {
    expect(sameProduct('012345678905', '0012345678905')).toBe(true);
  });

  it('does not fold two different products together', () => {
    expect(sameProduct('012345678905', '4006381333931')).toBe(false);
  });
});

describe('leading zeroes', () => {
  it('preserves them when padding', () => {
    expect(classify('012345678905').gtin14).toBe('00012345678905');
    expect(classify('40063812').gtin14).toBe('00000040063812');
  });

  it('does not treat interior zeros as a prefix', () => {
    // '00000200000000' has GS1 prefix '00'. The '2' further in is not a
    // prefix, and reading it as one refused ordinary UPC-A codes.
    expect(isRestricted('00000200000000')).toBe(false);
  });

  it('still finds a restricted prefix after padding', () => {
    expect(isRestricted('00200000000000')).toBe(true);
    expect(isRestricted('00400000000008')).toBe(true);
  });
});

describe('refusals name a recovery', () => {
  it('rejects an invalid check digit', () => {
    expect(classify('012345678906').status).toBe('bad_check_digit');
  });

  it.each(['12345', '123456', '0123456789', '012345678901234'])(
    'rejects the non-GS1 length %s',
    (raw) => {
      // The endpoint used to accept anything 6-14 digits and look it up.
      // There is no 6-digit GTIN; every one of those was a truncated read
      // that still cost two external round trips.
      expect(classify(raw).status).toBe('invalid_length');
    },
  );

  it.each(['', '   ', 'abc', 'n/a', '🍫'])('rejects the junk %s', (raw) => {
    expect(classify(raw).status).toBe('not_numeric');
  });

  it.each([null, undefined, 12345, {}])('survives the non-string %p', (raw) => {
    expect(classify(raw as never).status).toBe('not_numeric');
  });

  it.each([
    ['0200000000004', '02 in-store'],
    ['0400000000008', '04 in-store'],
    ['2000000000008', '20 restricted'],
    ['9900000000004', '99 coupon'],
    ['0490711802107', 'a real own-label code'],
  ])('refuses %s as a global identifier (%s)', (raw) => {
    expect(classify(raw as string).status).toBe('restricted');
  });

  it('marks a restricted code as NOT retryable', () => {
    // Scanning an in-store sticker again is a loop, not a recovery. Every
    // other refusal can plausibly succeed on a second try.
    expect(classify('0200000000004').retryable).toBe(false);
    expect(classify('012345678906').retryable).toBe(true);
    expect(classify('12345').retryable).toBe(true);
  });
});

describe('UPC-E', () => {
  it.each([
    ['04252614', '042100005264'],
    ['01234565', '012345000065'],
    ['12345670', '123456000070'],
  ])('expands %s to %s', (compressed, expanded) => {
    expect(expandUpcE(compressed as string)).toBe(expanded);
  });

  it('derives the check digit from the expanded form, not the compressed one', () => {
    expect(expandUpcE('04252614')).not.toBeNull();
    // The same eight digits are NOT a valid EAN-8.
    expect(hasValidCheckDigit('04252614')).toBe(false);
  });

  it('only number systems 0 and 1 have a UPC-E form', () => {
    expect(expandUpcE('24252614')).toBeNull();
    expect(expandUpcE('94252614')).toBeNull();
  });

  it('uses the symbology and never the digits', () => {
    // 58% of valid EAN-8 codes beginning 0 or 1 also parse as a valid UPC-E,
    // and the two readings name different products. Guessing is worse than a
    // coin toss, so the scanner's own report decides.
    expect(classify('04252614', 'upc_e').gtin14).toBe('00042100005264');
    expect(classify('04252614', 'ean8').status).toBe('bad_check_digit');
  });

  it('declines to expand when the symbology is unknown', () => {
    // A miss is recoverable; a wrong product is believed. Expanding an EAN-8
    // that was never a UPC-E fabricates a valid GTIN for a different product.
    expect(classify('04252614').status).toBe('bad_check_digit');
  });

  it('treats a named-but-unexpandable UPC-E as a damaged read', () => {
    expect(classify('24252614', 'upc_e').status).toBe('bad_check_digit');
  });
});

describe('StabilityGate: duplicate-frame suppression', () => {
  const A = '00012345678905';
  const B = '08906136651951';

  it('does not fire on a single frame', () => {
    // The previous implementation acted on the FIRST decode. One misread off
    // a curved or glossy pack was enough to look up the wrong product, and a
    // check digit does not catch a decode that is internally consistent.
    const gate = new StabilityGate();
    expect(gate.push(A)).toBeNull();
  });

  it('fires once two consecutive frames agree', () => {
    const gate = new StabilityGate();
    expect(gate.push(A)).toBeNull();
    expect(gate.push(A)).toBe(A);
  });

  it('never fires the same code twice, however long it stays in frame', () => {
    // The old guard expired after 2500 ms, so holding the camera on a pack
    // for three seconds fired the same lookup again.
    const gate = new StabilityGate();
    gate.push(A);
    expect(gate.push(A)).toBe(A);
    for (let i = 0; i < 200; i += 1) expect(gate.push(A)).toBeNull();
  });

  it('resets the streak when a different code appears', () => {
    const gate = new StabilityGate();
    expect(gate.push(A)).toBeNull();
    expect(gate.push(B)).toBeNull(); // A's streak is abandoned, not counted
    expect(gate.push(A)).toBeNull(); // and A starts over
    expect(gate.push(A)).toBe(A);
  });

  it('lets a second product through after the first has settled', () => {
    const gate = new StabilityGate();
    gate.push(A);
    expect(gate.push(A)).toBe(A);
    gate.push(B);
    expect(gate.push(B)).toBe(B);
  });

  it('fires again only when the user explicitly asks', () => {
    const gate = new StabilityGate();
    gate.push(A);
    gate.push(A);
    expect(gate.push(A)).toBeNull();
    gate.forget(A);
    gate.push(A);
    expect(gate.push(A)).toBe(A);
  });

  it('honours a stricter frame requirement', () => {
    const gate = new StabilityGate(3);
    expect(gate.push(A)).toBeNull();
    expect(gate.push(A)).toBeNull();
    expect(gate.push(A)).toBe(A);
  });

  it('forgets everything on reset', () => {
    const gate = new StabilityGate();
    gate.push(A);
    gate.push(A);
    gate.reset();
    expect(gate.push(A)).toBeNull();
    expect(gate.push(A)).toBe(A);
  });
});
