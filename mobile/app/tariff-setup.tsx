import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import api from '@/services/api';

interface TariffPreset {
  id: string;
  retailer: string;
  plan: string;
  type: 'flat' | 'tou';
  flatRate?: number;
  peakRate?: number;
  offPeakRate?: number;
  shoulderRate?: number;
  supplyCharge: number;
}

const PRESETS: TariffPreset[] = [
  { id: 'agl_tou', retailer: 'AGL', plan: 'Time of Use', type: 'tou', peakRate: 38.5, offPeakRate: 18.5, shoulderRate: 25, supplyCharge: 98 },
  { id: 'agl_flat', retailer: 'AGL', plan: 'Flat Rate', type: 'flat', flatRate: 28.5, supplyCharge: 98 },
  { id: 'origin_tou', retailer: 'Origin Energy', plan: 'Solar Boost', type: 'tou', peakRate: 42, offPeakRate: 16, shoulderRate: 26.5, supplyCharge: 102 },
  { id: 'origin_flat', retailer: 'Origin', plan: 'Basic Home', type: 'flat', flatRate: 29, supplyCharge: 102 },
  { id: 'ea_tou', retailer: 'Energy Australia', plan: 'Flexible', type: 'tou', peakRate: 40, offPeakRate: 17, shoulderRate: 24, supplyCharge: 95 },
  { id: 'ea_flat', retailer: 'Energy Australia', plan: 'Total Plan', type: 'flat', flatRate: 27.5, supplyCharge: 95 },
  { id: 'simply_flat', retailer: 'Simply Energy', plan: 'Simply Plus', type: 'flat', flatRate: 26, supplyCharge: 90 },
  { id: 'powershop_tou', retailer: 'Powershop', plan: 'Shopper Market', type: 'tou', peakRate: 36, offPeakRate: 15, shoulderRate: 23, supplyCharge: 88 },
];

