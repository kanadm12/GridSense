/**
 * API client for GridSense backend
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

// Configuration - use device's localhost for simulators, or computer's IP for physical devices
const getApiUrl = () => {
  // Check if running on web
  const runtimeWindow = (globalThis as {
    window?: { location?: { hostname?: string } };
  }).window;
  if (runtimeWindow?.location?.hostname) {
    return `http://${runtimeWindow.location.hostname}:8000/api/v1`;
  }
  // For Expo Go on physical device, use the computer's IP
  const debuggerHost = Constants.expoConfig?.hostUri || Constants.manifest2?.extra?.expoGo?.debuggerHost;
  if (debuggerHost) {
    const host = debuggerHost.split(':')[0];
    return `http://${host}:8000/api/v1`;
  }
  // Fallback
  return process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
};

const API_URL = getApiUrl();
const TOKEN_KEY = 'gridsense_token';
const REFRESH_TOKEN_KEY = 'gridsense_refresh_token';

/**
 * Platform-aware token storage.
 *
 * expo-secure-store is a native module (iOS Keychain / Android Keystore) and
 * has no web implementation — its methods are undefined on web, so any call
 * throws "ExpoSecureStore.default.* is not a function". Web has no secure
 * enclave, so fall back to AsyncStorage (localStorage-backed) there while
 * keeping the real secure store on native.
 */
const secureStorage = {
  getItem: (key: string): Promise<string | null> =>
    Platform.OS === 'web' ? AsyncStorage.getItem(key) : SecureStore.getItemAsync(key),
  setItem: (key: string, value: string): Promise<void> =>
    Platform.OS === 'web' ? AsyncStorage.setItem(key, value) : SecureStore.setItemAsync(key, value),
  removeItem: (key: string): Promise<void> =>
    Platform.OS === 'web' ? AsyncStorage.removeItem(key) : SecureStore.deleteItemAsync(key),
};

// Types
export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
}

export interface Meter {
  id: number;
  nmi: string;
  meter_serial: string | null;
  suffix: string | null;
  unit_of_measure: string;
  interval_minutes: number;
  state: string;
  postcode: string | null;
  name: string | null;
  created_at: string;
}

export interface TariffPeriodV1 {
  name: string;
  start_minute: number;
  end_minute: number;
  rate_cents_kwh: number;
  days: number[];
}

export interface UserTariff {
  id: number;
  user_id: number;
  tariff_type: 'flat' | 'tou' | 'demand' | 'flexible';
  retailer_name: string | null;
  flat_rate_cents_kwh: number | null;
  peak_rate_cents_kwh: number | null;
  off_peak_rate_cents_kwh: number | null;
  shoulder_rate_cents_kwh: number | null;
  feed_in_rate_cents_kwh: number | null;
  periods: TariffPeriodV1[] | null;
  effective_from: string | null;
  effective_to: string | null;
  rates_include_gst: boolean;
  is_preset: boolean;
  demand_charge_dollars_kw: number | null;
  daily_supply_charge_cents: number;
}

export interface DailyUsage {
  date: string;
  total_kwh: number;
  peak_kwh: number;
  off_peak_kwh: number;
  shoulder_kwh: number;
  max_interval_kwh: number;
  estimated_cost: number | null;
}

export interface HourlyUsage {
  hour: number;
  avg_kwh: number;
  total_kwh: number;
  reading_count: number;
}

export interface WeeklyUsage {
  day_of_week: number;
  day_name: string;
  avg_kwh: number;
  total_kwh: number;
}

export interface UsageSummary {
  meter_id: number;
  meter_name: string | null;
  nmi: string;
  start_date: string;
  end_date: string;
  days_count: number;
  total_kwh: number;
  avg_daily_kwh: number;
  max_daily_kwh: number;
  min_daily_kwh: number;
  peak_hour: number;
  peak_avg_kwh: number;
  off_peak_percentage: number;
  estimated_total_cost: number | null;
  estimated_daily_cost: number | null;
}

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  category: string;
  priority: 'high' | 'medium' | 'low';
  potential_savings_kwh: number | null;
  potential_savings_dollars: number | null;
  action: string;
  reason: string;
  observed_fact: string;
  proposed_action: string;
  conditional_opportunity: string;
  estimate_status: 'unquantified' | 'conditional_estimate';
  baseline: string;
  assumptions: string[];
  rate_difference_cents_kwh: number | null;
  applicable_intervals: string;
  uncertainty: string;
  confidence: 'low' | 'medium' | 'high';
  data_requirements: string[];
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  total_potential_savings: number | null;
  tariff_status:
    | 'missing'
    | 'illustrative'
    | 'outside_effective_dates'
    | 'missing_rates'
    | 'configured';
}

export interface BaselineIntervalV1 {
  interval_start: string;
  demand_kw: number;
}

