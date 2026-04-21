import { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useMetersStore, useRecommendationsStore } from '@/stores';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import type { Recommendation } from '@/services/api';

const priorityColors = {
  high: Colors.error,
  medium: Colors.warning,
  low: Colors.info,
};

const categoryIcons: Record<string, keyof typeof Ionicons.glyphMap> = {
  load_shifting: 'swap-horizontal',
  standby_reduction: 'power',
  solar_optimization: 'sunny',
  tariff_optimization: 'cash',
  general: 'information-circle',
};

export default function RecommendationsScreen() {
  const { selectedMeter } = useMetersStore();
  const { recommendations, totalSavings, fetchRecommendations, isLoading } =
    useRecommendationsStore();

  useEffect(() => {
    if (selectedMeter) {
      fetchRecommendations(selectedMeter.id);
    }
  }, [selectedMeter]);

  const refresh = () => {
    if (selectedMeter) {
      fetchRecommendations(selectedMeter.id);
    }
  };

  const renderRecommendation = (rec: Recommendation) => (
    <View key={rec.id} style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={[styles.iconContainer, { backgroundColor: priorityColors[rec.priority] + '20' }]}>
          <Ionicons
            name={categoryIcons[rec.category] || 'bulb'}
            size={24}
            color={priorityColors[rec.priority]}
          />
        </View>
        <View style={styles.cardTitleContainer}>
          <Text style={styles.cardTitle}>{rec.title}</Text>
          <View style={[styles.priorityBadge, { backgroundColor: priorityColors[rec.priority] + '20' }]}>
            <Text style={[styles.priorityText, { color: priorityColors[rec.priority] }]}>
              {rec.priority.toUpperCase()}
            </Text>
          </View>
        </View>
      </View>

      <Text style={styles.description}>{rec.description}</Text>

      <View style={styles.actionContainer}>
        <Ionicons name="checkmark-circle-outline" size={18} color={Colors.primary} />
        <Text style={styles.actionText}>{rec.action}</Text>
      </View>

      {(rec.potential_savings_kwh || rec.potential_savings_dollars) && (
        <View style={styles.savingsContainer}>
          <Ionicons name="trending-down" size={18} color={Colors.success} />
          <Text style={styles.savingsText}>
            Potential savings:{' '}
            {rec.potential_savings_dollars
              ? `$${rec.potential_savings_dollars.toFixed(2)}/month`
              : `${rec.potential_savings_kwh?.toFixed(1)} kWh`}
          </Text>
        </View>
      )}

      <View style={styles.reasonContainer}>
        <Text style={styles.reasonLabel}>Why this matters:</Text>
        <Text style={styles.reasonText}>{rec.reason}</Text>
      </View>
    </View>
  );

  if (!selectedMeter) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="bulb-outline" size={64} color={Colors.gray300} />
        <Text style={styles.emptyText}>Upload meter data to get recommendations</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={isLoading} onRefresh={refresh} />
      }
    >
      {/* Savings Summary */}
      {totalSavings && totalSavings > 0 && (
        <View style={styles.savingsSummary}>
          <View style={styles.savingsSummaryIcon}>
            <Ionicons name="wallet" size={32} color={Colors.success} />
          </View>
          <View>
            <Text style={styles.savingsSummaryLabel}>Potential Monthly Savings</Text>
            <Text style={styles.savingsSummaryValue}>
              ${totalSavings.toFixed(2)}
            </Text>
          </View>
        </View>
      )}

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Energy Tips</Text>
        <Text style={styles.headerSubtitle}>
          {recommendations.length} personalized recommendations
        </Text>
      </View>

      {/* Recommendations List */}
      {recommendations.length > 0 ? (
        recommendations.map(renderRecommendation)
      ) : (
        <View style={styles.noRecommendations}>
          <Ionicons name="checkmark-circle" size={48} color={Colors.success} />
          <Text style={styles.noRecommendationsTitle}>Looking good!</Text>
          <Text style={styles.noRecommendationsText}>
            We don't have any recommendations at the moment. Your energy usage patterns look efficient.
          </Text>
        </View>
      )}

      {/* Info Card */}
      <View style={styles.infoCard}>
        <Ionicons name="information-circle" size={24} color={Colors.info} />
        <View style={styles.infoContent}>
          <Text style={styles.infoTitle}>How recommendations work</Text>
          <Text style={styles.infoText}>
            We analyze your usage patterns and compare them with optimal energy usage profiles.
            Recommendations are based on Victorian Time-of-Use tariffs and typical household patterns.
          </Text>
        </View>
      </View>
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
  savingsSummary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.success + '10',
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.success + '30',
    gap: Spacing.md,
  },
  savingsSummaryIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.success + '20',
    justifyContent: 'center',
    alignItems: 'center',
  },
  savingsSummaryLabel: {
    fontSize: FontSize.sm,
    color: Colors.success,
  },
  savingsSummaryValue: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.success,
  },
  header: {
    marginBottom: Spacing.md,
  },
  headerTitle: {
    fontSize: FontSize.xl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
  },
  headerSubtitle: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    ...Shadow.md,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: Spacing.md,
    gap: Spacing.md,
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardTitleContainer: {
    flex: 1,
  },
  cardTitle: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.xs,
  },
  priorityBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: BorderRadius.sm,
  },
  priorityText: {
    fontSize: FontSize.xs,
    fontWeight: FontWeight.semibold,
  },
  description: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
    marginBottom: Spacing.md,
  },
  actionContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: Colors.primary + '10',
    padding: Spacing.sm,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
    gap: Spacing.sm,
  },
  actionText: {
    flex: 1,
    fontSize: FontSize.sm,
    color: Colors.primaryDark,
    fontWeight: FontWeight.medium,
  },
  savingsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  savingsText: {
    fontSize: FontSize.sm,
    color: Colors.success,
    fontWeight: FontWeight.medium,
  },
  reasonContainer: {
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    paddingTop: Spacing.sm,
    marginTop: Spacing.sm,
  },
  reasonLabel: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  reasonText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    fontStyle: 'italic',
  },
  noRecommendations: {
    alignItems: 'center',
    padding: Spacing.xl,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    ...Shadow.sm,
  },
  noRecommendationsTitle: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginTop: Spacing.md,
  },
  noRecommendationsText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginTop: Spacing.sm,
  },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: Colors.info + '10',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginTop: Spacing.md,
    gap: Spacing.sm,
  },
  infoContent: {
    flex: 1,
  },
  infoTitle: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.info,
    marginBottom: Spacing.xs,
  },
  infoText: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    lineHeight: 18,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.lg,
  },
  emptyText: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
});
