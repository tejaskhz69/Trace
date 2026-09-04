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

// ------------------------------------------------- server-composed wording
//
// `source_name` and `attribution` arrive from services/api/licensing.py. They
// exist because the tables in this module used to be the only copy of that
// mapping and the copy drifted: `nutritionix` reached the API and never
// reached here, so metered rows rendered "SOURCE UNKNOWN" -- dropping a credit
// owed by contract, silently, in a way no user could detect.

const served = {
  source: 'openfoodfacts',
  source_licence: 'odbl',
  source_name: 'Open Food Facts',
  attribution:
    'Nutrition data from Open Food Facts, made available under the Open Database License (ODbL).',
};

describe('server-composed attribution', () => {
  it('renders what the server sent, verbatim', () => {
    const a = attributionFor(served);
    expect(a.required).toBe(true);
    expect(a.tag).toBe('OPEN FOOD FACTS');
    expect(a.detail).toBe(served.attribution);
    expect(a.accessibilityLabel).toBe(served.attribution);
  });

  it('prefers the server wording over the local table', () => {
    // A source the local table has never heard of. Before the server sent
    // wording, this rendered "SOURCE UNKNOWN".
    const a = attributionFor({
      source: 'some_feed_added_next_year',
      source_licence: 'proprietary',
      source_name: 'Some Feed',
      attribution: 'Nutrition data from Some Feed, used under licence.',
    });
    expect(a.tag).toBe('SOME FEED');
    expect(a.detail).toBe('Nutrition data from Some Feed, used under licence.');
    expect(a.detail).not.toContain('not recorded');
  });

  it('treats a null attribution from the server as "nothing to credit"', () => {
    // NOT as "field missing". A curated row names its source and owes no
    // credit; rendering an empty notice would be wrong.
    const a = attributionFor({
      source: 'curated',
      source_licence: 'user',
      source_name: 'Trace',
      attribution: null,
    });
    expect(a.required).toBe(false);
    expect(a.tag).toBeNull();
    expect(a.detail).toBeNull();
  });

  it('falls back to the local table when the server sends neither field', () => {
    const a = attributionFor({ source: 'openfoodfacts', source_licence: 'odbl' });
    expect(a.tag).toBe('OPEN FOOD FACTS');
    expect(a.detail).toContain('Open Database License (ODbL)');
  });
});

describe('sources the local fallback must still cover', () => {
  it('credits Nutritionix rather than calling it unknown', () => {
    const a = attributionFor({ source: 'nutritionix', source_licence: 'proprietary' });
    expect(a.tag).toBe('NUTRITIONIX');
    expect(a.detail).toContain('Nutritionix');
    expect(a.detail).toContain('used under licence');
    expect(a.tag).not.toBe('SOURCE UNKNOWN');
  });

  it('does not label our own photo estimates as third-party data', () => {
    const a = attributionFor({ source: 'ai_estimated', source_licence: 'user' });
    expect(a.required).toBe(false);
    expect(a.tag).toBeNull();
  });

  it('credits IFCT by name even though its licence is unconfirmed', () => {
    const a = attributionFor({ source: 'ifct', source_licence: 'unknown' });
    expect(a.detail).toContain('Indian Food Composition Tables');
    expect(a.detail).toContain('licence not recorded');
  });
});

describe('every licence value the database can hold', () => {
  // The Licence enum in services/api/app/services/licensing.py.
  const LICENCES = ['odbl', 'public-domain', 'proprietary', 'user', 'unknown'];

  it.each(LICENCES)('renders a phrase for %s without inventing one', (lic) => {
    const a = attributionFor({ source: 'openfoodfacts', source_licence: lic });
    expect(a.detail).toBeTruthy();
    expect(a.detail).not.toContain('undefined');
    expect(a.detail).not.toContain('[object');
  });

  it('says nothing about a licence it cannot name', () => {
    const a = attributionFor({ source: 'openfoodfacts', source_licence: 'cc-by-sa-9.9' });
    expect(a.detail).toBe('Nutrition data from Open Food Facts.');
    expect(a.licence).toBe('cc-by-sa-9.9'); // reported, never rewritten
  });
});

