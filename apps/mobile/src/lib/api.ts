/**
 * Trace API client.
 *
 * This file is written to eliminate the five things that actually break
 * "login works on my machine but not on the device":
 *
 *  1. The base URL. `localhost` inside a React Native app means THE PHONE,
 *     not your laptop. On a real device it will never reach your dev server,
 *     and if you shipped a build with a localhost fallback it will never reach
 *     Railway either. resolveBaseUrl() below makes the resolution explicit and
 *     logs it, so you can see what the app is actually calling.
 *
 *  2. HTTPS. Android blocks cleartext HTTP by default (API 28+) and iOS blocks
 *     it via ATS. A Railway URL is always https -- if your EXPO_PUBLIC_API_URL
 *     starts with http:// the request fails with an opaque "Network request
 *     failed" that looks identical to the server being down.
 *
 *  3. Token storage. SecureStore has a ~2 KB value limit and is unavailable on
 *     web. A JWT with a fat payload silently fails to save, so the next request
 *     goes out unauthenticated. We store tokens under separate keys, check the
 *     size, and fall back to AsyncStorage on web.
 *
 *  4. Silent refresh. A 30-minute access token means users get logged out
 *     mid-session unless you refresh. The interceptor below does it once,
 *     queues concurrent 401s, and only bounces to login if the refresh itself
 *     fails.
 *
 *  5. Timeouts. fetch() in RN has no default timeout. A hanging request on a
 *     cold-started Railway container looks like a frozen app.
 */

import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

// ---------------------------------------------------------------------------
// Base URL
// ---------------------------------------------------------------------------

/**
 * Expo inlines any env var prefixed EXPO_PUBLIC_ at build time.
 *
 * Set it in .env (dev) and in your EAS build profile (production):
 *   EXPO_PUBLIC_API_URL=https://your-app.up.railway.app
 *
 * IMPORTANT: EXPO_PUBLIC_ vars are baked in at BUILD time, not read at
 * runtime. Changing .env requires restarting the bundler with `--clear`,
 * and changing it for a production build requires a NEW build. If you
 * "changed the URL and nothing happened", this is why.
 */
function resolveBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;

  if (fromEnv) {
    const url = fromEnv.replace(/\/+$/, '');
    if (url.startsWith('http://') && !url.includes('localhost') && !url.includes('192.168')) {
      console.warn(
        `[api] EXPO_PUBLIC_API_URL uses http:// (${url}). Android and iOS block ` +
          `cleartext traffic to non-local hosts, so every request will fail with ` +
          `"Network request failed". Use https://.`,
      );
    }
    return url;
  }

  // No env var: we are almost certainly in local dev.
  if (__DEV__) {
    // On a physical device, localhost is the PHONE. You must use your
    // machine's LAN IP. Expo exposes the packager host, which is exactly that.
    const debuggerHost =
      // expo-constants exposes this; read defensively so this file has no hard dep.
      (globalThis as any)?.expo?.modules?.ExponentConstants?.expoConfig?.hostUri ??
      (globalThis as any)?.__DEV_SERVER_HOST__;

    if (typeof debuggerHost === 'string' && debuggerHost.length > 0) {
      const host = debuggerHost.split(':')[0];
      const inferred = `http://${host}:8000`;
      console.log(`[api] No EXPO_PUBLIC_API_URL set; inferred dev API at ${inferred}`);
      return inferred;
    }
  }

  throw new Error(
    'EXPO_PUBLIC_API_URL is not set. Add it to .env for local dev and to your ' +
      'EAS build profile for release builds, then restart with `npx expo start --clear`.',
  );
}

export const API_BASE_URL = resolveBaseUrl();

// Log it once at startup. When login mysteriously fails, this line in the
// Metro/device console tells you immediately whether the app is even pointing
// at your Railway deployment.
console.log(`[api] base URL = ${API_BASE_URL}`);

const REQUEST_TIMEOUT_MS = 15_000;

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------

const ACCESS_KEY = 'trace.accessToken';
const REFRESH_KEY = 'trace.refreshToken';

// SecureStore is not available on web, and has a ~2 KB per-value limit.
const useSecureStore = Platform.OS !== 'web';

async function setItem(key: string, value: string): Promise<void> {
  if (value.length > 2000 && useSecureStore) {
    // SecureStore fails silently past its limit on some Android OEMs. Fall
    // back rather than losing the token.
    console.warn(`[api] ${key} is ${value.length} bytes; using AsyncStorage.`);
    await AsyncStorage.setItem(key, value);
    return;
  }
  if (useSecureStore) {
    await SecureStore.setItemAsync(key, value);
  } else {
    await AsyncStorage.setItem(key, value);
  }
}

async function getItem(key: string): Promise<string | null> {
  if (useSecureStore) {
    const secure = await SecureStore.getItemAsync(key);
    if (secure) return secure;
  }
  return AsyncStorage.getItem(key);
}

async function removeItem(key: string): Promise<void> {
  if (useSecureStore) {
    await SecureStore.deleteItemAsync(key).catch(() => undefined);
  }
  await AsyncStorage.removeItem(key).catch(() => undefined);
}

