# Fixing "I can't log in" — Expo app → Railway API

*Work top to bottom. The causes are ordered by how often they're the actual culprit. Steps 1–3 catch about 80% of these.*

---

## First: find out which layer is broken

Before changing anything, determine whether the request is **failing to reach the server** or **reaching it and being rejected**. These have completely different fixes and they look identical in the app.

### Test the server directly from your laptop

```bash
# 1. Is the API alive at all?
curl -i https://YOUR-APP.up.railway.app/health

# 2. Can it reach Postgres?
curl -i https://YOUR-APP.up.railway.app/healthz/db

# 3. Does login work server-side? (use a real account)
curl -i -X POST https://YOUR-APP.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpassword"}'
```

Now read the result:

| What you see | What it means | Go to |
|---|---|---|
| `curl: (6) Could not resolve host` / no response | The service isn't deployed or is crash-looping | **§A** |
| `502` / "Application failed to respond" | Container is up but not listening where Railway expects | **§A** |
| `/health` 200 but `/healthz/db` 503 | API is fine, database isn't connected | **§B** |
| `401 Incorrect email or password` | Server is fine — it's an auth-logic bug | **§C** |
| `422 Unprocessable Entity` | Server is fine — your client is sending the wrong body shape | **§D** |
| `200` with tokens | **The server is fine. The bug is in the app.** | **§E** |

That last row is the most common outcome, and it means you can stop debugging Railway entirely.

---

## §A — The container isn't serving

**A1. You bound to the wrong host or port.**
This is the single most common Railway deploy failure. Railway injects a `PORT` env var and routes to it. If you hardcode `8000`, or bind `127.0.0.1`, the proxy can't reach you.

```python
# WRONG — unreachable on Railway
uvicorn.run(app, host="127.0.0.1", port=8000)

# RIGHT
import os
uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
```

Or in the start command:
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
```

**A2. The healthcheck is killing your container.**
If `healthcheckPath` points at a route that touches the database, a slow first DB connection fails the check and Railway restarts the container — forever. Point it at a route that returns 200 without any I/O. That's why `/health` in this scaffold deliberately does not touch Postgres, and `/healthz/db` is separate.

**A3. Check the deploy logs.** Railway → your service → Deployments → click the latest → *Deploy Logs*. A crash on startup (bad import, missing env var, failed migration) shows here and nowhere else.

---

## §B — The database isn't connected

**B1. The URL scheme is wrong for your driver.**
Railway's Postgres plugin gives you `postgresql://...`. SQLAlchemy's *async* engine needs `postgresql+asyncpg://...`. With the plain scheme you get `InvalidRequestError: The asyncio extension requires an async driver` — but only at runtime, which is why it works locally if your local `.env` happens to have the right scheme.

The `config.py` in this scaffold normalises it automatically. If you're not using that, do it manually:

```python
url = os.environ["DATABASE_URL"]
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
elif url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
```

**B2. `?sslmode=require` breaks asyncpg.** That's a libpq parameter; asyncpg doesn't understand it and raises `TypeError: connect() got an unexpected keyword argument 'sslmode'`. Strip it (the scaffold does).

**B3. You're using the wrong variable.** Reference the plugin variable rather than pasting a value that may rotate:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```
Use the **internal** URL (`postgres.railway.internal`) for service-to-service — it's faster and doesn't count against egress. The public `containers-us-west-*.railway.app` URL is for connecting from your laptop.

**B4. Tables were never created.** If `init_db()` / your migration never ran, login returns a 500 with `relation "users" does not exist` in the logs. Run migrations on deploy, or hit `/healthz/db` and check the logs.

---

## §C — The server rejects a password you know is correct

**C1. Email case mismatch. This is the big one.**
iOS auto-capitalises the first character of a `TextInput` by default. A user who registered on the web as `tejas@gmail.com` types `Tejas@gmail.com` on the phone. Your lookup is case-sensitive. Login fails forever, with a correct password.

Fix on **both** sides:

```tsx
// Client
<TextInput
  autoCapitalize="none"     // <- without this, iOS capitalises
  autoCorrect={false}
  autoComplete="email"
  keyboardType="email-address"
  textContentType="emailAddress"
/>
```
```python
# Server — normalise on register AND login
email = payload.email.strip().lower()
```

If you already have users stored with mixed case, migrate them:
```sql
-- Check for collisions first!
SELECT lower(email), count(*) FROM users GROUP BY 1 HAVING count(*) > 1;
UPDATE users SET email = lower(trim(email));
```

**C2. bcrypt's 72-byte truncation.** bcrypt silently ignores anything past 72 bytes, and some library versions raise instead. If registration and login went through different code paths (or different library versions), hashes won't match. Pre-hash with SHA-256 so the bcrypt input is always 64 bytes — `security.py` in this scaffold does this. Note: changing this on an existing database invalidates all existing passwords, so do it now or plan a reset flow.

**C3. Whitespace.** Mobile keyboards love appending a trailing space, and password managers sometimes paste one. `.strip()` the email; do **not** strip the password (a trailing space could be intentional) — instead reject it at registration so it never gets stored.

