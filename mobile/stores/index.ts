/**
 * Global state stores using Zustand
 */

import { create } from 'zustand';
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
} from '@/services/api';

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
}

export const useMetersStore = create<MetersState>((set, get) => ({
  meters: [],
  selectedMeter: null,
  isLoading: false,
  error: null,

  fetchMeters: async () => {
    set({ isLoading: true, error: null });
    try {
      const meters = await metersApi.list();
      set({
        meters,
        selectedMeter: get().selectedMeter || meters[0] || null,
        isLoading: false,
      });
    } catch (error: unknown) {
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },

  selectMeter: (meter) => set({ selectedMeter: meter }),

  deleteMeter: async (meterId) => {
    try {
      await metersApi.delete(meterId);
      const meters = get().meters.filter((m) => m.id !== meterId);
      set({
        meters,
        selectedMeter: get().selectedMeter?.id === meterId ? meters[0] || null : get().selectedMeter,
      });
    } catch (error: unknown) {
      set({ error: getErrorMessage(error) });
    }
  },
}));

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
}

export const useUsageStore = create<UsageState>((set) => ({
  summary: null,
  dailyUsage: [],
  hourlyUsage: [],
  isLoading: false,
  error: null,

  fetchSummary: async (meterId) => {
    try {
      const summary = await usageApi.getSummary(meterId);
      set({ summary });
    } catch (error: unknown) {
      set({ error: getErrorMessage(error) });
    }
  },

  fetchDaily: async (meterId, days = 30) => {
    try {
      const dailyUsage = await usageApi.getDaily(meterId, days);
      set({ dailyUsage });
    } catch (error: unknown) {
      set({ error: getErrorMessage(error) });
    }
  },

  fetchHourly: async (meterId) => {
    try {
      const hourlyUsage = await usageApi.getHourly(meterId);
      set({ hourlyUsage });
    } catch (error: unknown) {
      set({ error: getErrorMessage(error) });
    }
  },

  fetchAllUsageData: async (meterId) => {
    set({ isLoading: true, error: null });
    try {
      const [summary, dailyUsage, hourlyUsage] = await Promise.all([
        usageApi.getSummary(meterId),
        usageApi.getDaily(meterId, 30),
        usageApi.getHourly(meterId),
      ]);
      set({ summary, dailyUsage, hourlyUsage, isLoading: false });
    } catch (error: unknown) {
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },
}));

// Recommendations Store
interface RecommendationsState {
  recommendations: Recommendation[];
  totalSavings: number | null;
  isLoading: boolean;
  error: string | null;

  fetchRecommendations: (meterId?: number) => Promise<void>;
}

export const useRecommendationsStore = create<RecommendationsState>((set) => ({
  recommendations: [],
  totalSavings: null,
  isLoading: false,
  error: null,

  fetchRecommendations: async (meterId) => {
    set({ isLoading: true, error: null });
    try {
      const response = meterId
        ? await recommendationsApi.getForMeter(meterId)
        : await recommendationsApi.getAll();
      set({
        recommendations: response.recommendations,
        totalSavings: response.total_potential_savings,
        isLoading: false,
      });
    } catch (error: unknown) {
      set({
        error: getErrorMessage(error),
        isLoading: false,
      });
    }
  },
}));
