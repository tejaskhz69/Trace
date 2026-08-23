/**
 * Tests for data-source attribution.
 *
 * The failure that matters here is not a crash -- it is crediting Open Food
 * Facts for data that did not come from it, or implying one licence covers a
 * mixed catalogue. Both are quiet, and both are wrong in a way a user cannot
 * detect. These tests are the guard.
 */

import {
  attributionFor,
  attributionsFor,
  confidenceLabel,
} from '../attribution';

const off = { source: 'openfoodfacts', source_licence: 'odbl', verification_tier: 6 };
const usda = { source: 'usda_fdc', source_licence: 'public-domain', verification_tier: 2 };
const curated = { source: 'curated', source_licence: 'user', verification_tier: 5 };
const user = { source: 'user', source_licence: 'user', verification_tier: 5 };

describe('attributionFor', () => {
  it('credits Open Food Facts for Open Food Facts rows', () => {
    const a = attributionFor(off);
    expect(a.required).toBe(true);
    expect(a.tag).toBe('OPEN FOOD FACTS');
    expect(a.detail).toContain('Open Food Facts');
    expect(a.detail).toContain('Open Database License (ODbL)');
  });

  it('credits USDA as public domain, not ODbL', () => {
    const a = attributionFor(usda);
    expect(a.detail).toContain('USDA FoodData Central');
    expect(a.detail).toContain('public domain');
    expect(a.detail).not.toContain('Open Food Facts');
    expect(a.detail).not.toContain('ODbL');
  });

  it('does NOT label curated rows as Open Food Facts', () => {
    const a = attributionFor(curated);
    expect(a.required).toBe(false);
    expect(a.tag).toBeNull();
    expect(a.detail).toBeNull();
  });

  it('does NOT label user-created rows as Open Food Facts', () => {
    expect(attributionFor(user).required).toBe(false);
    expect(attributionFor(user).tag).toBeNull();
  });

  it('handles a missing record safely', () => {
    for (const bad of [null, undefined, {}, { source: null }]) {
      const a = attributionFor(bad as never);
      expect(a.required).toBe(false);
      expect(a.tag).toBeNull();
    }
  });

  it('reports an unrecorded licence instead of inventing one', () => {
    const a = attributionFor({ source: 'openfoodfacts', source_licence: 'unknown' });
    expect(a.detail).toContain('licence not recorded');
    expect(a.licence).toBe('unknown');
  });

  it('omits the licence phrase when the field is absent', () => {
    const a = attributionFor({ source: 'openfoodfacts' });
    expect(a.detail).toBe('Nutrition data from Open Food Facts.');
    expect(a.licence).toBeNull();
  });

  it('does not guess at an unrecognised source', () => {
    const a = attributionFor({ source: 'some_new_feed', source_licence: 'odbl' });
    expect(a.tag).toBe('SOURCE UNKNOWN');
    expect(a.detail).not.toContain('Open Food Facts');
  });

  it('provides unabbreviated accessibility text', () => {
    const a = attributionFor(off);
    expect(a.accessibilityLabel).toBe(
      'Nutrition data from Open Food Facts, Open Database License (ODbL).',
    );
    // The visible tag is abbreviated; the screen-reader text must not be.
    expect(a.accessibilityLabel).not.toBe(a.tag);
  });
});

describe('attributionsFor', () => {
  it('lists each distinct source once', () => {
    const all = attributionsFor([off, off, usda, curated, user]);
    expect(all).toHaveLength(2);
    const text = all.map((a) => a.detail).join(' ');
    expect(text).toContain('Open Food Facts');
    expect(text).toContain('USDA');
  });

  it('never implies one licence covers everything', () => {
    const all = attributionsFor([off, usda]);
    expect(new Set(all.map((a) => a.licence))).toEqual(
      new Set(['odbl', 'public-domain']),
    );
  });

  it('is order-stable', () => {
    const a = attributionsFor([off, usda]).map((x) => x.detail);
    const b = attributionsFor([usda, off]).map((x) => x.detail);
    expect(a).toEqual(b);
  });

  it('returns nothing for an all-curated catalogue', () => {
    expect(attributionsFor([curated, user])).toEqual([]);
  });

  it('handles an empty list', () => {
    expect(attributionsFor([])).toEqual([]);
  });
});

describe('confidenceLabel', () => {
  it('maps tiers to plain words', () => {
    expect(confidenceLabel(1)).toBe('LAB VERIFIED');
    expect(confidenceLabel(2)).toBe('LAB VERIFIED');
    expect(confidenceLabel(4)).toBe('REFERENCE DATA');
    expect(confidenceLabel(6)).toBe('COMMUNITY DATA');
    expect(confidenceLabel(7)).toBe('ESTIMATE');
  });

  it('shows nothing rather than guessing when the tier is missing', () => {
    expect(confidenceLabel(null)).toBeNull();
    expect(confidenceLabel(undefined)).toBeNull();
    expect(confidenceLabel(NaN)).toBeNull();
  });
});