export const tokens = {
  async save(access: string, refresh: string): Promise<void> {
    await Promise.all([setItem(ACCESS_KEY, access), setItem(REFRESH_KEY, refresh)]);
  },
  getAccess: () => getItem(ACCESS_KEY),
  getRefresh: () => getItem(REFRESH_KEY),
  async clear(): Promise<void> {
    await Promise.all([removeItem(ACCESS_KEY), removeItem(REFRESH_KEY)]);
  },
};

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class NetworkError extends Error {
  constructor(
    message: string,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = 'NetworkError';
  }
}

// ---------------------------------------------------------------------------
// Core request
// ---------------------------------------------------------------------------

let refreshPromise: Promise<boolean> | null = null;
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

async function refreshAccessToken(): Promise<boolean> {
  // Collapse concurrent refreshes -- three parallel 401s must not fire three
  // refresh calls, because token rotation makes the 2nd and 3rd fail and log
  // the user out for no reason.
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refresh = await tokens.getRefresh();
    if (!refresh) return false;

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      await tokens.save(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  auth?: boolean;
  timeoutMs?: number;
  _isRetry?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = true, timeoutMs = REQUEST_TIMEOUT_MS, _isRetry, ...rest } = options;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...((rest.headers as Record<string, string>) ?? {}),
  };

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
    // Do NOT set Content-Type for FormData -- the runtime must add the
    // multipart boundary itself. Setting it manually is why image uploads
    // fail with a 422 that mentions a missing field.
    delete headers['Content-Type'];
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  if (auth) {
    const token = await tokens.getAccess();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      headers,
      body: payload,
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    // In RN this is where "Network request failed" surfaces. It means the
    // request never reached a server: wrong host, cleartext HTTP blocked,
    // no connectivity, or DNS. It is NOT a CORS problem -- native fetch is
    // not subject to CORS at all.
    const isAbort = (err as Error)?.name === 'AbortError';
    throw new NetworkError(
      isAbort
        ? `Request to ${path} timed out after ${timeoutMs}ms.`
        : `Could not reach ${API_BASE_URL}${path}. Check that the URL is correct, ` +
          `uses https, and that the server is running.`,
      err,
    );
  }
  clearTimeout(timer);

  if (response.status === 401 && auth && !_isRetry) {
    const detail = await response
      .clone()
      .json()
      .catch(() => null);
    if (detail?.detail === 'token_expired' || detail?.detail?.includes?.('Invalid token')) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return request<T>(path, { ...options, _isRetry: true });
      }
    }
    await tokens.clear();
    onUnauthorized?.();
    throw new ApiError('Your session expired. Please sign in again.', 401, detail);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const detail =
      (data as any)?.detail ?? (typeof data === 'string' ? data : 'Request failed');
    throw new ApiError(
      typeof detail === 'string' ? detail : JSON.stringify(detail),
      response.status,
      data,
    );
  }

  return data as T;
}

// ---------------------------------------------------------------------------
// Typed endpoints
// ---------------------------------------------------------------------------

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    display_name: string | null;
    is_pro: boolean;
    goal_type: string;
    /** null until the onboarding questionnaire is completed. */
    onboarded_at?: string | null;
  };
}

/** One day of the starting plan. Mirrors services/onboarding.py PlannedDay. */
export interface PlannedDay {
  day: string; // "Mon"
  index: number; // 0-6
  day_type: 'training' | 'rest';
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
}

export interface OnboardingAnswers {
  sex?: string | null;
  age_years?: number | null;
  height_cm: number;
  weight_kg: number;
  /** The "have you ever weighed X?" question. null = didn't say, NOT "no". */
  highest_weight_kg?: number | null;
  lifting_experience_months: number;
  lifting_sessions_per_week: number;
  cardio_sessions_per_week: number;
  daily_steps: number;
  goal_type: 'lose' | 'maintain' | 'gain' | 'recomp';
  goal_weight_kg?: number | null;
  training_day_indices?: number[] | null;
}

export interface OnboardingPlan {
  bmr: number;
  activity_multiplier: number;
  tdee_prior: number;
  calorie_target: number;
  protein_target_g: number;
  carb_target_g: number;
  fat_target_g: number;
  fiber_target_g: number;
  goal_rate_pct_per_week: number;
  week: {
    days: PlannedDay[];
    weekly_calories: number;
    daily_average: number;
    training_days: number;
    rationale: string;
    math: Record<string, number>;
  };
  adaptation_factor: number;
  pct_below_peak: number;
  notes: string[];
}

/** One row in the Trainer tab's exercise list. */
export interface CatalogueExercise {
  id: string;
  name: string;
  muscle_group: string;
  secondary_muscles: string[];
  equipment: string;
  is_compound: boolean;
  /** Heaviest working set in the last 30 days, or null if never trained. */
  working_weight_kg: number | null;
  /**
   * Percent change in best e1RM vs last week, or null.
   *
   * null means "no comparison available" and MUST render as a dash. Showing
   * 0.0% for a week the user didn't train invents a measurement.
   */
  delta_pct: number | null;
}

export interface CatalogueGroup {
  muscle_group: string;
  count: number;
  exercises: CatalogueExercise[];
}

/**
 * One day on the weight chart.
 *
 * `raw_kg` is null on a day with no weigh-in -- a genuine gap, not a zero. The
 * chart breaks its line there rather than interpolating, because drawing
 * through missing data invents measurements the user never took.
 */
export interface WeightPoint {
  date: string;
  raw_kg: number | null;
  trend_kg: number;
}

