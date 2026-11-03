import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import api from '@/services/api';
import { router } from 'expo-router';

interface BillComparisonData {
  meter_id: number;
  meter_name: string;
  comparison: {
    current_start: string;
    current_end: string;
    current_kwh: number;
    current_cost: number | null;
    current_days: number;
    current_daily_avg_kwh: number | null;
    previous_start: string;
    previous_end: string;
    previous_kwh: number;
    previous_cost: number | null;
    previous_days: number;
    previous_daily_avg_kwh: number | null;
    kwh_change: number | null;
    kwh_change_percent: number | null;
    cost_change: number | null;
    cost_change_percent: number | null;
    daily_avg_change_percent: number | null;
    trend: 'up' | 'down' | 'stable' | 'unavailable';
    insight: string;
  };
  recommendations: string[];
  current_breakdown: BillPeriodBreakdownData;
  previous_breakdown: BillPeriodBreakdownData;
}

interface BillPeriodBreakdownData {
  start_date: string;
  end_date: string;
  estimate_type: 'illustrative' | 'partial_estimate' | 'unavailable';
  tariff_status: string;
  data_status: string;
  provenance_status: string;
  gst_treatment: string;
  gst_amount: number | null;
  total_cost: number | null;
  customer_estimate_available: boolean;
  full_bill_available: boolean;
  coverage_fraction: number;
  line_items: {
    label: string;
    amount: number;
    included_in_total: boolean;
  }[];
  limitations: string[];
}

interface BillComparisonProps {
  meterId: number;
  illustrativeScenario?: boolean;
  currentStart?: Date;
  currentEnd?: Date;
}

