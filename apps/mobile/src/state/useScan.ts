/**
 * Scan state: the recognition result, the user's edits, and the commit.
 *
 * The single most important line in this file is the `api.request(
 * '/recognize/{id}/correct')` call in `commit()`. Every edit a user makes is a
 * labelled example of exactly the food our users actually eat, corrected by
 * the person who ate it. After six months that table is a proprietary dataset
 * a competitor cannot buy or scrape. Dropping it because "we already logged
 * the meal" would throw away the most valuable output of the whole flow.
 */

import { create } from 'zustand';

import { RecognitionResponse, api, request } from '../lib/api';

export interface ScanItem {
  key: string;
  name: string;
  name_local: string | null;
  portion_unit: string;
  portion_count: number;
  grams_est: number;
  kcal_point: number;
  kcal_low: number;
  kcal_high: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  confidence: number;
  clarifying_question: {
    text: string;
    options: string[];
    kcal_deltas: number[];
  } | null;
  /** User's portion adjustment. 1 = as detected. */
  multiplier: number;
  /** Index into clarifying_question.options, once answered. */
  answeredOption: number | null;
  /** True if the user touched anything on this item -- drives the feedback payload. */
  edited: boolean;
}

interface ScanState {
  result: RecognitionResponse | null;
  items: ScanItem[];
  scanning: boolean;
  submitting: boolean;
  error: string | null;

  scan: (uri: string, hint?: string) => Promise<boolean>;
  setPortion: (key: string, multiplier: number) => void;
  answerQuestion: (key: string, optionIndex: number) => void;
  removeItem: (key: string) => void;
  commit: (mealType: string) => Promise<void>;
  reset: () => void;
}

function toItems(res: RecognitionResponse): ScanItem[] {
  return res.items.map((raw, i) => ({
    key: `${i}-${raw.name}`,
    name: raw.name,
    name_local: (raw as { name_local?: string | null }).name_local ?? null,
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
  }));
}

export const useScan = create<ScanState>((set, get) => ({
  result: null,
  items: [],
  scanning: false,
  submitting: false,
  error: null,

  async scan(uri, hint) {
    set({ scanning: true, error: null });
    try {
      const res = await api.recognizePhoto(uri, hint);
      set({ result: res, items: toItems(res), scanning: false });
      return true;
    } catch (err) {
      set({
        scanning: false,
        error:
          (err as { status?: number })?.status === 402
            ? "You've used today's free scans. Barcode and search are still unlimited."
            : "Couldn't read that photo. Try again, or log it manually.",
      });
      return false;
    }
  },

  setPortion(key, multiplier) {
    const clamped = Math.max(0.25, Math.min(multiplier, 10));
    set({
      items: get().items.map((it) =>
        it.key === key
          ? { ...it, multiplier: Number(clamped.toFixed(2)), edited: true }
          : it,
      ),
    });
  },

  /**
   * Fold the answer into the item's calories.
   *
   * The delta from the model is expressed against the point estimate, so we
   * shift low/point/high together and tighten the range -- answering the
   * question genuinely reduces uncertainty, and the UI should show that.
   */
  answerQuestion(key, optionIndex) {
    set({
      items: get().items.map((it) => {
        if (it.key !== key || !it.clarifying_question) return it;
        const delta = it.clarifying_question.kcal_deltas[optionIndex] ?? 0;
        const halfWidth = (it.kcal_high - it.kcal_low) / 2;
        const tightened = halfWidth * 0.5;
        const point = Math.max(0, it.kcal_point + delta);
        // Attribute the delta to fat: cooking oil and ghee are pure fat.
        const fatDelta = delta / 9;
        return {
          ...it,
          kcal_point: point,
          kcal_low: Math.max(0, point - tightened),
          kcal_high: point + tightened,
          fat_g: Math.max(0, it.fat_g + fatDelta),
          confidence: Math.min(0.97, it.confidence + 0.15),
          answeredOption: optionIndex,
          edited: true,
        };
      }),
    });
  },

  removeItem(key) {
    set({ items: get().items.filter((it) => it.key !== key) });
  },

  async commit(mealType) {
    const { result, items } = get();
    if (!result) return;

    set({ submitting: true });
    try {
      // 1. Log each item.
      await Promise.all(
        items.map((it) =>
          api.logMeal({
            display_name: it.name,
            grams: it.grams_est * it.multiplier,
            serving_label: `${(it.portion_count * it.multiplier).toFixed(2)} ${it.portion_unit}`,
            meal_type: mealType,
            recognition_id: result.recognition_id,
            calories: it.kcal_point * it.multiplier,
            protein_g: it.protein_g * it.multiplier,
            carbs_g: it.carbs_g * it.multiplier,
            fat_g: it.fat_g * it.multiplier,
          }),
        ),
      );

      // 2. THE VALUABLE PART. Capture what the user changed.
      const edited = items.filter((it) => it.edited);
      const removed = result.items.length - items.length;
      if (edited.length > 0 || removed > 0) {
        await request(
          `/api/foods/recognize/${result.recognition_id}/correct`,
          {
            method: 'POST',
            body: {
              correction_type: removed > 0 && items.length === 0 ? 'reject' : 'edit',
              corrected_items: edited.map((it) => ({
                name: it.name,
                original_kcal: result.items.find((r) => r.name === it.name)?.kcal_point,
                corrected_kcal: it.kcal_point * it.multiplier,
                portion_multiplier: it.multiplier,
                answered_option: it.answeredOption,
                question: it.clarifying_question?.text ?? null,
              })),
              notes: removed > 0 ? `${removed} item(s) removed by user` : null,
            },
          },
        ).catch(() => undefined); // never block the log on telemetry
      } else {
        // A clean confirm is signal too -- it tells us the model was right.
        await request(
          `/api/foods/recognize/${result.recognition_id}/correct`,
          { method: 'POST', body: { correction_type: 'confirm' } },
        ).catch(() => undefined);
      }

      set({ submitting: false, result: null, items: [] });
    } catch {
      set({ submitting: false, error: "Couldn't save. Please try again." });
    }
  },

  reset: () => set({ result: null, items: [], error: null, scanning: false }),
}));
