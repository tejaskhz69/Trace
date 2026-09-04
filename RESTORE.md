# Restoring this copy on another machine

Copied 2026-09-03 from `Downloads/trace-app_2/trace`. Full git history came
with it — `git log` works, and `ca81911` is the tip.

## What was deliberately left out

`node_modules` (298 MB) and `services/api/.venv` (199 MB) were **not** copied.
This is not to save space. Both bake absolute Windows paths and
platform-specific compiled binaries into themselves, so a copied one is broken
on any other machine — including a different user account on this one. They
have to be rebuilt, which takes about two minutes:

```bash
# backend
cd services/api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

# mobile
cd apps/mobile
npm install
```

Also skipped: `__pycache__`, `.pytest_cache`, `.expo`, `.ruff_cache`, `*.pyc`.
All regenerate on first run.

## Two files in here contain live secrets

```
services/api/.env      GEMINI_API_KEY, JWT_SECRET, DATABASE_URL (with password)
apps/mobile/.env       LAN URL only — no secret
```

`.gitignore` keeps them out of git, so they will **not** travel with a
`git push`. But they are plain files sitting in this folder, so they **will**
travel with a zip, a Drive upload, or a USB copy.

If this folder is going anywhere that other people can read it, delete
`services/api/.env` first and rebuild it from `services/api/.env.example` on
the far side.

## Machine-specific values you will need to change

`apps/mobile/.env` points at `http://192.168.31.114:8002` — the LAN IP of the
laptop this was copied from. On another machine, or after a router reboot, find
the new address with `ipconfig` and update that line.

`EXPO_PUBLIC_*` variables are inlined at **build** time, not read at runtime.
After editing that file you must restart with `npx expo start --clear` or the
old address stays baked in.

## Running it

```bash
# terminal 1 -- backend, 0.0.0.0 so a phone can reach it
cd services/api
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002

# terminal 2 -- app
cd apps/mobile
npx expo start --clear
```

Postgres has to be running and reachable at whatever `DATABASE_URL` says. The
source machine used a local database named `trace` holding 578,773 food rows
and 897 exercises; **that data is not in this copy.** Only the schema travels,
in `services/api/alembic/`. To get a working database:

```bash
cd services/api
.venv/Scripts/alembic upgrade head
```

Then re-run the seed and ingest scripts in `app/scripts/` for the catalogue.

## Two stray files at the top level

`0.4` and `8.1%}` are both zero bytes and untracked — debris from a shell
redirect that lost its quoting. Nothing references them. Safe to delete.

## Where the project stands

See `docs/trace-implementation-baseline.md` for the full picture. The short
version: backend and mobile both work end to end on a LAN, the vision scanner
has never been measured against ground truth, and `eval/photos/` is empty and
waiting for real photographs. `eval/SHOPPING.md` is the list that fills it.