export type FixedBaselineProfileV1 =
  | {
      source: 'synthetic';
      profile_id: string;
      measurement_method: null;
      scenario_id: string;
      includes_scheduled_tasks: false;
      intervals: BaselineIntervalV1[];
    }
  | {
      source: 'independently_measured';
      profile_id: string;
      measurement_method: 'submeter' | 'validated_disaggregation';
      scenario_id?: string | null;
      includes_scheduled_tasks: false;
      intervals: BaselineIntervalV1[];
    };

export interface ApplianceTaskV1Fields {
  task_id: string;
  appliance: string;
  duration_minutes: number;
  earliest_start: string;
  deadline: string;
  preferred_start: string | null;
}

type ApplianceTaskEnergyV1 =
  | { rated_power_kw: number; energy_kwh?: null }
  | { rated_power_kw?: null; energy_kwh: number };

export type ApplianceTaskV1 = ApplianceTaskV1Fields &
  ApplianceTaskEnergyV1 &
  { mandatory: boolean; omission_penalty_aud?: number | null };

export interface SchedulingRequestV1 {
  schema_version: '1.0';
  meter_id: number;
  tariff_id?: number | null;
  scenario_id: string;
  interval_minutes: 5 | 15 | 30 | 60;
  timezone: string;
  currency: 'AUD';
  preference_penalty_aud_per_interval?: number;
  household_power_limit_kw?: number | null;
  grid_power_limit_kw?: number | null;
  tasks: ApplianceTaskV1[];
  baseline_profile: FixedBaselineProfileV1;
}

export type SchedulingStatusV1 =
  | 'blocked'
  | 'not_evaluated'
  | 'feasible'
  | 'infeasible'
  | 'timeout';
export type TariffResolutionStatusV1 =
  | 'configured'
  | 'missing'
  | 'illustrative'
  | 'outside_effective_dates'
  | 'missing_rates';

export interface ScheduledTaskV1 {
  task_id: string;
  start?: string | null;
  end?: string | null;
  power_kw: number | null;
  energy_kwh: number | null;
  omitted: boolean;
}

export interface ScheduleV1 {
  status: 'feasible' | 'not_found';
  method: 'milp' | 'deterministic_greedy';
  reason?: string | null;
  tasks: ScheduledTaskV1[];
  total_energy_kwh: number | null;
  total_cost_aud: number | null;
}

export interface SchedulingResponseV1 {
  schema_version: '1.0';
  scenario_id: string;
  meter_id: number;
  status: SchedulingStatusV1;
  tariff: {
    tariff_id?: number | null;
    status: TariffResolutionStatusV1;
    currency: 'AUD';
  };
  objective_breakdown?: {
    currency: 'AUD';
    baseline_energy_cost_aud?: number | null;
    candidate_energy_cost_aud?: number | null;
    reference_energy_cost_aud?: number | null;
    energy_cost_delta_aud?: number | null;
    preference_penalty_aud?: number | null;
    omission_penalty_aud?: number | null;
    total_objective_aud?: number | null;
    reference_preference_penalty_aud?: number | null;
    reference_omission_penalty_aud?: number | null;
    reference_objective_aud?: number | null;
  } | null;
  candidate_schedule?: ScheduleV1 | null;
  reference_schedule?: ScheduleV1 | null;
  assumptions: string[];
  blockers: string[];
}

export interface UploadResponse {
  message: string;
  meters_created: number;
  meters_updated: number;
  readings_imported: number;
  warnings: string[];
  errors: string[];
}

/** POST /upload now returns immediately and processes in the background. */
export interface UploadAccepted {
  upload_id: number;
  message: string;
}

export type UploadStatusValue = 'pending' | 'processing' | 'completed' | 'failed';

/** Shape of GET /upload/{id} while/after the background import runs. */
export interface UploadStatus {
  id: number;
  status: UploadStatusValue;
  progress_percent: number;
  total_readings: number | null;
  errors: string[];
  warnings: string[];
  processed_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiError {
  detail: string;
}

/**
 * Helper to extract error message from Axios errors
 */
export const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    return axiosError.response?.data?.detail || axiosError.message || 'An error occurred';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unknown error occurred';
};

// Track if we're currently refreshing to avoid multiple refresh attempts
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];
let authExpiredHandler: (() => void) | null = null;

