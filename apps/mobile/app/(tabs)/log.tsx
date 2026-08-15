/**
 * Food search + log.
 *
 * Debounced at 250ms. Without it, every keystroke fires a request, the server
 * fans out to Open Food Facts on cache misses, and you rate-limit yourself
 * within a week of launch.
 *
 * The "as prepared" affordance lives here too: when a food has a known
 * preparation (rava idli, dosa, upma...), we don't ask for grams of dry mix.
 * Nobody knows that. We ask "how many idlis?" and convert server-side.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { FlashList } from '@shopify/flash-list';
import Animated, { FadeIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { Button, Card } from '../../src/components/ui';
import { FoodItem, api, request } from '../../src/lib/api';
import { useToday } from '../../src/state/useToday';
import { palette, radius, space, type } from '../../src/theme';

interface PreparedResult {
  display_name: string;
  prepared_weight_g: number;
  pieces: number | null;
  grams_per_piece: number | null;
  per_piece: { kcal: number; protein_g: number; carbs_g: number; fat_g: number } | null;
  dilution_factor: number;
  warning: string;
  notes: string[];
}

export default function LogScreen() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FoodItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<FoodItem | null>(null);
  const [prepared, setPrepared] = useState<PreparedResult | null>(null);
  const [pieces, setPieces] = useState(1);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const applyOptimistic = useToday((s) => s.applyOptimisticMeal);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    if (query.trim().length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    debounce.current = setTimeout(async () => {
      try {
        const res = await api.searchFoods(query.trim());
        setResults(res.results);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [query]);

  const select = useCallback(async (item: FoodItem) => {
    Haptics.selectionAsync();
    setSelected(item);
    setPrepared(null);
    setPieces(1);

    // Does this food have a known preparation? If so, log by pieces.
    const prepKey = (item as unknown as { names_i18n?: { preparation_key?: string } })
      .names_i18n?.preparation_key;
    if (!prepKey) return;

    try {
      const res = await request<PreparedResult>('/api/preparations/convert', {
        method: 'POST',
        body: { food_item_id: item.id },
      });
      setPrepared(res);
      setPieces(1);
    } catch {
      setPrepared(null);
    }
  }, []);

  async function logIt() {
    if (!selected) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

    if (prepared?.per_piece && prepared.grams_per_piece) {
      const p = prepared.per_piece;
      applyOptimistic(
        p.kcal * pieces,
        p.protein_g * pieces,
        p.carbs_g * pieces,
        p.fat_g * pieces,
      );
      await api.logMeal({
        display_name: prepared.display_name,
        grams: prepared.grams_per_piece * pieces,
        serving_label: `${pieces} ${pieces === 1 ? 'piece' : 'pieces'}`,
        meal_type: 'snack',
        calories: p.kcal * pieces,
        protein_g: p.protein_g * pieces,
        carbs_g: p.carbs_g * pieces,
        fat_g: p.fat_g * pieces,
      });
    } else {
      const serving =
        selected.serving_sizes.find((s) => s.is_default) ??
        selected.serving_sizes[0] ?? { grams: 100, name: '100 g' };
      const f = (serving.grams * pieces) / 100;
      applyOptimistic(
        selected.calories * f,
        selected.protein_g * f,
        selected.carbs_g * f,
        selected.fat_g * f,
      );
      await api.logMeal({
        food_item_id: selected.id,
        grams: serving.grams * pieces,
        serving_label: `${pieces} × ${serving.name}`,
        meal_type: 'snack',
      });
    }

    setSelected(null);
    setPrepared(null);
    setQuery('');
    setResults([]);
  }

  return (
    <SafeAreaView style={styles.flex} edges={['top']}>
      <View style={styles.header}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search foods, brands, barcodes…"
          placeholderTextColor={palette.textFaint}
          style={styles.search}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
          accessibilityLabel="Search foods"
        />
        {searching && (
          <ActivityIndicator style={styles.spinner} color={palette.textFaint} />
        )}
      </View>

      {selected ? (
        <Animated.View entering={FadeIn.duration(200)} style={styles.padded}>
          <Card style={{ gap: space.md }}>
            <Pressable onPress={() => setSelected(null)} hitSlop={8}>
              <Text style={styles.back}>← Back to results</Text>
            </Pressable>

            <Text style={styles.selectedName}>
              {selected.brand ? `${selected.brand} ` : ''}
              {selected.name}
            </Text>

            {prepared ? (
              <>
                {/* THE DIFFERENTIATOR, made visible */}
                <View style={styles.warningBox}>
                  <Text style={styles.warningText}>{prepared.warning}</Text>
                </View>

                <Text style={styles.prepLabel}>
                  How many {prepared.display_name.toLowerCase().includes('idli')
                    ? 'idlis'
                    : 'pieces'}?
                </Text>
                <View style={styles.stepperRow}>
                  <Pressable
                    onPress={() => setPieces((p) => Math.max(1, p - 1))}
                    style={styles.stepButton}
                    hitSlop={8}
                  >
                    <Text style={styles.stepGlyph}>−</Text>
                  </Pressable>
                  <Text style={styles.pieceCount}>{pieces}</Text>
                  <Pressable
                    onPress={() => setPieces((p) => p + 1)}
                    style={styles.stepButton}
                    hitSlop={8}
                  >
                    <Text style={styles.stepGlyph}>＋</Text>
                  </Pressable>
                </View>

                {prepared.per_piece && (
                  <Text style={styles.prepTotal}>
                    {Math.round(prepared.per_piece.kcal * pieces)} kcal ·{' '}
                    {Math.round(prepared.per_piece.protein_g * pieces)}g protein
                    {prepared.grams_per_piece
                      ? ` · ${Math.round(prepared.grams_per_piece * pieces)} g`
                      : ''}
                  </Text>
                )}
              </>
            ) : (
              <>
                <Text style={styles.prepLabel}>Servings</Text>
                <View style={styles.stepperRow}>
                  <Pressable
                    onPress={() => setPieces((p) => Math.max(1, p - 1))}
                    style={styles.stepButton}
                    hitSlop={8}
                  >
                    <Text style={styles.stepGlyph}>−</Text>
                  </Pressable>
                  <Text style={styles.pieceCount}>{pieces}</Text>
                  <Pressable
                    onPress={() => setPieces((p) => p + 1)}
                    style={styles.stepButton}
                    hitSlop={8}
                  >
                    <Text style={styles.stepGlyph}>＋</Text>
                  </Pressable>
                </View>
                <Text style={styles.prepTotal}>
                  {Math.round(
                    (selected.calories *
                      ((selected.serving_sizes.find((s) => s.is_default)?.grams ?? 100) *
                        pieces)) /
                      100,
                  )}{' '}
                  kcal
                </Text>
              </>
            )}

            <Button label="Log it" onPress={logIt} />
          </Card>
        </Animated.View>
      ) : (
        <FlashList
          data={results}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: space.lg }}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item }) => <FoodRow item={item} onPress={select} />}
          ListEmptyComponent={
            query.length >= 2 && !searching ? (
              <Card>
                <Text style={styles.emptyText}>
                  Nothing found. Try a different spelling, scan the barcode, or
                  add it manually — it&apos;ll be there for everyone next time.
                </Text>
              </Card>
            ) : null
          }
        />
      )}
    </SafeAreaView>
  );
}

