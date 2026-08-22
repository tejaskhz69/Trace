/**
 * "How well do we actually know today?"
 *
 * THE BET, restated: every tracker prints a confident daily total assembled
 * entirely from guesses. "2,100 kcal" reads like a measurement and is a
 * barcode read, a photo estimate and a number somebody typed from memory,
 * added together and set in the same font.
 *
 * Two pieces, and the second is the one that matters:
 *
 *   CertaintyReadout  the day as a range — 640 ±95 — with the band rendered
 *                     as an actual region on the bar, not a footnote
 *   CertaintyStrip    where the width COMES FROM, by source, ordered widest
 *                     first, ending in one specific sentence about one
 *                     specific item
 *
 * WHY THE STRIP IS SIZED BY UNCERTAINTY AND NOT BY CALORIES
 * A strip sized by calories would say "44% of today was a photo scan", which
 * is a fact with nothing to do. Sized by contribution to the band, it says
 * "that one quick-added meal is most of why this number is vague" — and
 * because bands combine in quadrature, that is usually one item rather than a
 * habit. Fixing it is a single action, which is the whole point.
 *
 * NON-NEGOTIABLE #2 lives here. This is the component that stops a day total
 * being displayed as a single confident number.
 */

import React, { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Label, Panel, Plain, Rule } from './instrument';
import type { CertaintySlice, DayUncertainty } from '../lib/api';
import { useAccent } from '../state/useTheme';
import { palette, radius, space, type } from '../theme';

/** Source → series colour. Fixed, so the strip and the meal badges agree. */
const SOURCE_COLOR: Record<string, string> = {
  label: palette.seriesStrength,
  search: palette.seriesWeight,
  scan: palette.seriesEnergy,
  quick_add: palette.seriesAlert,
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: 'HIGH CONFIDENCE',
  medium: 'FAIR CONFIDENCE',
  low: 'WIDE ESTIMATE',
};

function sourceColor(source: string): string {
  return SOURCE_COLOR[source] ?? palette.textDim;
}

/**
 * The day, as a range.
 *
 * `left` is calories remaining when a target exists; the hero number is that,
 * because "how much more can I eat" is the question. Without a target it
 * falls back to what has been eaten — still a range either way.
 */
export const CertaintyReadout = memo(function CertaintyReadoutBase({
  report,
}: {
  report: DayUncertainty;
}) {
  const accent = useAccent();
  const target = report.calorie_target;
  const left = target !== null ? Math.round(target - report.total_kcal) : null;
  const band = Math.round(report.band);

  const confidenceColor =
    report.confidence === 'high'
      ? palette.seriesStrength
      : report.confidence === 'medium'
        ? palette.warn
        : palette.seriesAlert;

  // Bar geometry. The band is drawn as a translucent region straddling the
  // fill edge, so the uncertainty is a place on the bar rather than a number
  // printed next to it.
  const denom = target && target > 0 ? target : Math.max(1, report.high);
  const pct = (v: number) => Math.max(0, Math.min(1, v / denom));
  const fill = pct(report.total_kcal);
  const lo = pct(report.low);
  const hi = pct(report.high);

  return (
    <Panel
      label={target !== null ? 'Left today' : 'Eaten today'}
      right={<Label color={confidenceColor}>{CONFIDENCE_LABEL[report.confidence]}</Label>}
    >
      <View style={styles.readoutRow}>
        <Text style={styles.hero}>
          {left !== null ? left.toLocaleString() : Math.round(report.total_kcal).toLocaleString()}
        </Text>
        <Text style={styles.pm}>± {band}</Text>
      </View>

      <Text style={styles.sub}>
        {left !== null ? (
          <>
            Somewhere between{' '}
            <Text style={styles.b}>{(left - band).toLocaleString()}</Text> and{' '}
            <Text style={styles.b}>{(left + band).toLocaleString()}</Text>.
          </>
        ) : (
          report.headline
        )}
        {report.worst_item ? (
          <> Wide because {report.worst_item.toLowerCase()} was an estimate.</>
        ) : null}
      </Text>

      {/* ---- the bar, with the band as a region ------------------------- */}
      <View style={styles.bar}>
        <View style={styles.barTrack} />
        <View
          style={[
            styles.barBand,
            {
              left: `${lo * 100}%`,
              width: `${Math.max(0.01, hi - lo) * 100}%`,
              backgroundColor: accent.brand,
            },
          ]}
        />
        <View
          style={[
            styles.barFill,
            { width: `${fill * 100}%`, backgroundColor: accent.brand },
          ]}
        />
        <View style={[styles.barTick, { left: `${fill * 100}%` }]} />
      </View>

      <View style={styles.barLabels}>
        <Label color={palette.textFaint}>
          {Math.round(report.total_kcal).toLocaleString()} EATEN
        </Label>
        {target !== null ? (
          <Label color={palette.textFaint}>
            {Math.round(target).toLocaleString()} TARGET
          </Label>
        ) : null}
      </View>
    </Panel>
  );
});

/**
 * Where the width comes from.
 *
 * memo'd on the mix identity: this re-renders only when the day's provenance
 * actually changes, not on every parent render.
 */
