/**
 * Offline caching service using AsyncStorage
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';

// Cache keys
const CACHE_KEYS = {
  USER: '@cache_user',
  METERS: '@cache_meters',
  USAGE_DAILY: '@cache_usage_daily',
  USAGE_HOURLY: '@cache_usage_hourly',
  RECOMMENDATIONS: '@cache_recommendations',
  TARIFF: '@cache_tariff',
  LAST_SYNC: '@cache_last_sync',
} as const;

// Cache expiry time (1 hour for most data)
const CACHE_TTL = 60 * 60 * 1000;

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  expiresAt: number;
}

/**
 * Check if device is online
 */
export async function isOnline(): Promise<boolean> {
  const state = await NetInfo.fetch();
  return state.isConnected ?? false;
}

/**
 * Store data in cache
 */
export async function setCache<T>(
  key: string,
  data: T,
  ttl: number = CACHE_TTL
): Promise<void> {
  const entry: CacheEntry<T> = {
    data,
    timestamp: Date.now(),
    expiresAt: Date.now() + ttl,
  };
  await AsyncStorage.setItem(key, JSON.stringify(entry));
}

/**
 * Get data from cache
 */
export async function getCache<T>(key: string): Promise<T | null> {
  try {
    const stored = await AsyncStorage.getItem(key);
    if (!stored) return null;

    const entry: CacheEntry<T> = JSON.parse(stored);

    // Check if expired
    if (Date.now() > entry.expiresAt) {
      await AsyncStorage.removeItem(key);
      return null;
    }

    return entry.data;
  } catch {
    return null;
  }
}

/**
 * Get data from cache (even if expired - useful for offline mode)
 */
export async function getCacheStale<T>(key: string): Promise<{
  data: T | null;
  isStale: boolean;
  age: number;
}> {
  try {
    const stored = await AsyncStorage.getItem(key);
    if (!stored) {
      return { data: null, isStale: true, age: 0 };
    }

    const entry: CacheEntry<T> = JSON.parse(stored);
    const isStale = Date.now() > entry.expiresAt;
    const age = Date.now() - entry.timestamp;

    return { data: entry.data, isStale, age };
  } catch {
    return { data: null, isStale: true, age: 0 };
  }
}

/**
 * Remove item from cache
 */
export async function removeCache(key: string): Promise<void> {
  await AsyncStorage.removeItem(key);
}

/**
 * Clear all cached data
 */
export async function clearAllCache(): Promise<void> {
  const keys = Object.values(CACHE_KEYS);
  await AsyncStorage.multiRemove(keys);
}

/**
 * Get cache age for a key
 */
export async function getCacheAge(key: string): Promise<number | null> {
  try {
    const stored = await AsyncStorage.getItem(key);
    if (!stored) return null;

    const entry: CacheEntry<unknown> = JSON.parse(stored);
    return Date.now() - entry.timestamp;
  } catch {
    return null;
  }
}

// ============ Specific cache helpers ============

export const cacheUser = {
  get: () => getCache<any>(CACHE_KEYS.USER),
  set: (data: any) => setCache(CACHE_KEYS.USER, data, CACHE_TTL * 24), // 24 hours
  clear: () => removeCache(CACHE_KEYS.USER),
};

export const cacheMeters = {
  get: () => getCache<any[]>(CACHE_KEYS.METERS),
  getStale: () => getCacheStale<any[]>(CACHE_KEYS.METERS),
  set: (data: any[]) => setCache(CACHE_KEYS.METERS, data),
  clear: () => removeCache(CACHE_KEYS.METERS),
};

export const cacheUsageDaily = {
  get: (meterId: number) => getCache<any>(`${CACHE_KEYS.USAGE_DAILY}_${meterId}`),
  getStale: (meterId: number) => getCacheStale<any>(`${CACHE_KEYS.USAGE_DAILY}_${meterId}`),
  set: (meterId: number, data: any) => setCache(`${CACHE_KEYS.USAGE_DAILY}_${meterId}`, data),
  clear: (meterId: number) => removeCache(`${CACHE_KEYS.USAGE_DAILY}_${meterId}`),
};