export const api = {
  health: () => request<{ status: string }>('/health', { auth: false }),

  /** The Trainer tab's exercise list, grouped by muscle. One round trip. */
  exerciseCatalogue: (q?: string) =>
    request<{ groups: CatalogueGroup[]; total: number }>(
      `/api/workouts/catalogue${q ? `?q=${encodeURIComponent(q)}` : ''}`,
    ),

  lastPerformance: (exerciseId: string) =>
    request<{
      sets: Array<{ weight_kg: number; reps: number; rpe: number | null }>;
      best_e1rm: number | null;
    }>(`/api/workouts/sessions/last-performance?exercise_id=${exerciseId}`),

  /**
   * Compute a plan WITHOUT saving it. Unauthenticated, so the wizard's final
   * step can show a real week before the user commits.
   */
  previewPlan: (answers: OnboardingAnswers) =>
    request<OnboardingPlan>('/api/onboarding/preview', {
      method: 'POST',
      auth: false,
      body: answers as unknown as Record<string, unknown>,
    }),

  /** Save the questionnaire and seed week one's targets. */
  submitOnboarding: (answers: OnboardingAnswers) =>
    request<OnboardingPlan>('/api/onboarding', {
      method: 'POST',
      body: answers as unknown as Record<string, unknown>,
    }),

  onboardingStatus: () =>
    request<{ onboarded: boolean; onboarded_at: string | null }>(
      '/api/onboarding/status',
    ),

  async login(email: string, password: string): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      auth: false,
      // Trim + lowercase on the client as well as the server. iOS auto-
      // capitalises the first character of a text input by default, so
      // "Tejas@gmail.com" is what actually gets submitted unless you also
      // set autoCapitalize="none" autoCorrect={false} on the TextInput.
      body: { email: email.trim().toLowerCase(), password },
    });
    await tokens.save(res.access_token, res.refresh_token);
    return res;
  },

  async register(payload: {
    email: string;
    password: string;
    display_name?: string;
    height_cm?: number;
    weight_kg?: number;
    goal_type?: string;
  }): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      auth: false,
      body: { ...payload, email: payload.email.trim().toLowerCase() },
    });
    await tokens.save(res.access_token, res.refresh_token);
    return res;
  },

  async logout(): Promise<void> {
    const refresh = await tokens.getRefresh();
    if (refresh) {
      await request('/api/auth/logout', {
        method: 'POST',
        body: { refresh_token: refresh },
      }).catch(() => undefined);
    }
    await tokens.clear();
  },

  me: () => request<AuthResponse['user']>('/api/auth/me'),

  /**
   * Ask for a one-time code.
   *
   * The response is deliberately identical whether or not that number has an
   * account -- telling the client "no account with that number" would make
   * this a free tool for checking whether a given person uses Trace.
   */
  phoneStart: (phone: string) =>
    request<{
      sent: boolean;
      /** Masked, e.g. "••••3210". The full number is never echoed back. */
      phone: string;
      expires_in: number;
      length: number;
      /** Development only, and only when no SMS provider is configured. */
      dev_code?: string;
      dev_note?: string;
    }>('/api/auth/phone/start', {
      method: 'POST',
      auth: false,
      body: { phone },
    }),

  /**
   * Verify the code. This both signs in and signs up: a verified number IS
   * the account, so there is no "are you new" question anywhere in the flow.
   */
  async phoneVerify(
    phone: string,
    code: string,
    displayName?: string,
  ): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/api/auth/phone/verify', {
      method: 'POST',
      auth: false,
      body: { phone, code, display_name: displayName },
    });
    await tokens.save(res.access_token, res.refresh_token);
    return res;
  },

  /** Which social buttons the server can actually complete. */
  authProviders: () =>
    request<{ providers: string[] }>('/api/auth/providers', { auth: false }),

  /**
   * Exchange a verified Google/Apple identity token for a Trace session.
   *
   * `displayName` matters for Apple specifically: it sends the user's name
   * exactly once, on the first authorization, and never inside the token. If
   * it is not forwarded at that moment it is gone for good.
   */
  async socialSignIn(
    provider: 'google' | 'apple',
    idToken: string,
    displayName?: string,
  ): Promise<AuthResponse> {
    const res = await request<AuthResponse>('/api/auth/social', {
      method: 'POST',
      auth: false,
      body: { provider, id_token: idToken, display_name: displayName },
    });
    await tokens.save(res.access_token, res.refresh_token);
    return res;
  },

  searchFoods: (q: string, country?: string) =>
    request<{ results: FoodItem[]; took_ms: number; source: string }>(
      `/api/foods/search?q=${encodeURIComponent(q)}${country ? `&country=${country}` : ''}`,
    ),

  /** Which sources are live, and how big the catalogue actually is. */
  sourcesStatus: () =>
    request<{
      free: Record<string, boolean>;
      catalogue_size: number | null;
      paid: Record<string, unknown>;
    }>('/api/foods/sources/status'),

  /** Foods this user has logged before -- the two-tap re-log path. */
  recentFoods: (limit = 20) =>
    request<FoodItem[]>(`/api/foods/recent?limit=${limit}`),

  resolveBarcode: (barcode: string) =>
    request<{
      found: boolean;
      barcode: string;
      item: FoodItem | null;
      resolved_from: string | null;
      message: string | null;
    }>(`/api/foods/barcode/${barcode}`),

  recognizePhoto: (uri: string, hint?: string) => {
    const form = new FormData();
    // RN's FormData needs this exact shape: { uri, name, type }.
    form.append('image', {
      uri,
      name: 'meal.jpg',
      type: 'image/jpeg',
    } as unknown as Blob);
    if (hint) form.append('hint', hint);
    return request<RecognitionResponse>('/api/foods/recognize', {
      method: 'POST',
      body: form,
      // MUST EXCEED THE SERVER'S OWN DEADLINE (VISION_DEADLINE_MS, 24 s) plus
      // the upload. It used to be 30 s against a pipeline whose measured
      // worst case was 58 s, so a scan that escalated was aborted here every
      // single time -- the server finished the work, billed us for it, and
      // the user was told the photo couldn't be read. A client timeout below
      // the server's is not a safety net, it is a guaranteed failure.
      timeoutMs: 45_000,
    });
  },

  // -- Recipes --------------------------------------------------------------
  //
  // A recipe logs by SERVING, not by grams. The server refuses a gram amount
  // for a recipe whose finished weight nobody measured (`yield_estimated`),
  // because the raw ingredient sum is not the cooked weight -- so the UI must
  // hide the grams control when that flag is set rather than rely on the 422.

  /** The user's own shelf. `all` = written by them plus saved from others. */
  myRecipes: (scope: RecipeScope = 'all', q?: string) =>
    request<RecipeListResponse>(
      `/api/recipes?scope=${scope}${q ? `&q=${encodeURIComponent(q)}` : ''}`,
    ),

  /** Everything published, by anyone. */
  discoverRecipes: (opts: { q?: string; cuisine?: string; sort?: RecipeSort } = {}) => {
    const qs = new URLSearchParams();
    if (opts.q) qs.set('q', opts.q);
    if (opts.cuisine) qs.set('cuisine', opts.cuisine);
    qs.set('sort', opts.sort ?? 'popular');
    return request<RecipeListResponse>(`/api/recipes/discover?${qs.toString()}`);
  },

  recipe: (id: string) => request<Recipe>(`/api/recipes/${id}`),

  createRecipe: (payload: RecipeDraft) =>
    request<Recipe>('/api/recipes', {
      method: 'POST',
      body: payload as unknown as Record<string, unknown>,
    }),

  updateRecipe: (id: string, payload: RecipeDraft) =>
    request<Recipe>(`/api/recipes/${id}`, {
      method: 'PUT',
      body: payload as unknown as Record<string, unknown>,
    }),

  deleteRecipe: (id: string) =>
    request<void>(`/api/recipes/${id}`, { method: 'DELETE' }),

  /** Dry run, so the publish sheet shows the blockers BEFORE the user taps. */
  recipePublishCheck: (id: string) =>
    request<PublishCheck>(`/api/recipes/${id}/publish-check`),

  setRecipeVisibility: (id: string, visibility: RecipeVisibility) =>
    request<Recipe>(`/api/recipes/${id}/visibility`, {
      method: 'POST',
      body: { visibility, acknowledged_cautions: true },
    }),

  /** Keep someone's recipe on your shelf. Follows their edits. */
  saveRecipe: (id: string) =>
    request<void>(`/api/recipes/${id}/save`, { method: 'POST' }),

  unsaveRecipe: (id: string) =>
    request<void>(`/api/recipes/${id}/save`, { method: 'DELETE' }),

  /** Take a private copy. Does NOT follow the original's edits. */
  forkRecipe: (id: string) =>
    request<Recipe>(`/api/recipes/${id}/fork`, { method: 'POST' }),

  logRecipe: (id: string, portion: { servings?: number; grams?: number; meal_type?: string }) =>
    request<{ id: string; calories: number; serving_label: string | null }>(
      `/api/recipes/${id}/log`,
      { method: 'POST', body: portion },
    ),

  logMeal: (payload: Record<string, unknown>) =>
    request('/api/meals/log', { method: 'POST', body: payload }),

  dailySummary: (date: string) => request<DailySummary>(`/api/meals/daily?date=${date}`),

  logWeight: (weight_kg: number, measured_on?: string) =>
    request('/api/weight/log', { method: 'POST', body: { weight_kg, measured_on } }),

  weightTrend: (days = 90) => request<WeightPoint[]>(`/api/weight/trend?days=${days}`),

  weeklyVerdict: (recompute = false) =>
    request<Adjudication>(`/api/adjudication/weekly?recompute=${recompute}`),

  // Unauthenticated -- this is the login-screen "ask a quick question" box,
  // asked before there's a session to attach it to.
  askTrainer: (question: string) =>
    request<{ answer: string }>('/api/chat/ask', {
      method: 'POST',
      auth: false,
      body: { question },
    }),

  // --- Live workout ------------------------------------------------------

  startSession: (routine_name?: string) =>
    request<{ id: string; started_at: string }>('/api/workouts/sessions', {
      method: 'POST',
      body: { routine_name },
    }),

  /** Everything the live set screen needs, in one request. */
  nextSet: (sessionId: string, exerciseId: string) =>
    request<NextSet>(
      `/api/workouts/sessions/${sessionId}/next-set?exercise_id=${exerciseId}`,
    ),

  /**
   * Log a set. The verdict comes back WITH the write, so the screen can
   * render it without a second round trip while the lifter is still standing
   * at the bar.
   */
  logSet: (sessionId: string, payload: LogSetPayload) =>
    request<SetResult>(`/api/workouts/sessions/${sessionId}/sets`, {
      method: 'POST',
      body: payload as unknown as Record<string, unknown>,
    }),

  finishSession: (sessionId: string) =>
    request<SessionSummary>(`/api/workouts/sessions/${sessionId}/finish`, {
      method: 'POST',
    }),

  sessionSummary: (sessionId: string) =>
    request<SessionSummary>(`/api/workouts/sessions/${sessionId}/summary`),

  workoutHistory: (limit = 30) =>
    request<{ sessions: SessionRow[]; active_session_id: string | null }>(
      `/api/workouts/sessions?limit=${limit}`,
    ),

  muscleVolume: (days: 7 | 30 = 7) =>
    request<VolumeReport>(`/api/workouts/volume?days=${days}`),

  /* -------------------------------------------------------------- sports */

  /* ------------------------------------------------------ nutrition v2 */

  /** The day total as a range, and where the width comes from. */
  dayUncertainty: (day?: string) =>
    request<DayUncertainty>(
      `/api/insights/uncertainty${day ? `?date=${day}` : ''}`,
    ),

  /** The week as a budget, with flagged days already paid for. */
  weekBudget: (flagged: string[] = []) =>
    request<WeekBudget>(
      `/api/insights/week${flagged.length ? `?flagged=${flagged.join(',')}` : ''}`,
    ),

  /** Protein timing, the shortfall, and the cheapest way to close it. */
  proteinReport: (vegOnly = false) =>
    request<ProteinReport>(`/api/insights/protein?veg_only=${vegOnly}`),

  /** All 26 nutrients, with an explicit gap where the data is thin. */
  nutrientPanel: (day?: string) =>
    request<NutrientPanel>(
      `/api/insights/nutrients${day ? `?date=${day}` : ''}`,
    ),

  /** Whether yesterday's carbs show up in today's session. */
  fuelReport: (trainingTomorrow = false) =>
    request<FuelReport>(
      `/api/insights/fuel?training_tomorrow=${trainingTomorrow}`,
    ),

  /**
   * Streak, consistency, and whether the bulk or cut is working.
   *
   * ONE CALL RETURNS BOTH so the UI cannot render the flattering half
   * without the honest half.
   */
  progressReport: (windowDays = 30) =>
    request<ProgressReport>(
      `/api/health/consistency?window_days=${windowDays}`,
    ),

  /**
   * The sport catalogue, plus the user's weight.
   *
   * The weight rides along so the burn readout can move with the duration
   * dial locally. Asking the server per stepper tap would put a few hundred
   * milliseconds between the control and the number, which reads as broken.
   */
  sports: () =>
    request<{ sports: Sport[]; weight_kg: number | null }>(
      '/api/health/sports',
    ),

  /** Sessions the user did, plus whatever the watch and Strava sent. */
  activities: (days = 14) =>
    request<Activity[]>(`/api/health/activities?days=${days}`),

  logActivity: (draft: ActivityDraft) =>
    request<ActivityLogged>('/api/health/activities', {
      method: 'POST',
      body: draft,
    }),

  deleteActivity: (id: string) =>
    request<void>(`/api/health/activities/${id}`, { method: 'DELETE' }),

  /**
   * Speak a set; get a PROPOSAL back. This never writes anything -- a
   * misheard "sixty" as "sixteen" entering the training history would corrupt
   * the strength trend, so the review screen is mandatory.
   */
  voiceLog: (uri: string, unit: 'kg' | 'lb' = 'kg') => {
    const form = new FormData();
    form.append('audio', {
      uri,
      name: 'set.m4a',
      type: 'audio/m4a',
    } as unknown as Blob);
    form.append('unit', unit);
    return request<VoiceResult>('/api/workouts/voice', {
      method: 'POST',
      body: form,
      timeoutMs: 30_000,
    });
  },

  /** Measured maintenance, its uncertainty band, and how it was arrived at. */
  maintenance: () => request<Maintenance>('/api/weight/maintenance'),

  /**
   * Photograph the nutrition panel; get the numbers typed for you.
   *
   * The fallback for every product a barcode misses — a local brand, a small
   * market's own-label, anything from a country Open Food Facts covers
   * thinly. Note this TRANSCRIBES rather than estimating, so unlike a plate
   * scan there is no ± band: an unreadable field comes back null and the user
   * fills it, because a plausible invented number is worse than a blank.
   */
  readLabel: (uri: string) => {
    const form = new FormData();
    form.append('image', {
      uri,
      name: 'label.jpg',
      type: 'image/jpeg',
    } as unknown as Blob);
    return request<LabelReading>('/api/foods/read-label', {
      method: 'POST',
      body: form,
      timeoutMs: 40_000,
    });
  },
};

