/**
 * Food search + log.
 *
 * Pushed from the Nutrition tab rather than being a tab itself: the tab's job
 * is to make the fastest path to logging obvious, and a search UI on it pushed
 * the four entry tiles below the fold. Accepts an optional `q` param so
 * "tap to repeat" on a recent meal lands here pre-filled, and a `barcode`
 * param so a scan lands on the portion picker directly.
 *
 * WHY THIS SCREEN WAS REBUILT
 * It was the last screen still on the legacy `ui.tsx` vocabulary — plain
 * cards, `palette.bg`, ad-hoc steppers — while everything around it had moved
 * to the instrument panel. That mismatch is what "the nutrition tab doesn't
 * look as good" actually was: the tab looked right and the screen behind its
 * primary action did not.
 *
 * THE EMPTY STATE IS THE FEATURE, not a placeholder. An empty search box is a
 * dead end; most logging is repetition, so before a single character is typed
 * this screen already offers the foods you personally eat, then the ones
 * everyone eats. Typing is the fallback path, not the main one.
 *
 * Debounced at 250 ms. Without it, every keystroke fires a request, the server
 * fans out to Open Food Facts on cache misses, and you rate-limit yourself
 * within a week of launch.
 *
 * The "as prepared" affordance lives here too: when a food has a known
 * preparation (rava idli, dosa, upma...), we don't ask for grams of dry mix.
 * Nobody knows that. We ask "how many idlis?" and convert server-side.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { FlashList } from '@shopify/flash-list';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import {
  Button,
  Choice,
  GroupHeader,
  Label,
  Panel,
  Plain,
  Rule,
  SearchField,
  Skeleton,
  Stepper,
} from '../src/components/instrument';
import {
  IconBarcode,
  IconCamera,
  IconSearch,
} from '../src/components/icons';
import { attributionFor } from '../src/lib/attribution';
import {
  QUALITY_LABEL,
  basisLabel,
  isIncomplete,
  qualityStatus,
} from '../src/lib/serving-basis';
import { FoodItem, api, request } from '../src/lib/api';
import { useToday } from '../src/state/useToday';
import { useAccent, useSurfaces } from '../src/state/useTheme';
import { motion, palette, radius, space, type } from '../src/theme';

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

/**
 * The quick-log grid.
 *
 * These are SEARCHES, not categories in the database — tapping one fills the
 * box and runs it. That is deliberate: a curated taxonomy is a maintenance
 * burden that goes stale the moment the catalogue grows, whereas a search
 * term stays correct as long as the food exists. It also teaches the search
 * box by example, which is the actual job of an empty state.
 */
const QUICK: { group: string; terms: string[] }[] = [
  {
    group: 'Everyday',
    terms: ['Rice', 'Roti', 'Dal', 'Eggs', 'Chicken', 'Paneer', 'Curd', 'Milk'],
  },
  {
    group: 'Protein',
    terms: ['Whey', 'Protein bar', 'Greek yogurt', 'Tofu', 'Fish', 'Soya chunks'],
  },
  {
    group: 'Store brands',
    terms: ['Kirkland', 'Great Value', 'Good & Gather', "Trader Joe's", 'Amul', 'Tesco'],
  },
  {
    group: 'Out',
    terms: ['Biryani', 'Dosa', 'Pizza', 'Sandwich', 'Burger', 'Samosa'],
  },
];

