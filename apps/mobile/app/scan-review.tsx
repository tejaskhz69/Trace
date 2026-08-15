/**
 * Scan review — the screen where Trace's accuracy story becomes visible.
 *
 * Three things happen here that no competitor does:
 *
 *  1. Every item shows a RANGE, not a fake-precise number. "240 kcal ±60"
 *     is honest, and it's why users stop noticing that re-scans drift.
 *  2. Low-confidence items surface ONE clarifying question, almost always
 *     about invisible cooking fat. A tbsp of ghee is ~120 kcal and leaves no
 *     visual trace; one tap resolves more error than a depth sensor.
 *  3. Every edit is posted back to /recognize/{id}/correct. That endpoint
 *     builds the proprietary dataset. If the user edits and we don't capture
 *     it, we've thrown away the most valuable thing in the product.
 *
 * Item rows are their own memoized component (`ScanItemRow`): `setPortion`
 * in useScan.ts only replaces the ONE item that changed, so unaffected items
 * keep the same object reference and React.memo's default shallow prop
 * comparison skips re-rendering every other row on each stepper tap.
 */

import React, { memo, useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  FadeIn,
  FadeInDown,
  LinearTransition,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  Button,
  Label,
  Panel,
  Readout,
  Rule,
  StatCell,
} from '../src/components/instrument';
import { useScan, ScanItem } from '../src/state/useScan';
import { useToday } from '../src/state/useToday';
import { HAIRLINE, motion, palette, radius, space, type } from '../src/theme';

function confidenceColor(c: number): string {
  if (c >= 0.75) return palette.signal;
  if (c >= 0.5) return palette.warn;
  return palette.danger;
}

export default function ScanReviewScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ mealType?: string }>();
  const { result, items, setPortion, answerQuestion, removeItem, commit, submitting } =
    useScan();
  const applyOptimistic = useToday((s) => s.applyOptimisticMeal);

  const totals = useMemo(
    () =>
      items.reduce(
        (acc, it) => ({
          kcal: acc.kcal + it.kcal_point * it.multiplier,
          low: acc.low + it.kcal_low * it.multiplier,
          high: acc.high + it.kcal_high * it.multiplier,
          protein: acc.protein + it.protein_g * it.multiplier,
          carbs: acc.carbs + it.carbs_g * it.multiplier,
          fat: acc.fat + it.fat_g * it.multiplier,
        }),
        { kcal: 0, low: 0, high: 0, protein: 0, carbs: 0, fat: 0 },
      ),
    [items],
  );

  if (!result) {
    return (
      <SafeAreaView style={styles.flex}>
        <View style={styles.center}>
          <Text style={styles.emptyText}>No scan to review.</Text>
          <Button label="Close" variant="outline" onPress={() => router.back()} />
        </View>
      </SafeAreaView>
    );
  }

  const uncertainty = Math.round((totals.high - totals.low) / 2);

  async function onSave() {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    // Update the ring immediately; the server call follows.
    applyOptimistic(totals.kcal, totals.protein, totals.carbs, totals.fat);
    await commit(params.mealType ?? 'snack');
    router.dismissAll();
  }

  return (
    <SafeAreaView style={styles.flex} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.title}>What I found</Text>
          <Label color={confidenceColor(result.overall_confidence)}>
            {Math.round(result.overall_confidence * 100)}% match
          </Label>
        </View>

        {/* Totals, with honest uncertainty */}
        <Animated.View entering={FadeInDown.duration(240)}>
          <Panel padded={false}>
            <View style={styles.totalBody}>
              <View style={styles.totalHeaderRow}>
                <Label color={palette.textGhost}>Total</Label>
                {result.cached ? (
                  <Label color={palette.signal}>Same as last scan</Label>
                ) : null}
              </View>
              <View style={styles.totalReadoutRow}>
                <Readout value={Math.round(totals.kcal)} />
                <Text style={styles.totalUnit}>kcal</Text>
              </View>
              <Text style={styles.totalRange}>± {uncertainty}</Text>
            </View>

            <Rule />

            <View style={styles.statRow}>
              <StatCell
                label="Protein"
                value={Math.round(totals.protein)}
                unit="g"
                color={palette.protein}
              />
              <Rule vertical />
              <StatCell
                label="Carbs"
                value={Math.round(totals.carbs)}
                unit="g"
                color={palette.carbs}
                align="center"
              />
              <Rule vertical />
              <StatCell
                label="Fat"
                value={Math.round(totals.fat)}
                unit="g"
                color={palette.fat}
                align="right"
              />
            </View>
          </Panel>
        </Animated.View>

        {items.map((item, index) => (
          <ScanItemRow
            key={item.key}
            item={item}
            index={index}
            onSetPortion={setPortion}
            onAnswerQuestion={answerQuestion}
            onRemove={removeItem}
          />
        ))}

        {result.hidden_ingredients.length > 0 && (
          <Panel label="Also counted">
            <Text style={styles.hiddenBody}>
              {result.hidden_ingredients.join(' · ')}
            </Text>
            <Text style={styles.hiddenNote}>
              These don&apos;t show up in a photo, so I estimated them. Adjust
              above if I got it wrong.
            </Text>
          </Panel>
        )}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          label="Cancel"
          variant="ghost"
          onPress={() => router.back()}
          style={styles.footerCancel}
        />
        <Button
          label={`Log ${Math.round(totals.kcal)} kcal`}
          onPress={onSave}
          loading={submitting}
          disabled={items.length === 0}
          style={styles.flex}
        />
      </View>
    </SafeAreaView>
  );
}