export interface LabelReading {
  legible: boolean;
  basis: '100g' | 'serving' | 'unknown';
  /** Every field may be null — that means "not printed", never zero. */
  per_100g: {
    calories: number | null;
    protein_g: number | null;
    carbs_g: number | null;
    sugar_g: number | null;
    fat_g: number | null;
    saturated_fat_g: number | null;
    fiber_g: number | null;
    sodium_mg: number | null;
  };
  serving_size_g: number | null;
  product_name: string | null;
  brand: string | null;
  confidence: number;
  quality: number;
  verdict: string;
  warnings: string[];
  model: string;
  latency_ms: number;
  /** False when the panel failed validation. Keep one-tap save disabled. */
  safe_to_save: boolean;
}

// ---------------------------------------------------------------------------
// Live workout types
// ---------------------------------------------------------------------------

export type SetVerdict = 'PURPLE' | 'ON_TARGET' | 'UNDER' | 'UNRATED';
export type MuscleStatus = 'UNTRAINED' | 'UNDER' | 'IN_RANGE' | 'OVER';
export type ExerciseTrend = 'CONFIRMED' | 'NO_CHANGE' | 'DECLINE' | 'FIRST_TIME';

export interface LogSetPayload {
  exercise_id: string;
  weight_kg: number;
  reps: number;
  /** Reps left in the tank. This is what makes the set a measurement. */
  rir?: number | null;
  is_warmup?: boolean;
}

