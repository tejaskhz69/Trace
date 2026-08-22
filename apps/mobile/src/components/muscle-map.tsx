/**
 * The body map — which muscles got trained, and how hard.
 *
 * WHY A MAP AND NOT JUST A LIST
 * A list of nine numbers is read one row at a time. A body shaded by volume
 * is read in one glance, and the thing you notice first is the part that is
 * NOT shaded — which is exactly the finding worth surfacing. Most people
 * under-train their back and over-train their arms and have no idea, because
 * a tally of sets never made the imbalance visible.
 *
 * WHAT THE SHADING MEANS
 * Opacity tracks `intensity`, which the API computes as sets ÷ the productive
 * ceiling for that muscle. It saturates at the ceiling, NOT at the user's own
 * biggest number — shading relative to your best week would make a light week
 * look identical to a heavy one, and the map would say nothing.
 *
 * A muscle past its productive ceiling is drawn in `warn`, not in a brighter
 * accent. More is not better up there, and the colour should not congratulate
 * someone for junk volume.
 *
 * GEOMETRY
 * Deliberately simplified anatomy: rounded slabs, not a medical illustration.
 * The instrument language is line-work and hairlines, and a photorealistic
 * écorché would look like it came from a different app. Regions are grouped to
 * match the catalogue's nine muscle groups, because shading a muscle the data
 * cannot distinguish would be inventing precision.
 */

import React, { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Ellipse, G, Path, Rect } from 'react-native-svg';

import { useAccent } from '../state/useTheme';
import { palette, space, type } from '../theme';
import type { MuscleRow } from '../lib/api';

const W = 120;
const H = 260;

/** Untrained muscle. Present, but clearly inert. */
const BASE_FILL = '#161C22';
const OUTLINE = '#232A32';

type Region = { d?: string; rect?: [number, number, number, number, number] };

/**
 * Front view. Each muscle group is one or more slabs. Coordinates are in a
 * 120×260 box; the whole thing scales with `size`.
 */
const FRONT: Record<string, Region[]> = {
  neck: [{ rect: [52, 34, 16, 10, 4] }],
  shoulders: [
    { rect: [30, 46, 16, 18, 8] },
    { rect: [74, 46, 16, 18, 8] },
  ],
  chest: [
    { rect: [44, 48, 15, 22, 6] },
    { rect: [61, 48, 15, 22, 6] },
  ],
  biceps: [
    { rect: [27, 66, 13, 26, 6] },
    { rect: [80, 66, 13, 26, 6] },
  ],
  forearms: [
    { rect: [24, 94, 12, 30, 5] },
    { rect: [84, 94, 12, 30, 5] },
  ],
  core: [
    { rect: [47, 72, 26, 34, 5] },
  ],
  legs: [
    { rect: [42, 116, 17, 52, 8] },
    { rect: [61, 116, 17, 52, 8] },
    { rect: [44, 172, 14, 44, 7] },
    { rect: [62, 172, 14, 44, 7] },
  ],
};

/** Back view. Lats and glutes are the shapes that carry it. */
const BACK: Record<string, Region[]> = {
  neck: [{ rect: [52, 34, 16, 10, 4] }],
  shoulders: [
    { rect: [30, 46, 16, 18, 8] },
    { rect: [74, 46, 16, 18, 8] },
  ],
  back: [
    // Traps + rhomboids, then the lats flaring out.
    { rect: [48, 46, 24, 18, 5] },
    { d: 'M44 64 L76 64 L72 106 L60 112 L48 106 Z' },
  ],
  triceps: [
    { rect: [27, 66, 13, 26, 6] },
    { rect: [80, 66, 13, 26, 6] },
  ],
  forearms: [
    { rect: [24, 94, 12, 30, 5] },
    { rect: [84, 94, 12, 30, 5] },
  ],
  legs: [
    // Glutes, then hamstrings, then calves.
    { rect: [44, 112, 15, 20, 7] },
    { rect: [61, 112, 15, 20, 7] },
    { rect: [43, 134, 16, 40, 7] },
    { rect: [61, 134, 16, 40, 7] },
    { rect: [45, 178, 13, 36, 6] },
    { rect: [62, 178, 13, 36, 6] },
  ],
};

/** The inert silhouette drawn under everything, so the body reads as a body. */
function Silhouette() {
  return (
    <G opacity={0.5}>
      <Ellipse cx={60} cy={22} rx={13} ry={15} fill={BASE_FILL} stroke={OUTLINE} strokeWidth={1} />
      <Path
        d="M40 46 Q60 40 80 46 L86 76 L82 118 L76 118 L74 170 L70 218 L62 218 L60 150 L58 218 L50 218 L46 170 L44 118 L38 118 L34 76 Z"
        fill={BASE_FILL}
        stroke={OUTLINE}
        strokeWidth={1}
      />
      <Path d="M34 62 L26 124 L34 126 L42 66 Z" fill={BASE_FILL} stroke={OUTLINE} strokeWidth={1} />
      <Path d="M86 62 L94 124 L86 126 L78 66 Z" fill={BASE_FILL} stroke={OUTLINE} strokeWidth={1} />
    </G>
  );
}