describe('never asserts compliance', () => {
  const SOURCES = [
    'openfoodfacts',
    'usda_fdc',
    'ifct',
    'nutritionix',
    'ai_estimated',
    'curated',
    'user',
    'unheard_of',
  ];

  it.each(SOURCES)('%s: states a fact and stops', (source) => {
    const a = attributionFor({ source, source_licence: 'odbl' });
    const shown = `${a.tag ?? ''} ${a.detail ?? ''}`.toLowerCase();
    for (const banned of ['compliant', 'compliance', 'permitted', 'we own', 'all rights']) {
      expect(shown).not.toContain(banned);
    }
  });

  it.each(SOURCES)('%s: never credits a party it did not come from', (source) => {
    const detail = attributionFor({ source, source_licence: 'odbl' }).detail ?? '';
    if (source !== 'openfoodfacts') expect(detail).not.toContain('Open Food Facts');
    if (source !== 'usda_fdc') expect(detail).not.toContain('USDA');
  });
});

describe('malformed records do not break rendering', () => {
  const BAD: unknown[] = [
    null,
    undefined,
    {},
    { source: null },
    { source: '' },
    { source: 'openfoodfacts', source_licence: null },
    { source: 'openfoodfacts', source_name: '', attribution: '' },
    { source: 'openfoodfacts', source_name: null, attribution: 'orphaned sentence' },
    { source: 123 },
    { source: 'openfoodfacts', verification_tier: 'six' },
  ];

  it.each(BAD.map((b, i) => [i, b]))('case %i returns a usable shape', (_i, bad) => {
    const a = attributionFor(bad as never);
    expect(typeof a.required).toBe('boolean');
    expect(a.tag === null || typeof a.tag === 'string').toBe(true);
    expect(a.detail === null || typeof a.detail === 'string').toBe(true);
    // required implies there is something to render.
    if (a.required) expect(a.tag).toBeTruthy();
  });

  it('an attribution sentence without a source name is not rendered alone', () => {
    // Half a payload is not evidence of provenance.
    const a = attributionFor({ source: 'unheard_of', attribution: 'orphaned sentence' });
    expect(a.detail).not.toBe('orphaned sentence');
  });
});

describe('long source text', () => {
  const LONG = 'Fundacion Espanola de la Nutricion y Composicion de Alimentos';
  const longRow = {
    source: 'x',
    source_licence: 'odbl',
    source_name: LONG,
    attribution: `Nutrition data from ${LONG}, used under licence.`,
  };

  it('keeps the tag to a single line so a dense row cannot reflow', () => {
    // The row renders this with numberOfLines={1}; what matters here is that
    // the string itself carries no break the layout would have to honour.
    const a = attributionFor(longRow);
    expect(a.tag).not.toContain('\n');
    expect(a.tag).toBe(LONG.toUpperCase());
  });

  it('puts the unabbreviated text where a screen reader will find it', () => {
    // The visible tag is truncated by the layout; the accessibility label and
    // the detail sheet are what carry the whole credit.
    const a = attributionFor(longRow);
    expect(a.accessibilityLabel).toContain(LONG);
    expect(a.detail).toContain(LONG);
    expect(a.accessibilityLabel).not.toBe(a.tag);
  });
});

describe('mixed-source lists', () => {
  it('lists server-composed and fallback rows together, once each', () => {
    const all = attributionsFor([served, usda, curated, served]);
    expect(all).toHaveLength(2);
    expect(all.map((a) => a.licence).sort()).toEqual(['odbl', 'public-domain']);
  });

  it('drops rows that owe no credit rather than listing them blank', () => {
    const all = attributionsFor([
      curated,
      { source: 'ai_estimated', source_licence: 'user' },
      { source: 'user', source_licence: 'user' },
    ]);
    expect(all).toEqual([]);
  });
});