export interface SetResult {
  id: string;
  set_index: number;
  e1rm: number | null;
  rir: number | null;
  rpe: number | null;
  verdict: SetVerdict;
  headline: string;
  detail: string;
  load_pct: number | null;
  reference_e1rm: number | null;
  route: { reps_needed: number | null; weight_needed_kg: number | null };
}

export interface NextSet {
  exercise: {
    id: string;
    name: string;
    muscle_group: string;
    equipment: string;
    is_compound: boolean;
  };
  reference_e1rm: number | null;
  weight_step_kg: number;
  prescription: {
    weight_kg: number | null;
    reps: number;
    target_rir: number;
    rest_s: number;
    note: string;
  };
  sets_done: Array<{
    set_index: number;
    weight_kg: number;
    reps: number;
    rir: number | null;
    e1rm: number | null;
    is_warmup: boolean;
    verdict: SetVerdict | null;
  }>;
}

export interface SessionSummary {
  session_id: string;
  routine_name: string | null;
  started_at: string;
  ended_at: string | null;
  duration_min: number | null;
  total_sets: number;
  total_reps: number;
  volume_kg: number;
  avg_rpe: number | null;
  purple_sets: number;
  lifts_moved_up: number;
  headline: string;
  muscle_split: Array<{ muscle: string; volume_kg: number; pct: number }>;
  exercises: Array<{
    exercise_id: string;
    name: string;
    sets: number;
    top_weight_kg: number;
    volume_kg: number;
    best_e1rm: number | null;
    previous_e1rm: number | null;
    delta_pct: number | null;
    trend: ExerciseTrend;
    set_verdicts: SetVerdict[];
  }>;
}