function Body({
  regions,
  intensity,
  over,
  color,
  size,
}: {
  regions: Record<string, Region[]>;
  intensity: Record<string, number>;
  over: Set<string>;
  color: string;
  size: number;
}) {
  return (
    <Svg width={size} height={(size * H) / W} viewBox={`0 0 ${W} ${H}`}>
      <Silhouette />
      {Object.entries(regions).map(([muscle, shapes]) => {
        const v = intensity[muscle] ?? 0;
        if (v <= 0) return null;
        const fill = over.has(muscle) ? palette.warn : color;
        // Floor the opacity so a trained muscle is always visibly trained;
        // 0.1 intensity rendering at 10% opacity would read as untrained.
        const opacity = 0.28 + Math.min(1, v) * 0.62;
        return (
          <G key={muscle} opacity={opacity}>
            {shapes.map((s, i) =>
              s.rect ? (
                <Rect
                  key={i}
                  x={s.rect[0]}
                  y={s.rect[1]}
                  width={s.rect[2]}
                  height={s.rect[3]}
                  rx={s.rect[4]}
                  fill={fill}
                />
              ) : (
                <Path key={i} d={s.d} fill={fill} />
              ),
            )}
          </G>
        );
      })}
    </Svg>
  );
}

export const MuscleMap = memo(function MuscleMapBase({
  muscles,
  size = 116,
}: {
  muscles: MuscleRow[];
  size?: number;
}) {
  const accent = useAccent();

  const intensity: Record<string, number> = {};
  const over = new Set<string>();
  for (const m of muscles) {
    intensity[m.muscle] = m.intensity;
    if (m.status === 'OVER') over.add(m.muscle);
  }

  return (
    <View>
      <View style={styles.bodies}>
        <Body
          regions={FRONT}
          intensity={intensity}
          over={over}
          color={accent.brand}
          size={size}
        />
        <Body
          regions={BACK}
          intensity={intensity}
          over={over}
          color={accent.brand}
          size={size}
        />
      </View>
      <View style={styles.viewLabels}>
        <Text style={styles.viewLabel}>Front</Text>
        <Text style={styles.viewLabel}>Back</Text>
      </View>
    </View>
  );
});

/**
 * The ranked bars under the map.
 *
 * Every bar is drawn against the SAME scale — the productive ceiling — so bar
 * length is comparable across muscles and a tick marks where the useful range
 * begins. Scaling each bar to its own maximum, which is the obvious
 * implementation, would make 4 sets of chest and 4 sets of neck look
 * identical, and they mean opposite things.
 */
export const MuscleBars = memo(function MuscleBarsBase({
  muscles,
  limit = 6,
}: {
  muscles: MuscleRow[];
  limit?: number;
}) {
  const accent = useAccent();
  const shown = muscles.filter((m) => m.sets > 0).slice(0, limit);

  if (shown.length === 0) {
    return <Text style={styles.empty}>No sets logged in this window.</Text>;
  }

  return (
    <View style={styles.bars}>
      {shown.map((m) => {
        const ceiling = m.productive_max || 1;
        const frac = Math.min(1, m.sets / ceiling);
        const floorAt = m.min_effective / ceiling;
        const tone =
          m.status === 'OVER'
            ? palette.warn
            : m.status === 'UNDER'
              ? palette.textFaint
              : accent.brand;
        return (
          <View key={m.muscle} style={styles.barRow}>
            <Text style={styles.barName}>{m.muscle}</Text>
            <View style={styles.barTrack}>
              <View
                style={[styles.barFill, { width: `${frac * 100}%`, backgroundColor: tone }]}
              />
              {m.min_effective > 0 ? (
                <View style={[styles.barTick, { left: `${floorAt * 100}%` }]} />
              ) : null}
            </View>
            <Text style={[styles.barValue, { color: tone }]}>
              {m.sets % 1 === 0 ? m.sets : m.sets.toFixed(1)}
            </Text>
          </View>
        );
      })}
      <Text style={styles.legend}>
        Bar is sets against the productive range · the notch is where growth
        typically starts
      </Text>
    </View>
  );
});

const styles = StyleSheet.create({
  bodies: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.lg,
  },
  viewLabels: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.xxxl + space.xl,
    marginTop: space.xs,
  },
  viewLabel: { ...type.labelSm, color: palette.textGhost },
  bars: { gap: space.sm, marginTop: space.md },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  barName: {
    ...type.labelSm,
    color: palette.textDim,
    width: 62,
    textTransform: 'capitalize',
  },
  barTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: palette.hairline,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  barFill: { height: 6, borderRadius: 3 },
  barTick: {
    position: 'absolute',
    width: 1,
    height: 10,
    backgroundColor: palette.textGhost,
  },
  barValue: { ...type.valueSm, width: 34, textAlign: 'right' },
  legend: {
    ...type.labelSm,
    color: palette.textGhost,
    marginTop: space.xs,
    lineHeight: 13,
  },
  empty: { ...type.caption, color: palette.textFaint, paddingVertical: space.md },
});
