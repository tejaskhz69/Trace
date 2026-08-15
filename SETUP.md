# Open this in VS Code

> Deploying to Railway? See **DEPLOY.md** — it covers the full path from
> `git init` to a live URL, including the Root Directory setting that trips up
> every monorepo deploy.

```bash
unzip trace-app.zip && cd trace && code .
```

## 1. Backend (~2 min)

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
python -m pip install --only-binary=:all: -r requirements.txt
cp .env.example .env
```

Generate a JWT secret and paste it into `.env` as `JWT_SECRET` — set it once and
never change it, or every container restart logs all your users out:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start Postgres and the API:

```bash
docker run -d --name trace-db -e POSTGRES_USER=trace -e POSTGRES_PASSWORD=trace \
  -e POSTGRES_DB=trace -p 5432:5432 postgres:16

uvicorn app.main:app --reload
```

→ http://localhost:8000/docs

Seed food data:

```bash
python -m app.scripts.seed_dishes            # ~100 world dishes
python -m app.scripts.seed_indian_brands     # 44 verified brand products
```

Run the tests (should be 84 passing):

```bash
python -m pytest tests/ -q
```

## 2. Mobile (~3 min)

```bash
cd apps/mobile
npm install
cp .env.example .env      # set EXPO_PUBLIC_API_URL
npx expo start --clear    # --clear is REQUIRED after any .env change
```

Checks:

```bash
npx tsc --noEmit    # 0 errors
npx jest            # 10 passing
```

**On a physical device in dev**, `localhost` means *the phone*. Use your
machine's LAN IP: `EXPO_PUBLIC_API_URL=http://192.168.1.x:8000`

**Apple Health needs a development build** — it will not work in Expo Go:

```bash
npx expo run:ios
```

## 3. Claude Code

From the repo root:

```bash
claude
```

It reads `CLAUDE.md` automatically. Already set up for you:

- **`CLAUDE.md`** — stack, commands, the six product non-negotiables, and every
  gotcha that has already cost us time.
- **`.claude/skills/trace-design-system/`** — the instrument-panel design
  language plus a screen-migration checklist. Claude reads this before touching
  UI.
- **`.claude/agents/design-reviewer.md`** — audits UI against the design system.
- **`.claude/agents/rn-perf-auditor.md`** — catches the five jank patterns.
- **`.claude/settings.json`** — allowlists the safe commands, denies reads and
  edits on `.env`.

To continue the redesign:

```
Read .claude/skills/trace-design-system/SKILL.md, then migrate
app/(tabs)/log.tsx to the instrument vocabulary. Typecheck when done.
```

Then: `Run the design-reviewer agent on the file you just changed.`

## Where things are

```
CLAUDE.md              ← Claude Code reads this first
.claude/               ← skills, agents, permissions

docs/
  01-competitor-teardown.md      Cal AI, MacroFactor, Hevy, SnapCalorie
  02-product-blueprint.md        features, algorithms, build order, jank fixes
  03-gtm-monetization.md         pricing, paywall, CAC/LTV, ASO
  04-fix-expo-railway-login.md   ← the login bug, ranked by likelihood
  05-food-database.md            ← the Pintola/barcode fix
  06-indian-brand-database.md    MTR/Gits/Aachi + the validator
  07-fitness-coach-and-health.md Apple Health + the coach

services/api/app/services/       ← the real IP. Pure, tested functions.
  tdee.py              adaptive expenditure
  adjudication.py      muscle vs fat verdict
  activity.py          NEAT drift, sleep, weigh-in prompts
  coach.py             cheapest-lever-first coaching
  nutrition_validator.py  quarantines bad food data
  preparation.py       dry mix → cooked food
  vision.py            Claude food recognition

apps/mobile/src/theme.ts               ← design tokens
apps/mobile/src/components/instrument.tsx  ← the primitives
```

## Totals

32 API endpoints · 84 backend tests · 18 mobile source files · 0 type errors · 10 mobile tests