export default function FoodSearchScreen() {
  const params = useLocalSearchParams<{
    q?: string;
    barcode?: string;
    /** A FoodItem the scanner already resolved, so we do not look it up twice. */
    prefetched?: string;
  }>();
  const router = useRouter();
  const accent = useAccent();
  const surfaces = useSurfaces();

  const [query, setQuery] = useState(params.q ?? '');
  const [results, setResults] = useState<FoodItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<FoodItem | null>(null);
  const [prepared, setPrepared] = useState<PreparedResult | null>(null);
  const [pieces, setPieces] = useState(1);
  const [servingIndex, setServingIndex] = useState(0);
  const [recent, setRecent] = useState<FoodItem[] | null>(null);
  const [logged, setLogged] = useState<string | null>(null);
  const [logging, setLogging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const applyOptimistic = useToday((s) => s.applyOptimisticMeal);

  useEffect(() => {
    let alive = true;
    api
      .recentFoods()
      .then((r) => alive && setRecent(r))
      .catch(() => alive && setRecent([]));
    return () => {
      alive = false;
    };
  }, []);

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
    setServingIndex(
      Math.max(0, item.serving_sizes.findIndex((s) => s.is_default)),
    );
    setLogged(null);

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

  /**
   * A barcode arrived from the scanner.
   *
   * The scanner has usually already resolved it and hands the food over in
   * `prefetched`, so the common path does no request at all. The lookup below
   * is the fallback for a direct link, a stale param, or a payload that failed
   * to parse — it is not the normal route, and it used to be: this effect
   * re-resolved every scanned code, so each successful scan cost two identical
   * lookups and, on a catalogue miss, two full fan-outs to Open Food Facts.
   */
  const [barcodeMiss, setBarcodeMiss] = useState<string | null>(null);

  useEffect(() => {
    const code = params.barcode;
    if (!code) return;

    // THE SCANNER MAY HAVE ALREADY DONE THIS.
    //
    // scan.tsx resolves the barcode, then navigates here with the code — and
    // this effect resolved it a second time. Every successful scan cost two
    // identical lookups: two local queries, and on a catalogue miss two full
    // fan-outs to Open Food Facts and USDA, with the second one racing the
    // first to write the same row. The scanner now hands the resolved item
    // over in `prefetched`, so the common path costs one lookup and the user
    // sees the portion picker without a second spinner.
    //
    // It is still only a hint: a direct link here, or a stale param, falls
    // through to the request below.
    if (params.prefetched) {
      try {
        const item = JSON.parse(params.prefetched) as FoodItem;
        if (item?.id) {
          select(item);
          return;
        }
      } catch {
        // Malformed param: ignore it and resolve properly.
      }
    }

    let alive = true;
    setSearching(true);
    api
      .resolveBarcode(code)
      .then((res) => {
        if (!alive) return;
        if (res.found && res.item) {
          select(res.item as unknown as FoodItem);
        } else {
          setBarcodeMiss(
            res.message ??
              "We couldn't find that barcode. Search for it by name and it'll be there next time.",
          );
        }
      })
      .catch(
        () =>
          alive &&
          setBarcodeMiss("Couldn't look that barcode up. Check your connection."),
      )
      .finally(() => alive && setSearching(false));
    return () => {
      alive = false;
    };
  }, [params.barcode, select]);

  const serving = useMemo(() => {
    if (!selected) return { name: '100 g', grams: 100 };
    return (
      selected.serving_sizes[servingIndex] ??
      selected.serving_sizes.find((s) => s.is_default) ??
      selected.serving_sizes[0] ?? { name: '100 g', grams: 100 }
    );
  }, [selected, servingIndex]);

  /** What the user is about to log, recomputed as they turn the dials. */
  const totals = useMemo(() => {
    if (!selected) return null;
    if (prepared?.per_piece) {
      const p = prepared.per_piece;
      return {
        kcal: p.kcal * pieces,
        protein: p.protein_g * pieces,
        carbs: p.carbs_g * pieces,
        fat: p.fat_g * pieces,
        grams: (prepared.grams_per_piece ?? 0) * pieces,
      };
    }
    const f = (serving.grams * pieces) / 100;
    return {
      kcal: selected.calories * f,
      protein: selected.protein_g * f,
      carbs: selected.carbs_g * f,
      fat: selected.fat_g * f,
      grams: serving.grams * pieces,
    };
  }, [selected, prepared, pieces, serving]);

  async function logIt() {
    if (!selected || !totals || logging) return;
    setLogging(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

    // The optimistic update goes in first so the ring moves immediately, and
    // is ROLLED BACK on failure. Leaving it applied after a failed write is
    // the worst outcome available here: the user sees their calories go up,
    // believes the meal is logged, and it isn't.
    applyOptimistic(totals.kcal, totals.protein, totals.carbs, totals.fat);

    try {
      if (prepared?.per_piece && prepared.grams_per_piece) {
        await api.logMeal({
          display_name: prepared.display_name,
          grams: prepared.grams_per_piece * pieces,
          serving_label: `${pieces} ${pieces === 1 ? 'piece' : 'pieces'}`,
          meal_type: 'snack',
          calories: totals.kcal,
          protein_g: totals.protein,
          carbs_g: totals.carbs,
          fat_g: totals.fat,
        });
      } else {
        await api.logMeal({
          food_item_id: selected.id,
          grams: serving.grams * pieces,
          serving_label: `${pieces} × ${serving.name}`,
          meal_type: 'snack',
        });
      }
    } catch {
      applyOptimistic(-totals.kcal, -totals.protein, -totals.carbs, -totals.fat);
      setError("Couldn't save that. Check your connection and try again.");
      setLogging(false);
      return;
    }

    setLogging(false);
    setLogged(`${Math.round(totals.kcal)} kcal logged`);
    setSelected(null);
    setPrepared(null);
    setQuery('');
    setResults([]);
    api.recentFoods().then(setRecent).catch(() => undefined);
  }

  const showBrowse = query.trim().length < 2 && !selected;

  return (
    <SafeAreaView
      style={[styles.flex, { backgroundColor: surfaces.void }]}
      edges={['top']}
    >
      {/* ------------------------------------------------------- header */}
      <View style={styles.header}>
        <SearchField
          value={query}
          onChangeText={setQuery}
          placeholder="Search foods, brands, restaurants"
          leading={<IconSearch size={17} color={palette.textFaint} />}
          autoFocus={!params.barcode && !params.q}
        />
        {searching ? (
          <ActivityIndicator
            style={styles.spinner}
            size="small"
            color={palette.textFaint}
          />
        ) : null}
      </View>

      {logged ? (
        <Animated.View entering={FadeIn.duration(motion.fast)} style={styles.padded}>
          <Plain>{logged}. Search again, or go back to see your day.</Plain>
        </Animated.View>
      ) : null}

      {barcodeMiss && !selected ? (
        <View style={styles.padded}>
          <Plain tone="warn">{barcodeMiss}</Plain>
        </View>
      ) : null}

      {/* ------------------------------------------------- portion sheet */}
      {selected ? (
        <ScrollView
          contentContainerStyle={styles.padded}
          keyboardShouldPersistTaps="handled"
        >
          <Animated.View entering={FadeInDown.duration(motion.base)}>
            <Panel
              label={selected.brand ?? 'Food'}
              right={
                selected.is_verified ? (
                  <Label color={accent.brand}>VERIFIED</Label>
                ) : (
                  <Label color={palette.textFaint}>ESTIMATE</Label>
                )
              }
            >
              <Text style={styles.selectedName}>{selected.name}</Text>

              {prepared ? (
                <>
                  {/* THE DIFFERENTIATOR, made visible */}
                  <Plain tone="warn" style={styles.gapV}>
                    {prepared.warning}
                  </Plain>
                  <Label color={palette.textFaint}>
                    How many{' '}
                    {prepared.display_name.toLowerCase().includes('idli')
                      ? 'idlis'
                      : 'pieces'}
                    ?
                  </Label>
                </>
              ) : (
                <>
                  {selected.serving_sizes.length > 1 ? (
                    <>
                      <Label color={palette.textFaint}>Serving</Label>
                      <Choice
                        options={selected.serving_sizes.map((sz, i) => ({
                          value: i,
                          label: sz.name,
                        }))}
                        value={servingIndex}
                        onChange={setServingIndex}
                        columns={2}
                      />
                      <Rule style={styles.gapV} />
                    </>
                  ) : null}
                  <Label color={palette.textFaint}>
                    How many × {serving.name}?
                  </Label>
                </>
              )}

              <Stepper value={pieces} onChange={setPieces} min={1} max={20} />

              <Rule style={styles.gapV} />

              {/* The number they're committing to, and its macros. */}
              <View style={styles.totalRow}>
                <Text style={styles.totalKcal}>
                  {Math.round(totals?.kcal ?? 0)}
                  <Text style={styles.totalUnit}> kcal</Text>
                </Text>
                <Text style={styles.totalGrams}>
                  {Math.round(totals?.grams ?? 0)} g
                </Text>
              </View>

              <View style={styles.macroRow}>
                <Macro label="Protein" value={totals?.protein ?? 0} color={palette.protein} />
                <Macro label="Carbs" value={totals?.carbs ?? 0} color={palette.carbs} />
                <Macro label="Fat" value={totals?.fat ?? 0} color={palette.fat} />
              </View>

              {/* WHICH BASIS THESE NUMBERS ARE ON, and what they are worth.
                  Three bases meet here and share one set of digits: the
                  catalogue stores per 100 g/ml, the packet prints per serving,
                  and the figures above are for the portion the user dialled
                  in. Nothing on screen said which, so a disagreement with the
                  label in their hand was indistinguishable from a units
                  mismatch. Both lines come from `src/lib/serving-basis.ts`,
                  which is pure so every case is testable without a renderer. */}
              <Text style={styles.basis} accessibilityLabel={basisLabel({
                isLiquid: selected.is_liquid,
                portionGrams: totals?.grams,
                servingName: prepared ? null : serving.name,
                servingCount: pieces,
              })}>
                {basisLabel({
                  isLiquid: selected.is_liquid,
                  portionGrams: totals?.grams,
                  servingName: prepared ? null : serving.name,
                  servingCount: pieces,
                })}
              </Text>

              <Text style={styles.basis}>
                {QUALITY_LABEL[
                  qualityStatus({
                    isVerified: selected.is_verified,
                    verificationTier: selected.verification_tier,
                    incomplete: isIncomplete(selected),
                  })
                ]}
              </Text>

              {/* SOURCE, AT THE MOMENT THE NUMBERS ARE READ.
                  The list row carries a three-word tag, which is all a dense
                  row can hold; this is the only place the full sentence fits,
                  and it is where the user is actually looking at the figures
                  being credited. A tag alone names a source without saying
                  under what terms it is used. Rendered only when the server
                  says a third party is owed credit — our own dishes and a
                  user's own foods show nothing rather than an empty notice. */}
              {(() => {
                const attr = attributionFor(selected);
                if (!attr.required || !attr.detail) return null;
                return (
                  <>
                    <Rule style={styles.gapV} />
                    <Text
                      style={styles.attribution}
                      accessibilityLabel={attr.accessibilityLabel ?? undefined}
                    >
                      {attr.detail}
                    </Text>
                  </>
                );
              })()}

              {error ? <Plain tone="danger" style={styles.gapV}>{error}</Plain> : null}

              <Button
                label={logging ? 'Saving…' : 'Log it'}
                onPress={logIt}
                loading={logging}
                style={styles.gapV}
              />
              <Pressable
                onPress={() => setSelected(null)}
                hitSlop={8}
                style={styles.back}
              >
                <Label color={palette.textDim}>Back to results</Label>
              </Pressable>
            </Panel>
          </Animated.View>
        </ScrollView>
      ) : showBrowse ? (
        /* ----------------------------------------------- the empty state */
        <ScrollView
          contentContainerStyle={styles.padded}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.ways}>
            <WayIn
              icon={<IconCamera size={19} color={accent.brand} />}
              label="AI scan"
              onPress={() => router.push('/scan')}
              border={surfaces.hairlineBright}
            />
            <WayIn
              icon={<IconBarcode size={19} color={palette.textDim} />}
              label="Barcode"
              onPress={() =>
                router.push({ pathname: '/scan', params: { mode: 'barcode' } })
              }
              border={surfaces.hairlineBright}
            />
          </View>

          {recent === null ? (
            <Panel label="Yours"><Skeleton height={64} /></Panel>
          ) : recent.length > 0 ? (
            <Panel
              label="Log it again"
              right={<Label color={palette.textFaint}>{recent.length}</Label>}
              padded={false}
            >
              {recent.slice(0, 8).map((f, i) => (
                <FoodRow key={f.id} item={f} onPress={select} first={i === 0} />
              ))}
            </Panel>
          ) : null}

          <Panel label="Start here">
            {QUICK.map((g) => (
              <View key={g.group} style={styles.quickGroup}>
                <GroupHeader
                  label={g.group.toUpperCase()}
                  count={g.terms.length}
                  unit="searches"
                />
                <View style={styles.chips}>
                  {g.terms.map((t) => (
                    <Pressable
                      key={t}
                      onPress={() => {
                        Haptics.selectionAsync();
                        setQuery(t);
                      }}
                      style={[
                        styles.chip,
                        { borderColor: surfaces.hairlineBright },
                      ]}
                      accessibilityRole="button"
                      accessibilityLabel={`Search ${t}`}
                    >
                      <Text style={styles.chipText}>{t}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ))}
          </Panel>
        </ScrollView>
      ) : (
        /* ---------------------------------------------------- results */
        <FlashList
          data={results}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: space.lg }}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item, index }) => (
            <FoodRow item={item} onPress={select} first={index === 0} boxed />
          )}
          ListEmptyComponent={
            query.trim().length >= 2 && !searching ? (
              <Plain tone="warn">
                Nothing found for &ldquo;{query.trim()}&rdquo;. Try a different
                spelling, scan the barcode, or add it manually — it&apos;ll be
                there for everyone next time.
              </Plain>
            ) : null
          }
        />
      )}
    </SafeAreaView>
  );
}