export default function BillComparison({
  meterId,
  illustrativeScenario = false,
  currentStart,
  currentEnd,
}: BillComparisonProps) {
  const [data, setData] = useState<BillComparisonData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    
    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const now = new Date();
        const start = currentStart || new Date(now.getFullYear(), now.getMonth(), 1);
        const end = currentEnd || now;

        const params = new URLSearchParams({
          current_start: formatLocalDate(start),
          current_end: formatLocalDate(end),
        });
        if (illustrativeScenario) params.set('illustrative_scenario', 'true');

        const response = await api.get(`/billing/comparison/${meterId}?${params}`);
        if (isMounted) {
          setData(response.data);
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.response?.data?.detail || 'Failed to load comparison');
        }
      }

      if (isMounted) {
        setLoading(false);
      }
    };

    fetchData();
    return () => { isMounted = false; };
  }, [meterId, currentStart, currentEnd, illustrativeScenario]);

  const fetchComparison = async () => {
    setLoading(true);
    setError(null);

    try {
      const now = new Date();
      const start = currentStart || new Date(now.getFullYear(), now.getMonth(), 1);
      const end = currentEnd || now;

      const params = new URLSearchParams({
        current_start: formatLocalDate(start),
        current_end: formatLocalDate(end),
      });
      if (illustrativeScenario) params.set('illustrative_scenario', 'true');

      const response = await api.get(`/billing/comparison/${meterId}?${params}`);
      setData(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load comparison');
    }

    setLoading(false);
  };

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>Analyzing your bills...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.container}>
        <Ionicons name="alert-circle-outline" size={48} color={Colors.error} />
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={fetchComparison}>
          <Text style={styles.retryText}>Try Again</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!data) return null;

  const { comparison } = data;
  const trendIcon =
    comparison.trend === 'down' ? 'trending-down' :
    comparison.trend === 'up' ? 'trending-up' : 'remove';
  const trendColor =
    comparison.trend === 'down' ? Colors.success :
    comparison.trend === 'up' ? Colors.error : Colors.textSecondary;
  const trendLabel =
    comparison.trend === 'unavailable' ? 'Unavailable' :
    comparison.trend === 'stable' ? 'Stable' :
    comparison.trend === 'down' ? 'Lower import' : 'Higher import';
  const neutralTrend = comparison.trend === 'down' || comparison.trend === 'up';
  const displayedTrendColor = neutralTrend ? Colors.info : trendColor;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Bill Comparison</Text>
          <Text style={styles.subtitle}>{data.meter_name}</Text>
        </View>
        <View style={[styles.trendBadge, { backgroundColor: displayedTrendColor + '15' }]}>
          <Ionicons name={trendIcon} size={16} color={displayedTrendColor} />
          <Text style={[styles.trendText, { color: displayedTrendColor }]}>
            {trendLabel}
          </Text>
        </View>
      </View>

      {/* Main comparison */}
      <View style={styles.comparisonRow}>
        {/* Current Period */}
        <View style={styles.periodCard}>
          <Text style={styles.periodLabel}>This Period · observed</Text>
          <Text style={styles.costValue}>
            {formatMoney(comparison.current_cost)}
          </Text>
          <Text style={styles.kwhValue}>{comparison.current_kwh.toFixed(1)} kWh eligible imports</Text>
          <Text style={styles.dateRange}>
            {formatDateRange(comparison.current_start, comparison.current_end)}
          </Text>
        </View>

        {/* Change indicator */}
        <View style={styles.changeIndicator}>
          <Ionicons
            name={
              comparison.cost_change_percent === null
                ? 'remove'
                : (comparison.cost_change ?? 0) >= 0
                  ? 'arrow-up'
                  : 'arrow-down'
            }
            size={24}
            color={
              comparison.cost_change_percent === null
                ? Colors.textSecondary
                : (comparison.cost_change ?? 0) >= 0
                  ? Colors.error
                  : Colors.success
            }
          />
          <Text style={[
            styles.changeValue,
            {
              color: comparison.cost_change_percent === null
                ? Colors.textSecondary
                : (comparison.cost_change ?? 0) >= 0
                  ? Colors.error
                  : Colors.success,
            }
          ]}>
            {comparison.cost_change_percent === null
              ? 'N/A'
              : `${(comparison.cost_change ?? 0) >= 0 ? '+' : ''}${comparison.cost_change_percent.toFixed(1)}%`}
          </Text>
        </View>

        {/* Previous Period */}
        <View style={[styles.periodCard, styles.previousPeriod]}>
          <Text style={styles.periodLabel}>Last Period · observed</Text>
          <Text style={[styles.costValue, styles.previousCost]}>
            {formatMoney(comparison.previous_cost)}
          </Text>
          <Text style={styles.kwhValue}>{comparison.previous_kwh.toFixed(1)} kWh eligible imports</Text>
          <Text style={styles.dateRange}>
            {formatDateRange(comparison.previous_start, comparison.previous_end)}
          </Text>
        </View>
      </View>

      {/* Stats row */}
      <View style={styles.statsRow}>
        <StatBox
          label="Daily Avg"
          value={comparison.current_daily_avg_kwh === null
            ? 'Unavailable'
            : `${comparison.current_daily_avg_kwh.toFixed(1)} kWh`}
          change={comparison.daily_avg_change_percent}
        />
        <StatBox
          label="Usage Change"
          value={comparison.kwh_change === null
            ? 'Unavailable'
            : `${Math.abs(comparison.kwh_change).toFixed(1)} kWh`}
          change={comparison.kwh_change_percent}
        />
        <StatBox
          label="Cost Change"
          value={comparison.cost_change === null
            ? 'Unavailable'
            : `$${Math.abs(comparison.cost_change).toFixed(2)}`}
          change={comparison.cost_change_percent}
        />
      </View>

      <BillBreakdownCard title="This period" breakdown={data.current_breakdown} />
      <BillBreakdownCard title="Last period" breakdown={data.previous_breakdown} />

      {/* Insight */}
      <View style={styles.insightCard}>
        <Ionicons name="bulb-outline" size={20} color={Colors.warning} />
        <Text style={styles.insightText}>{comparison.insight}</Text>
      </View>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <View style={styles.recommendationsSection}>
          <Text style={styles.recommendationsTitle}>Recommendations</Text>
          {data.recommendations.map((rec, index) => (
            <View key={index} style={styles.recommendationItem}>
              <Ionicons name="checkmark-circle" size={16} color={Colors.success} />
              <Text style={styles.recommendationText}>{rec}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function BillBreakdownCard({
  title,
  breakdown,
}: {
  title: string;
  breakdown: BillPeriodBreakdownData;
}) {
  return (
    <View style={styles.breakdownCard}>
      <Text style={styles.breakdownTitle}>
        {title} · {breakdown.estimate_type === 'illustrative'
          ? 'Illustrative scenario'
          : breakdown.estimate_type === 'unavailable'
            ? 'Estimate unavailable'
            : 'Partial estimate'}
      </Text>
      <Text style={styles.breakdownStatus}>
        {formatDateRange(breakdown.start_date, breakdown.end_date)} ·{' '}
        {breakdown.data_status.replace(/_/g, ' ')} {breakdown.provenance_status} data · tariff:{' '}
        {breakdown.tariff_status.replace(/_/g, ' ')} · GST:{' '}
        {breakdown.gst_treatment.replace(/_/g, ' ')}
      </Text>
      {breakdown.line_items.map((item, index) => (
        <View key={`${item.label}-${index}`} style={styles.breakdownRow}>
          <Text style={styles.breakdownLabel}>
            {item.label}{item.included_in_total ? '' : ' (memo)'}
          </Text>
          <Text style={styles.breakdownAmount}>
            ${item.amount.toFixed(2)}
          </Text>
        </View>
      ))}
      <View style={styles.breakdownTotalRow}>
        <Text style={styles.breakdownTotalLabel}>
          {breakdown.full_bill_available ? 'Estimated total' : 'Modeled components'}
        </Text>
        <Text style={styles.breakdownTotalAmount}>
          {formatMoney(breakdown.total_cost)}
        </Text>
      </View>
      {breakdown.limitations.map((limitation, index) => (
        <Text key={index} style={styles.breakdownLimitation}>• {limitation}</Text>
      ))}
      {['no_confirmed_tariff', 'outside_effective_dates', 'partially_priced'].includes(
        breakdown.tariff_status
      ) && (
        <TouchableOpacity
          style={styles.tariffAction}
          onPress={() => router.push('/tariff-setup')}
          accessibilityRole="link"
          accessibilityLabel="Review or confirm tariff"
        >
          <Text style={styles.tariffActionText}>Review or confirm tariff</Text>
          <Ionicons name="arrow-forward" size={16} color={Colors.primaryDark} />
        </TouchableOpacity>
      )}
    </View>
  );
}

function formatMoney(value: number | null): string {
  return value === null ? 'Unavailable' : `$${value.toFixed(2)}`;
}

function StatBox({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: number | null;
}) {
  if (change === null) {
    return (
      <View style={styles.statBox}>
        <Text style={styles.statLabel}>{label}</Text>
        <Text style={styles.statValue}>{value}</Text>
        <Text style={[styles.statChange, { color: Colors.textSecondary }]}>N/A</Text>
      </View>
    );
  }

  const isPositive = change >= 0;
  const color = isPositive ? Colors.error : Colors.success;

  return (
    <View style={styles.statBox}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={[styles.statChange, { color }]}>
        {isPositive ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
      </Text>
    </View>
  );
}

function formatDateRange(start: string, end: string): string {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const startMonth = startDate.toLocaleDateString('en-AU', { month: 'short', day: 'numeric' });
  const endMonth = endDate.toLocaleDateString('en-AU', { month: 'short', day: 'numeric' });
  return `${startMonth} - ${endMonth}`;
}

function formatLocalDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    ...Shadow.md,
  },
  loadingText: {
    marginTop: Spacing.md,
    color: Colors.textSecondary,
    fontSize: FontSize.md,
  },
  errorText: {
    marginTop: Spacing.md,
    color: Colors.error,
    fontSize: FontSize.md,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: Spacing.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
  },
  retryText: {
    color: Colors.white,
    fontWeight: FontWeight.semibold,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: Spacing.lg,
  },
  title: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.bold,
    color: Colors.text,
  },
  subtitle: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  trendBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.sm,
    gap: 4,
  },
  trendText: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.medium,
  },
  comparisonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.lg,
  },
  periodCard: {
    flex: 1,
    alignItems: 'center',
  },
  previousPeriod: {
    opacity: 0.7,
  },
  periodLabel: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    marginBottom: Spacing.xs,
  },
  costValue: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.primary,
  },
  previousCost: {
    color: Colors.text,
  },
  kwhValue: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  dateRange: {
    fontSize: FontSize.xs,
    color: Colors.gray400,
    marginTop: Spacing.xs,
  },
  changeIndicator: {
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
  },
  changeValue: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.bold,
    marginTop: 4,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    marginBottom: Spacing.lg,
  },
  breakdownCard: {
    backgroundColor: Colors.gray100,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
  },
  breakdownTitle: {
    color: Colors.text,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  breakdownStatus: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    marginTop: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  breakdownRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.xs,
  },
  breakdownLabel: {
    flex: 1,
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
  },
  breakdownAmount: {
    color: Colors.text,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.medium,
    marginLeft: Spacing.sm,
  },
  breakdownTotalRow: {
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: Spacing.sm,
    marginTop: Spacing.xs,
  },
  breakdownTotalLabel: {
    color: Colors.text,
    fontSize: FontSize.md,
    fontWeight: FontWeight.bold,
  },
  breakdownTotalAmount: {
    color: Colors.primary,
    fontSize: FontSize.md,
    fontWeight: FontWeight.bold,
  },
  breakdownLimitation: {
    color: Colors.warning,
    fontSize: FontSize.xs,
    marginTop: Spacing.sm,
  },
  tariffAction: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginTop: Spacing.sm,
    paddingVertical: Spacing.xs,
  },
  tariffActionText: {
    color: Colors.primaryDark,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  statBox: {
    flex: 1,
    alignItems: 'center',
  },
  statLabel: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
  },
  statValue: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginTop: 4,
  },
  statChange: {
    fontSize: FontSize.xs,
    marginTop: 2,
  },
  insightCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: Colors.warning + '10',
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  insightText: {
    flex: 1,
    fontSize: FontSize.sm,
    color: Colors.text,
    lineHeight: 20,
  },
  recommendationsSection: {
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    paddingTop: Spacing.md,
  },
  recommendationsTitle: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
  },
  recommendationItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  recommendationText: {
    flex: 1,
    fontSize: FontSize.sm,
    color: Colors.text,
    lineHeight: 20,
  },
});
