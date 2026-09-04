/**
 * Every exercise in the catalogue gets a real figure.
 *
 * WHY THIS IS A TEST AND NOT A ONE-OFF SCRIPT
 * The illustration matcher works on keywords, and the catalogue is seeded from
 * an external dataset. Both sides move independently: a re-seed adds names
 * nobody wrote a pattern for, and a refactor of the pattern list can silently
 * drop one. Neither shows up as a crash — the screen just quietly starts
 * showing a dumbbell glyph where a drawing used to be, on a screen nobody
 * opens during development.
 *
 * Measured before this test existed: 752/873 names matched, 121 fell through
 * to the equipment glyph. After adding a category tier and 45 patterns it is
 * 873/873. This asserts it stays there.
 *
 * The catalogue is read from the BACKEND seed file rather than a copy, so the
 * test fails when the real data changes rather than when a fixture goes stale.
 */
import fs from 'fs';
import path from 'path';

import { exerciseArt } from '../exercise-art';

interface CatalogueRow {
  name: string;
  equipment: string | null;
  category: string | null;
}

const CATALOGUE = path.resolve(
  __dirname,
  '../../../../../services/api/app/scripts/data/exercises.json',
);

// If the seed file moves, fail loudly here rather than silently testing zero
// rows — a test that asserts nothing passes forever.
const rows: CatalogueRow[] = JSON.parse(fs.readFileSync(CATALOGUE, 'utf8'));

describe('exercise illustration coverage', () => {
  it('reads a non-empty catalogue', () => {
    expect(rows.length).toBeGreaterThan(800);
  });

  it('gives every exercise a real figure, not an equipment glyph', () => {
    const bare = rows
      .filter((r) => !exerciseArt(r.name, r.equipment, r.category).drawn)
      .map((r) => `${r.name} [${r.equipment} / ${r.category}]`);

    // Named in the failure so the fix is obvious: either add a keyword
    // pattern, or map the category.
    expect(bare).toEqual([]);
  });

  it('answers most exercises from the name, not the category fallback', () => {
    // The category tier is a safety net, not the plan. If it ever carries the
    // majority, the pattern list has rotted and the screens are showing
    // generic family figures where a specific movement was drawn.
    const byName = rows.filter(
      (r) => exerciseArt(r.name, r.equipment, r.category).tier === 'name',
    ).length;

    expect(byName / rows.length).toBeGreaterThan(0.85);
  });

  it('still falls back to a glyph for something outside the catalogue', () => {
    // The fallback must remain reachable. A matcher that returns `drawn: true`
    // for literally anything is not coverage, it is a broken conditional.
    const made_up = exerciseArt('Zorbing With Kettlebells', 'other', null);
    expect(made_up.drawn).toBe(false);
    expect(made_up.tier).toBe('equipment');
  });

  it('prefers the specific pattern over the general one', () => {
    // Order in PATTERNS is load-bearing: 'incline press' must beat 'press'.
    expect(exerciseArt('Incline Dumbbell Press', 'dumbbell', 'strength').tier).toBe(
      'name',
    );
    // And a stretch whose name contains a movement word must not be captured
    // by that movement — 'stretch' sits near the bottom of the list for this.
    expect(exerciseArt("Child's Pose", null, 'stretching').drawn).toBe(true);
  });
});
