/**
 * Push notification service for Expo
 */
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import api from './api';

// Configure notification handler
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

/**
 * Register for push notifications and get the Expo push token
 */
export async function registerForPushNotifications(): Promise<string | null> {
  // Check if physical device (required for push)
  if (!Device.isDevice) {
    console.log('Push notifications require a physical device');
    return null;
  }

  // Get existing permissions
  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  // Request permissions if not already granted
  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission not granted');
    return null;
  }

  // Get Expo push token
  try {
    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const tokenData = await Notifications.getExpoPushTokenAsync({
      projectId,
    });

    // Register token with backend
    const platform = Platform.OS === 'ios' ? 'ios' : 'android';
    await api.post('/notifications/register-token', {
      token: tokenData.data,
      platform,
    });

    console.log('Push token registered:', tokenData.data);
    return tokenData.data;
  } catch (error) {
    console.error('Failed to get push token:', error);
    return null;
  }
}

/**
 * Unregister push notifications
 */
export async function unregisterPushNotifications(): Promise<void> {
  try {
    const token = await Notifications.getExpoPushTokenAsync({
      projectId: Constants.expoConfig?.extra?.eas?.projectId,
    });
    const platform = Platform.OS === 'ios' ? 'ios' : 'android';
    await api.post('/notifications/unregister-token', {
      token: token.data,
      platform,
    });
  } catch (error) {
    console.error('Failed to unregister push token:', error);
  }
}

/**
 * Handle notification received while app is foregrounded
 */
export function addNotificationReceivedListener(
  callback: (notification: Notifications.Notification) => void
): Notifications.Subscription {
  return Notifications.addNotificationReceivedListener(callback);
}

/**
 * Handle notification interaction (tap)
 */
export function addNotificationResponseListener(
  callback: (response: Notifications.NotificationResponse) => void
): Notifications.Subscription {
  return Notifications.addNotificationResponseReceivedListener(callback);
}

/**
 * Schedule a local notification
 */
export async function scheduleLocalNotification(
  title: string,
  body: string,
  data?: Record<string, unknown>,
  trigger?: Notifications.NotificationTriggerInput
): Promise<string> {
  return Notifications.scheduleNotificationAsync({
    content: {
      title,
      body,
      data: data ?? {},
      sound: true,
    },
    trigger: trigger ?? null, // null = immediate
  });
}

/**
 * Cancel all scheduled notifications
 */
export async function cancelAllNotifications(): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();
}

/**
 * Set badge count (iOS)
 */
export async function setBadgeCount(count: number): Promise<void> {
  await Notifications.setBadgeCountAsync(count);
}

/**
 * Clear badge count
 */
export async function clearBadge(): Promise<void> {
  await setBadgeCount(0);
}

/**
 * Example: Schedule peak hour warning
 */
export async function schedulePeakHourReminder(): Promise<void> {
  // Schedule daily reminder at 2:45 PM (before 3 PM peak)
  await Notifications.scheduleNotificationAsync({
    content: {
      title: '⚡ Peak Hours Starting Soon',
      body: 'Peak pricing begins at 3 PM. Finish high-energy tasks now!',
      data: { type: 'peak_warning' },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: 14,
      minute: 45,
    },
  });
}

/**
 * Example: Schedule weekly usage summary
 */
export async function scheduleWeeklySummary(): Promise<void> {
  // Schedule for Sunday at 9 AM
  await Notifications.scheduleNotificationAsync({
    content: {
      title: '📊 Your Weekly Energy Summary',
      body: 'Check your usage report and see how much you saved!',
      data: { type: 'weekly_summary' },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.WEEKLY,
      weekday: 1, // Sunday
      hour: 9,
      minute: 0,
    },
  });
}

// Types for notification data
export interface NotificationPreferences {
  anomalyAlerts: boolean;
  forecastUpdates: boolean;
  recommendations: boolean;
  peakAlerts: boolean;
  weeklySummary: boolean;
  savingsTips: boolean;
}

/**
 * Get notification preferences from API
 */
export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  try {
    const response = await api.get('/notifications/preferences');
    return {
      anomalyAlerts: response.data.anomaly_alerts,
      forecastUpdates: response.data.forecast_updates,
      recommendations: response.data.recommendations,
      peakAlerts: response.data.peak_alerts,
      weeklySummary: response.data.weekly_summary,
      savingsTips: response.data.savings_tips,
    };
  } catch {
    // Return defaults if failed
    return {
      anomalyAlerts: true,
      forecastUpdates: true,
      recommendations: true,
      peakAlerts: true,
      weeklySummary: true,
      savingsTips: true,
    };
  }
}

/**
 * Update notification preferences
 */
export async function updateNotificationPreferences(
  prefs: NotificationPreferences
): Promise<void> {
  await api.put('/notifications/preferences', {
    anomaly_alerts: prefs.anomalyAlerts,
    forecast_updates: prefs.forecastUpdates,
    recommendations: prefs.recommendations,
    peak_alerts: prefs.peakAlerts,
    weekly_summary: prefs.weeklySummary,
    savings_tips: prefs.savingsTips,
  });

  // Update scheduled notifications based on preferences
  await cancelAllNotifications();
  
  if (prefs.peakAlerts) {
    await schedulePeakHourReminder();
  }
  
  if (prefs.weeklySummary) {
    await scheduleWeeklySummary();
  }
}
