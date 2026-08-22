/**
 * Protein: when it landed, how short you are, and the cheapest way to fix it.
 *
 * THE BET: "47 g short" is a diagnosis. "Dal + curd + eggs = 31 g for ₹50" is
 * a prescription. Every tracker ships the diagnosis and stops there.
 *
 * Three panels, in the order the question actually unfolds:
 *
 *   TODAY          protein by hour, so a back-loaded day is visibly
 *                  back-loaded and the thin meal is named
 *   CLOSE THE GAP  real foods, real portions, real prices, and a total
 *   PER RUPEE      the ranking — because for a student on a mess plan, cost
 *                  per gram is the binding constraint and no app shows it
 *
 * THE PRICES CARRY THEIR OWN AGE. `prices_stale_months` comes off the wire and
 * is rendered when it grows. A wrong price is worse than no price here — it
 * makes the ranking wrong, and the ranking is the entire feature — so the
 * table is allowed to be visibly old rather than quietly incorrect.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  InteractionManager,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';

import {
  Label,
  Panel,
  Plain,
  Rule,
  Segmented,
  Skeleton,
} from '../../src/components/instrument';
import { api, type ProteinFood, type ProteinReport } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

const SHAPE_LABEL: Record<string, string> = {
  even: 'EVENLY SPREAD',
  back_loaded: 'BACK-LOADED',
  front_loaded: 'FRONT-LOADED',
  single_dose: 'ONE SITTING',
  unknown: '—',
};

export default function ProteinScreen() {
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [diet, setDiet] = useState<'all' | 'veg'>('all');
  const [report, setReport] = useState<ProteinReport | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback((vegOnly: boolean) => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .proteinReport(vegOnly)
        .then((r) => alive && setReport(r))
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  useEffect(() => load(diet === 'veg'), [load, diet]);

  const shapeColor =
    report?.shape === 'even'
      ? accent.brand
      : report?.shape === 'unknown'
        ? palette.textFaint
        : palette.warn;

  /** Tallest sitting sets the scale. */
  const peak = useMemo(
    () => Math.max(1, ...(report?.meals ?? []).map((m) => m.protein_g)),
    [report],
  );

  return (
    <SafeAreaView
      style={[styles.screen, { backgroundColor: surfaces.void }]}
      edges={['top']}
    >
      <View style={styles.head}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Label color={palette.textDim}>← Nutrition</Label>
        </Pressable>
        <View style={styles.dietToggle}>
          <Segmented
            options={[
              { value: 'all' as const, label: 'All' },
              { value: 'veg' as const, label: 'Veg' },
            ]}
            value={diet}
            onChange={setDiet}
          />
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {failed ? (
          <Plain tone="danger">Couldn&apos;t load your protein data.</Plain>
        ) : !report ? (
          <>
            <Skeleton height={200} />
            <Skeleton height={160} />
          </>
        ) : (
          <>
            {/* -------------------------------------------- timing ------ */}
            <Animated.View entering={FadeInDown.duration(motion.base)}>
              <Panel
                label="Today"
                right={
                  <Label color={shapeColor}>
                    {SHAPE_LABEL[report.shape] ?? '—'}
                  </Label>
                }
              >
                <View style={styles.heroRow}>
                  <Text style={styles.hero}>{Math.round(report.total_g)}</Text>
                  <Text style={styles.heroUnit}>
                    {report.target_g ? `/ ${Math.round(report.target_g)} g` : 'g'}
                  </Text>
                </View>

                {report.meals.length > 0 ? (
                  <>
                    <View style={styles.chart}>
                      {report.meals.map((m, i) => {
                        const h = Math.max(3, (m.protein_g / peak) * 84);
                        const thin = m.name === report.thinnest_meal;
                        return (
                          <View key={`${m.name}-${i}`} style={styles.hourCol}>
                            <Text
                              style={[
                                styles.hourVal,
                                thin && { color: palette.warn },
                              ]}
                            >
                              {Math.round(m.protein_g)}
                            </Text>
                            <View
                              style={[
                                styles.hourBar,
                                {
                                  height: h,
                                  backgroundColor: thin
                                    ? palette.warn
                                    : accent.brand,
                                },
                              ]}
                            />
                            <Text style={styles.hourLbl}>
                              {formatHour(m.hour)}
                            </Text>
                          </View>
                        );
                      })}
                    </View>
                    <Rule style={styles.gap} />
                  </>
                ) : null}

                <Plain
                  tone={report.shape === 'even' ? 'signal' : 'warn'}
                  style={styles.gap}
                >
                  {report.detail}
                </Plain>
              </Panel>
            </Animated.View>

            {/* --------------------------------------- close the gap ---- */}
            {report.short_by_g > 0 ? (
              <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
                <Panel
                  label="Close the gap"
                  right={
                    <Label color={palette.warn}>
                      {Math.round(report.short_by_g)} G SHORT
                    </Label>
                  }
                >
                  {report.fix_foods.map((f, i) => (
                    <View key={f.key}>
                      {i > 0 ? <Rule /> : null}
                      <View style={styles.fixRow}>
                        <View style={styles.fixMid}>
                          <Text style={styles.fixName}>{f.name}</Text>
                          <Text style={styles.fixPortion}>{f.portion}</Text>
                        </View>
                        <Text style={styles.fixP}>
                          {Math.round(f.protein_g)}
                          <Text style={styles.fixUnit}> g</Text>
                        </Text>
                        <Text style={styles.fixRs}>₹{Math.round(f.rupees)}</Text>
                      </View>
                    </View>
                  ))}
                  <Rule style={styles.gap} />
                  <View style={styles.totalRow}>
                    <Text style={[styles.totalText, { color: accent.brand }]}>
                      {report.fix_note}
                    </Text>
                  </View>
                </Panel>
              </Animated.View>
            ) : (
              <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
                <Panel label="Close the gap" right={<Label color={accent.brand}>DONE</Label>}>
                  <Plain>
                    You&apos;re at target. Nothing to add — the rest of the day
                    is calories, not protein.
                  </Plain>
                </Panel>
              </Animated.View>
            )}

            {/* ------------------------------------------ per rupee ----- */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
              <Panel
                label="Protein per rupee"
                right={<Label color={palette.textFaint}>G PER ₹10</Label>}
              >
                {report.ranked.map((f) => (
                  <CostRow
                    key={f.key}
                    food={f}
                    best={report.ranked[0].g_per_10_rupees}
                    brand={accent.brand}
                  />
                ))}
                <Plain style={styles.gap}>
                  {report.prices_stale_months >= 6
                    ? `Typical ${report.prices_region} prices, last checked ${report.prices_as_of} — ${report.prices_stale_months} months ago, so treat the ranking as a guide rather than a quote.`
                    : `Typical ${report.prices_region} prices, ${report.prices_as_of}. A wrong price makes the ranking wrong, so this table says how old it is.`}
                </Plain>
              </Panel>
            </Animated.View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function formatHour(h: number): string {
  const hr = Math.floor(h);
  const suffix = hr < 12 ? 'a' : 'p';
  const display = hr % 12 === 0 ? 12 : hr % 12;
  return `${display}${suffix}`;
}

const CostRow = React.memo(
  function CostRowBase({
    food,
    best,
    brand,
  }: {
    food: ProteinFood;
    best: number;
    brand: string;
  }) {
    const frac = best > 0 ? food.g_per_10_rupees / best : 0;
    // Top third of the ranking gets the accent; the rest stays quiet. One
    // accent, per the design rules — highlighting everything highlights
    // nothing.
    const strong = frac >= 0.66;
    return (
      <View style={styles.costRow}>
        <Text style={styles.costName} numberOfLines={1}>
          {food.name}
        </Text>
        <View style={styles.costTrack}>
          <View
            style={[
              styles.costFill,
              {
                width: `${Math.max(2, frac * 100)}%`,
                backgroundColor: strong ? brand : palette.hairlineBright,
              },
            ]}
          />
        </View>
        <Text style={styles.costVal}>{food.g_per_10_rupees.toFixed(1)}</Text>
      </View>
    );
  },
  (a, b) =>
    a.food.key === b.food.key &&
    a.food.g_per_10_rupees === b.food.g_per_10_rupees &&
    a.best === b.best,
);

const styles = StyleSheet.create({
  screen: { flex: 1 },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.md,
  },
  dietToggle: { width: 130 },
  body: { padding: space.lg, paddingTop: 0, gap: space.md, paddingBottom: space.xxl },

  heroRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  hero: { ...type.readout, fontSize: 44, color: palette.text },
  heroUnit: { ...type.value, color: palette.textDim },

  chart: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-around',
    marginTop: space.lg,
    minHeight: 120,
  },
  hourCol: { alignItems: 'center', gap: space.xs, flex: 1 },
  hourVal: { ...type.valueSm, fontSize: 12, color: palette.textDim },
  hourBar: { width: 26, borderRadius: radius.sm },
  hourLbl: { ...type.labelSm, color: palette.textFaint },

  gap: { marginTop: space.md },

  fixRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
  },
  fixMid: { flex: 1, gap: 2 },
  fixName: { ...type.heading, color: palette.text },
  fixPortion: { ...type.labelSm, color: palette.textFaint },
  fixP: { ...type.valueSm, fontSize: 16, color: palette.text },
  fixUnit: { ...type.labelSm, color: palette.textDim },
  fixRs: { ...type.valueSm, fontSize: 15, color: palette.textDim, width: 46, textAlign: 'right' },

  totalRow: { marginTop: space.md },
  totalText: { ...type.heading },

  costRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
  },
  costName: { ...type.body, fontSize: 13, color: palette.textDim, width: 82 },
  costTrack: {
    flex: 1,
    height: 9,
    borderRadius: radius.pill,
    backgroundColor: palette.hairline,
    overflow: 'hidden',
  },
  costFill: { height: '100%', borderRadius: radius.pill },
  costVal: {
    ...type.valueSm,
    fontSize: 14,
    color: palette.text,
    width: 38,
    textAlign: 'right',
  },
});
