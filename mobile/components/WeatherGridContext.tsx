import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { BorderRadius, Colors, FontSize, FontWeight, Shadow, Spacing } from '@/constants/theme';
import { contextApi, MarketContextResponse, WeatherForecastResponse } from '@/services/api';
import { useAuthStore } from '@/stores';

const weatherLocationStorageKey = (userId: number) => `gridsense_weather_location_${userId}`;

type WeatherLocation = { latitude: number; longitude: number };

function localTime(value: string | null): string {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not available';
  return new Intl.DateTimeFormat('en-AU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Australia/Melbourne',
  }).format(date);
}

export default function WeatherGridContext() {
  const { user } = useAuthStore();
  const userId = user?.id;
  const [location, setLocation] = useState<WeatherLocation | null>(null);
  const [locationOwnerId, setLocationOwnerId] = useState<number | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [weather, setWeather] = useState<WeatherForecastResponse | null>(null);
  const [weatherOwnerId, setWeatherOwnerId] = useState<number | null>(null);
  const [market, setMarket] = useState<MarketContextResponse | null>(null);
  const [loadingOwnerId, setLoadingOwnerId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [localWeatherStale, setLocalWeatherStale] = useState(false);
  const currentUserLocation = locationOwnerId === userId ? location : null;

  useEffect(() => {
    let active = true;

    if (userId === undefined) {
      return () => {
        active = false;
      };
    }

    AsyncStorage.getItem(weatherLocationStorageKey(userId))
      .then((saved) => {
        if (!active || !saved) return;
        const parsed = JSON.parse(saved) as WeatherLocation;
        if (
          Number.isFinite(parsed.latitude) &&
          Number.isFinite(parsed.longitude) &&
          parsed.latitude >= -90 &&
          parsed.latitude <= 90 &&
          parsed.longitude >= -180 &&
          parsed.longitude <= 180
        ) {
          setLatitude(parsed.latitude.toFixed(2));
          setLongitude(parsed.longitude.toFixed(2));
          setLocation(parsed);
          setLocationOwnerId(userId);
        }
      })
      .catch(() => {
        if (active) setMessage('Saved weather location could not be read.');
      });
    contextApi.getMarketSummary().then(setMarket).catch(() => {
      if (active) setMarket(null);
    });
    return () => {
      active = false;
    };
  }, [userId]);

  useEffect(() => {
    if (!currentUserLocation || userId === undefined) return;
    let active = true;
    const frame = requestAnimationFrame(() => {
      if (!active) return;
      setLoadingOwnerId(userId);
      setMessage(null);
      contextApi
        .getWeatherSummary(currentUserLocation.latitude, currentUserLocation.longitude)
        .then((result) => {
          if (active) {
            setWeather(result);
            setWeatherOwnerId(userId);
            setLocalWeatherStale(false);
          }
        })
        .catch(() => {
          if (active) {
            setLocalWeatherStale(true);
            setMessage('Weather context is unavailable. Meter analytics continue to work.');
          }
        })
        .finally(() => {
          if (active) setLoadingOwnerId(null);
        });
    });
    return () => {
      active = false;
      cancelAnimationFrame(frame);
    };
  }, [currentUserLocation, userId]);

  const saveLocation = async () => {
    const parsedLatitude = Number(latitude);
    const parsedLongitude = Number(longitude);
    if (
      !Number.isFinite(parsedLatitude) ||
      !Number.isFinite(parsedLongitude) ||
      parsedLatitude < -90 ||
      parsedLatitude > 90 ||
      parsedLongitude < -180 ||
      parsedLongitude > 180
    ) {
      setMessage('Enter a valid latitude (-90 to 90) and longitude (-180 to 180).');
      return;
    }

    const approximate = {
      latitude: Number(parsedLatitude.toFixed(2)),
      longitude: Number(parsedLongitude.toFixed(2)),
    };
    if (!user) {
      setMessage('Sign in before saving a weather location.');
      return;
    }
    try {
      await AsyncStorage.setItem(
        weatherLocationStorageKey(user.id),
        JSON.stringify(approximate)
      );
      setLocation(approximate);
      setLocationOwnerId(user.id);
      setMessage(null);
    } catch {
      setMessage('The weather location could not be saved on this device.');
    }
  };

  const currentUserWeather = weatherOwnerId === user?.id ? weather : null;
  const loading = loadingOwnerId === user?.id && user !== null;
  const current = currentUserWeather?.hourly[0];
  const updatedAt = localTime(currentUserWeather?.provider.retrieved_at ?? null);
  const statusText = currentUserWeather?.provider.status === 'stale' || localWeatherStale
    ? 'Stale forecast'
    : currentUserWeather?.provider.status === 'valid'
      ? 'Forecast'
      : currentUserWeather?.provider.error_code === 'provider_not_configured'
        ? 'Weather provider not configured'
        : currentUserWeather?.provider.status === 'rate_limited'
          ? 'Weather provider rate limited the request'
          : currentUserWeather?.provider.status === 'unauthorized'
            ? 'Weather provider authorization unavailable'
            : currentUserWeather?.provider.status === 'malformed'
              ? 'Weather response could not be validated'
              : 'Forecast unavailable';

  return (
    <View style={styles.card}>
      <View style={styles.heading}>
        <Ionicons name="cloud-outline" size={22} color={Colors.primary} />
        <Text style={styles.title}>Weather &amp; Grid Context</Text>
      </View>
      <Text style={styles.caption}>
        Optional approximate location. Coordinates are rounded to about 1 km before weather lookup.
      </Text>
      <View style={styles.locationRow}>
        <TextInput
          accessibilityLabel="Approximate latitude"
          keyboardType="numbers-and-punctuation"
          placeholder="Latitude"
          value={locationOwnerId === user?.id ? latitude : ''}
          onChangeText={setLatitude}
          style={styles.input}
        />
        <TextInput
          accessibilityLabel="Approximate longitude"
          keyboardType="numbers-and-punctuation"
          placeholder="Longitude"
          value={locationOwnerId === user?.id ? longitude : ''}
          onChangeText={setLongitude}
          style={styles.input}
        />
        <TouchableOpacity
          style={styles.saveButton}
          onPress={saveLocation}
          accessibilityRole="button"
          accessibilityLabel="Save approximate weather location"
        >
          <Text style={styles.saveButtonText}>
            {locationOwnerId === user?.id && location ? 'Update' : 'Set'}
          </Text>
        </TouchableOpacity>
      </View>

      {loading && <ActivityIndicator color={Colors.primary} />}
      {message && <Text style={styles.message}>{message}</Text>}

      {current ? (
        <View style={styles.weatherBlock}>
          <View style={styles.weatherHeading}>
            <Text style={styles.status}>{statusText}</Text>
            <Text style={styles.updated}>Retrieved {updatedAt} (Melbourne time)</Text>
          </View>
          <Text style={styles.temperature}>
            {current.temperature_2m === null ? '—' : `${current.temperature_2m.toFixed(1)} °C`}
          </Text>
          <Text style={styles.detail}>
            Feels like {current.apparent_temperature === null
              ? 'unavailable'
              : `${current.apparent_temperature.toFixed(1)} °C`}
            {' · '}
            Humidity {current.relative_humidity === null
              ? 'unavailable'
              : `${Math.round(current.relative_humidity)}%`}
          </Text>
          <Text style={styles.detail}>
            Cloud {current.cloud_cover === null ? 'unavailable' : `${Math.round(current.cloud_cover)}%`}
            {' · '}
            Solar {current.shortwave_radiation === null
              ? 'unavailable'
              : `${Math.round(current.shortwave_radiation)} W/m²`}
          </Text>
          <Text style={styles.forecastNote}>
            Hourly forecast, not an observation. Forecast issue time is not supplied by this endpoint.
          </Text>
          <TouchableOpacity
            onPress={() =>
              Linking.openURL(
                currentUserWeather?.provider.attribution_url ?? 'https://open-meteo.com/'
              )
            }
            accessibilityRole="link"
          >
            <Text style={styles.attribution}>Weather data by Open-Meteo.com</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => Linking.openURL('https://creativecommons.org/licenses/by/4.0/')}
            accessibilityRole="link"
          >
            <Text style={styles.attribution}>CC BY 4.0 license</Text>
          </TouchableOpacity>
          <Text style={styles.forecastNote}>
            Units are normalized and timestamps are stored in UTC.
          </Text>
        </View>
      ) : locationOwnerId === user?.id && location && !loading ? (
        <Text style={styles.message}>
          {currentUserWeather?.provider.error_code === 'provider_not_configured'
            ? `${statusText}. A licensed Open-Meteo paid API key is required for this product integration.`
            : `${statusText}. Meter analytics and tariff calculations remain independent.`}
        </Text>
      ) : null}

      <View style={styles.marketBlock}>
        <Text style={styles.marketTitle}>Victorian wholesale market</Text>
        <Text style={styles.detail}>
          {market?.provider.status === 'blocked'
            ? 'Unavailable — AEMO data contract and reuse terms are still being verified.'
            : 'Market context unavailable.'}
        </Text>
        <Text style={styles.forecastNote}>
          Wholesale prices are not your customer retail tariff and are not used in bill or savings estimates.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    ...Shadow.sm,
  },
  heading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  title: {
    color: Colors.text,
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
  },
  caption: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
  },
  locationRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginTop: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  input: {
    flex: 1,
    minWidth: 70,
    borderColor: Colors.borderStrong,
    borderWidth: 1,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    color: Colors.text,
    fontSize: FontSize.sm,
  },
  saveButton: {
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.primary,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  saveButtonText: {
    color: Colors.white,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  message: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    marginVertical: Spacing.xs,
  },
  weatherBlock: {
    borderTopColor: Colors.border,
    borderTopWidth: 1,
    marginTop: Spacing.xs,
    paddingTop: Spacing.sm,
  },
  weatherHeading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: Spacing.xs,
  },
  status: {
    color: Colors.primaryDark,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  updated: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
  },
  temperature: {
    color: Colors.text,
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    marginTop: Spacing.xs,
  },
  detail: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
  },
  forecastNote: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    marginTop: Spacing.sm,
  },
  attribution: {
    color: Colors.secondaryDark,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
    textDecorationLine: 'underline',
  },
  marketBlock: {
    borderTopColor: Colors.border,
    borderTopWidth: 1,
    marginTop: Spacing.md,
    paddingTop: Spacing.sm,
  },
  marketTitle: {
    color: Colors.text,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
});