export interface SessionRow {
  id: string;
  routine_name: string | null;
  started_at: string;
  ended_at: string | null;
  is_active: boolean;
  duration_min: number;
  total_sets: number;
  total_reps: number;
  volume_kg: number;
}

export interface MuscleRow {
  muscle: string;
  sets: number;
  direct_sets: number;
  sessions: number;
  volume_kg: number;
  min_effective: number;
  productive_max: number;
  status: MuscleStatus;
  note: string;
  /** 0-1, for shading the body map. */
  intensity: number;
}

/* ------------------------------------------------------------------ sports
   The Activities half of the Trainer tab.

   `burn` is CONTEXT, not an allowance. The server sends `where_this_goes`
   alongside it saying the calorie target is unchanged, and the UI renders
   that verbatim rather than paraphrasing it -- see services/sports.py.      */

/* -------------------------------------------------- consistency + phase
   Returned together from one endpoint on purpose: a streak rendered without
   the verdict beside it is a slot machine. See services/streak.py.        */

/* ===================================================== nutrition v2 =====
   The four bets from the nutrition mockup. Each screen is one request:
   these views need several related numbers at once, and splitting them
   would let a screen render half a state.                                 */

export interface CertaintySlice {
  source: string;
  label: string;
  kcal: number;
  share: number;
  /** Share of the day's UNCERTAINTY, which is the actionable one. */
  uncertainty_share: number;
}

export interface UncertainItem {
  name: string;
  kcal: number;
  band: number;
  source: string;
  source_label: string;
}

export interface DayUncertainty {
  total_kcal: number;
  band: number;
  low: number;
  high: number;
  confidence: 'high' | 'medium' | 'low';
  band_pct: number;
  mix: CertaintySlice[];
  items: UncertainItem[];
  worst_item: string | null;
  worst_item_band: number | null;
  headline: string;
  advice: string | null;
  calorie_target: number | null;
}

export interface BudgetDay {
  day: string;
  baseline_kcal: number;
  planned_kcal: number;
  logged_kcal: number | null;
  shift: number;
  delta: number | null;
  flagged: boolean;
  is_past: boolean;
  is_today: boolean;
}

export interface WeekBudget {
  start: string;
  end: string;
  daily_target: number;
  week_target: number;
  spent: number;
  remaining: number;
  days_left: number;
  per_day_remaining: number | null;
  status: 'on_pace' | 'ahead' | 'behind' | 'blown';
  days: BudgetDay[];
  headline: string;
  detail: string;
  notes: string[];
  /** Always 0. Sent so the client states the promise rather than recalls it. */
  carries_forward: number;
}

export interface ProteinFood {
  key: string;
  name: string;
  portion: string;
  protein_g: number;
  kcal: number;
  rupees: number;
  g_per_10_rupees: number;
  veg: boolean;
  price_confidence: string;
}