function Macro({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <View style={styles.macroCell}>
      <View style={[styles.macroDot, { backgroundColor: color }]} />
      <Text style={styles.macroValue}>{Math.round(value)}g</Text>
      <Text style={styles.macroLabel}>{label.toUpperCase()}</Text>
    </View>
  );
}

function WayIn({
  icon,
  label,
  onPress,
  border,
}: {
  icon: React.ReactNode;
  label: string;
  onPress: () => void;
  border: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={[styles.wayIn, { borderColor: border }]}
    >
      {icon}
      <Text style={styles.wayInText}>{label}</Text>
    </Pressable>
  );
}

/**
 * One food.
 *
 * memo'd on primitives: the results list re-renders on every keystroke and
 * these rows must not re-render with it.
 */
const FoodRow = React.memo(
  function FoodRowBase({
    item,
    onPress,
    first,
    boxed,
  }: {
    item: FoodItem;
    onPress: (i: FoodItem) => void;
    first?: boolean;
    /** Standalone row in a list, rather than stacked inside a Panel. */
    boxed?: boolean;
  }) {
    const accent = useAccent();
    const def =
      item.serving_sizes.find((s) => s.is_default) ?? item.serving_sizes[0];
    const grams = def?.grams ?? 100;
    const kcal = Math.round((item.calories * grams) / 100);
    const protein = Math.round((item.protein_g * grams) / 100);
    const attr = attributionFor(item);

    // ONE LABEL FOR THE WHOLE ROW.
    //
    // The row is a Pressable, so it is a single accessibility element and the
    // Text children inside it are never focused individually -- an
    // accessibilityLabel on the attribution tag alone was therefore read by
    // nobody. Everything a sighted user can see in this row has to be in this
    // string, including the source, spelled out rather than abbreviated:
    // "OPEN FOOD FACTS" as a tag is a visual shorthand, not something a
    // screen reader should be left to pronounce on its own.
    const spoken = [
      item.brand ? `${item.brand}, ${item.name}` : item.name,
      `${kcal} calories per ${def?.name ?? '100 g'}`,
      `${protein} grams protein`,
      item.is_verified ? 'Verified' : null,
      item.matched_via === 'alias' && item.matched_alias
        ? `Matched on ${item.matched_alias}`
        : null,
      attr.accessibilityLabel,
    ]
      .filter(Boolean)
      .join('. ');

    return (
      <>
        {!first && !boxed ? <Rule /> : null}
        <Pressable
          onPress={() => onPress(item)}
          accessibilityRole="button"
          accessibilityLabel={spoken}
          style={[styles.row, boxed && styles.rowBoxed]}
        >
          <View style={styles.rowMid}>
            <Text style={styles.rowName} numberOfLines={1}>
              {item.brand ? `${item.brand} · ` : ''}
              {item.name}
            </Text>
            <Text style={styles.rowMeta} numberOfLines={1}>
              {def?.name ?? '100 g'} · {protein} g protein
              {item.barcode ? ' · BARCODE' : ''}
            </Text>
            {/* Why this row matched, when it was not the name the user typed.
                Without it, searching 'dosai' and getting 'Plain dosa' looks
                like a mistake rather than a working synonym. */}
            {item.matched_via === 'alias' && item.matched_alias ? (
              <Text style={styles.rowMeta} numberOfLines={1}>
                matched “{item.matched_alias}”
              </Text>
            ) : null}
          </View>
          <View style={styles.rowRight}>
            <Text style={styles.rowKcal}>
              {kcal}
              <Text style={styles.rowUnit}> kcal</Text>
            </Text>
            {/* Data provenance, visible. Verified rows earn a mark. */}
            {item.is_verified ? (
              <Text style={[styles.rowTag, { color: accent.brand }]}>
                VERIFIED
              </Text>
            ) : null}
            {/* Per-row attribution. Curated and user rows return required
                === false and render nothing, so our own dishes are never
                labelled as somebody else's data.

                `numberOfLines={1}` bounds a long source name to the row
                instead of reflowing it; the unabbreviated wording is in the
                row's accessibilityLabel and the full sentence is on the
                detail sheet, so nothing is lost by truncating here.
                `importantForAccessibility="no"` because the parent Pressable
                already speaks this — without it VoiceOver reads the tag
                twice on platforms that flatten the subtree. */}
            {attr.required && attr.tag ? (
              <Text
                style={styles.rowTag}
                numberOfLines={1}
                importantForAccessibility="no"
              >
                {attr.tag}
              </Text>
            ) : null}
          </View>
        </Pressable>
      </>
    );
  },
  (a, b) => a.item.id === b.item.id && a.first === b.first,
);

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: { padding: space.lg, justifyContent: 'center' },
  spinner: { position: 'absolute', right: space.xl + space.sm },
  padded: { padding: space.lg, paddingTop: 0, gap: space.md },
  gapV: { marginTop: space.md },

  ways: { flexDirection: 'row', gap: space.md },
  wayIn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.md,
    paddingVertical: space.md,
  },
  wayInText: { ...type.labelSm, color: palette.text },

  quickGroup: { marginTop: space.md, gap: space.xs },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  chipText: { ...type.body, fontSize: 13.5, color: palette.textDim },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  rowBoxed: {
    backgroundColor: palette.surface,
    borderRadius: radius.md,
    marginBottom: 1,
    paddingHorizontal: space.md,
  },
  rowMid: { flex: 1, gap: 2 },
  rowName: { ...type.heading, color: palette.text },
  rowMeta: { ...type.labelSm, color: palette.textFaint },
  rowRight: { alignItems: 'flex-end', gap: 2 },
  rowKcal: { ...type.valueSm, fontSize: 17, color: palette.text },
  rowUnit: { ...type.labelSm, color: palette.textDim },
  /* An explicit colour, because there is no global default text colour in
     this app: a Text with none renders in React Native's built-in black, and
     on `palette.void` (#07090B) that is invisible. The VERIFIED tag overrode
     it and looked fine; the attribution tag did not, so the per-row credit
     was in the tree, passing its tests, and unreadable on the screen.
     `textDim` rather than `textFaint` — 6.6:1 against the panel instead of
     3.4:1, and a licence notice is the last thing that should be squinted at. */
  rowTag: { ...type.labelSm, color: palette.textDim },

  selectedName: { ...type.title, color: palette.text },

  /* Attribution is a legal notice, not a data readout: sentence case at
     caption size, quiet but not faint, above the primary action so it is on
     screen without competing with it. `textDim` clears 4.5:1 against the
     panel; `textFaint` does not, and a notice nobody can read is not a
     notice. */
  /* The basis line and the data-quality line: tracked micro-labels, dimmest
     step that still clears contrast, sitting directly under the numbers they
     qualify. */
  basis: { ...type.labelSm, color: palette.textDim, marginTop: space.sm },
  attribution: {
    ...type.caption,
    color: palette.textDim,
    marginTop: space.md,
  },

  totalRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
  },
  totalKcal: { ...type.figure, color: palette.text },
  totalUnit: { ...type.labelSm, color: palette.textDim },
  totalGrams: { ...type.valueSm, color: palette.textFaint },

  macroRow: { flexDirection: 'row', marginTop: space.md },
  macroCell: { flex: 1, gap: 3 },
  macroDot: { width: 16, height: 2, borderRadius: 1 },
  macroValue: { ...type.valueSm, fontSize: 16, color: palette.text },
  macroLabel: { ...type.labelSm, color: palette.textFaint },

  back: { alignItems: 'center', paddingVertical: space.sm },
});