export const cacheUsageHourly = {
  get: (meterId: number, date: string) => getCache<any>(`${CACHE_KEYS.USAGE_HOURLY}_${meterId}_${date}`),
  getStale: (meterId: number, date: string) => getCacheStale<any>(`${CACHE_KEYS.USAGE_HOURLY}_${meterId}_${date}`),
  set: (meterId: number, date: string, data: any) => setCache(`${CACHE_KEYS.USAGE_HOURLY}_${meterId}_${date}`, data),
  clear: (meterId: number, date: string) => removeCache(`${CACHE_KEYS.USAGE_HOURLY}_${meterId}_${date}`),
};

export const cacheRecommendations = {
  get: (meterId: number) => getCache<any[]>(`${CACHE_KEYS.RECOMMENDATIONS}_${meterId}`),
  getStale: (meterId: number) => getCacheStale<any[]>(`${CACHE_KEYS.RECOMMENDATIONS}_${meterId}`),
  set: (meterId: number, data: any[]) => setCache(`${CACHE_KEYS.RECOMMENDATIONS}_${meterId}`, data),
  clear: (meterId: number) => removeCache(`${CACHE_KEYS.RECOMMENDATIONS}_${meterId}`),
};

export const cacheTariff = {
  get: () => getCache<any>(CACHE_KEYS.TARIFF),
  set: (data: any) => setCache(CACHE_KEYS.TARIFF, data, CACHE_TTL * 24), // 24 hours
  clear: () => removeCache(CACHE_KEYS.TARIFF),
};

// ============ Sync status ============

export interface SyncStatus {
  lastSync: number | null;
  isStale: boolean;
  offlineMode: boolean;
}

export async function getSyncStatus(): Promise<SyncStatus> {
  const online = await isOnline();
  const lastSyncStr = await AsyncStorage.getItem(CACHE_KEYS.LAST_SYNC);
  const lastSync = lastSyncStr ? parseInt(lastSyncStr, 10) : null;

  const isStale = lastSync ? Date.now() - lastSync > CACHE_TTL : true;

  return {
    lastSync,
    isStale,
    offlineMode: !online,
  };
}

export async function updateLastSync(): Promise<void> {
  await AsyncStorage.setItem(CACHE_KEYS.LAST_SYNC, Date.now().toString());
}

/**
 * Format the last sync time for display
 */
export function formatLastSync(timestamp: number | null): string {
  if (!timestamp) return 'Never synced';

  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (hours < 24) return `${hours} hours ago`;
  return new Date(timestamp).toLocaleDateString();
}

// ============ Network-aware fetch wrapper ============

interface FetchOptions<T> {
  fetchFn: () => Promise<T>;
  cacheKey: string;
  cacheTtl?: number;
  allowStale?: boolean;
}

/**
 * Fetch data with automatic caching and offline support
 */
export async function fetchWithCache<T>({
  fetchFn,
  cacheKey,
  cacheTtl = CACHE_TTL,
  allowStale = true,
}: FetchOptions<T>): Promise<{ data: T; fromCache: boolean }> {
  const online = await isOnline();

  if (online) {
    try {
      const data = await fetchFn();
      await setCache(cacheKey, data, cacheTtl);
      await updateLastSync();
      return { data, fromCache: false };
    } catch (error) {
      // If fetch fails, try cache
      if (allowStale) {
        const cached = await getCacheStale<T>(cacheKey);
        if (cached.data) {
          return { data: cached.data, fromCache: true };
        }
      }
      throw error;
    }
  } else {
    // Offline - use cache
    const cached = await getCacheStale<T>(cacheKey);
    if (cached.data) {
      return { data: cached.data, fromCache: true };
    }
    throw new Error('No internet connection and no cached data available');
  }
}
