/**
 * Global state stores using Zustand
 */

import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  User,
  Meter,
  UsageSummary,
  DailyUsage,
  HourlyUsage,
  Recommendation,
  authApi,
  metersApi,
  usageApi,
  recommendationsApi,
  getToken,
  removeToken,
  removeRefreshToken,
  getErrorMessage,
  setAuthExpiredHandler,
} from '@/services/api';

let accountDataEpoch = 0;

// Auth Store
interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,

  login: async (email, password) => {
    resetAccountScopedData();
    set({ isLoading: true, error: null });
    try {
      await authApi.login(email, password);
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (error: unknown) {
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
      throw error;
    }
  },

  register: async (email, password, fullName) => {
    resetAccountScopedData();
    set({ isLoading: true, error: null });
    try {
      await authApi.register(email, password, fullName);
      // Auto-login after registration
      await authApi.login(email, password);
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (error: unknown) {
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
      throw error;
    }
  },

  logout: async () => {
    await removeToken();
    await removeRefreshToken();
    resetAccountScopedData();
    set({ user: null, isAuthenticated: false });
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const token = await getToken();
      if (token) {
        const user = await authApi.getMe();
        set({ user, isAuthenticated: true, isLoading: false });
      } else {
        set({ isLoading: false });
      }
    } catch {
      await removeToken();
      await removeRefreshToken();
      resetAccountScopedData();
      set({ isLoading: false, isAuthenticated: false });
    }
  },

  clearError: () => set({ error: null }),
}));

// Meters Store
interface MetersState {
  meters: Meter[];
  selectedMeter: Meter | null;
  isLoading: boolean;
  error: string | null;

  fetchMeters: () => Promise<void>;
  selectMeter: (meter: Meter) => void;
  deleteMeter: (meterId: number) => Promise<void>;
  clearMeters: () => void;
}

const selectedMeterStorageKey = (userId: number) => `gridsense_selected_meter_${userId}`;

export const useMetersStore = create<MetersState>((set, get) => ({
  meters: [],
  selectedMeter: null,
  isLoading: false,
  error: null,

  fetchMeters: async () => {
    const requestEpoch = accountDataEpoch;
    set({ isLoading: true, error: null });
    try {
      const meters = await metersApi.list();
      if (requestEpoch !== accountDataEpoch) return;
      const userId = useAuthStore.getState().user?.id;
      let savedMeterId: number | null = null;
      if (userId) {
        try {
          const storedId = await AsyncStorage.getItem(selectedMeterStorageKey(userId));
          if (requestEpoch !== accountDataEpoch) return;
          savedMeterId = storedId ? Number(storedId) : null;
        } catch (error: unknown) {
          if (requestEpoch !== accountDataEpoch) return;
          set({ error: `Could not restore the saved meter selection: ${getErrorMessage(error)}` });
        }
      }
      if (requestEpoch !== accountDataEpoch) return;
      const currentMeterId = get().selectedMeter?.id;
      const selectedMeter =
        meters.find((meter) => meter.id === currentMeterId) ??
        meters.find((meter) => meter.id === savedMeterId) ??
        meters[0] ??
        null;
      set({
        meters,
        selectedMeter,
        isLoading: false,
      });
      if (userId && selectedMeter) {
        await AsyncStorage.setItem(selectedMeterStorageKey(userId), String(selectedMeter.id));
      }
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },

  selectMeter: (meter) => {
    set({ selectedMeter: meter, error: null });
    const userId = useAuthStore.getState().user?.id;
    if (userId) {
      void AsyncStorage.setItem(selectedMeterStorageKey(userId), String(meter.id)).catch(
        (error: unknown) =>
          set({ error: `Could not save the selected meter: ${getErrorMessage(error)}` })
      );
    }
  },

  deleteMeter: async (meterId) => {
    const requestEpoch = accountDataEpoch;
    try {
      await metersApi.delete(meterId);
      if (requestEpoch !== accountDataEpoch) return;
      const meters = get().meters.filter((m) => m.id !== meterId);
      const selectedMeter =
        get().selectedMeter?.id === meterId ? meters[0] || null : get().selectedMeter;
      set({
        meters,
        selectedMeter,
      });
      const userId = useAuthStore.getState().user?.id;
      if (userId && selectedMeter) {
        await AsyncStorage.setItem(selectedMeterStorageKey(userId), String(selectedMeter.id));
      }
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({ error: getErrorMessage(error) });
    }
  },

  clearMeters: () =>
    set({ meters: [], selectedMeter: null, isLoading: false, error: null }),
}));

setAuthExpiredHandler(() => {
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    error: 'Your session expired. Please sign in again.',
  });
  resetAccountScopedData();
});

