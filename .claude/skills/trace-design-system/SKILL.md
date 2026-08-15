---
name: trace-design-system
description: The Trace "instrument panel" visual language. Read before writing or changing ANY UI in apps/mobile. Covers tokens, primitives, layout rules, and the migration checklist for redesigning a screen.
---

# Trace design system — instrument panel

Reference points: Whoop, Oura, aircraft avionics. **Not** consumer wellness apps.
The premise is that this is measuring equipment and should look like it — every
competitor uses soft rounded cards and pastel rings, so looking like an
instrument is itself differentiation.

## Before you write anything

Read `apps/mobile/src/theme.ts` and `apps/mobile/src/components/instrument.tsx`.
Compose the existing primitives. Do not invent new components unless nothing in
the vocabulary fits — and if that happens, add it to `instrument.tsx` rather
than inline in a screen.

## The seven rules

1. **Near-black, not dark grey.** `palette.void` = `#07090B`. Real contrast
   makes data pop and saves OLED battery on a screen opened ten times a day.
2. **Tabular numerals on every changing number.** Use `type.readout`,
   `type.figure`, `type.value`, `type.valueSm` — they all carry
   `fontVariant: ['tabular-nums']`. Proportional digits visibly jitter as glyph
   widths change. This is the single biggest tell of an amateur data UI.
3. **Hairlines, not shadows.** Use the `<Rule />` component and 1px borders at
   `palette.hairline`. Never `shadowColor` or `elevation`. Shadows imply soft
   physical objects; instruments have edges.
4. **One accent.** `palette.signal` (#3DDC84) means on-track / active / confirm.
   `warn` and `danger` are states, never decoration. If three things are
   highlighted in a view, nothing is.
5. **Uppercase tracked micro-labels.** `type.label` / `type.labelSm`. This is the
   signature of the whole system — it's what reads as "readout" rather than
   "paragraph".
6. **One big number per screen.** `type.readout` (64px) is used exactly once.
   Everything else steps down.
7. **No hardcoded values, ever.** Every colour, space, radius, and duration comes
   from `theme.ts`. If you're typing a hex code or `duration: 300`, add a token.

## The primitives

| Component | Use for |
|---|---|
| `Panel` | A bordered region. Takes `label` and optional `right` for a header row. Not a floating card. |
| `Rule` | The 1px divider. `vertical` for column separators. The primary structural element. |
| `Label` | Uppercase tracked micro-label. |
| `Readout` | The hero number. Counts up on the UI thread via `useAnimatedProps` — React never re-renders during the animation. |
| `Gauge` | Linear progress with tick marks. The instrument alternative to a ring. |
| `Sparkbar` | Compact multi-day bar chart (e.g. 7 days of steps). |
| `StatCell` | Label/value/delta in a gridded row, separated by vertical `Rule`s. |
| `Button` | `primary` / `outline` / `ghost`. 100ms 0.97x press on the UI thread. |
| `Skeleton` | Loading state. Never a spinner. |

## Layout grammar

- Screen padding `space.lg` (16), gap between panels `space.md` (12).
- Inside a panel: header row → `Rule` → body at `space.lg`.
- Stat rows are cells separated by vertical `Rule`s, never gaps alone.
- Masthead: eyebrow label + name on the left, clock + date right-aligned.

## Motion

Every duration comes from `motion`. `press: 100`, `fast: 180`, `base: 240`,
`slow: 320`. Entrances use `FadeInDown.duration(motion.base)` staggered 40-50ms.
Instruments **settle**; use `motion.settle` (zero overshoot) not a bouncy spring.

## Non-negotiable performance rules

- Animate via Reanimated **shared values** only. Never `setState`.
- `React.memo` any component receiving frequently-changing props, compared on
  primitives.
- Screens render a skeleton first and fetch after
  `InteractionManager.runAfterInteractions`.
- Lists use FlashList with rows memo'd.

## Migrating a screen — checklist

1. Read the screen and list every hardcoded value.
2. Replace `Card` → `Panel`, `Divider` → `Rule`, ad-hoc labels → `Label`.
3. Identify the ONE hero number → `Readout`. Everything else steps down.
4. Replace progress rings/bars → `Gauge`. Multi-day data → `Sparkbar`.
5. Convert stat groupings into `StatCell` rows separated by vertical `Rule`s.
6. Delete any legacy token alias usage (`palette.bg`, `palette.textMuted`,
   `palette.primary`, `type.micro`, `type.display`, `type.bodyStrong`) and use
   the real names. These aliases exist only so the redesign can land screen by
   screen; the goal is to delete them from `theme.ts` entirely.
7. Run `npx tsc --noEmit` — must be 0 errors.
8. Run the `design-reviewer` agent on the changed file.

## Screens already migrated

`app/(auth)/login.tsx`, `app/(tabs)/index.tsx`.

## Screens still on the legacy vocabulary

`app/(auth)/signup.tsx`, `app/(tabs)/log.tsx`, `app/(tabs)/train.tsx`,
`app/(tabs)/progress.tsx`, `app/scan.tsx`, `app/scan-review.tsx`,
`src/components/VerdictCard.tsx`, `src/components/ui.tsx`.

Migrate one at a time. Typecheck between each.
