import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import api from '@/services/api';

interface BillComparisonData {
  meter_id: number;
  meter_name: string;
  comparison: {
    current_start: string;
    current_end: string;
    current_kwh: number;
    current_cost: number;
    current_days: number;
    current_daily_avg_kwh: number;
    previous_start: string;
    previous_end: string;
    previous_kwh: number;
    previous_cost: number;
    previous_days: number;
    previous_daily_avg_kwh: number;
    kwh_change: number;
    kwh_change_percent: number;
    cost_change: number;
    cost_change_percent: number;
    daily_avg_change_percent: number;
    trend: 'up' | 'down' | 'stable';
    insight: string;
  };
  recommendations: string[];
}

interface BillComparisonProps {
  meterId: number;
  currentStart?: Date;
  currentEnd?: Date;
}

export default function BillComparison({
  meterId,
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
          current_start: start.toISOString().split('T')[0],
          current_end: end.toISOString().split('T')[0],
        });

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
  }, [meterId, currentStart, currentEnd]);

  const fetchComparison = async () => {
    setLoading(true);
    setError(null);

    try {
      const now = new Date();
      const start = currentStart || new Date(now.getFullYear(), now.getMonth(), 1);
      const end = currentEnd || now;

      const params = new URLSearchParams({
        current_start: start.toISOString().split('T')[0],
        current_end: end.toISOString().split('T')[0],
      });

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

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Bill Comparison</Text>
          <Text style={styles.subtitle}>{data.meter_name}</Text>
        </View>
        <View style={[styles.trendBadge, { backgroundColor: trendColor + '15' }]}>
          <Ionicons name={trendIcon} size={16} color={trendColor} />
          <Text style={[styles.trendText, { color: trendColor }]}>
            {comparison.trend === 'stable' ? 'Stable' : 
             comparison.trend === 'down' ? 'Improved' : 'Increased'}
          </Text>
        </View>
      </View>

      {/* Main comparison */}
      <View style={styles.comparisonRow}>
        {/* Current Period */}
        <View style={styles.periodCard}>
          <Text style={styles.periodLabel}>This Period</Text>
          <Text style={styles.costValue}>${comparison.current_cost.toFixed(2)}</Text>
          <Text style={styles.kwhValue}>{comparison.current_kwh.toFixed(1)} kWh</Text>
          <Text style={styles.dateRange}>
            {formatDateRange(comparison.current_start, comparison.current_end)}
          </Text>
        </View>

        {/* Change indicator */}
        <View style={styles.changeIndicator}>
          <Ionicons
            name={comparison.cost_change >= 0 ? 'arrow-up' : 'arrow-down'}
            size={24}
            color={comparison.cost_change >= 0 ? Colors.error : Colors.success}
          />
          <Text style={[
            styles.changeValue,
            { color: comparison.cost_change >= 0 ? Colors.error : Colors.success }
          ]}>
            {comparison.cost_change >= 0 ? '+' : ''}{comparison.cost_change_percent.toFixed(1)}%
          </Text>
        </View>

        {/* Previous Period */}
        <View style={[styles.periodCard, styles.previousPeriod]}>
          <Text style={styles.periodLabel}>Last Period</Text>
          <Text style={[styles.costValue, styles.previousCost]}>
            ${comparison.previous_cost.toFixed(2)}
          </Text>
          <Text style={styles.kwhValue}>{comparison.previous_kwh.toFixed(1)} kWh</Text>
          <Text style={styles.dateRange}>
            {formatDateRange(comparison.previous_start, comparison.previous_end)}
          </Text>
        </View>
      </View>

      {/* Stats row */}
      <View style={styles.statsRow}>
        <StatBox
          label="Daily Avg"
          value={`${comparison.current_daily_avg_kwh.toFixed(1)} kWh`}
          change={comparison.daily_avg_change_percent}
        />
        <StatBox
          label="Usage Change"
          value={`${Math.abs(comparison.kwh_change).toFixed(1)} kWh`}
          change={comparison.kwh_change_percent}
        />
        <StatBox
          label="Cost Change"
          value={`$${Math.abs(comparison.cost_change).toFixed(2)}`}
          change={comparison.cost_change_percent}
        />
      </View>

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

function StatBox({ label, value, change }: { label: string; value: string; change: number }) {
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
