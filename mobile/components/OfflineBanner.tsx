import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { isOnline, getSyncStatus, formatLastSync } from '@/services/offline';
import { Colors, Spacing, FontSize, FontWeight } from '@/constants/theme';

interface OfflineBannerProps {
  showSyncStatus?: boolean;
}

export default function OfflineBanner({ showSyncStatus = true }: OfflineBannerProps) {
  const [online, setOnline] = useState(true);
  const [lastSync, setLastSync] = useState<number | null>(null);
  const [slideAnim] = useState(new Animated.Value(-50));

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 10000); // Check every 10s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    Animated.timing(slideAnim, {
      toValue: online ? -50 : 0,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [online]);

  const checkStatus = async () => {
    const isConnected = await isOnline();
    setOnline(isConnected);

    if (showSyncStatus) {
      const status = await getSyncStatus();
      setLastSync(status.lastSync);
    }
  };

  if (online && !showSyncStatus) return null;

  return (
    <Animated.View
      style={[
        styles.container,
        { transform: [{ translateY: slideAnim }] },
      ]}
    >
      <View style={styles.content}>
        <Ionicons
          name={online ? 'cloud-done' : 'cloud-offline'}
          size={16}
          color={Colors.white}
        />
        <Text style={styles.text}>
          {online
            ? `Synced ${formatLastSync(lastSync)}`
            : 'You are offline'}
        </Text>
      </View>
      {!online && (
        <Text style={styles.hint}>
          Using cached data
        </Text>
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.gray700,
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  text: {
    color: Colors.white,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.medium,
  },
  hint: {
    color: Colors.gray300,
    fontSize: FontSize.xs,
  },
});
