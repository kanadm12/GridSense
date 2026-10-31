import { router, Stack, useSegments } from 'expo-router';
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
  const { checkAuth, isAuthenticated, isLoading } = useAuthStore();
  const segments = useSegments();

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    if (isLoading) {
      return;
    }

    const inAuthGroup = segments[0] === '(auth)';
    if (!isAuthenticated && !inAuthGroup) {
      router.replace('/(auth)/login');
    } else if (isAuthenticated && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [isAuthenticated, isLoading, segments]);

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
        <Stack.Screen name="scheduling" options={{ presentation: 'modal' }} />
      </Stack>
    </>
  );
}
