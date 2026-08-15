/**
 * Tests for scan-state maths.
 *
 * The clarifying-question logic is the one piece of client-side arithmetic
 * that affects what lands in a user's diary. If it silently breaks, every
 * "how much ghee?" answer stops changing the number and nobody notices,
 * because the UI still looks correct.
 */

import { useScan } from '../useScan';
import type { RecognitionResponse } from '../../lib/api';

const RESULT: RecognitionResponse = {
  recognition_id: 'rec_1',
  overall_confidence: 0.72,
  cached: false,
  hidden_ingredients: ['tempering oil'],
  items: [
    {
      name: 'Dal tadka',
      portion_unit: 'katori',
      portion_count: 1,
      grams_est: 150,
      kcal_point: 240,
      kcal_low: 180,
      kcal_high: 300,
      protein_g: 9,
      carbs_g: 26,
      fat_g: 11,
      confidence: 0.7,
      clarifying_question: {
        text: 'How much ghee/oil?',
        options: ['None', '1 tsp', '1 tbsp', 'Restaurant-style'],
        kcal_deltas: [-60, 0, 45, 110],
      },
    },
    {
      name: 'Chapati',
      portion_unit: 'chapati',
      portion_count: 2,
      grams_est: 80,
      kcal_point: 220,
      kcal_low: 200,
      kcal_high: 240,
      protein_g: 7,
      carbs_g: 42,
      fat_g: 3,
      confidence: 0.93,
    },
  ],
};

function seed() {
  // Bypass the network: push the result straight into the store.
  useScan.setState({
    result: RESULT,
    items: RESULT.items.map((raw, i) => ({
      key: `${i}-${raw.name}`,
      name: raw.name,
      name_local: null,
      portion_unit: raw.portion_unit,
      portion_count: raw.portion_count,
      grams_est: raw.grams_est,
      kcal_point: raw.kcal_point,
      kcal_low: raw.kcal_low,
      kcal_high: raw.kcal_high,
      protein_g: raw.protein_g,
      carbs_g: raw.carbs_g,
      fat_g: raw.fat_g,
      confidence: raw.confidence,
      clarifying_question: raw.clarifying_question ?? null,
      multiplier: 1,
      answeredOption: null,
      edited: false,
    })),
  });
}

beforeEach(seed);

describe('portion adjustment', () => {
  it('scales the multiplier and marks the item edited', () => {
    const key = useScan.getState().items[0].key;
    useScan.getState().setPortion(key, 1.5);

    const item = useScan.getState().items[0];
    expect(item.multiplier).toBe(1.5);
    expect(item.edited).toBe(true);
  });

  it('clamps to a sane range', () => {
    const key = useScan.getState().items[0].key;

    useScan.getState().setPortion(key, -5);
    expect(useScan.getState().items[0].multiplier).toBe(0.25);

    useScan.getState().setPortion(key, 999);
    expect(useScan.getState().items[0].multiplier).toBe(10);
  });
});

describe('clarifying question', () => {
  it('applies a negative delta when the user says no ghee', () => {
    const key = useScan.getState().items[0].key;
    useScan.getState().answerQuestion(key, 0); // "None" -> -60

    const item = useScan.getState().items[0];
    expect(item.kcal_point).toBe(180);
    expect(item.answeredOption).toBe(0);
    expect(item.edited).toBe(true);
  });

  it('applies a positive delta for restaurant-style', () => {
    const key = useScan.getState().items[0].key;
    useScan.getState().answerQuestion(key, 3); // +110
    expect(useScan.getState().items[0].kcal_point).toBe(350);
  });

  it('TIGHTENS the range — answering genuinely reduces uncertainty', () => {
    const before = useScan.getState().items[0];
    const widthBefore = before.kcal_high - before.kcal_low;

    useScan.getState().answerQuestion(before.key, 2);

    const after = useScan.getState().items[0];
    const widthAfter = after.kcal_high - after.kcal_low;

    expect(widthAfter).toBeLessThan(widthBefore);
    // Point estimate stays centred in the new range.
    expect((after.kcal_low + after.kcal_high) / 2).toBeCloseTo(after.kcal_point, 5);
  });

  it('attributes the delta to fat, because cooking oil is pure fat', () => {
    const key = useScan.getState().items[0].key;
    const fatBefore = useScan.getState().items[0].fat_g;

    useScan.getState().answerQuestion(key, 2); // +45 kcal

    const fatAfter = useScan.getState().items[0].fat_g;
    expect(fatAfter - fatBefore).toBeCloseTo(45 / 9, 5);
  });

  it('raises confidence but never to certainty', () => {
    const key = useScan.getState().items[0].key;
    useScan.getState().answerQuestion(key, 1);
    const item = useScan.getState().items[0];
    expect(item.confidence).toBeGreaterThan(0.7);
    expect(item.confidence).toBeLessThanOrEqual(0.97);
  });

  it('never drives calories negative', () => {
    const key = useScan.getState().items[0].key;
    // Force a delta larger than the item's calories.
    useScan.setState({
      items: useScan.getState().items.map((it) =>
        it.key === key
          ? {
              ...it,
              kcal_point: 30,
              clarifying_question: {
                text: 'x',
                options: ['a'],
                kcal_deltas: [-500],
              },
            }
          : it,
      ),
    });
    useScan.getState().answerQuestion(key, 0);
    expect(useScan.getState().items[0].kcal_point).toBe(0);
    expect(useScan.getState().items[0].kcal_low).toBe(0);
  });

  it('ignores items with no question', () => {
    const key = useScan.getState().items[1].key; // Chapati, no question
    const before = useScan.getState().items[1].kcal_point;
    useScan.getState().answerQuestion(key, 0);
    expect(useScan.getState().items[1].kcal_point).toBe(before);
  });
});

describe('removal', () => {
  it('drops the item', () => {
    const key = useScan.getState().items[0].key;
    useScan.getState().removeItem(key);
    expect(useScan.getState().items).toHaveLength(1);
    expect(useScan.getState().items[0].name).toBe('Chapati');
  });
});