export default function TariffSetupScreen() {
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [customMode, setCustomMode] = useState(false);
  const [tariffType, setTariffType] = useState<'flat' | 'tou'>('flat');
  const [customRates, setCustomRates] = useState({
    flatRate: '',
    peakRate: '',
    offPeakRate: '',
    shoulderRate: '',
    supplyCharge: '100',
  });
  const [isLoading, setIsLoading] = useState(false);

  const handleSelectPreset = (preset: TariffPreset) => {
    setSelectedPreset(preset.id);
    setCustomMode(false);
  };

  const handleSave = async () => {
    setIsLoading(true);

    try {
      if (selectedPreset) {
        // Apply preset
        await api.post(`/tariffs/from-preset/${selectedPreset}`);
      } else if (customMode) {
        // Create custom tariff
        const data: any = {
          tariff_type: tariffType,
          daily_supply_charge_cents: parseFloat(customRates.supplyCharge) || 100,
        };

        if (tariffType === 'flat') {
          data.flat_rate_cents_kwh = parseFloat(customRates.flatRate) || 25;
        } else {
          data.peak_rate_cents_kwh = parseFloat(customRates.peakRate) || 38;
          data.off_peak_rate_cents_kwh = parseFloat(customRates.offPeakRate) || 18;
          data.shoulder_rate_cents_kwh = parseFloat(customRates.shoulderRate) || 25;
        }

        await api.post('/tariffs', data);
      }

      Alert.alert('Success', 'Your tariff has been saved', [
        { text: 'OK', onPress: () => router.back() },
      ]);
    } catch (error: any) {
      Alert.alert('Error', error.response?.data?.detail || 'Failed to save tariff');
    }

    setIsLoading(false);
  };

  const renderPreset = (preset: TariffPreset) => {
    const isSelected = selectedPreset === preset.id;

    return (
      <TouchableOpacity
        key={preset.id}
        style={[styles.presetCard, isSelected && styles.presetSelected]}
        onPress={() => handleSelectPreset(preset)}
      >
        <View style={styles.presetHeader}>
          <Text style={styles.presetRetailer}>{preset.retailer}</Text>
          <Text style={styles.presetPlan}>{preset.plan}</Text>
        </View>

        <View style={styles.presetRates}>
          {preset.type === 'flat' ? (
            <View style={styles.rateChip}>
              <Text style={styles.rateValue}>{preset.flatRate}c/kWh</Text>
            </View>
          ) : (
            <>
              <View style={[styles.rateChip, styles.peakChip]}>
                <Text style={styles.rateLabel}>Peak</Text>
                <Text style={styles.rateValue}>{preset.peakRate}c</Text>
              </View>
              <View style={[styles.rateChip, styles.shoulderChip]}>
                <Text style={styles.rateLabel}>Shoulder</Text>
                <Text style={styles.rateValue}>{preset.shoulderRate}c</Text>
              </View>
              <View style={[styles.rateChip, styles.offPeakChip]}>
                <Text style={styles.rateLabel}>Off-Peak</Text>
                <Text style={styles.rateValue}>{preset.offPeakRate}c</Text>
              </View>
            </>
          )}
        </View>

        {isSelected && (
          <View style={styles.checkmark}>
            <Ionicons name="checkmark-circle" size={24} color={Colors.primary} />
          </View>
        )}
      </TouchableOpacity>
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.closeButton} onPress={() => router.back()}>
          <Ionicons name="close" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>Set Your Tariff</Text>
        <Text style={styles.subtitle}>
          This helps us calculate accurate cost savings for your recommendations.
        </Text>
      </View>

      {/* Info banner */}
      <View style={styles.infoBanner}>
        <Ionicons name="information-circle" size={20} color={Colors.info} />
        <Text style={styles.infoText}>
          Find your rates on your electricity bill or retailer's website.
        </Text>
      </View>

      {/* Presets */}
      <Text style={styles.sectionTitle}>Select your plan</Text>
      {PRESETS.map(renderPreset)}

      {/* Custom option */}
      <TouchableOpacity
        style={[styles.customButton, customMode && styles.customButtonActive]}
        onPress={() => {
          setCustomMode(true);
          setSelectedPreset(null);
        }}
      >
        <Ionicons
          name="create-outline"
          size={20}
          color={customMode ? Colors.primary : Colors.textSecondary}
        />
        <Text style={[styles.customText, customMode && styles.customTextActive]}>
          Enter custom rates
        </Text>
      </TouchableOpacity>

      {/* Custom form */}
      {customMode && (
        <View style={styles.customForm}>
          {/* Tariff type selector */}
          <View style={styles.typeSelector}>
            <TouchableOpacity
              style={[styles.typeButton, tariffType === 'flat' && styles.typeButtonActive]}
              onPress={() => setTariffType('flat')}
            >
              <Text style={[styles.typeText, tariffType === 'flat' && styles.typeTextActive]}>
                Flat Rate
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.typeButton, tariffType === 'tou' && styles.typeButtonActive]}
              onPress={() => setTariffType('tou')}
            >
              <Text style={[styles.typeText, tariffType === 'tou' && styles.typeTextActive]}>
                Time of Use
              </Text>
            </TouchableOpacity>
          </View>

          {tariffType === 'flat' ? (
            <View style={styles.inputRow}>
              <Text style={styles.inputLabel}>Rate (c/kWh)</Text>
              <TextInput
                style={styles.input}
                value={customRates.flatRate}
                onChangeText={(t) => setCustomRates({ ...customRates, flatRate: t })}
                keyboardType="decimal-pad"
                placeholder="25.0"
                placeholderTextColor={Colors.gray400}
              />
            </View>
          ) : (
            <>
              <View style={styles.inputRow}>
                <Text style={styles.inputLabel}>Peak rate (c/kWh)</Text>
                <TextInput
                  style={styles.input}
                  value={customRates.peakRate}
                  onChangeText={(t) => setCustomRates({ ...customRates, peakRate: t })}
                  keyboardType="decimal-pad"
                  placeholder="38.0"
                  placeholderTextColor={Colors.gray400}
                />
              </View>
              <View style={styles.inputRow}>
                <Text style={styles.inputLabel}>Shoulder rate (c/kWh)</Text>
                <TextInput
                  style={styles.input}
                  value={customRates.shoulderRate}
                  onChangeText={(t) => setCustomRates({ ...customRates, shoulderRate: t })}
                  keyboardType="decimal-pad"
                  placeholder="25.0"
                  placeholderTextColor={Colors.gray400}
                />
              </View>
              <View style={styles.inputRow}>
                <Text style={styles.inputLabel}>Off-peak rate (c/kWh)</Text>
                <TextInput
                  style={styles.input}
                  value={customRates.offPeakRate}
                  onChangeText={(t) => setCustomRates({ ...customRates, offPeakRate: t })}
                  keyboardType="decimal-pad"
                  placeholder="18.0"
                  placeholderTextColor={Colors.gray400}
                />
              </View>
            </>
          )}

          <View style={styles.inputRow}>
            <Text style={styles.inputLabel}>Daily supply charge (c/day)</Text>
            <TextInput
              style={styles.input}
              value={customRates.supplyCharge}
              onChangeText={(t) => setCustomRates({ ...customRates, supplyCharge: t })}
              keyboardType="decimal-pad"
              placeholder="100"
              placeholderTextColor={Colors.gray400}
            />
          </View>
        </View>
      )}

      {/* Save button */}
      <TouchableOpacity
        style={[
          styles.saveButton,
          (!selectedPreset && !customMode) && styles.saveButtonDisabled,
        ]}
        onPress={handleSave}
        disabled={(!selectedPreset && !customMode) || isLoading}
      >
        <Text style={styles.saveButtonText}>
          {isLoading ? 'Saving...' : 'Save Tariff'}
        </Text>
      </TouchableOpacity>

      {/* Skip option */}
      <TouchableOpacity style={styles.skipButton} onPress={() => router.back()}>
        <Text style={styles.skipText}>Skip for now (use default rates)</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    padding: Spacing.lg,
    paddingBottom: Spacing.xxl,
  },
  header: {
    marginBottom: Spacing.lg,
  },
  closeButton: {
    alignSelf: 'flex-end',
    padding: Spacing.xs,
    marginBottom: Spacing.sm,
  },
  title: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
  },
  subtitle: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.info + '15',
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    marginBottom: Spacing.lg,
    gap: Spacing.sm,
  },
  infoText: {
    flex: 1,
    fontSize: FontSize.sm,
    color: Colors.info,
  },
  sectionTitle: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: Spacing.md,
  },
  presetCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    borderWidth: 2,
    borderColor: 'transparent',
    ...Shadow.sm,
  },
  presetSelected: {
    borderColor: Colors.primary,
  },
  presetHeader: {
    marginBottom: Spacing.sm,
  },
  presetRetailer: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
  },
  presetPlan: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  presetRates: {
    flexDirection: 'row',
    gap: Spacing.sm,
    flexWrap: 'wrap',
  },
  rateChip: {
    backgroundColor: Colors.gray100,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.sm,
  },
  peakChip: {
    backgroundColor: Colors.error + '15',
  },
  shoulderChip: {
    backgroundColor: Colors.warning + '15',
  },
  offPeakChip: {
    backgroundColor: Colors.success + '15',
  },
  rateLabel: {
    fontSize: 10,
    color: Colors.textSecondary,
  },
  rateValue: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
  },
  checkmark: {
    position: 'absolute',
    top: Spacing.md,
    right: Spacing.md,
  },
  customButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.md,
    marginTop: Spacing.md,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    borderStyle: 'dashed',
    gap: Spacing.sm,
  },
  customButtonActive: {
    borderColor: Colors.primary,
    backgroundColor: Colors.primary + '10',
    borderStyle: 'solid',
  },
  customText: {
    color: Colors.textSecondary,
    fontSize: FontSize.md,
  },
  customTextActive: {
    color: Colors.primary,
    fontWeight: FontWeight.medium,
  },
  customForm: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginTop: Spacing.md,
    ...Shadow.sm,
  },
  typeSelector: {
    flexDirection: 'row',
    backgroundColor: Colors.gray100,
    borderRadius: BorderRadius.md,
    padding: Spacing.xs,
    marginBottom: Spacing.md,
  },
  typeButton: {
    flex: 1,
    paddingVertical: Spacing.sm,
    alignItems: 'center',
    borderRadius: BorderRadius.sm,
  },
  typeButtonActive: {
    backgroundColor: Colors.white,
    ...Shadow.sm,
  },
  typeText: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  typeTextActive: {
    color: Colors.text,
    fontWeight: FontWeight.medium,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.md,
  },
  inputLabel: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.text,
  },
  input: {
    width: 100,
    backgroundColor: Colors.gray50,
    borderRadius: BorderRadius.md,
    padding: Spacing.sm,
    textAlign: 'center',
    fontSize: FontSize.md,
    color: Colors.text,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  saveButton: {
    backgroundColor: Colors.primary,
    padding: Spacing.md,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    marginTop: Spacing.xl,
  },
  saveButtonDisabled: {
    opacity: 0.5,
  },
  saveButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  skipButton: {
    alignItems: 'center',
    marginTop: Spacing.md,
  },
  skipText: {
    color: Colors.textSecondary,
    fontSize: FontSize.md,
  },
});