export interface ProteinReport {
  total_g: number;
  target_g: number | null;
  short_by_g: number;
  shape: 'even' | 'back_loaded' | 'front_loaded' | 'single_dose' | 'unknown';
  thinnest_meal: string | null;
  real_doses: number;
  meals: { name: string; hour: number; protein_g: number }[];
  headline: string;
  detail: string;
  fix_foods: ProteinFood[];
  fix_protein_g: number;
  fix_rupees: number;
  fix_note: string;
  ranked: ProteinFood[];
  prices_as_of: string;
  prices_region: string;
  prices_stale_months: number;
}

export interface FuelReport {
  verdict: 'positive' | 'none_found' | 'insufficient_data' | 'no_contrast';
  pairs: number;
  rho: number | null;
  high_carb_volume: number | null;
  low_carb_volume: number | null;
  uplift_pct: number | null;
  carb_threshold_g: number | null;
  headline: string;
  detail: string;
  notes: string[];
  suggestion: {
    carbs_delta_g: number;
    fat_delta_g: number;
    kcal_delta: number;
    headline: string;
    detail: string;
  } | null;
}

export interface NutrientRow {
  key: string;
  name: string;
  unit: string;
  group: string;
  kind: 'floor' | 'ceiling';
  amount: number | null;
  target: number;
  /** null when coverage is too thin to claim one. */
  pct: number | null;
  status: 'short' | 'low' | 'ok' | 'over' | 'unknown';
  /** Share of the day's calories from foods carrying this nutrient. */
  covered: number;
}

export interface NutrientPanel {
  rows: NutrientRow[];
  notable: string[];
  tracked: number;
  known: number;
  headline: string;
  notes: Record<string, string>;
  sodium_potassium_ratio: number | null;
  sodium_potassium_note: string;
}

export interface ConsistencyReport {
  current_streak: number;
  longest_streak: number;
  days_logged: number;
  window_days: number;
  consistency_pct: number;
  logged_today: boolean;
  /** How much the adaptive engine can trust its own output right now. */
  data_confidence: number;
  milestone: string | null;
  next_milestone: string | null;
  days_to_next: number | null;
  headline: string;
}

export interface PhaseReport {
  verdict:
    | 'on_track'
    | 'too_fast'
    | 'too_slow'
    | 'wrong_way'
    | 'insufficient_data';
  goal: string;
  weeks_elapsed: number;
  start_weight_kg: number | null;
  current_weight_kg: number | null;
  total_change_kg: number | null;
  rate_kg_per_week: number | null;
  target_rate_kg_per_week: number | null;
  headline: string;
  detail: string;
  notes: string[];
}

export interface ProgressReport {
  consistency: ConsistencyReport;
  phase: PhaseReport;
}

export interface Sport {
  key: string;
  name: string;
  group: string;
  met: number;
  /** True when the MET is interpolated rather than cited. Shown as a caveat. */
  estimated: boolean;
  tracks_distance: boolean;
}

export interface Burn {
  low: number;
  point: number;
  high: number;
  band: number;
  met_used: number;
  assumed_weight: boolean;
  met_estimated: boolean;
  /** True when this came off a device rather than out of the MET table. */
  measured: boolean;
}

export interface Activity {
  id: string;
  sport: string;
  name: string;
  started_at: string;
  duration_minutes: number;
  distance_km: number | null;
  mean_heart_rate: number | null;
  source: string;
  burn: Burn | null;
}

export interface ActivityLogged {
  activity: Activity;
  where_this_goes: [string, string][];
  target_explainer: string;
}

export interface ActivityDraft {
  sport: string;
  duration_minutes: number;
  intensity?: 'easy' | 'moderate' | 'hard';
  distance_km?: number | null;
  mean_heart_rate?: number | null;
  active_energy_kcal?: number | null;
}

export interface VolumeReport {
  days: number;
  headline: string;
  weakest: string | null;
  total_sets: number;
  total_volume_kg: number;
  muscles: MuscleRow[];
}

export interface VoiceEntry {
  exercise_phrase: string;
  exercise_id: string | null;
  exercise_name: string | null;
  match_score: number;
  alternatives: Array<{ id: string; name: string }>;
  sets: number;
  weight_kg: number | null;
  weight_was_converted: boolean;
  unit_assumed: boolean;
  reps_low: number;
  reps_high: number;
  confidence: number;
  warnings: string[];
}

export interface VoiceResult {
  transcript: string;
  model: string;
  latency_ms: number;
  entries: VoiceEntry[];
}

export interface Maintenance {
  maintenance_kcal: number;
  band_low: number;
  band_high: number;
  dialed_pct: number;
  is_data_driven: boolean;
  prior_kcal: number;
  observed_kcal: number | null;
  vs_calculator: number | null;
  weigh_ins: number;
  logged_days: number;
  eating_kcal: number | null;
  eating_delta: number | null;
  expected_rate_kg_per_week: number | null;
  source_line: string;
  notes: string[];
  history: Array<{ date: string; kcal: number; low: number; high: number }>;
}

export interface FoodItem {
  id: string;
  name: string;
  brand: string | null;
  barcode: string | null;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  serving_sizes: Array<{ name: string; grams: number; is_default: boolean }>;
  data_quality: number;
  is_verified: boolean;
  /** Where this row's nutrition data came from: 'openfoodfacts', 'usda_fdc',
   *  'curated', 'user'. Per row -- the catalogue is not single-source. */
  source?: string | null;
  /** Licence of THIS row, e.g. 'odbl', 'public-domain'. Never global. */
  source_licence?: string | null;
  /** 1..7, lower is better evidence. */
  verification_tier?: number | null;
  /** Deterministic upstream URL where one exists. */
  source_url?: string | null;
  /** How search reached this row: 'direct' or 'alias'. */
  matched_via?: string | null;
  /** The alias text that matched, when matched_via === 'alias'. */
  matched_alias?: string | null;
}

