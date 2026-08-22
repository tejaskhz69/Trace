/**
 * The maintenance card — what we MEASURED your expenditure to be.
 *
 * THIS CARD IS THE PRODUCT'S WHOLE ARGUMENT
 * Every calorie app gives you a number. Almost all of them get it from the
 * same Mifflin-St Jeor equation, which carries roughly ±10% error on an
 * individual and is worse at the tails. Trace reconstructs the number from
 * the energy balance the user actually demonstrated — what they ate against
 * what their weight trend did — and when that disagrees with the equation by
 * 200 kcal, THAT GAP is the reason the app exists. So `vs_calculator` is
 * rendered prominently rather than hidden in a settings screen.
 *
 * WHY THE BAND IS NEVER OPTIONAL
 * A bare "2,514" invites more confidence than any expenditure estimate has
 * earned. The band, the "dialed" bar and the source line all travel with the
 * number so the user can see how much evidence is behind it. The band never
 * collapses below ±4%, because true daily expenditure moves with NEAT and
 * water and claiming ±1% would be a lie told in a confident voice.
 *
 * THE HONEST FAILURE MODE
 * With too little data the card says so, and says exactly what would unlock a
 * real measurement — "8 more weigh-ins and I can measure it". That is far
 * better than a confident wrong number, and it is the same rule as the
 * adjudication engine's INSUFFICIENT_DATA.
 */

import React, { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Path, Circle } from 'react-native-svg';

import { Label, Panel, Rule } from './instrument';
import { useAccent } from '../state/useTheme';
import { palette, radius, space, type } from '../theme';
import type { Maintenance } from '../lib/api';

const CHART_H = 96;

export const MaintenanceCard = memo(function MaintenanceCardBase({
  data,
  width = 320,
}: {
  data: Maintenance;
  width?: number;
}) {
  const accent = useAccent();
  const measured = data.is_data_driven;

  return (
    <Panel
      label="Maintenance"
      right={
        <View
          style={[
            styles.badge,
            {
              borderColor: measured ? accent.brandDim : palette.hairlineBright,
            },
          ]}
        >
          <Text
            style={[
              styles.badgeText,
              { color: measured ? accent.brand : palette.textFaint },
            ]}
          >
            {measured ? 'MEASURED' : 'ESTIMATED'}
          </Text>
        </View>
      }
    >
      {/* --------------------------------------------------- the number */}
      <View style={styles.headRow}>
        <View style={styles.headL}>
          <Text style={styles.big}>
            {data.maintenance_kcal.toLocaleString('en-US')}
          </Text>
          <Text style={styles.bigUnit}>kcal/day</Text>
        </View>
        {data.vs_calculator != null ? (
          <View style={styles.vsCalc}>
            <Label>vs calculator</Label>
            <Text
              style={[
                styles.vsValue,
                {
                  color:
                    data.vs_calculator > 0 ? palette.up : palette.down,
                },
              ]}
            >
              {data.vs_calculator > 0 ? '↑' : '↓'}{' '}
              {Math.abs(data.vs_calculator).toLocaleString('en-US')}
            </Text>
          </View>
        ) : null}
      </View>

      {/* The range, stated in words as well as drawn. A band nobody can read
          the endpoints of is decoration. */}
      <Text style={styles.range}>
        {data.band_low.toLocaleString('en-US')} –{' '}
        {data.band_high.toLocaleString('en-US')} kcal
      </Text>

      <BandChart data={data} width={width} color={accent.brand} />

      {/* ------------------------------------------------ how dialed in */}
      <View style={styles.dialedRow}>
        <Label>Band precision</Label>
        <Text style={[styles.dialedPct, { color: accent.brand }]}>
          {data.dialed_pct}% DIALED
        </Text>
      </View>
      <View style={styles.dialedTrack}>
        <View
          style={[
            styles.dialedFill,
            { width: `${data.dialed_pct}%`, backgroundColor: accent.brand },
          ]}
        />
      </View>

      <Text style={styles.source}>{data.source_line}</Text>

      {/* ------------------------------------------- eating vs expected */}
      {data.eating_kcal != null ? (
        <>
          <Rule style={styles.rule} />
          <View style={styles.footRow}>
            <View style={styles.footCell}>
              <Label>Eating</Label>
              <View style={styles.footVals}>
                <Text style={styles.footValue}>
                  {data.eating_kcal.toLocaleString('en-US')}
                </Text>
                {data.eating_delta != null ? (
                  <Text
                    style={[
                      styles.footDelta,
                      {
                        color:
                          data.eating_delta < 0 ? palette.down : palette.up,
                      },
                    ]}
                  >
                    {data.eating_delta > 0 ? '+' : ''}
                    {data.eating_delta.toLocaleString('en-US')}
                  </Text>
                ) : null}
              </View>
            </View>
            <Rule vertical />
            <View style={[styles.footCell, styles.footCellR]}>
              <Label>Expected</Label>
              <Text style={styles.footValue}>
                {data.expected_rate_kg_per_week != null
                  ? `${data.expected_rate_kg_per_week > 0 ? '+' : ''}${data.expected_rate_kg_per_week} kg/wk`
                  : '—'}
              </Text>
            </View>
          </View>
          <Text style={styles.caveat}>
            Expected rate is an energy-balance projection, not a promise. Water
            and glycogen move the scale far faster than tissue does.
          </Text>
        </>
      ) : null}
    </Panel>
  );
});

