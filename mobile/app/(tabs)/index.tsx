import { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { router } from 'expo-router';
import { useMetersStore, useUsageStore, useAuthStore } from '@/stores';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

export default function DashboardScreen() {
  const { user } = useAuthStore();
  const { meters, selectedMeter, fetchMeters, isLoading: metersLoading } = useMetersStore();
  const { summary, fetchAllUsageData, isLoading: usageLoading } = useUsageStore();

  const isLoading = metersLoading || usageLoading;

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedMeter) {
      fetchAllUsageData(selectedMeter.id);
    }
  }, [selectedMeter]);

  const loadData = async () => {
    await fetchMeters();
  };

  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 18) return 'Good afternoon';
    return 'Good evening';
  };

  const formatCurrency = (value: number) => `$${value.toFixed(2)}`;
  const formatKwh = (value: number) => `${value.toFixed(1)} kWh`;

  if (meters.length === 0 && !metersLoading) {
    return (
      <View style={styles.emptyContainer}>
        <View style={styles.emptyContent}>
          <View style={styles.emptyIcon}>
            <Ionicons name="flash-outline" size={64} color={Colors.gray300} />
          </View>
          <Text style={styles.emptyTitle}>No Data Yet</Text>
          <Text style={styles.emptyText}>
            Upload your NEM12 smart meter data to start tracking your energy usage.
          </Text>
          <TouchableOpacity
            style={styles.uploadButton}
            onPress={() => router.push('/upload')}
          >
            <Ionicons name="cloud-upload-outline" size={20} color={Colors.white} />
            <Text style={styles.uploadButtonText}>Upload NEM12 File</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isLoading} onRefresh={loadData} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>{greeting()}</Text>
          <Text style={styles.userName}>{user?.full_name || 'Energy Saver'}</Text>
        </View>
        <TouchableOpacity
          style={styles.uploadIconButton}
          onPress={() => router.push('/upload')}
        >
          <Ionicons name="add-circle" size={32} color={Colors.primary} />
        </TouchableOpacity>
      </View>

      {/* Meter Selector */}
      {meters.length > 1 && (
        <View style={styles.meterSelector}>
          <Text style={styles.sectionLabel}>Viewing meter</Text>
          <TouchableOpacity style={styles.meterButton}>
            <Ionicons name="flash" size={18} color={Colors.primary} />
            <Text style={styles.meterText}>
              {selectedMeter?.name || selectedMeter?.nmi.slice(-4)}
            </Text>
            <Ionicons name="chevron-down" size={18} color={Colors.gray400} />
          </TouchableOpacity>
        </View>
      )}

      {/* Summary Cards */}
      {isLoading && !summary ? (
        <View style={styles.loadingCard}>
          <ActivityIndicator size="large" color={Colors.primary} />
        </View>
      ) : summary ? (
        <>
          {/* Main Stats */}
          <View style={styles.statsGrid}>
            <View style={[styles.statCard, styles.primaryCard]}>
              <Ionicons name="flash" size={24} color={Colors.white} />
              <Text style={styles.statValue}>{formatKwh(summary.total_kwh)}</Text>
              <Text style={styles.statLabel}>Total Usage</Text>
              <Text style={styles.statPeriod}>{summary.days_count} days</Text>
            </View>

            <View style={styles.statCard}>
              <Ionicons name="wallet-outline" size={24} color={Colors.primary} />
              <Text style={[styles.statValue, styles.darkText]}>
                {formatCurrency(summary.estimated_total_cost)}
              </Text>
              <Text style={[styles.statLabel, styles.darkLabel]}>Est. Cost</Text>
            </View>
          </View>

          <View style={styles.statsRow}>
            <View style={[styles.smallCard]}>
              <Text style={styles.smallValue}>{formatKwh(summary.avg_daily_kwh)}</Text>
              <Text style={styles.smallLabel}>Daily Avg</Text>
            </View>
            <View style={[styles.smallCard]}>
              <Text style={styles.smallValue}>{summary.peak_hour}:00</Text>
              <Text style={styles.smallLabel}>Peak Hour</Text>
            </View>
            <View style={[styles.smallCard]}>
              <Text style={styles.smallValue}>{summary.off_peak_percentage}%</Text>
              <Text style={styles.smallLabel}>Off-Peak</Text>
            </View>
          </View>

          {/* Quick Actions */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Quick Actions</Text>
            <View style={styles.actionGrid}>
              <TouchableOpacity
                style={styles.actionCard}
                onPress={() => router.push('/(tabs)/usage')}
              >
                <View style={[styles.actionIcon, { backgroundColor: Colors.secondary + '20' }]}>
                  <Ionicons name="analytics" size={24} color={Colors.secondary} />
                </View>
                <Text style={styles.actionText}>View Charts</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.actionCard}
                onPress={() => router.push('/(tabs)/recommendations')}
              >
                <View style={[styles.actionIcon, { backgroundColor: Colors.warning + '20' }]}>
                  <Ionicons name="bulb" size={24} color={Colors.warning} />
                </View>
                <Text style={styles.actionText}>Get Tips</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.actionCard}
                onPress={() => router.push('/upload')}
              >
                <View style={[styles.actionIcon, { backgroundColor: Colors.primary + '20' }]}>
                  <Ionicons name="cloud-upload" size={24} color={Colors.primary} />
                </View>
                <Text style={styles.actionText}>Upload Data</Text>
              </TouchableOpacity>
            </View>
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    padding: Spacing.md,
    paddingBottom: Spacing.xxl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  greeting: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  userName: {
    fontSize: FontSize.xl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
  },
  uploadIconButton: {
    padding: Spacing.xs,
  },
  meterSelector: {
    marginBottom: Spacing.md,
  },
  sectionLabel: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  meterButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    padding: Spacing.sm,
    borderRadius: BorderRadius.md,
    gap: Spacing.xs,
    ...Shadow.sm,
  },
  meterText: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.text,
  },
  loadingCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.xxl,
    alignItems: 'center',
    ...Shadow.md,
  },
  statsGrid: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.md,
  },
  statCard: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    ...Shadow.md,
  },
  primaryCard: {
    backgroundColor: Colors.primary,
  },
  statValue: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.white,
    marginTop: Spacing.sm,
  },
  darkText: {
    color: Colors.text,
  },
  statLabel: {
    fontSize: FontSize.sm,
    color: Colors.white,
    opacity: 0.9,
  },
  darkLabel: {
    color: Colors.textSecondary,
  },
  statPeriod: {
    fontSize: FontSize.xs,
    color: Colors.white,
    opacity: 0.7,
    marginTop: Spacing.xs,
  },
  statsRow: {
    flexDirection: 'row',
    gap: Spacing.md,
    marginBottom: Spacing.lg,
  },
  smallCard: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    alignItems: 'center',
    ...Shadow.sm,
  },
  smallValue: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
  },
  smallLabel: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  section: {
    marginBottom: Spacing.lg,
  },
  sectionTitle: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  actionGrid: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  actionCard: {
    flex: 1,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    alignItems: 'center',
    ...Shadow.sm,
  },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  actionText: {
    fontSize: FontSize.sm,
    color: Colors.text,
    fontWeight: FontWeight.medium,
  },
  emptyContainer: {
    flex: 1,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.lg,
  },
  emptyContent: {
    alignItems: 'center',
    maxWidth: 300,
  },
  emptyIcon: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: Colors.gray100,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  emptyTitle: {
    fontSize: FontSize.xl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  emptyText: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
  uploadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.primary,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    borderRadius: BorderRadius.md,
    gap: Spacing.sm,
  },
  uploadButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
});
