# Running Trace — VS Code → Railway

Two halves. **Backend goes on Railway** (it's a server). **The mobile app runs on
your machine** and points at Railway. There is nothing to deploy for the app
itself until you ship to the App Store.

---

# Part 1 — Running locally in VS Code

```bash
unzip trace-app.zip && cd trace && code .
```

**Extensions worth installing** (VS Code will likely prompt you):
Python + Pylance, Ruff, ESLint, Prettier, Expo Tools, Thunder Client (or REST
Client) for poking the API.

## 1a. Backend

Open a terminal in VS Code (`Ctrl+``) :

```bash
cd services/api
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --only-binary=:all: -r requirements.txt
```

Tell VS Code to use that interpreter: `Cmd/Ctrl+Shift+P` → **Python: Select
Interpreter** → pick `./services/api/.venv`. Without this, imports show red
squiggles even though the code runs fine.

Start Postgres:

```bash
docker run -d --name trace-db \
  -e POSTGRES_USER=trace -e POSTGRES_PASSWORD=trace -e POSTGRES_DB=trace \
  -p 5432:5432 postgres:16
```

Create your `.env`:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste that value as `JWT_SECRET` in `.env`. **Generate it once and never change
it** — a rotating secret invalidates every token that was ever issued, which
shows up as users being "randomly logged out".

Run it:

```bash
uvicorn app.main:app --reload
```

→ http://localhost:8000/docs — interactive API docs, and you can hit every
endpoint from there.

Seed the food database and run the tests:

```bash
python -m app.scripts.seed_dishes
python -m app.scripts.seed_indian_brands
python -m pytest tests/ -q          # 84 passing
```

## 1b. Mobile

Second terminal (`+` in the VS Code terminal panel — keep the API running):

```bash
cd apps/mobile
npm install
cp .env.example .env
```

Edit `apps/mobile/.env`. **On a simulator**, localhost works. **On a real
phone**, `localhost` means *the phone itself* — you need your machine's LAN IP:

```bash
# Find your IP
ipconfig getifaddr en0        # macOS
hostname -I | awk '{print $1}' # Linux
ipconfig                       # Windows — look for IPv4 Address
```

```bash
EXPO_PUBLIC_API_URL=http://192.168.1.42:8000
```

Start it:

```bash
npx expo start --clear
```

Scan the QR with Expo Go. Then verify before doing anything else:

```bash
npx tsc --noEmit     # 0 errors
npx jest             # 10 passing
```

> **`--clear` is not optional.** `EXPO_PUBLIC_*` variables are inlined into the
> bundle at build time, not read at runtime. Edit `.env` without `--clear` and
> nothing changes, which is maddening to debug.

---

# Part 2 — Deploying the backend to Railway

## 2a. Push to GitHub

```bash
cd trace
git init
git add .
git commit -m "feat: initial Trace app"
gh repo create trace --private --source=. --push
```

(Or create the repo on github.com and `git remote add origin ... && git push -u origin main`.)

`.env` is already gitignored. Confirm before pushing: `git status` should not
list it.

## 2b. Create the service

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Pick your `trace` repo
3. **Settings → Root Directory → `services/api`** ← **do this before the first build**

> **Why this matters.** Railway's Root Directory becomes the Docker *build
> context*. The Dockerfile does `COPY requirements.txt .` and `COPY app ./app`,
> and those paths only exist inside `services/api`. Leave Root Directory at the
> repo root and the build fails with `requirements.txt: not found`. This is the
> single most common monorepo deploy failure.

Railway will detect `Dockerfile` and `railway.json` automatically.

## 2c. Add Postgres

**+ New → Database → Add PostgreSQL.** Railway provisions it and exposes its
variables to the project.

## 2d. Set variables

Your API service → **Variables** → add:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` ← reference, don't paste a literal |
| `JWT_SECRET` | the value you generated (**same one, forever**) |
| `ENV` | `production` |
| `GEMINI_API_KEY` | from aistudio.google.com/apikey (needed for photo scanning) |
| `OFF_USER_AGENT` | `Trace/1.0 (you@yourdomain.com)` |
| `USDA_FDC_API_KEY` | optional — free at fdc.nal.usda.gov/api-key-signup.html |

Use the `${{Postgres.DATABASE_URL}}` reference syntax rather than copying the
connection string. Railway rotates credentials; a pasted literal silently goes
stale.

Three things the code already handles for you, so you don't have to:

- Railway hands you `postgresql://`, but the async driver needs
  `postgresql+asyncpg://`. `config.py` normalises it.
- `?sslmode=require` breaks asyncpg. It's stripped.
- The app **refuses to boot in production without an explicit `JWT_SECRET`** —
  a loud failure instead of a silent one that logs everyone out on every deploy.

## 2e. Generate a domain

**Settings → Networking → Generate Domain** → you get
`https://trace-api-production-xxxx.up.railway.app`.

## 2f. Verify

```bash
APP=https://your-app.up.railway.app

curl -i $APP/health        # {"status":"ok"} — does NOT touch the DB
curl -i $APP/healthz/db    # {"database":"ok"} — does
```

Two separate endpoints on purpose: the Railway healthcheck points at `/health`,
so a slow first DB connection can't kill the container in a restart loop.

Full smoke test:

```bash
curl -s -X POST $APP/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"a-real-password-123"}'

curl -s -X POST $APP/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"a-real-password-123"}'
```

Both should return tokens.

## 2g. Seed production food data

Railway service → **⋮ → Railway CLI** or locally:

```bash
npm i -g @railway/cli
railway login
railway link                    # pick your project
railway run python -m app.scripts.seed_dishes
railway run python -m app.scripts.seed_indian_brands
```

`railway run` executes against your production env vars, so it hits the
production database.

## 2h. Point the app at production

`apps/mobile/.env`:

```bash
EXPO_PUBLIC_API_URL=https://your-app.up.railway.app
```

```bash
npx expo start --clear
```

Then in the app: **triple-tap the TRACE wordmark on the login screen.** It shows
the API URL the build actually resolved to, and whether it's on TLS. If that
isn't your Railway URL, your env var didn't take — and you've just saved
yourself an hour.

---

# When it doesn't work

Read the failure, then jump to the section.

| Symptom | Cause | Fix |
|---|---|---|
| Build fails: `requirements.txt: not found` | Root Directory not set | §2b — set it to `services/api` |
| "Application failed to respond" | Not binding `$PORT`/`0.0.0.0` | Already handled in the Dockerfile — check Deploy Logs for a crash instead |
| `/health` 200 but `/healthz/db` 503 | DB not connected | §2d — use `${{Postgres.DATABASE_URL}}` |
| Container restart loop | Healthcheck hitting a DB route | Confirm healthcheck path is `/health` |
| Login works, then random 401s | `JWT_SECRET` changing | Set it explicitly and never touch it again |
| `Network request failed` on device | Wrong URL, or `http://` to a remote host | §2h — triple-tap the wordmark |
| Correct password rejected | Email case mismatch | Already fixed both sides — see `docs/04` |

**Deploy Logs are the answer to most of these.** Railway → your service →
Deployments → click the latest → *Deploy Logs*. A startup crash appears there
and nowhere else.

`docs/04-fix-expo-railway-login.md` has a ranked diagnostic with a copy-paste
triage script if the login specifically misbehaves.

---

# Costs

- Railway: Hobby is $5/month of usage credit. This API plus Postgres sits
  comfortably inside it at low traffic.
- Gemini API: roughly $0.003 per photo scan with the Flash→Pro routing, on the
  published per-token rates at the time of writing. That is an estimate from
  the rate card, not a measured bill — check your first month against it.
  Free-tier users are capped at 3 scans/day.

---

# Day-to-day loop

```bash
# Terminal 1 — API
cd services/api && source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2 — app
cd apps/mobile && npx expo start

# Terminal 3 — Claude Code
claude
```

Push to `main` and Railway redeploys automatically.

Before every push:

```bash
cd services/api && python -m pytest tests/ -q
cd apps/mobile && npx tsc --noEmit && npx jest
```
