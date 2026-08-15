/**
 * Jest setup: mock the native modules the API client touches.
 *
 * Without these, importing src/lib/api.ts explodes in Node because
 * AsyncStorage and SecureStore are native modules with no JS fallback.
 */
jest.mock('@react-native-async-storage/async-storage', () => {
  const store = new Map();
  return {
    __esModule: true,
    default: {
      setItem: jest.fn(async (k, v) => void store.set(k, v)),
      getItem: jest.fn(async (k) => store.get(k) ?? null),
      removeItem: jest.fn(async (k) => void store.delete(k)),
      clear: jest.fn(async () => store.clear()),
    },
  };
});

jest.mock('expo-secure-store', () => {
  const store = new Map();
  return {
    setItemAsync: jest.fn(async (k, v) => void store.set(k, v)),
    getItemAsync: jest.fn(async (k) => store.get(k) ?? null),
    deleteItemAsync: jest.fn(async (k) => void store.delete(k)),
  };
});

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  selectionAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success' },
}));

// The app reads this at module load and throws if it's unset.
process.env.EXPO_PUBLIC_API_URL = 'https://test.invalid';
