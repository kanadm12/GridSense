import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Dimensions,
} from 'react-native';
import { BarChart } from 'react-native-gifted-charts';
import { useMetersStore, useUsageStore } from '@/stores';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

const screenWidth = Dimensions.get('window').width;

type ChartType = 'daily' | 'hourly' | 'weekly';

export default function UsageScreen() {
  const { selectedMeter } = useMetersStore();
  const { dailyUsage, hourlyUsage, fetchAllUsageData, isLoading } = useUsageStore();
  const [chartType, setChartType] = useState<ChartType>('daily');

  useEffect(() => {
    if (selectedMeter) {
      fetchAllUsageData(selectedMeter.id);
    }
  }, [selectedMeter]);

  const refresh = () => {
    if (selectedMeter) {
      fetchAllUsageData(selectedMeter.id);
    }
  };

  // Prepare chart data
  const getDailyChartData = () => {
    return dailyUsage
      .slice(0, 14) // Last 14 days
      .reverse()
      .map((day) => ({
        value: day.total_kwh,
        label: new Date(day.date).getDate().toString(),
        frontColor: Colors.primary,
      }));
  };

  const getHourlyChartData = () => {
    return hourlyUsage.map((hour) => ({
      value: hour.avg_kwh,
      label: hour.hour.toString(),
      frontColor:
        hour.hour >= 15 && hour.hour < 21
          ? Colors.chartPeak
          : hour.hour >= 22 || hour.hour < 7
          ? Colors.chartOffPeak
          : Colors.chartShoulder,
    }));
  };

  const chartData = chartType === 'daily' ? getDailyChartData() : getHourlyChartData();
  const chartWidth = screenWidth - Spacing.md * 4;
  const barWidth = Math.max(12, chartWidth / chartData.length - 8);

  if (!selectedMeter) {
    return (
      <View style={styles.emptyContainer}>
        <Ionicons name="analytics-outline" size={64} color={Colors.gray300} />
        <Text style={styles.emptyText}>No meter data available</Text>
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
      {/* Chart Type Selector */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, chartType === 'daily' && styles.tabActive]}
          onPress={() => setChartType('daily')}
        >
          <Text style={[styles.tabText, chartType === 'daily' && styles.tabTextActive]}>
            Daily
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, chartType === 'hourly' && styles.tabActive]}
          onPress={() => setChartType('hourly')}
        >
          <Text style={[styles.tabText, chartType === 'hourly' && styles.tabTextActive]}>
            By Hour
          </Text>
        </TouchableOpacity>
      </View>

      {/* Chart Card */}
      <View style={styles.chartCard}>
        <Text style={styles.chartTitle}>
          {chartType === 'daily' ? 'Daily Usage (kWh)' : 'Hourly Pattern (Avg kWh)'}
        </Text>

        {chartData.length > 0 ? (
          <View style={styles.chartContainer}>
            <BarChart
              data={chartData}
              width={chartWidth}
              height={200}
              barWidth={barWidth}
              spacing={4}
              roundedTop
              roundedBottom
              hideRules
              xAxisThickness={1}
              yAxisThickness={0}
              xAxisColor={Colors.gray200}
              yAxisTextStyle={{ color: Colors.textSecondary, fontSize: 10 }}
              xAxisLabelTextStyle={{ color: Colors.textSecondary, fontSize: 10 }}
              noOfSections={4}
              maxValue={Math.max(...chartData.map((d) => d.value)) * 1.2}
            />
          </View>
        ) : (
          <View style={styles.noDataContainer}>
            <Text style={styles.noDataText}>No data available</Text>
          </View>
        )}

        {chartType === 'hourly' && (
          <View style={styles.legend}>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: Colors.chartPeak }]} />
              <Text style={styles.legendText}>Peak (3-9pm)</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: Colors.chartShoulder }]} />
              <Text style={styles.legendText}>Shoulder</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: Colors.chartOffPeak }]} />
              <Text style={styles.legendText}>Off-Peak</Text>
            </View>
          </View>
        )}
      </View>

      {/* Daily Breakdown List */}
      {chartType === 'daily' && dailyUsage.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recent Days</Text>
          {dailyUsage.slice(0, 7).map((day) => (
            <View key={day.date} style={styles.dayRow}>
              <View>
                <Text style={styles.dayDate}>
                  {new Date(day.date).toLocaleDateString('en-AU', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                  })}
                </Text>
                <Text style={styles.dayBreakdown}>
                  Peak: {day.peak_kwh.toFixed(1)} | Off-Peak: {day.off_peak_kwh.toFixed(1)}
                </Text>
              </View>
              <View style={styles.dayStats}>
                <Text style={styles.dayValue}>{day.total_kwh.toFixed(1)} kWh</Text>
                {day.estimated_cost && (
                  <Text style={styles.dayCost}>${day.estimated_cost.toFixed(2)}</Text>
                )}
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Hourly Insights */}
      {chartType === 'hourly' && hourlyUsage.length > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Peak Hours</Text>
          {hourlyUsage
            .filter((h) => h.hour >= 15 && h.hour < 21)
            .map((hour) => (
              <View key={hour.hour} style={styles.hourRow}>
                <Text style={styles.hourLabel}>
                  {hour.hour.toString().padStart(2, '0')}:00
                </Text>
                <View style={styles.hourBar}>
                  <View
                    style={[
                      styles.hourBarFill,
                      {
                        width: `${(hour.avg_kwh / Math.max(...hourlyUsage.map((h) => h.avg_kwh))) * 100}%`,
                        backgroundColor: Colors.chartPeak,
                      },
                    ]}
                  />
                </View>
                <Text style={styles.hourValue}>{hour.avg_kwh.toFixed(2)}</Text>
              </View>
            ))}
        </View>
      )}
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
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.gray100,
    borderRadius: BorderRadius.md,
    padding: Spacing.xs,
    marginBottom: Spacing.md,
  },
  tab: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.sm,
  },
  tabActive: {
    backgroundColor: Colors.white,
    ...Shadow.sm,
  },
  tabText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    fontWeight: FontWeight.medium,
  },
  tabTextActive: {
    color: Colors.text,
  },
  chartCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    ...Shadow.md,
  },
  chartTitle: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  chartContainer: {
    alignItems: 'center',
  },
  noDataContainer: {
    height: 200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  noDataText: {
    color: Colors.textSecondary,
  },
  legend: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: Spacing.md,
    marginTop: Spacing.md,
    paddingTop: Spacing.md,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  legendText: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
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
  dayRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: Colors.white,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.sm,
    ...Shadow.sm,
  },
  dayDate: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.medium,
    color: Colors.text,
  },
  dayBreakdown: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  dayStats: {
    alignItems: 'flex-end',
  },
  dayValue: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.primary,
  },
  dayCost: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  hourRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.sm,
    gap: Spacing.sm,
  },
  hourLabel: {
    width: 50,
    fontSize: FontSize.sm,
    color: Colors.text,
  },
  hourBar: {
    flex: 1,
    height: 8,
    backgroundColor: Colors.gray100,
    borderRadius: 4,
    overflow: 'hidden',
  },
  hourBarFill: {
    height: '100%',
    borderRadius: 4,
  },
  hourValue: {
    width: 50,
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    textAlign: 'right',
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
  },
});
