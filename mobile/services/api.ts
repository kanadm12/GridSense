/**
 * API client for GridSense backend
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

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
  estimated_total_cost: number;
  estimated_daily_cost: number;
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
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  total_potential_savings: number | null;
}

export interface UploadResponse {
  message: string;
  meters_created: number;
  meters_updated: number;
  readings_imported: number;
  warnings: string[];
  errors: string[];
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
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
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
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // If 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
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
        const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
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
  await SecureStore.setItemAsync(TOKEN_KEY, token);
};

export const getToken = async () => {
  return SecureStore.getItemAsync(TOKEN_KEY);
};

export const removeToken = async () => {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
};

export const setRefreshToken = async (token: string) => {
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token);
};

export const getRefreshToken = async () => {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
};

export const removeRefreshToken = async () => {
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
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

// Upload API
export const uploadApi = {
  uploadNem12: async (fileUri: string, fileName: string) => {
    const formData = new FormData();
    formData.append('file', {
      uri: fileUri,
      name: fileName,
      type: 'text/csv',
    } as any);

    const response = await api.post<UploadResponse>('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
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

export default api;