const ScanItemRow = memo(function ScanItemRowBase({
  item,
  index,
  onSetPortion,
  onAnswerQuestion,
  onRemove,
}: {
  item: ScanItem;
  index: number;
  onSetPortion: (key: string, multiplier: number) => void;
  onAnswerQuestion: (key: string, optionIndex: number) => void;
  onRemove: (key: string) => void;
}) {
  return (
    <Animated.View
      entering={FadeInDown.duration(motion.base).delay(index * 40)}
      layout={LinearTransition.duration(motion.fast)}
    >
      <Panel>
        <View style={styles.itemBody}>
          <View style={styles.itemHeader}>
            <View style={styles.flex}>
              <Text style={styles.itemName}>{item.name}</Text>
              {item.name_local ? (
                <Label color={palette.textGhost}>{item.name_local}</Label>
              ) : null}
            </View>
            <Label color={confidenceColor(item.confidence)}>
              {Math.round(item.confidence * 100)}%
            </Label>
          </View>

          <View style={styles.itemStats}>
            <Text style={styles.itemKcal}>
              {Math.round(item.kcal_point * item.multiplier)} kcal
            </Text>
            <Text style={styles.itemRange}>
              ±{Math.round(((item.kcal_high - item.kcal_low) / 2) * item.multiplier)}
            </Text>
          </View>

          {/* Portion stepper -- the fastest possible correction */}
          <View style={styles.portionRow}>
            <Text style={styles.portionLabel}>
              {(item.portion_count * item.multiplier).toFixed(
                item.portion_count * item.multiplier < 1 ? 1 : 0,
              )}{' '}
              {item.portion_unit}
              <Text style={styles.portionGrams}>
                {'  '}·{'  '}
                {Math.round(item.grams_est * item.multiplier)} g
              </Text>
            </Text>
            <View style={styles.stepper}>
              <StepButton
                glyph="−"
                onPress={() => onSetPortion(item.key, item.multiplier - 0.25)}
              />
              <StepButton
                glyph="+"
                onPress={() => onSetPortion(item.key, item.multiplier + 0.25)}
              />
            </View>
          </View>

          {/* THE ONE QUESTION THAT HALVES THE ERROR */}
          {item.clarifying_question && item.answeredOption == null && (
            <Animated.View entering={FadeIn.duration(motion.fast)} style={styles.question}>
              <Text style={styles.questionText}>
                {item.clarifying_question.text}
              </Text>
              <View style={styles.optionRow}>
                {item.clarifying_question.options.map((opt, i) => (
                  <Pressable
                    key={opt}
                    onPress={() => {
                      Haptics.selectionAsync();
                      onAnswerQuestion(item.key, i);
                    }}
                    style={styles.option}
                    accessibilityRole="button"
                  >
                    <Text style={styles.optionText}>{opt}</Text>
                    <Text style={styles.optionDelta}>
                      {item.clarifying_question!.kcal_deltas[i] >= 0 ? '+' : ''}
                      {Math.round(item.clarifying_question!.kcal_deltas[i])}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </Animated.View>
          )}

          {item.answeredOption != null && item.clarifying_question && (
            <Text style={styles.answered}>
              ✓ {item.clarifying_question.options[item.answeredOption]}
            </Text>
          )}

          <Pressable
            onPress={() => onRemove(item.key)}
            hitSlop={8}
            accessibilityRole="button"
          >
            <Label color={palette.textFaint}>Not in my meal</Label>
          </Pressable>
        </View>
      </Panel>
    </Animated.View>
  );
});

function StepButton({ glyph, onPress }: { glyph: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={() => {
        Haptics.selectionAsync();
        onPress();
      }}
      style={styles.stepButton}
      hitSlop={6}
      accessibilityRole="button"
      accessibilityLabel={glyph === '+' ? 'Increase portion' : 'Decrease portion'}
    >
      <Text style={styles.stepGlyph}>{glyph}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.void },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg },
  scroll: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { ...type.title, color: palette.text },

  totalBody: { padding: space.lg, gap: space.xs, alignItems: 'center' },
  totalHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignSelf: 'stretch',
  },
  totalReadoutRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.sm,
    marginTop: space.sm,
  },
  totalUnit: { ...type.heading, color: palette.textFaint },
  // A number that moves every time the portion stepper is tapped -- tabular
  // figures so the digits don't jitter as their widths change.
  totalRange: { ...type.caption, color: palette.textFaint, fontVariant: ['tabular-nums'] },

  statRow: { flexDirection: 'row', alignItems: 'center', padding: space.lg },

  itemBody: { gap: space.md },
  itemHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  itemName: { ...type.heading, color: palette.text },
  itemStats: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  itemKcal: { ...type.value, color: palette.text },
  itemRange: {
    ...type.caption,
    color: palette.textGhost,
    fontVariant: ['tabular-nums'],
  },

  portionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  portionLabel: {
    ...type.caption,
    color: palette.textDim,
    fontVariant: ['tabular-nums'],
  },
  portionGrams: { color: palette.textFaint, fontVariant: ['tabular-nums'] },
  stepper: { flexDirection: 'row', gap: space.sm },
  stepButton: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: palette.raised,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepGlyph: { ...type.heading, color: palette.text },

  question: {
    backgroundColor: palette.void,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.sm,
  },
  questionText: { ...type.caption, color: palette.text, fontWeight: '600' },
  optionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  option: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    borderWidth: HAIRLINE,
    borderColor: palette.hairline,
    backgroundColor: palette.raised,
    alignItems: 'center',
  },
  optionText: { ...type.caption, color: palette.text },
  optionDelta: {
    ...type.micro,
    color: palette.textGhost,
    fontVariant: ['tabular-nums'],
  },
  answered: { ...type.caption, color: palette.signal },

  hiddenBody: { ...type.caption, color: palette.text },
  hiddenNote: { ...type.micro, color: palette.textGhost, lineHeight: 16 },

  footer: {
    flexDirection: 'row',
    gap: space.md,
    padding: space.lg,
    borderTopWidth: HAIRLINE,
    borderTopColor: palette.hairline,
    backgroundColor: palette.surface,
  },
  footerCancel: { paddingHorizontal: space.lg },
  emptyText: { ...type.body, color: palette.textDim },
});
