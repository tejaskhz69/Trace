# Google & Apple sign-in — what's built and what you still have to create

The **entire flow is implemented and tested**. What it cannot ship without is
a set of client IDs, because those are issued to *you* by Google and Apple and
identify your app specifically. Until you paste them in, the buttons are hidden
on purpose — `/api/auth/providers` reports an empty list and the login screen
falls back to email and password.

That is a deliberate design choice: a button that opens a browser, authorises,
and then fails the exchange strands the user *outside* the app with no way
back. Not offering the button is a better failure.

---

## What already works, with no credentials

- `POST /api/auth/social` — verifies a Google/Apple identity token and returns
  a Trace session, mirroring `/api/auth/login`.
- `GET /api/auth/providers` — tells the client which buttons to render.
- Signature, audience, issuer and expiry verification against each provider's
  published JWKS (`app/services/social_auth.py`).
- Account linking by **verified** email, so signing in with Google on an
  address that already has a password account lands in that same account.
- 15 security tests in `tests/test_social_auth.py`, including forged tokens,
  `alg=none`, expired tokens, and tokens issued for a *different app*.
- The mobile side: Apple via `expo-apple-authentication`, Google via
  `expo-auth-session`, both wired into the login screen.

---

## Step 1 — Google

Go to the [Google Cloud console](https://console.cloud.google.com/apis/credentials)
→ **Credentials** → **Create credentials** → **OAuth client ID**.

You need **three separate client IDs**, not one. A native Google app gets a
different client ID per platform, and the ID token carries whichever one
requested it. Configuring only the web ID is the classic *"Google sign-in works
in the simulator but not on my phone"* — the token is perfectly valid and then
fails the audience check.

| Type | Needed for | Extra input it asks for |
|---|---|---|
| **iOS** | the iOS build | bundle ID: `com.trace.app` |
| **Android** | the Android build | package name + the **SHA-1** of your signing certificate |
| **Web** | Expo Go and the dev flow | authorised redirect URIs |

To get the Android SHA-1 for an EAS build:

```bash
cd apps/mobile
eas credentials          # Android → production → Keystore → shows the SHA-1
```

## Step 2 — Apple

At [developer.apple.com](https://developer.apple.com/account/resources/identifiers/list):

1. **Identifiers** → your App ID (`com.trace.app`) → enable the
   **Sign In with Apple** capability.
2. For the web/Expo flow only, create a **Services ID** as well and configure
   its return URL.

`app.json` already sets `ios.usesAppleSignIn: true`, which is what puts the
entitlement into the build. Without it `signInAsync` throws at runtime on a
real device even though everything compiles.

**Sign in with Apple requires a paid Apple Developer account ($99/yr).** Google
sign-in does not cost anything, so if the budget is the blocker, ship Google
first — Apple's guideline 4.8 only requires the Apple button if you offer
another social login *and* you are shipping to the App Store.

## Step 3 — paste them in

`services/api/.env` (server — this is what verification checks against):

```
GOOGLE_CLIENT_ID_IOS=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_ID_ANDROID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_ID_WEB=xxxx.apps.googleusercontent.com
APPLE_BUNDLE_ID=com.trace.app
APPLE_CLIENT_ID=com.trace.app.signin      # the Services ID, web flow only
```

`apps/mobile/.env` (client — which IDs to *request* a token with):

```
EXPO_PUBLIC_GOOGLE_CLIENT_ID_IOS=xxxx.apps.googleusercontent.com
EXPO_PUBLIC_GOOGLE_CLIENT_ID_ANDROID=xxxx.apps.googleusercontent.com
EXPO_PUBLIC_GOOGLE_CLIENT_ID_WEB=xxxx.apps.googleusercontent.com
```

Then restart the bundler with `--clear`. `EXPO_PUBLIC_*` vars are inlined at
**build** time, not read at runtime, so without `--clear` you will keep running
the old empty values and conclude the config did nothing.

## Step 4 — a development build

**Neither provider works in Expo Go.** Apple sign-in needs a real entitlement,
and Google's native flow needs the URL scheme from your iOS client ID baked
into the binary.

```bash
cd apps/mobile
eas build --profile development --platform ios
```

---

## The security properties, and why they matter

The phone hands the server a string and claims it came from Google. The server
does not believe it. Three checks run before a single field inside the token is
trusted, and skipping any one is a real vulnerability:

| Check | What it stops |
|---|---|
| **Signature**, against the provider's published keys | Without it the token is just base64 the attacker chose. "Sign in as anyone@gmail.com" is a one-liner. |
| **Audience** — the token was minted *for us* | A Google token issued to a **different app** is perfectly signed. Accepting it lets any other developer's app log into Trace accounts. **This is the check people most often forget.** |
| **Issuer + expiry** | Replayed and wrong-provider tokens. |

`jwt.decode(..., verify_signature=False)` appears nowhere in
`social_auth.py`, and must never be added to it.

**Linking is only ever on a `email_verified` address.** Linking on an
unverified one would let someone claim an existing Trace account by signing up
to a provider with that email.

## Two provider quirks that will otherwise cost you an afternoon

**Apple sends the user's name exactly once.** It arrives in the credential
object on the very first authorization — never inside the token, and never
again. If it is not captured then, it is gone permanently. That is why
`display_name` travels as its own field on the request rather than being read
out of the token.

**Apple's private relay addresses are real.** `…@privaterelay.appleid.com` is
stable per app and mail delivered to it reaches the user, so it is a perfectly
good account key. Rejecting it locks out everyone who chose *Hide My Email*.
