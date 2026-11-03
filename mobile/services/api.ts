/**
 * API client for GridSense backend
 */

import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
  create,
  isAxiosError,
} from 'axios';
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
  mdm_data_stream_identifier?: string | null;
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
  revision_number: number | null;
  confirmed_at: string | null;
  confirmation_source: string | null;
  is_confirmed: boolean;
  unsupported_components: string[];
}

export interface TariffRevision {
  id: number;
  tariff_id: number;
  revision_number: number;
  source_type: string;
  source_plan_id: string | null;
  confirmed_at: string | null;
  effective_from: string | null;
  effective_to: string | null;
  tariff_type: UserTariff['tariff_type'];
  retailer_name: string | null;
  flat_rate_cents_kwh: number | null;
  peak_rate_cents_kwh: number | null;
  off_peak_rate_cents_kwh: number | null;
  shoulder_rate_cents_kwh: number | null;
  feed_in_rate_cents_kwh: number | null;
  periods: TariffPeriodV1[] | null;
  rates_include_gst: boolean;
  demand_charge_dollars_kw: number | null;
  daily_supply_charge_cents: number | null;
  unsupported_components: string[];
  is_illustrative: boolean;
  created_at: string;
}

export interface AERRetailer {
  retailer: string;
  brand: string;
  base_uri: string;
}

export interface AERPlanSummary {
  plan_id: string;
  brand: string;
  brand_name: string | null;
  display_name: string;
  plan_type: string | null;
  fuel_type: string;
  effective_from: string | null;
  effective_to: string | null;
  last_updated: string | null;
  customer_type: string | null;
  included_postcodes: string[];
  distributors: string[];
  requested_postcode: string;
  source_api_version: number;
  source_registry_version: string;
  retrieved_at: string;
  source_url: string;
}

export interface AERPlanDetail {
  plan_id: string;
  brand: string;
  brand_name: string | null;
  display_name: string | null;
  effective_from: string | null;
  effective_to: string | null;
  last_updated: string | null;
  source_api_version: number;
  source_registry_version: string;
  retrieved_at: string;
  terms: Record<string, unknown>;
  unsupported_components: string[];
  requires_manual_user_review: boolean;
  source_url: string;
}

export interface AERRetailerCatalog {
  source: string;
  document_version: string;
  source_url: string;
  source_last_updated: string;
  retailers: AERRetailer[];
}

export interface ProviderFreshness {
  provider: 'open_meteo' | 'aemo_nemweb' | string;
  source_version: string;
  status:
    | 'valid'
    | 'stale'
    | 'unavailable'
    | 'malformed'
    | 'unauthorized'
    | 'rate_limited'
    | 'blocked';
  configured: boolean;
  retrieved_at: string | null;
  fresh_until: string | null;
  last_successful_fetch_at: string | null;
  error_code: string | null;
  retry_after: string | null;
  attribution: string | null;
  attribution_url: string | null;
}

export interface WeatherForecastHour {
  source_time_label: string;
  target_time_utc: string;
  interval_start_utc: string | null;
  interval_end_utc: string | null;
  time_semantics: string;
  interval_semantics_field: string | null;
  temperature_2m: number | null;
  apparent_temperature: number | null;
  relative_humidity: number | null;
  cloud_cover: number | null;
  shortwave_radiation: number | null;
  source_units: Record<string, string>;
  normalized_units: Record<string, string>;
}

export interface WeatherForecastResponse {
  provider: ProviderFreshness;
  data_kind: 'forecast';
  latitude: number | null;
  longitude: number | null;
  timezone: string;
  forecast_issued_at: string | null;
  issue_time_available: boolean;
  model_selection: string | null;
  provider_metadata: Record<string, unknown>;
  hourly: WeatherForecastHour[];
}

export interface MarketContextResponse {
  provider: ProviderFreshness;
  region: string;
  data_kind: 'observed' | 'forecast' | 'simulated';
  price_aud_mwh: number | null;
  demand_mw: number | null;
  target_time_utc: string | null;
  interval_start_utc: string | null;
  interval_end_utc: string | null;
  message: string;
}

