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
  };
}

export const api = {
  health: () => request<{ status: string }>('/health', { auth: false }),

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

  searchFoods: (q: string, country?: string) =>
    request<{ results: FoodItem[]; took_ms: number; source: string }>(
      `/api/foods/search?q=${encodeURIComponent(q)}${country ? `&country=${country}` : ''}`,
    ),

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
      timeoutMs: 30_000, // vision calls are slower than CRUD
    });
  },

  logMeal: (payload: Record<string, unknown>) =>
    request('/api/meals/log', { method: 'POST', body: payload }),

  dailySummary: (date: string) => request<DailySummary>(`/api/meals/daily?date=${date}`),

  logWeight: (weight_kg: number, measured_on?: string) =>
    request('/api/weight/log', { method: 'POST', body: { weight_kg, measured_on } }),

  weightTrend: (days = 90) =>
    request<Array<{ date: string; raw_kg: number | null; trend_kg: number }>>(
      `/api/weight/trend?days=${days}`,
    ),

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
};

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
  calorie_target: number | null;
  protein_target_g: number | null;
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