function FoodRow({
  item,
  onPress,
}: {
  item: FoodItem;
  onPress: (i: FoodItem) => void;
}) {
  return (
    <Pressable onPress={() => onPress(item)} style={styles.row} accessibilityRole="button">
      <View style={styles.flex}>
        <Text style={styles.rowName} numberOfLines={1}>
          {item.brand ? `${item.brand} · ` : ''}
          {item.name}
        </Text>
        <Text style={styles.rowMeta}>
          {Math.round(item.calories)} kcal / 100 g · {Math.round(item.protein_g)}g protein
        </Text>
      </View>
      {/* Data provenance, visible. Verified rows earn a mark. */}
      {item.is_verified && <Text style={styles.verified}>✓</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: palette.bg },
  padded: { padding: space.lg },
  header: { padding: space.lg, justifyContent: 'center' },
  search: {
    height: 48,
    borderRadius: radius.md,
    backgroundColor: palette.surface,
    borderWidth: 1,
    borderColor: palette.border,
    paddingHorizontal: space.lg,
    color: palette.text,
    ...type.body,
  },
  spinner: { position: 'absolute', right: space.xl + space.sm },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: palette.border,
    gap: space.md,
  },
  rowName: { ...type.bodyStrong, color: palette.text },
  rowMeta: { ...type.micro, color: palette.textFaint, marginTop: 2 },
  verified: { color: palette.primary, fontSize: 14 },

  back: { ...type.micro, color: palette.textMuted },
  selectedName: { ...type.heading, color: palette.text },

  warningBox: {
    backgroundColor: palette.primarySoft,
    borderRadius: radius.md,
    padding: space.md,
  },
  warningText: { ...type.caption, color: palette.primary, lineHeight: 19 },

  prepLabel: { ...type.micro, color: palette.textMuted, textTransform: 'uppercase' },
  stepperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xl,
  },
  stepButton: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
    backgroundColor: palette.surfaceRaised,
    borderWidth: 1,
    borderColor: palette.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepGlyph: { ...type.title, color: palette.text },
  pieceCount: { ...type.display, color: palette.text, minWidth: 64, textAlign: 'center' },
  prepTotal: { ...type.body, color: palette.textMuted, textAlign: 'center' },

  emptyText: { ...type.body, color: palette.textMuted, lineHeight: 22 },
});
