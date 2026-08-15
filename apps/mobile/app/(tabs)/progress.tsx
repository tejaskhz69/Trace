/**
 * Progress: the weekly verdict in full, plus the weight trend.
 *
 * The trend chart shows RAW weigh-ins faintly and the TREND line boldly. That
 * one design choice prevents most "I gained 1.5 kg overnight" churn — the
 * spike is visible, but it's visibly noise.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { Button, Card, Skeleton } from '../../src/components/ui';
import { VerdictCard } from '../../src/components/VerdictCard';
import { useToday } from '../../src/state/useToday';
import { api, request } from '../../src/lib/api';
import { palette, radius, space, type } from '../../src/theme';

interface TrendPoint {
  date: string;
  raw_kg: number | null;
  trend_kg: number;
}

export default function ProgressScreen() {
  const { verdict, load, refreshing, refresh } = useToday();
  const [trend, setTrend] = useState<TrendPoint[] | null>(null);

  const loadTrend = useCallback(() => {
    api
      .weightTrend(90)
      .then((t) => setTrend(t as TrendPoint[]))
      .catch(() => setTrend([]));
  }, []);

  useEffect(() => {
    load();
    loadTrend();
  }, [load, loadTrend]);

  async function acceptTarget() {
    if (!verdict) return;
    await request(`/api/adjudication/${verdict.id}/accept?accepted=true`, {
      method: 'POST',
    }).catch(() => undefined);
    await refresh();
  }

  return (
    <SafeAreaView style={styles.flex} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              refresh();
              loadTrend();
            }}
            tintColor={palette.textMuted}
          />
        }
      >
        <Text style={styles.title}>Progress</Text>

        {verdict ? (
          <Animated.View entering={FadeInDown.duration(240)}>
            <VerdictCard verdict={verdict} onAccept={acceptTarget} />
          </Animated.View>
        ) : (
          <Card style={styles.pending}>
            <Text style={styles.pendingTitle}>Your first verdict is coming</Text>
            <Text style={styles.pendingBody}>
              I need about 8 workouts and 14 weigh-ins over three weeks before I
              can tell muscle from fat. Keep logging — this unlocks on its own.
            </Text>
          </Card>
        )}

        <Text style={styles.sectionTitle}>Weight</Text>
        {trend === null ? (
          <Skeleton height={180} />
        ) : trend.length < 2 ? (
          <Card>
            <Text style={styles.pendingBody}>
              Log your weight each morning. Daily numbers bounce around with
              salt and water — the trend line is the signal.
            </Text>
          </Card>
        ) : (
          <Card>
            <TrendChart points={trend} />
          </Card>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

/**
 * Lightweight SVG line chart. Deliberately dependency-free: a charting library
 * for two polylines is 300kB of bundle for no benefit.
 */
function TrendChart({ points }: { points: TrendPoint[] }) {
  const W = 300;
  const H = 160;
  const PAD = 12;

  const { trendPath, rawDots, min, max, latest, change } = useMemo(() => {
    const values = points.flatMap((p) =>
      p.raw_kg != null ? [p.trend_kg, p.raw_kg] : [p.trend_kg],
    );
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const span = Math.max(hi - lo, 0.5);

    const x = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
    const y = (v: number) => H - PAD - ((v - lo) / span) * (H - PAD * 2);

    const path = points
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.trend_kg).toFixed(1)}`)
      .join(' ');

    const dots = points
      .map((p, i) => (p.raw_kg != null ? { cx: x(i), cy: y(p.raw_kg) } : null))
      .filter(Boolean) as Array<{ cx: number; cy: number }>;

    const first = points[0].trend_kg;
    const last = points[points.length - 1].trend_kg;

    return {
      trendPath: path,
      rawDots: dots,
      min: lo,
      max: hi,
      latest: last,
      change: last - first,
    };
  }, [points]);

  return (
    <View style={{ gap: space.md }}>
      <View style={styles.trendHeader}>
        <View>
          <Text style={styles.trendValue}>{latest.toFixed(1)} kg</Text>
          <Text style={styles.trendLabel}>trend weight</Text>
        </View>
        <Text
          style={[
            styles.trendChange,
            { color: change >= 0 ? palette.caution : palette.good },
          ]}
        >
          {change >= 0 ? '+' : ''}
          {change.toFixed(1)} kg
        </Text>
      </View>

      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
        {/* Raw weigh-ins: faint. Visible, but clearly not the signal. */}
        {rawDots.map((d, i) => (
          <Circle key={i} cx={d.cx} cy={d.cy} r={1.8} fill={palette.textFaint} opacity={0.5} />
        ))}
        {/* Trend: bold. This is what the user should read. */}
        <Path
          d={trendPath}
          stroke={palette.primary}
          strokeWidth={2.5}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>

      <View style={styles.trendFooter}>
        <Text style={styles.trendAxis}>{min.toFixed(1)}</Text>
        <Text style={styles.trendNote}>
          Faint dots are daily weigh-ins. The line is what matters.
        </Text>
        <Text style={styles.trendAxis}>{max.toFixed(1)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.bg },
  scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xxl },
  title: { ...type.title, color: palette.text },
  sectionTitle: { ...type.heading, color: palette.text },

  pending: { gap: space.sm },
  pendingTitle: { ...type.heading, color: palette.text },
  pendingBody: { ...type.body, color: palette.textMuted, lineHeight: 22 },

  trendHeader: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
  },
  trendValue: { ...type.title, color: palette.text },
  trendLabel: { ...type.micro, color: palette.textFaint },
  trendChange: { ...type.bodyStrong },

  trendFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  trendAxis: { ...type.micro, color: palette.textFaint },
  trendNote: { ...type.micro, color: palette.textFaint, flex: 1, textAlign: 'center' },
});