export const setAuthExpiredHandler = (handler: (() => void) | null) => {
  authExpiredHandler = handler;
};

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await secureStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;
    const isAuthRequest = ['/auth/login', '/auth/register', '/auth/refresh'].some((path) =>
      originalRequest?.url?.endsWith(path)
    );

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && originalRequest && !isAuthRequest && !originalRequest._retry) {
      if (isRefreshing) {
        // Wait for the refresh to complete
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshToken = await secureStorage.getItem(REFRESH_TOKEN_KEY);
        if (!refreshToken) {
          throw new Error('No refresh token available');
        }

        // Try to refresh the token
        const response = await axios.post<AuthResponse>(`${API_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token, refresh_token: newRefreshToken } = response.data;
        await setToken(access_token);
        await setRefreshToken(newRefreshToken);

        processQueue(null, access_token);
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        // Clear tokens and let the app handle re-authentication
        await removeToken();
        await removeRefreshToken();
        authExpiredHandler?.();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// Token management
export const setToken = async (token: string) => {
  await secureStorage.setItem(TOKEN_KEY, token);
};

export const getToken = async () => {
  return secureStorage.getItem(TOKEN_KEY);
};

export const removeToken = async () => {
  await secureStorage.removeItem(TOKEN_KEY);
};

export const setRefreshToken = async (token: string) => {
  await secureStorage.setItem(REFRESH_TOKEN_KEY, token);
};

export const getRefreshToken = async () => {
  return secureStorage.getItem(REFRESH_TOKEN_KEY);
};

export const removeRefreshToken = async () => {
  await secureStorage.removeItem(REFRESH_TOKEN_KEY);
};

// Auth API
export const authApi = {
  register: async (email: string, password: string, fullName?: string) => {
    const response = await api.post<User>('/auth/register', {
      email,
      password,
      full_name: fullName,
    });
    return response.data;
  },

  login: async (email: string, password: string) => {
    const response = await api.post<AuthResponse>('/auth/login', {
      email,
      password,
    });
    await setToken(response.data.access_token);
    await setRefreshToken(response.data.refresh_token);
    return response.data;
  },

  logout: async () => {
    await removeToken();
    await removeRefreshToken();
  },

  getMe: async () => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  refreshToken: async () => {
    const refreshToken = await getRefreshToken();
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }
    const response = await axios.post<AuthResponse>(`${API_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    await setToken(response.data.access_token);
    await setRefreshToken(response.data.refresh_token);
    return response.data;
  },
};

// Meters API
export const metersApi = {
  list: async () => {
    const response = await api.get<Meter[]>('/meters');
    return response.data;
  },

  get: async (meterId: number) => {
    const response = await api.get<Meter>(`/meters/${meterId}`);
    return response.data;
  },

  delete: async (meterId: number) => {
    await api.delete(`/meters/${meterId}`);
  },
};

export const tariffsApi = {
  getMine: async () => {
    const response = await api.get<UserTariff | null>('/tariffs');
    return response.data;
  },
};

// Upload API
export const uploadApi = {
  uploadNem12: async (fileUri: string, fileName: string): Promise<UploadAccepted> => {
    const formData = new FormData();

    if (Platform.OS === 'web') {
      // On web, expo-document-picker gives a blob: URL. Fetch it into a real
      // Blob so multipart carries the actual file bytes — appending a plain
      // { uri, name, type } object (the React Native convention) would stringify
      // to "[object Object]" and the server would reject it with HTTP 422.
      const blob = await (await fetch(fileUri)).blob();
      formData.append('file', blob, fileName);

      // Setting Content-Type to undefined lets the browser generate the correct
      // `multipart/form-data; boundary=...` header. Our axios instance defaults
      // to application/json, which would otherwise break the upload.
      const response = await api.post<UploadAccepted>('/upload', formData, {
        headers: { 'Content-Type': undefined } as never,
      });
      return response.data;
    }

    // Native (iOS/Android): React Native's FormData accepts the file descriptor.
    formData.append('file', {
      uri: fileUri,
      name: fileName,
      type: 'text/csv',
    } as any);

    const response = await api.post<UploadAccepted>('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getStatus: async (uploadId: number): Promise<UploadStatus> => {
    const response = await api.get<UploadStatus>(`/upload/${uploadId}`);
    return response.data;
  },
};

// Usage API
export const usageApi = {
  getSummary: async (meterId: number, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await api.get<UsageSummary>(
      `/usage/summary/${meterId}?${params.toString()}`
    );
    return response.data;
  },

  getDaily: async (meterId: number, limit = 30, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await api.get<DailyUsage[]>(
      `/usage/daily/${meterId}?${params.toString()}`
    );
    return response.data;
  },

  getHourly: async (meterId: number, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await api.get<HourlyUsage[]>(
      `/usage/hourly/${meterId}?${params.toString()}`
    );
    return response.data;
  },

  getWeekly: async (meterId: number, startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await api.get<WeeklyUsage[]>(
      `/usage/weekly/${meterId}?${params.toString()}`
    );
    return response.data;
  },
};

// Recommendations API
export const recommendationsApi = {
  getForMeter: async (meterId: number) => {
    const response = await api.get<RecommendationsResponse>(
      `/recommendations/${meterId}`
    );
    return response.data;
  },

  getAll: async () => {
    const response = await api.get<RecommendationsResponse>('/recommendations');
    return response.data;
  },
};

export const schedulingApi = {
  previewV1: async (request: SchedulingRequestV1) => {
    const response = await api.post<SchedulingResponseV1>(
      '/scheduling/v1/plans/preview',
      request
    );
    return response.data;
  },
};

export default api;