export const CertaintyStrip = memo(function CertaintyStripBase({
  report,
}: {
  report: DayUncertainty;
}) {
  if (report.mix.length === 0) return null;

  return (
    <Panel label="How well do we know today?">
      <View style={styles.strip}>
        {report.mix.map((m) => (
          <View
            key={m.source}
            style={[
              styles.stripSeg,
              {
                flex: Math.max(0.02, m.uncertainty_share),
                backgroundColor: sourceColor(m.source),
              },
            ]}
          />
        ))}
      </View>

      <View style={styles.key}>
        {report.mix.map((m) => (
          <KeyItem key={m.source} slice={m} />
        ))}
      </View>

      {/* The whole reason the strip exists: one item, one action. */}
      {report.advice ? (
        <Plain tone="warn" style={styles.gap}>
          {report.advice}
        </Plain>
      ) : (
        <Plain style={styles.gap}>
          Nothing here is dragging the estimate on its own — today&apos;s band
          is about as tight as it gets for what you logged.
        </Plain>
      )}
    </Panel>
  );
});

const KeyItem = memo(
  function KeyItemBase({ slice }: { slice: CertaintySlice }) {
    return (
      <View style={styles.keyItem}>
        <View
          style={[styles.keyDot, { backgroundColor: sourceColor(slice.source) }]}
        />
        <Text style={styles.keyText}>
          {slice.label} · {Math.round(slice.uncertainty_share * 100)}%
        </Text>
      </View>
    );
  },
  (a, b) =>
    a.slice.source === b.slice.source &&
    a.slice.uncertainty_share === b.slice.uncertainty_share,
);

/** The provenance badge on a diary row. */
export const SourceBadge = memo(function SourceBadgeBase({
  source,
  label,
}: {
  source: string;
  label: string;
}) {
  const c = sourceColor(source);
  return (
    <View style={[styles.badge, { backgroundColor: `${c}22` }]}>
      <Text style={[styles.badgeText, { color: c }]}>{label.toUpperCase()}</Text>
    </View>
  );
});

/** The diary, with every row carrying its own band and its provenance. */
export const CertaintyMeals = memo(function CertaintyMealsBase({
  report,
}: {
  report: DayUncertainty;
}) {
  if (report.items.length === 0) return null;
  return (
    <Panel
      label={`Meals · ${report.items.length}`}
      right={
        <Label color={palette.textDim}>
          {Math.round(report.total_kcal).toLocaleString()} kcal
        </Label>
      }
      padded={false}
    >
      {report.items.map((it, i) => (
        <View key={`${it.name}-${i}`}>
          {i > 0 ? <Rule /> : null}
          <View style={styles.mealRow}>
            <View style={styles.mealMid}>
              <Text style={styles.mealName} numberOfLines={1}>
                {it.name}
              </Text>
              <View style={styles.mealMeta}>
                <SourceBadge source={it.source} label={it.source_label} />
              </View>
            </View>
            <View style={styles.mealRight}>
              <Text style={styles.mealKcal}>{Math.round(it.kcal)}</Text>
              {/* Every item shows its own width. A barcode row reading ±6
                  next to a quick-add reading ±84 is the argument, made
                  without a single word of explanation. */}
              <Text style={styles.mealBand}>± {Math.round(it.band)}</Text>
            </View>
          </View>
        </View>
      ))}
    </Panel>
  );
});

const styles = StyleSheet.create({
  readoutRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  hero: { ...type.readout, color: palette.text },
  pm: { ...type.value, color: palette.textDim },
  sub: { ...type.body, fontSize: 13, color: palette.textDim, marginTop: space.xs, lineHeight: 19 },
  b: { fontFamily: type.heading.fontFamily, color: palette.text },

  bar: { height: 12, marginTop: space.lg, justifyContent: 'center' },
  barTrack: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: radius.pill,
    backgroundColor: palette.hairline,
  },
  barBand: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    opacity: 0.22,
  },
  barFill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    borderRadius: radius.pill,
  },
  barTick: {
    position: 'absolute',
    top: -3,
    bottom: -3,
    width: 2,
    backgroundColor: palette.text,
  },
  barLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: space.sm,
  },

  strip: { flexDirection: 'row', height: 9, gap: 2 },
  stripSeg: { borderRadius: 3 },
  key: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md, marginTop: space.sm },
  keyItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  keyDot: { width: 8, height: 8, borderRadius: 2 },
  keyText: { ...type.labelSm, color: palette.textDim, letterSpacing: 0.4 },

  gap: { marginTop: space.md },

  mealRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  mealMid: { flex: 1, gap: 4 },
  mealName: { ...type.heading, color: palette.text },
  mealMeta: { flexDirection: 'row' },
  mealRight: { alignItems: 'flex-end' },
  mealKcal: { ...type.valueSm, fontSize: 17, color: palette.text },
  mealBand: { ...type.labelSm, color: palette.textFaint },

  badge: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
  badgeText: { ...type.labelSm, fontSize: 9, letterSpacing: 0.9 },
});
