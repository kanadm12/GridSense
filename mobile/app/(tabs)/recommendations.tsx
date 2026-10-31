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
  const { recommendations, fetchRecommendations, isLoading } =
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

      <View style={styles.evidenceContainer}>
        <Text style={styles.detailLabel}>Observed</Text>
        <Text style={styles.detailText}>{rec.observed_fact}</Text>
        <Text style={styles.detailLabel}>Baseline</Text>
        <Text style={styles.detailText}>{rec.baseline}</Text>
      </View>

      <View style={styles.actionContainer}>
        <Ionicons name="checkmark-circle-outline" size={18} color={Colors.primary} />
        <View style={styles.actionTextContainer}>
          <Text style={styles.detailLabel}>Potential action</Text>
          <Text style={styles.actionText}>{rec.proposed_action}</Text>
        </View>
      </View>

      <View style={styles.opportunityContainer}>
        <Text style={styles.detailLabel}>Conditional opportunity · not quantified</Text>
        <Text style={styles.detailText}>{rec.conditional_opportunity}</Text>
        <Text style={styles.detailLabel}>Applicable intervals</Text>
        <Text style={styles.detailText}>{rec.applicable_intervals}</Text>
        {rec.rate_difference_cents_kwh !== null && (
          <Text style={styles.detailText}>
            Configured rate spread: {rec.rate_difference_cents_kwh.toFixed(2)} c/kWh.
            This is not a savings estimate.
          </Text>
        )}
        <Text style={styles.detailLabel}>Assumptions</Text>
        {rec.assumptions.map((assumption, index) => (
          <Text key={index} style={styles.detailText}>• {assumption}</Text>
        ))}
        <Text style={styles.detailLabel}>Uncertainty · {rec.confidence} confidence</Text>
        <Text style={styles.detailText}>{rec.uncertainty}</Text>
        <Text style={styles.detailLabel}>Needed to quantify</Text>
        {rec.data_requirements.map((requirement, index) => (
          <Text key={index} style={styles.detailText}>• {requirement}</Text>
        ))}
      </View>

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
            Recommendations describe patterns in imported interval data; they do not identify
            appliances or prove that energy can be shifted or saved. Dollar estimates require
            a verified current tariff and a declared appliance, its rated power or energy demand,
            and a feasible operating window. GridSense bill comparisons are estimates, not retailer bills.
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
  actionTextContainer: {
    flex: 1,
  },
  evidenceContainer: {
    padding: Spacing.sm,
    marginBottom: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.background,
  },
  opportunityContainer: {
    padding: Spacing.sm,
    marginBottom: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.info + '08',
  },
  detailLabel: {
    fontSize: FontSize.xs,
    fontWeight: FontWeight.semibold,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
    marginBottom: 2,
  },
  detailText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 19,
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
