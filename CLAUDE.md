# Trace

AI nutrition + strength tracker. The product claim: **we tell you whether you're
gaining muscle or fat**, not just whether the scale moved.

## Repo layout

```
apps/mobile/        Expo Router + TypeScript + Reanimated 4
  app/              file-based routes: (auth)/ (tabs)/ scan.tsx scan-review.tsx
  src/theme.ts      ← design tokens. NOTHING hardcodes a colour or duration.
  src/components/   instrument.tsx = the primitive vocabulary
  src/state/        zustand stores
  src/lib/api.ts    API client (auth, tokens, refresh)
  src/lib/health.ts HealthKit + Health Connect adapter

services/api/       FastAPI + SQLModel + Postgres
  app/services/     ← PURE FUNCTIONS. tdee, adjudication, activity, coach,
                      nutrition_validator, preparation. No I/O. Fully tested.
  app/routers/      thin HTTP layer over the services
  app/scripts/      data ingestion (Open Food Facts, USDA, brand seeds)
  tests/            the spec. Run pytest for the current count.
```

## Commands

```bash
# Mobile
cd apps/mobile && npx expo start --clear   # --clear REQUIRED after .env changes
npx tsc --noEmit                            # must be 0 errors
npx jest

# Backend
cd services/api && uvicorn app.main:app --reload
python -m pytest tests/ -q                  # must be green; run it for the count
```

## Non-negotiables

These are product invariants. Breaking one is a bug even if tests pass.

1. **Never add exercise calories to a calorie target.** The adaptive TDEE
   already contains them via the weight trend. Adding HealthKit active energy
   double-counts. See `services/activity.py` for the full argument.
2. **Nutrition estimates carry uncertainty.** Photo scans return low/point/high
   and the UI shows `±`. Never display a single confident number for an
   estimate.
3. **Refusing to answer beats answering wrong.** The adjudication engine
   returns `INSUFFICIENT_DATA` rather than guessing. Keep it that way.
4. **Every user correction is captured.** `POST /recognize/{id}/correct` is the
   most valuable endpoint in the product — it builds the proprietary dataset.
5. **The coach reaches for the cheapest lever first**: sleep → activity →
   adherence → protein → calories. Calories is LAST.
6. **Food data is validated before it's served.** Public nutrition data has a
   ~30% defect rate. `nutrition_validator.py` quarantines bad rows.

## Conventions

**TypeScript / React Native**
- Strict mode. `npx tsc --noEmit` must be clean before any commit.
- All colours, spacing, radii, durations come from `src/theme.ts`. If you find
  yourself typing a hex code or a `duration: 300`, add a token instead.
- Animations run on the **UI thread** via Reanimated shared values. Never
  animate with `setState` — that was the source of the original jank.
- `react-native-reanimated/plugin` must stay **last** in `babel.config.js`.
- Lists use FlashList with rows `memo`'d on primitives.
- Screens render a skeleton first and fetch after
  `InteractionManager.runAfterInteractions`.

**Python / FastAPI**
- Business logic lives in `app/services/` as **pure functions with no I/O**, so
  it can be tested exhaustively. Routers stay thin.
- Type hints on everything. Async endpoints.
- New algorithm behaviour needs a test that would fail without it.

## Design system

The app uses an **instrument panel** visual language — near-black, hairlines,
tabular numerals, one accent. Read `.claude/skills/trace-design-system/SKILL.md`
before touching any UI. Don't invent components; compose the primitives in
`src/components/instrument.tsx`.

## Gotchas that have already bitten us

- **Email case:** iOS auto-capitalises the first character. Normalise on the
  client AND the server, and always set `autoCapitalize="none"`.
- **`EXPO_PUBLIC_*` vars are inlined at BUILD time**, not read at runtime.
  Changing `.env` needs `--clear`; changing it for release needs a new build.
- **`localhost` in a RN app means the phone**, not your laptop.
- **CORS is never the cause of a native RN login failure** — native fetch sends
  no Origin header.
- **HealthKit does not work in Expo Go.** Development build required.
- **`JWT_SECRET` must be set explicitly in production**, or every container
  restart invalidates all tokens.

## Working style

- For anything non-trivial: propose a plan before writing code.
- Prefer editing existing files over creating new ones.
- Tests are the spec — when changing algorithm behaviour, show me the failing
  test first.
- Don't add dependencies without saying why the stdlib/existing deps won't do.
## Usage constraints

- Do not spawn subagents by default.
- Work in the main session for normal coding tasks.
- Use a subagent only for a genuinely independent, parallelizable task.
- Ask before launching multiple agents.
- Do not use expensive design or research agents for small UI changes.
