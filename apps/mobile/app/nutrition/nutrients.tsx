/**
 * Every nutrient, in one scannable column.
 *
 * WHY A COLUMN AND NOT A TABLE
 * MacroFactor ships a table. A table is a reference document — you consult it
 * when you already have a question. This is bars against a common 100% tick,
 * which you can SCAN: short and over read the same way at a glance because
 * position on the bar carries the meaning. Colour is a second signal, never
 * the only one.
 *
 * THE TICK IS THE WHOLE DESIGN. Every bar is drawn on the same scale with
 * 100% of target at a fixed x, so a row at 143% visibly overshoots the mark
 * and a row at 22% visibly falls far short of it — without a legend, and
 * without the reader having to remember which colour means which.
 *
 * WHAT MAKES THIS HONEST RATHER THAN IMPRESSIVE
 * `status: "unknown"` rows. Public food data is patchy — Open Food Facts has
 * energy for nearly everything and vitamin K for nearly nothing — so a naive
 * sum reports "Vitamin D: 4%" for someone eating perfectly well. That is a
 * fact about our database, not their diet, and rendering it as a deficiency
 * invites somebody to supplement against an artefact. Those rows render as a
 * dash with the coverage stated.
 *
 * WORTH KNOWING sits ABOVE the list, because twenty-six numbers is a
 * reference table and nobody reads one daily. The server picks the handful
 * actually off and explains the consequence.
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

import { Label, Panel, Plain, Rule, Skeleton } from '../../src/components/instrument';
import { api, type NutrientPanel, type NutrientRow } from '../../src/lib/api';
import { useAccent, useSurfaces } from '../../src/state/useTheme';
import { motion, palette, radius, space, type } from '../../src/theme';

/** Where 100% of target sits on every bar. */
const TICK = 0.62;
/** The most a bar may overshoot, so a 400% row doesn't blow the layout. */
const MAX_FRACTION = 1.55;