export interface DailyUsage {
  date: string;
  observed_eligible_kwh: number;
  total_kwh: number;
  peak_kwh: number;
  off_peak_kwh: number;
  shoulder_kwh: number;
  max_interval_kwh: number;
  estimated_cost: number | null;
  expected_interval_count: number;
  observed_interval_count: number;
  eligible_interval_count: number;
  missing_interval_count: number;
  excluded_quality_count: number;
  unresolved_direction_count: number;
  legacy_direction_unverified_count: number;
  duplicate_interval_count: number;
  invalid_interval_count: number;
  invalid_unit_count: number;
  coverage_fraction: number;
  coverage_status: string;
  provenance_status: string;
  observed_interval_average_demand_kw: number | null;
  observed_interval_peak_demand_kw: number | null;
  full_period_average_demand_kw: number | null;
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
  complete_day_count: number;
  coverage_status: string;
}

export interface UsageSummary {
  meter_id: number;
  meter_name: string | null;
  nmi: string;
  start_date: string;
  end_date: string;
  days_count: number;
  total_kwh: number;
  avg_daily_kwh: number | null;
  max_daily_kwh: number | null;
  min_daily_kwh: number | null;
  peak_hour: number | null;
  peak_avg_kwh: number | null;
  off_peak_percentage: number | null;
  estimated_total_cost: number | null;
  estimated_daily_cost: number | null;
  eligible_import_kwh: number;
  eligible_export_kwh: number;
  net_grid_kwh: number | null;
  expected_interval_count: number;
  observed_interval_count: number;
  eligible_interval_count: number;
  missing_interval_count: number;
  excluded_quality_count: number;
  unresolved_direction_count: number;
  legacy_direction_unverified_count: number;
  duplicate_interval_count: number;
  invalid_interval_count: number;
  invalid_unit_count: number;
  unresolved_time_basis_count: number;
  coverage_fraction: number;
  coverage_status: string;
  provenance_status: string;
  channel_classification_status: string;
  explanation: string | null;
  observed_interval_average_demand_kw: number | null;
  observed_interval_peak_demand_kw: number | null;
  full_period_average_demand_kw: number | null;
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
  status:
    | 'validated'
    | 'estimated'
    | 'illustrative'
    | 'unquantified'
    | 'unavailable'
    | 'expired'
    | 'no_supported_action';
  calculation_evidence: CalculationEvidence | null;
}

export interface CalculationEvidence {
  schema_version: '1.0';
  recommendation_id: string;
  rule_id: string;
  rule_version: string;
  owner_user_id: number;
  meter_id: number;
  created_at: string;
  expires_at: string;
  status: Recommendation['status'];
  analysis_start_date: string | null;
  analysis_end_date: string | null;
  input_references: string[];
  input_record_count: number;
  input_digest_sha256: string | null;
  provenance_counts: Record<string, number>;
  coverage: {
    expected_intervals: number;
    eligible_intervals: number;
    missing_intervals: number;
    excluded_quality_intervals: number;
    unresolved_direction_intervals: number;
    legacy_direction_unverified_intervals: number;
    unresolved_time_basis_intervals: number;
    duplicate_intervals: number;
    invalid_intervals: number;
    coverage_fraction: number;
    coverage_status: string;
    provenance_status: string;
  };
  eligibility_checks: Record<string, string>;
  tariff_revision_id: number | null;
  baseline_scenario: string;
  proposed_scenario: string;
  calculation_method_version: string;
  calculated_values: Record<string, number>;
  value_units: Record<string, string>;
  energy_difference_kwh: number | null;
  financial_difference_aud: number | null;
  rounding_rule: string;
  assumptions: string[];
  limitations: string[];
  invalidation_conditions: string[];
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
  method: 'milp' | 'deterministic_greedy' | 'preferred';
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
    preferred_energy_cost_aud?: number | null;
    milp_vs_preferred_energy_cost_delta_aud?: number | null;
    greedy_vs_preferred_energy_cost_delta_aud?: number | null;
  } | null;
  candidate_schedule?: ScheduleV1 | null;
  reference_schedule?: ScheduleV1 | null;
  preferred_schedule?: ScheduleV1 | null;
  baseline_eligibility: {
    status: 'eligible_synthetic' | 'eligible_measured' | 'unavailable';
    source: 'synthetic' | 'independently_measured';
    eligible_for_costed_preview: boolean;
    explanation: string;
  };
  calculation_evidence: CalculationEvidence & {
    task_set_digest_sha256: string;
    tariff_revision_ids: number[];
    tariff_effective_from: string | null;
    tariff_effective_to: string | null;
    baseline_source_classification: string;
    formulas: Record<string, string>;
    formula_inputs: Record<string, number>;
    scenario_values: Record<string, Record<string, number | null>>;
  };
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
  detail?: unknown;
  error?: unknown;
  details?: unknown;
}