/**
 * The estimate over time, with its uncertainty band.
 *
 * The band genuinely narrows because the server re-ran the estimator against
 * progressively less data — it is not a decorative taper applied to today's
 * number. That distinction is the difference between showing your work and
 * drawing a picture of showing your work.
 */
function BandChart({
  data,
  width,
  color,
}: {
  data: Maintenance;
  width: number;
  color: string;
}) {
  const pts = data.history;
  if (pts.length < 2) {
    return (
      <View style={[styles.chartEmpty, { height: CHART_H }]}>
        <Text style={styles.chartEmptyText}>
          The chart appears once there are a couple of weeks to plot.
        </Text>
      </View>
    );
  }

  const lo = Math.min(...pts.map((p) => p.low));
  const hi = Math.max(...pts.map((p) => p.high));
  const span = hi - lo || 1;
  const x = (i: number) => (i / (pts.length - 1)) * width;
  const y = (v: number) => CHART_H - ((v - lo) / span) * CHART_H;

  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i)} ${y(p.kcal)}`).join(' ');
  const bandTop = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i)} ${y(p.high)}`).join(' ');
  const bandBottom = pts
    .slice()
    .reverse()
    .map((p, i) => `L${x(pts.length - 1 - i)} ${y(p.low)}`)
    .join(' ');
  const band = `${bandTop} ${bandBottom} Z`;

  const last = pts[pts.length - 1];

  return (
    <View style={styles.chart}>
      <Svg width={width} height={CHART_H}>
        <Path d={band} fill={color} opacity={0.12} />
        <Path d={line} stroke={color} strokeWidth={1.6} fill="none" />
        <Circle cx={x(pts.length - 1)} cy={y(last.kcal)} r={3} fill={color} />
      </Svg>
      <View style={styles.chartAxis}>
        <Text style={styles.axisText}>{Math.round(lo).toLocaleString('en-US')}</Text>
        <Text style={styles.axisText}>{Math.round(hi).toLocaleString('en-US')}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderWidth: 1,
    borderRadius: radius.xs,
    paddingHorizontal: space.sm,
    paddingVertical: 2,
  },
  badgeText: { ...type.labelSm, fontSize: 8 },

  headRow: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  headL: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  big: { ...type.figure, color: palette.text },
  bigUnit: { ...type.caption, color: palette.textFaint },
  vsCalc: { alignItems: 'flex-end', gap: 2 },
  vsValue: { ...type.valueSm },

  range: { ...type.labelSm, color: palette.textGhost, marginTop: space.xs },

  chart: { marginTop: space.md },
  chartAxis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: space.xs },
  axisText: { ...type.labelSm, fontSize: 8, color: palette.textGhost },
  chartEmpty: { justifyContent: 'center', marginTop: space.md },
  chartEmptyText: { ...type.caption, color: palette.textGhost },

  dialedRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: space.md,
  },
  dialedPct: { ...type.labelSm },
  dialedTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: palette.hairline,
    marginTop: space.xs,
    overflow: 'hidden',
  },
  dialedFill: { height: 4, borderRadius: 2 },

  source: {
    ...type.caption,
    color: palette.textFaint,
    marginTop: space.md,
    lineHeight: 18,
  },

  rule: { marginVertical: space.md },
  footRow: { flexDirection: 'row' },
  footCell: { flex: 1, gap: space.xs },
  footCellR: { alignItems: 'flex-end', paddingLeft: space.md },
  footVals: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  footValue: { ...type.valueSm, color: palette.text },
  footDelta: { ...type.labelSm },
  caveat: {
    ...type.labelSm,
    color: palette.textGhost,
    marginTop: space.md,
    textTransform: 'none',
    letterSpacing: 0,
    lineHeight: 14,
  },
});