export default function NutrientsScreen() {
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [panel, setPanel] = useState<NutrientPanel | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    let alive = true;
    const task = InteractionManager.runAfterInteractions(() => {
      api
        .nutrientPanel()
        .then((p) => alive && setPanel(p))
        .catch(() => alive && setFailed(true));
    });
    return () => {
      alive = false;
      task.cancel();
    };
  }, []);

  useEffect(load, [load]);

  /** Group in the server's order so Macros lead and Vitamins close. */
  const groups = useMemo(() => {
    if (!panel) return [];
    const out: { group: string; rows: NutrientRow[] }[] = [];
    for (const r of panel.rows) {
      const last = out[out.length - 1];
      if (last && last.group === r.group) last.rows.push(r);
      else out.push({ group: r.group, rows: [r] });
    }
    return out;
  }, [panel]);

  const notable = useMemo(
    () =>
      panel
        ? panel.notable
            .map((k) => panel.rows.find((r) => r.key === k))
            .filter((r): r is NutrientRow => Boolean(r))
        : [],
    [panel],
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
        <Label color={palette.textFaint}>
          {panel ? `${panel.known} of ${panel.tracked} known` : 'Nutrients'}
        </Label>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        {failed ? (
          <Plain tone="danger">Couldn&apos;t load today&apos;s nutrients.</Plain>
        ) : !panel ? (
          <>
            <Skeleton height={150} />
            <Skeleton height={320} />
          </>
        ) : (
          <>
            {/* ------------------------------------- worth knowing ------ */}
            {notable.length > 0 ? (
              <Animated.View entering={FadeInDown.duration(motion.base)}>
                <Panel
                  label="Worth knowing"
                  right={
                    <Label color={palette.textFaint}>
                      FROM {panel.tracked} NUTRIENTS
                    </Label>
                  }
                >
                  {notable.map((r, i) => (
                    <View key={r.key}>
                      {i > 0 ? <Rule style={styles.gap} /> : null}
                      <View style={[styles.notableHead, i > 0 && styles.gap]}>
                        <Text style={styles.notableName}>{r.name}</Text>
                        <Text
                          style={[
                            styles.notablePct,
                            { color: statusColor(r.status, accent.brand) },
                          ]}
                        >
                          {r.pct !== null ? `${Math.round(r.pct * 100)}%` : '—'}
                        </Text>
                      </View>
                      {panel.notes[r.key] ? (
                        <Text style={styles.notableNote}>{panel.notes[r.key]}</Text>
                      ) : null}
                    </View>
                  ))}
                </Panel>
              </Animated.View>
            ) : null}

            {/* -------------------------------- sodium vs potassium ----- */}
            {panel.sodium_potassium_ratio !== null ? (
              <Animated.View entering={FadeInDown.duration(motion.base).delay(40)}>
                <Panel
                  label="Sodium vs potassium"
                  right={
                    <Label
                      color={
                        panel.sodium_potassium_ratio <= 1.2
                          ? accent.brand
                          : palette.warn
                      }
                    >
                      {panel.sodium_potassium_ratio.toFixed(1)} : 1
                    </Label>
                  }
                >
                  <Plain
                    tone={panel.sodium_potassium_ratio <= 1.2 ? 'signal' : 'warn'}
                  >
                    {panel.sodium_potassium_note}
                  </Plain>
                </Panel>
              </Animated.View>
            ) : null}

            {/* ------------------------------------- the full panel ----- */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(80)}>
              <Panel
                label={`${panel.tracked} tracked`}
                right={
                  <Label color={palette.textFaint}>TICK = 100% OF TARGET</Label>
                }
              >
                <Text style={styles.headline}>{panel.headline}</Text>
                {groups.map((g) => (
                  <View key={g.group}>
                    <Text style={styles.groupLabel}>{g.group.toUpperCase()}</Text>
                    {g.rows.map((r) => (
                      <NutrientBar key={r.key} row={r} brand={accent.brand} />
                    ))}
                  </View>
                ))}
              </Panel>
            </Animated.View>

            {/* -------------------------------------- the disclosure ---- */}
            <Animated.View entering={FadeInDown.duration(motion.base).delay(120)}>
              <Panel label="Why some rows are blank">
                <Plain>
                  A dash means we don&apos;t have enough data to say — not that
                  you had none. Public food databases carry energy and macros
                  for almost everything and vitamin K for almost nothing, so a
                  row only reports a number once at least half your day&apos;s
                  calories came from foods that actually list it.
                </Plain>
              </Panel>
            </Animated.View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function statusColor(status: string, brand: string): string {
  switch (status) {
    case 'short':
      return palette.seriesAlert;
    case 'low':
      return palette.warn;
    case 'over':
      return palette.info;
    case 'unknown':
      return palette.textGhost;
    default:
      return brand;
  }
}

/**
 * One nutrient.
 *
 * memo'd on primitives: twenty-six of these render at once and none of them
 * should re-render when a sibling changes.
 */
const NutrientBar = React.memo(
  function NutrientBarBase({
    row,
    brand,
  }: {
    row: NutrientRow;
    brand: string;
  }) {
    const unknown = row.status === 'unknown' || row.pct === null;
    // The bar is drawn so TICK on the track always means 100% of target.
    // Every row therefore shares one scale, which is what makes the column
    // scannable rather than twenty-six separate charts.
    const frac = unknown
      ? 0
      : Math.min(MAX_FRACTION, (row.pct as number)) * TICK;
    const color = unknown ? palette.hairlineBright : statusColor(row.status, brand);

    return (
      <View style={styles.nutRow}>
        <Text style={styles.nutName} numberOfLines={1}>
          {row.name}
        </Text>
        <View style={styles.nutTrack}>
          {!unknown ? (
            <View
              style={[
                styles.nutFill,
                { width: `${Math.max(1, frac * 100)}%`, backgroundColor: color },
              ]}
            />
          ) : null}
          {/* The tick. Fixed position, every row. */}
          <View style={[styles.nutTick, { left: `${TICK * 100}%` }]} />
        </View>
        <Text
          style={[
            styles.nutPct,
            { color: unknown ? palette.textGhost : statusColor(row.status, brand) },
          ]}
        >
          {unknown ? '—' : `${Math.round((row.pct as number) * 100)}%`}
        </Text>
      </View>
    );
  },
  (a, b) =>
    a.row.key === b.row.key &&
    a.row.pct === b.row.pct &&
    a.row.status === b.row.status,
);

const styles = StyleSheet.create({
  screen: { flex: 1 },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  body: { padding: space.lg, paddingTop: 0, gap: space.md, paddingBottom: space.xxl },

  gap: { marginTop: space.md },
  headline: { ...type.body, fontSize: 13, color: palette.textDim, lineHeight: 19 },

  notableHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  notableName: { ...type.heading, color: palette.text },
  notablePct: { ...type.value, fontSize: 18 },
  notableNote: {
    ...type.body,
    fontSize: 12.5,
    color: palette.textDim,
    lineHeight: 19,
    marginTop: space.xs,
  },

  groupLabel: {
    ...type.labelSm,
    color: palette.textGhost,
    marginTop: space.lg,
    marginBottom: space.sm,
  },

  nutRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginBottom: 7,
  },
  nutName: { ...type.body, fontSize: 12, color: palette.textDim, width: 78 },
  nutTrack: {
    flex: 1,
    height: 7,
    borderRadius: 4,
    backgroundColor: palette.hairline,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  nutFill: { position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 4 },
  nutTick: {
    position: 'absolute',
    top: -2,
    bottom: -2,
    width: 1.5,
    backgroundColor: palette.hairlineBright,
  },
  nutPct: {
    ...type.valueSm,
    fontSize: 11.5,
    width: 42,
    textAlign: 'right',
  },
});