---

## §D — The client sends the wrong shape

**D1. JSON vs form-encoded.** Most FastAPI tutorials use `OAuth2PasswordRequestForm`, which requires `application/x-www-form-urlencoded` with a field literally named `username`. If your RN client posts `{"email": ..., "password": ...}` as JSON, you get:

```json
{"detail":[{"type":"missing","loc":["body","username"],"msg":"Field required"}]}
```

A 422 mentioning `username` when you never wrote the word "username" is this bug. The `auth.py` in this scaffold accepts both shapes so it can't bite you.

**D2. You set `Content-Type` manually on a `FormData` upload.** The runtime must set it itself so it can add the multipart boundary. If you set `'Content-Type': 'multipart/form-data'` by hand, the boundary is missing and the server can't parse the body. Delete the header and let fetch handle it. (This breaks photo upload, not login — but it's the same class of bug and you'll hit it next.)

---

## §E — The server is fine, so it's the app

This is where you land most often. Five causes:

**E1. `localhost` in the app means THE PHONE.**
`http://localhost:8000` from a React Native app tries to reach port 8000 *on the phone itself*. It will never reach your laptop, and it will never reach Railway.

- On a **physical device in dev**: use your machine's LAN IP (`http://192.168.1.x:8000`).
- On an **Android emulator**: `http://10.0.2.2:8000` is the host machine.
- In **production**: your Railway URL, always `https://`.

Add this line and read your Metro console:
```ts
console.log('[api] base URL =', API_BASE_URL);
```
If it doesn't print your Railway URL, that's your bug. Nothing else matters until it does.

**E2. `EXPO_PUBLIC_*` vars are baked in at BUILD time.**
This catches almost everyone. Expo inlines them into the bundle when it builds — they are not read at runtime. So:

- Editing `.env` does nothing until you restart with `npx expo start --clear`.
- Changing the URL for a production build requires a **new build**. Updating a Railway variable does not update your shipped app.
- The var **must** be prefixed `EXPO_PUBLIC_` or it won't be inlined at all and will be `undefined` in the app.

```bash
# .env — dev
EXPO_PUBLIC_API_URL=https://your-app.up.railway.app
```
```json
// eas.json — production
{ "build": { "production": { "env": { "EXPO_PUBLIC_API_URL": "https://your-app.up.railway.app" } } } }
```

**E3. Cleartext HTTP is blocked.**
Android (API 28+) and iOS ATS block plain `http://` to non-local hosts. It surfaces as `TypeError: Network request failed` — indistinguishable from the server being down. Railway always gives you HTTPS; make sure your URL uses it. Never disable ATS or add `usesCleartextTraffic` to "fix" this — it's telling you something real.

**E4. A trailing slash mismatch.**
`https://app.railway.app//api/auth/login` (double slash) or a base URL ending in `/` combined with a path starting with `/` produces a 404 that looks like a broken endpoint. Strip trailing slashes from the base URL — the scaffold's `resolveBaseUrl()` does.

**E5. The token is saved but never sent, or never saved.**
`expo-secure-store` has a **~2 KB per-value limit** and is unavailable on web. An oversized JWT fails to store — sometimes silently on certain Android OEMs — so login "succeeds" and the very next authenticated request 401s. Keep JWT payloads minimal (`sub`, `type`, `exp`, `jti` — never the whole user object), and fall back to AsyncStorage if a value is large. The scaffold's `tokens` helper does both.

**Not the problem: CORS.** Native React Native `fetch` sends no `Origin` header and is not subject to CORS at all. If someone tells you to fix CORS to make a device login work, they're guessing. CORS only matters for **Expo Web** in a browser.

---

## The 10-minute triage script

```bash
APP=https://YOUR-APP.up.railway.app

echo "--- health ---";  curl -s -o /dev/null -w "%{http_code}\n" $APP/health
echo "--- db ---";      curl -s $APP/healthz/db
echo "--- register ---"
curl -s -X POST $APP/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"probe+1@example.com","password":"probe-password-123"}' | head -c 300
echo; echo "--- login ---"
curl -s -X POST $APP/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"probe+1@example.com","password":"probe-password-123"}' | head -c 300
echo; echo "--- login, wrong case ---"
curl -s -X POST $APP/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"Probe+1@Example.com","password":"probe-password-123"}' | head -c 300
```

If the last one fails and the one before it succeeds, **§C1 is your bug** — and it's the most likely single cause of what you're seeing.

---

## The one that bites after everything else works

**A rotating `JWT_SECRET`.** If your secret is generated at import time rather than read from an env var, every container restart invalidates every token ever issued. Railway restarts containers on redeploy, on crash, and on plan changes. Symptom: login works, then users are "randomly" logged out, or a token issued 30 seconds ago returns 401.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Set that once in Railway → Variables → `JWT_SECRET`, and never change it. `config.py` in this scaffold refuses to boot in production without it, precisely so this can't happen silently.