export interface RecognitionResponse {
  recognition_id: string;
  items: Array<{
    name: string;
    portion_unit: string;
    portion_count: number;
    grams_est: number;
    kcal_point: number;
    kcal_low: number;
    kcal_high: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
    confidence: number;
    clarifying_question?: {
      text: string;
      options: string[];
      kcal_deltas: number[];
    };
  }>;
  hidden_ingredients: string[];
  overall_confidence: number;
  cached: boolean;
}

export interface DailySummary {
  date: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  calorie_target: number | null;
  protein_target_g: number | null;
  carb_target_g: number | null;
  fat_target_g: number | null;
  fiber_target_g: number | null;

  /**
   * The Home screen's "worth watching" ledger.
   *
   * `null` means NOT KNOWN for today's foods — deliberately distinct from 0.
   * Render an unknown bar as unknown; showing an empty bar would tell a user
   * they are safely under a limit they may actually have blown.
   */
  sodium_mg: number | null;
  potassium_mg: number | null;
  sugars_g: number | null;
  sodium_limit_mg: number;
  potassium_target_mg: number;
  sugars_limit_g: number;

  meals: Array<Record<string, unknown>>;
}

export interface Adjudication {
  id: string;
  verdict: string;
  headline: string;
  explanation: string;
  strength_index_delta_pct: number | null;
  weight_delta_pct_per_week: number | null;
  recommended_target: number | null;
  math_breakdown: Record<string, unknown>;
  guardrails_triggered: string[];
}


// ---------------------------------------------------------------------------
// Recipes
// ---------------------------------------------------------------------------

export type RecipeVisibility = 'private' | 'published';
export type RecipeScope = 'mine' | 'saved' | 'all';
export type RecipeSort = 'popular' | 'recent' | 'protein';

export interface NutritionPanel {
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  sugar_g: number;
  sodium_mg: number;
  saturated_fat_g: number;
}

export interface RecipeIngredient {
  id: string;
  food_item_id: string | null;
  display_name: string;
  grams: number;
  quantity_label: string | null;
  note: string | null;
  sort_order: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
}

export interface Recipe {
  id: string;
  name: string;
  description: string | null;
  cuisine: string | null;
  photo_url: string | null;
  visibility: RecipeVisibility;
  published_at: string | null;

  servings: number;
  cooked_weight_g: number | null;
  /**
   * TRUE means nobody weighed the finished dish, so per-100 g is unknowable.
   *
   * Do not fall back to the raw ingredient sum: a dal loses ~15% of its
   * weight as steam, and dividing by the raw weight under-reports every gram
   * logged against it. When this is true the portion control shows servings
   * only — the server rejects a grams payload anyway.
   */
  yield_estimated: boolean;
  serving_grams: number | null;

  prep_minutes: number | null;
  cook_minutes: number | null;
  steps: string[];
  tags: string[];

  total: NutritionPanel;
  per_serving: NutritionPanel;
  /** Null whenever `yield_estimated` is true. */
  per_100g: NutritionPanel | null;
  ingredient_grams: number;
  /** 0..1 — share of calories traceable to a real catalogue food. */
  sourced_fraction: number;
  warnings: string[];

  ingredients: RecipeIngredient[];

  is_owner: boolean;
  is_saved: boolean;
  author_name: string | null;
  forked_from_id: string | null;
  save_count: number;
  log_count: number;
  created_at: string;
  updated_at: string;
}

export interface RecipeSummary {
  id: string;
  name: string;
  cuisine: string | null;
  photo_url: string | null;
  visibility: RecipeVisibility;
  servings: number;
  calories_per_serving: number;
  protein_per_serving_g: number;
  ingredient_count: number;
  yield_estimated: boolean;
  author_name: string | null;
  is_owner: boolean;
  is_saved: boolean;
  save_count: number;
  log_count: number;
  updated_at: string;
}

export interface RecipeListResponse {
  recipes: RecipeSummary[];
  total: number;
}

/** One line of a recipe being edited. Mirrors RecipeIngredientInput. */
export interface RecipeDraftIngredient {
  food_item_id?: string | null;
  display_name: string;
  grams: number;
  quantity_label?: string | null;
  note?: string | null;
  /** Ignored by the server when `food_item_id` is set. */
  calories?: number;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
  fiber_g?: number;
}

export interface RecipeDraft {
  name: string;
  description?: string | null;
  cuisine?: string | null;
  photo_url?: string | null;
  servings: number;
  cooked_weight_g?: number | null;
  prep_minutes?: number | null;
  cook_minutes?: number | null;
  steps: string[];
  tags: string[];
  visibility: RecipeVisibility;
  ingredients: RecipeDraftIngredient[];
}

/**
 * Why a recipe can or cannot be published.
 *
 * `blockers` are hard stops. `cautions` are shown but never prevent the
 * publish — they are the difference between "this is broken" and "you could
 * make this better", and conflating the two trains people to ignore both.
 */
export interface PublishCheck {
  ok: boolean;
  blockers: string[];
  cautions: string[];
}