const extractApiErrorMessage = (payload: unknown): string | undefined => {
  if (typeof payload !== 'object' || payload === null) return undefined;
  const response = payload as Record<string, unknown>;
  if (typeof response.detail === 'string') return response.detail;

  const summary = typeof response.error === 'string' ? response.error : undefined;
  const entries = Array.isArray(response.details)
    ? response.details
    : Array.isArray(response.detail)
      ? response.detail
      : [];
  const messages = entries.flatMap((entry) => {
    if (typeof entry !== 'object' || entry === null) return [];
    const detail = entry as Record<string, unknown>;
    const message =
      typeof detail.message === 'string'
        ? detail.message
        : typeof detail.msg === 'string'
          ? detail.msg
          : null;
    if (!message) return [];

    const field =
      typeof detail.field === 'string'
        ? detail.field
        : Array.isArray(detail.loc)
          ? detail.loc.map(String).join('.')
          : null;
    return [field ? `${field}: ${message}` : message];
  });

  if (messages.length > 0) {
    return summary ? `${summary}: ${messages.join('; ')}` : messages.join('; ');
  }
  return summary;
};

/**
 * Helper to extract error message from Axios errors
 */
export const getErrorMessage = (error: unknown): string => {
  if (isAxiosError(error)) {
    const responseMessage = extractApiErrorMessage(error.response?.data);
    return responseMessage || error.message || 'An error occurred';
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unknown error occurred';
};

// Track if we're currently refreshing to avoid multiple refresh attempts
let isRefreshing = false;
let failedQueue: {
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}[] = [];
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
const api: AxiosInstance = create({
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
  getRevisions: async () => {
    const response = await api.get<TariffRevision[]>('/tariffs/revisions');
    return response.data;
  },
  getAERRetailers: async () => {
    const response = await api.get<AERRetailerCatalog>('/tariffs/catalog/aer/retailers');
    return response.data;
  },
  searchAERPlans: async (brand: string, postcode: string) => {
    const response = await api.get<{
      source: string;
      source_registry_version: string;
      retrieved_at: string;
      plans: AERPlanSummary[];
    }>('/tariffs/catalog/aer/plans', { params: { brand, postcode } });
    return response.data;
  },
  getAERPlanDetail: async (brand: string, planId: string) => {
    const response = await api.get<AERPlanDetail>(
      `/tariffs/catalog/aer/plans/${encodeURIComponent(planId)}`,
      { params: { brand } },
    );
    return response.data;
  },
};

export const contextApi = {
  getWeatherSummary: async (latitude: number, longitude: number) => {
    const response = await api.post<WeatherForecastResponse>('/context/weather/summary', {
      latitude,
      longitude,
    });
    return response.data;
  },
  getWeatherHourly: async (latitude: number, longitude: number, hours = 24) => {
    const response = await api.post<WeatherForecastResponse>('/context/weather/hourly', {
      latitude,
      longitude,
      hours,
    });
    return response.data;
  },
  getMarketSummary: async () => {
    const response = await api.get<MarketContextResponse>('/context/market/summary');
    return response.data;
  },
  getProviderAvailability: async () => {
    const response = await api.get<{ providers: ProviderFreshness[] }>('/context/providers');
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
      formData.append('file', new File([blob], fileName, { type: blob.type }));

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
