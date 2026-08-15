# Trace — mobile app

Expo Router + TypeScript + Reanimated 4. 18 source files, 0 type errors, 10 passing tests.

```bash
cp .env.example .env        # set EXPO_PUBLIC_API_URL to your Railway URL
npm install
npx expo start --clear      # --clear is REQUIRED after any .env change
```

---

## Screens

| Route | What it does |
|---|---|
| `(auth)/login` | Sign in. Tap the wordmark 3× to reveal which API URL the build is using |
| `(auth)/signup` | Email, password, height, weight, goal. Deliberately short |
| `(tabs)/index` | Dashboard — calorie ring, macro bars, quick actions, verdict preview |
| `(tabs)/log` | Food search + the as-prepared "how many idlis?" flow |
| `(tabs)/train` | Workout logging with previous-performance auto-fill |
| `(tabs)/progress` | Full weekly verdict + weight trend chart |
| `scan` | Camera. Barcode checked first, photo as fallback |
| `scan-review` | Confidence ranges, the ghee question, correction capture |

---

## The jank fixes

Your prototype's lag was almost certainly one of these. All five are addressed:

**1. The calorie ring was re-rendering every frame.** The naive version holds progress in `useState` and updates it on a timer — a full React reconcile per frame, on the JS thread. `CalorieRing.tsx` drives the arc from a Reanimated **shared value** via `useAnimatedProps`, so the animation runs on the UI thread and React never re-renders during it. Not once. The number in the middle is animated the same way, through a read-only `TextInput`.

**2. Fetching during the navigation transition.** `InteractionManager.runAfterInteractions` on the dashboard: the skeleton paints immediately, the fetch fires once the push animation has finished. A JSON parse landing mid-transition eats frames.

**3. Unbounded list rendering.** FlashList with recycling for the exercise, food, and set lists. Rows are `memo`'d on primitives, so logging set 12 doesn't re-render sets 1–11.

**4. Inconsistent timing.** Every duration comes from `theme.ts` — `press: 100`, `fast: 180`, `base: 240`, `slow: 320`. No component hardcodes a duration. That consistency is most of what makes an app feel built rather than assembled.

**5. Spinners instead of skeletons.** `Skeleton` shimmer runs on a shared value; every loading state uses it.

**The one that silently undoes all of this:** `react-native-reanimated/plugin` must be **last** in `babel.config.js`. If it isn't, worklets fall back to the JS thread with no error and every animation janks. Also note Reanimated 4 moved worklets into a separate `react-native-worklets` package — it's in the dependency list.

---

## The login fix, end to end

Both halves of the case-mismatch bug are closed:

```tsx
<TextInput
  autoCapitalize="none"   // iOS capitalises the first char by default
  autoCorrect={false}
  autoComplete="email"
  keyboardType="email-address"
  textContentType="emailAddress"
/>
```

…plus `.trim().toLowerCase()` client-side in `api.login()`, plus normalisation server-side in `routers/auth.py`. All three, because any one alone leaves a hole.

`useAuth` uses a three-state machine (`restoring` / `signedOut` / `signedIn`) rather than a boolean. With a boolean, cold start reads `false` for the few hundred ms while SecureStore answers, the router kicks an authenticated user to login, and they report it as "it logs me out randomly." The root layout redirects **nowhere** while `status === 'restoring'`.

Offline is handled separately from unauthorised: a `NetworkError` during restore keeps the user signed in rather than destroying their session because they went into a tunnel.

---

## Where the product lives

**`scan-review.tsx`** — every item shows `240 kcal ±60`, not a fake-precise number. Low-confidence items surface one clarifying question, almost always about invisible cooking fat. Answering it shifts the estimate *and tightens the range*, because resolving uncertainty should visibly reduce it. There's a test asserting exactly that.

**`useScan.commit()`** — posts every user edit to `/recognize/{id}/correct`. This is the most valuable line in the app. Each correction is a labelled example of the food your users actually eat, corrected by the person who ate it. A clean confirm is signal too. Dropping this because "we already logged the meal" throws away the only asset a competitor can't buy.

**`VerdictCard.tsx`** — the weekly verdict, with "Show the math" always available. It renders whatever `math_breakdown` the server sent rather than a fixed shape, so adding a term to the algorithm surfaces here automatically. Guardrail codes are translated into plain English (`novice_discount_applied` → "You're new to lifting, so I discounted early strength gains — a lot of it is skill, not muscle").

**`(tabs)/log.tsx`** — when a food has a known preparation, it doesn't ask for grams of dry mix. Nobody knows that. It asks "how many idlis?" and shows the dilution warning.

---

## Testing

```bash
npm run typecheck   # 0 errors
npm test            # 10 passing
```

The tests cover the clarifying-question arithmetic specifically, because it's the one piece of client-side maths that changes what lands in a user's diary — and if it silently breaks, the UI still looks correct.

---

## Not built yet

Onboarding flow · paywall · weight-entry screen · meal templates · Apple Health / Health Connect · push notifications · offline queue. The offline queue is the one I'd do next: gym wifi is bad everywhere, and a set that fails to log is worse than no app.