// Usage Store
interface UsageState {
  summary: UsageSummary | null;
  dailyUsage: DailyUsage[];
  hourlyUsage: HourlyUsage[];
  isLoading: boolean;
  error: string | null;

  fetchSummary: (meterId: number) => Promise<void>;
  fetchDaily: (meterId: number, days?: number) => Promise<void>;
  fetchHourly: (meterId: number) => Promise<void>;
  fetchAllUsageData: (meterId: number) => Promise<void>;
  clearUsage: () => void;
}

export const useUsageStore = create<UsageState>((set) => ({
  summary: null,
  dailyUsage: [],
  hourlyUsage: [],
  isLoading: false,
  error: null,

  fetchSummary: async (meterId) => {
    const requestEpoch = accountDataEpoch;
    try {
      const summary = await usageApi.getSummary(meterId);
      if (requestEpoch !== accountDataEpoch) return;
      set({ summary });
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({ error: getErrorMessage(error) });
    }
  },

  fetchDaily: async (meterId, days = 30) => {
    const requestEpoch = accountDataEpoch;
    try {
      const dailyUsage = await usageApi.getDaily(meterId, days);
      if (requestEpoch !== accountDataEpoch) return;
      set({ dailyUsage });
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({ error: getErrorMessage(error) });
    }
  },

  fetchHourly: async (meterId) => {
    const requestEpoch = accountDataEpoch;
    try {
      const hourlyUsage = await usageApi.getHourly(meterId);
      if (requestEpoch !== accountDataEpoch) return;
      set({ hourlyUsage });
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({ error: getErrorMessage(error) });
    }
  },

  fetchAllUsageData: async (meterId) => {
    const requestEpoch = accountDataEpoch;
    set({ isLoading: true, error: null });
    try {
      const [summary, dailyUsage, hourlyUsage] = await Promise.all([
        usageApi.getSummary(meterId),
        usageApi.getDaily(meterId, 30),
        usageApi.getHourly(meterId),
      ]);
      if (requestEpoch !== accountDataEpoch) return;
      set({ summary, dailyUsage, hourlyUsage, isLoading: false });
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },

  clearUsage: () =>
    set({
      summary: null,
      dailyUsage: [],
      hourlyUsage: [],
      isLoading: false,
      error: null,
    }),
}));

// Recommendations Store
interface RecommendationsState {
  recommendations: Recommendation[];
  totalSavings: number | null;
  isLoading: boolean;
  error: string | null;

  fetchRecommendations: (meterId?: number) => Promise<void>;
  clearRecommendations: () => void;
}

export const useRecommendationsStore = create<RecommendationsState>((set) => ({
  recommendations: [],
  totalSavings: null,
  isLoading: false,
  error: null,

  fetchRecommendations: async (meterId) => {
    const requestEpoch = accountDataEpoch;
    set({ isLoading: true, error: null });
    try {
      const response = meterId
        ? await recommendationsApi.getForMeter(meterId)
        : await recommendationsApi.getAll();
      if (requestEpoch !== accountDataEpoch) return;
      set({
        recommendations: response.recommendations,
        totalSavings: response.total_potential_savings,
        isLoading: false,
      });
    } catch (error: unknown) {
      if (requestEpoch !== accountDataEpoch) return;
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },
  clearRecommendations: () =>
    set({
      recommendations: [],
      totalSavings: null,
      isLoading: false,
      error: null,
    }),
}));

function resetAccountScopedData(): void {
  accountDataEpoch += 1;
  useMetersStore.getState().clearMeters();
  useUsageStore.getState().clearUsage();
  useRecommendationsStore.getState().clearRecommendations();
}
