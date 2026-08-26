import { Stack } from 'expo-router';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { useAuthStore } from '@/stores';
import {
  addNotificationReceivedListener,
  addNotificationResponseListener,
  registerForPushNotifications,
  unregisterPushNotifications,
} from '@/services/notifications';

export default function RootLayout() {
  const { checkAuth, isAuthenticated } = useAuthStore();

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    void registerForPushNotifications();
    const receivedSubscription = addNotificationReceivedListener(() => undefined);
    const responseSubscription = addNotificationResponseListener(() => undefined);

    return () => {
      receivedSubscription.remove();
      responseSubscription.remove();
      void unregisterPushNotifications();
    };
  }, [isAuthenticated]);

  return (
    <>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="upload" options={{ presentation: 'modal' }} />
      </Stack>
    </>
  );
}
