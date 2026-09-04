/**
 * Serving basis and data-quality labelling.
 *
 * The failure these guard against is quiet: three bases share one set of
 * digits on the portion sheet, and a figure on the wrong basis stays entirely
 * plausible. A user comparing against the packet in their hand cannot tell a
 * data problem from a units problem, so they conclude the app is wrong about
 * the food rather than about the arithmetic.
 */

import {
  QUALITY_LABEL,
  basisLabel,
  isIncomplete,
  qualityStatus,
  unitFor,
} from '../serving-basis';

describe('unit', () => {
  it('uses grams for solids and millilitres for liquids', () => {
    expect(unitFor(false)).toBe('g');
    expect(unitFor(true)).toBe('ml');
  });

  it('defaults to grams when liquidity is unrecorded', () => {
    expect(unitFor(null)).toBe('g');
    expect(unitFor(undefined)).toBe('g');
  });
});

describe('basisLabel', () => {
  it('names the serving, the count and the resulting weight', () => {
    const s = basisLabel({
      portionGrams: 90,
      servingName: '1 bar (45 g)',
      servingCount: 2,
    });
    expect(s).toContain('2 × 1 bar (45 g)');
    expect(s).toContain('90 g');
    expect(s).toContain('per 100 g');
  });

  it('changes when the serving changes', () => {
    const a = basisLabel({ portionGrams: 45, servingName: '1 bar', servingCount: 1 });
    const b = basisLabel({ portionGrams: 30, servingName: '1 square', servingCount: 1 });
    expect(a).not.toBe(b);
    expect(a).toContain('45 g');
    expect(b).toContain('30 g');
  });

  it('changes when the portion stepper changes', () => {
    const one = basisLabel({ portionGrams: 45, servingName: '1 bar', servingCount: 1 });
    const three = basisLabel({ portionGrams: 135, servingName: '1 bar', servingCount: 3 });
    expect(one).toContain('1 × 1 bar');
    expect(three).toContain('3 × 1 bar');
    expect(three).toContain('135 g');
  });

  it('says millilitres for a drink and never grams', () => {
    const s = basisLabel({
      isLiquid: true,
      portionGrams: 250,
      servingName: '1 glass',
      servingCount: 1,
    });
    expect(s).toContain('250 ml');
    expect(s).toContain('per 100 ml');
    // No GRAM unit anywhere: a drink measured in grams is a silent 1:1
    // volume-to-mass claim. Matched as a unit token so the 'g' in "1 glass"
    // does not count.
    expect(s).not.toMatch(/\d+\s*g\b/);
    expect(s).not.toMatch(/per 100 g\b/);
  });

  it('says grams for a weight-based food', () => {
    const s = basisLabel({ isLiquid: false, portionGrams: 200, servingName: 'bowl', servingCount: 1 });
    expect(s).toContain('200 g');
    expect(s).toContain('per 100 g');
  });

  it('falls back to raw weight when there is no named serving', () => {
    const s = basisLabel({ portionGrams: 120 });
    expect(s).toContain('120 g');
    expect(s).toContain('per 100 g');
  });

  it('says so plainly when no serving size is recorded', () => {
    // A missing basis line is worse than one saying the basis is unknown:
    // the reader assumes the previous line still applies.
    const s = basisLabel({});
    expect(s).toContain('Per 100 g');
    expect(s).toContain('no serving size recorded');
  });

  it('describes an AI estimate as the photographed portion, not a serving', () => {
    const s = basisLabel({ isEstimate: true, portionGrams: 210 });
    expect(s).toContain('Estimated');
    expect(s).toContain('photo');
    expect(s).toContain('210 g');
    // An estimate has no serving to be "per".
    expect(s).not.toContain('per 100');
  });

  it('describes an estimate with no weight without inventing one', () => {
    const s = basisLabel({ isEstimate: true });
    expect(s).toContain('Estimated');
    expect(s).not.toMatch(/\d/);
  });

  it('never returns an empty string', () => {
    for (const input of [{}, { portionGrams: 0 }, { isEstimate: true }, { isLiquid: true }]) {
      expect(basisLabel(input).length).toBeGreaterThan(0);
    }
  });

  it('never mixes two bases in one sentence', () => {
    // "per serving" and "per 100 g" describing the same digits is the exact
    // confusion this line exists to remove.
    const s = basisLabel({ portionGrams: 90, servingName: '1 bar', servingCount: 2 });
    expect(s.match(/per 100/g)?.length ?? 0).toBeLessThanOrEqual(1);
  });
});

describe('qualityStatus', () => {
  it('reports a lab-verified row as verified', () => {
    expect(qualityStatus({ verificationTier: 2 })).toBe('verified');
  });

  it('reports crowd-sourced data as estimated', () => {
    expect(qualityStatus({ verificationTier: 6 })).toBe('estimated');
  });

  it('NEVER reports an AI estimate as verified', () => {
    // Checked before `isVerified` so no combination of flags can render a
    // photo estimate as established fact.
    expect(qualityStatus({ isEstimate: true, isVerified: true })).toBe('estimated');
    expect(qualityStatus({ isEstimate: true, verificationTier: 1 })).toBe('estimated');
  });

  it('surfaces a server review flag over a trusted source', () => {
    expect(
      qualityStatus({ isVerified: true, verificationTier: 1, reviewRequired: true }),
    ).toBe('needs_review');
  });

  it('surfaces incompleteness over everything else', () => {
    // A row can come from a trusted source AND be missing half its panel,
    // and the missing half is what the user needs to know about.
    expect(
      qualityStatus({ isVerified: true, verificationTier: 1, incomplete: true }),
    ).toBe('incomplete');
  });

  it('says "needs review" rather than inventing a score when nothing is known', () => {
    expect(qualityStatus({})).toBe('needs_review');
    expect(qualityStatus({ verificationTier: null })).toBe('needs_review');
    expect(qualityStatus({ verificationTier: NaN })).toBe('needs_review');
  });

  it('has plain, non-clinical wording for every status', () => {
    const all = Object.values(QUALITY_LABEL).join(' ').toLowerCase();
    for (const banned of ['diagnos', 'disease', 'treat', 'cure', 'prevent', 'healthy']) {
      expect(all).not.toContain(banned);
    }
    expect(Object.keys(QUALITY_LABEL).sort()).toEqual([
      'estimated',
      'incomplete',
      'needs_review',
      'verified',
    ]);
  });
});

describe('isIncomplete', () => {
  it('accepts a full panel', () => {
    expect(isIncomplete({ calories: 250, protein_g: 8, carbs_g: 30, fat_g: 10 })).toBe(false);
  });

  it('flags a row with calories and no macros at all', () => {
    // What a bad crowd-sourced import looks like. It would otherwise render
    // as a confident, complete-looking result.
    expect(isIncomplete({ calories: 250 })).toBe(true);
  });

  it('flags a row whose macros are all exactly zero', () => {
    expect(isIncomplete({ calories: 250, protein_g: 0, carbs_g: 0, fat_g: 0 })).toBe(true);
  });

  it('flags a row with no energy figure', () => {
    expect(isIncomplete({ calories: 0, protein_g: 8, carbs_g: 30, fat_g: 10 })).toBe(true);
  });

  it('accepts a genuinely zero-macro food that still has energy from one macro', () => {
    // Black coffee: no protein or fat, a little carbohydrate.
    expect(isIncomplete({ calories: 2, protein_g: 0, carbs_g: 0.4, fat_g: 0 })).toBe(false);
  });
});
