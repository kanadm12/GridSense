import { useEffect, useState } from 'react';
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
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const { selectedMeter } = useMetersStore();
  const { recommendations, fetchRecommendations, isLoading } =
    useRecommendationsStore();

  useEffect(() => {
    const initialUpdate = setTimeout(() => setNow(Date.now()), 0);
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => {
      clearTimeout(initialUpdate);
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (selectedMeter) {
      fetchRecommendations(selectedMeter.id);
    }
  }, [selectedMeter, fetchRecommendations]);

  const refresh = () => {
    if (selectedMeter) {
      fetchRecommendations(selectedMeter.id);
    }
  };

  const renderRecommendation = (rec: Recommendation) => {
    const evidence = rec.calculation_evidence;
    const evidenceExpired = Boolean(
      evidence && new Date(evidence.expires_at).getTime() <= now,
    );
    const isExpanded = expandedEvidence === rec.id;
    if (evidenceExpired) {
      return (
        <View key={rec.id} style={styles.card}>
          <Text style={styles.cardTitle}>{rec.title}</Text>
          <Text style={styles.statusText}>Evidence status: expired</Text>
          <Text style={styles.detailText}>
            This recommendation is no longer current. Refresh to reevaluate its source data.
          </Text>
          <TouchableOpacity style={styles.evidenceToggle} onPress={refresh}>
            <Text style={styles.evidenceToggleText}>Refresh recommendations</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return (
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
      <Text style={styles.statusText}>
        Evidence status: {rec.status.replace(/_/g, ' ')}
        {evidence ? ` · ${evidence.coverage.provenance_status}` : ''}
      </Text>

      <View style={styles.evidenceContainer}>
        <Text style={styles.detailLabel}>
          {evidence?.status === 'illustrative' ? 'Illustrative source data' : 'Observed'}
        </Text>
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

      <TouchableOpacity
        accessibilityRole="button"
        accessibilityState={{ expanded: isExpanded }}
        style={styles.evidenceToggle}
        onPress={() => setExpandedEvidence(isExpanded ? null : rec.id)}
      >
        <Text style={styles.evidenceToggleText}>
          {isExpanded ? 'Hide calculation details' : 'How was this calculated?'}
        </Text>
        <Ionicons
          name={isExpanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={Colors.primary}
        />
      </TouchableOpacity>
      {isExpanded && (
        <View style={styles.calculationDetails}>
          {evidence ? (
            <>
              <Text style={styles.detailLabel}>Source and coverage</Text>
              <Text style={styles.detailText}>
                {evidence.coverage.eligible_intervals} eligible of {evidence.coverage.expected_intervals} expected intervals
                {' '}({(evidence.coverage.coverage_fraction * 100).toFixed(1)}%); {evidence.coverage.coverage_status}.
              </Text>
              <Text style={styles.detailText}>
                {evidence.input_record_count} source records · rule {evidence.rule_id} v{evidence.rule_version}
              </Text>
              <Text style={styles.detailText}>
                Evaluated {new Date(evidence.created_at).toLocaleString('en-AU')} · expires {new Date(evidence.expires_at).toLocaleString('en-AU')}
              </Text>
              <Text style={styles.detailText}>
                Analysis window: {evidence.analysis_start_date ?? 'unknown'} to {evidence.analysis_end_date ?? 'unknown'}
              </Text>
              <Text style={styles.detailLabel}>Eligibility checks</Text>
              {Object.entries(evidence.eligibility_checks).map(([name, result]) => (
                <Text key={name} style={styles.detailText}>
                  {name.replace(/_/g, ' ')}: {result}
                </Text>
              ))}
              <Text style={styles.detailLabel}>Method</Text>
              <Text style={styles.detailText}>{evidence.calculation_method_version}</Text>
              <Text style={styles.detailText}>{evidence.baseline_scenario}</Text>
              <Text style={styles.detailLabel}>Calculated observations</Text>
              {Object.entries(evidence.calculated_values).length > 0 ? (
                Object.entries(evidence.calculated_values).map(([name, value]) => (
                  <Text key={name} style={styles.detailText}>
                    {name.replace(/_/g, ' ')}: {value}
                    {evidence.value_units[name] ? ` ${evidence.value_units[name]}` : ''}
                  </Text>
                ))
              ) : (
                <Text style={styles.detailText}>No quantified impact is supported.</Text>
              )}
              <Text style={styles.detailLabel}>Limitations</Text>
              {evidence.limitations.map((limitation, index) => (
                <Text key={index} style={styles.detailText}>• {limitation}</Text>
              ))}
              <Text style={styles.detailText}>
                Source digest: {evidence.input_digest_sha256 ?? 'unavailable'}
              </Text>
            </>
          ) : (
            <Text style={styles.detailText}>Calculation evidence is unavailable.</Text>
          )}
        </View>
      )}
    </View>
    );
  };

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
          <Ionicons name="information-circle" size={48} color={Colors.info} />
          <Text style={styles.noRecommendationsTitle}>No current recommendations</Text>
          <Text style={styles.noRecommendationsText}>
            No supported action is available from the current evidence. This does not mean your usage is efficient.
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
  statusText: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
    textTransform: 'capitalize',
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
  evidenceToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    paddingTop: Spacing.sm,
    marginTop: Spacing.sm,
  },
  evidenceToggleText: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  calculationDetails: {
    marginTop: Spacing.sm,
    padding: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.background,
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
