import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Alert,
  Platform,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';
import api, {
  AERPlanDetail,
  AERPlanSummary,
  AERRetailer,
  getErrorMessage,
  tariffsApi,
  UserTariff,
  TariffRevision,
} from '@/services/api';

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
  { id: 'agl_residential_tou', retailer: 'AGL', plan: 'Residential Time of Use', type: 'tou', peakRate: 38.5, offPeakRate: 18.5, shoulderRate: 25, supplyCharge: 98 },
  { id: 'agl_residential_flat', retailer: 'AGL', plan: 'Residential Flat', type: 'flat', flatRate: 28.5, supplyCharge: 98 },
  { id: 'origin_residential_tou', retailer: 'Origin Energy', plan: 'Solar Boost Plus', type: 'tou', peakRate: 42, offPeakRate: 16, shoulderRate: 26.5, supplyCharge: 102 },
  { id: 'origin_residential_flat', retailer: 'Origin Energy', plan: 'Basic Home', type: 'flat', flatRate: 29, supplyCharge: 102 },
  { id: 'energyaus_tou', retailer: 'Energy Australia', plan: 'Total Plan Flexible', type: 'tou', peakRate: 40, offPeakRate: 17, shoulderRate: 24, supplyCharge: 95 },
  { id: 'energyaus_flat', retailer: 'Energy Australia', plan: 'Total Plan Home', type: 'flat', flatRate: 27.5, supplyCharge: 95 },
  { id: 'simply_energy_flat', retailer: 'Simply Energy', plan: 'Simply Plus', type: 'flat', flatRate: 26, supplyCharge: 90 },
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
    feedInRate: '',
    effectiveFrom: '',
    effectiveTo: '',
  });
  const [ratesIncludeGst, setRatesIncludeGst] = useState(true);
  const [termsReviewed, setTermsReviewed] = useState(false);
  const [noOtherComponents, setNoOtherComponents] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [currentTariff, setCurrentTariff] = useState<UserTariff | null>(null);
  const [tariffHistory, setTariffHistory] = useState<TariffRevision[]>([]);
  const [aerRetailers, setAerRetailers] = useState<AERRetailer[]>([]);
  const [aerBrand, setAerBrand] = useState('agl');
  const [aerBrandSearch, setAerBrandSearch] = useState('AGL');
  const [aerPostcode, setAerPostcode] = useState('');
  const [aerPlans, setAerPlans] = useState<AERPlanSummary[]>([]);
  const [aerPlanDetail, setAerPlanDetail] = useState<AERPlanDetail | null>(null);
  const [aerLoading, setAerLoading] = useState(false);
  const [aerError, setAerError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([tariffsApi.getMine(), tariffsApi.getRevisions()])
      .then(([tariff, revisions]) => {
        setCurrentTariff(tariff);
        setTariffHistory(revisions);
      })
      .catch((error: unknown) => setSaveError(getErrorMessage(error)));
    tariffsApi.getAERRetailers()
      .then((catalog) => setAerRetailers(catalog.retailers))
      .catch((error: unknown) => setAerError(getErrorMessage(error)));
  }, []);

  const matchingAERRetailers = aerRetailers
    .filter((retailer) =>
      `${retailer.retailer} ${retailer.brand}`
        .toLowerCase()
        .includes(aerBrandSearch.trim().toLowerCase()),
    )
    .slice(0, 5);

  const handleSearchAERPlans = async () => {
    setAerLoading(true);
    setAerError(null);
    setAerPlanDetail(null);
    try {
      const result = await tariffsApi.searchAERPlans(aerBrand, aerPostcode.trim());
      setAerPlans(result.plans);
      if (result.plans.length === 0) {
        setAerError('No current plan listing confirmed for that postcode and retailer.');
      }
    } catch (error: unknown) {
      setAerError(getErrorMessage(error));
    } finally {
      setAerLoading(false);
    }
  };

  const handleViewAERPlan = async (plan: AERPlanSummary) => {
    setAerLoading(true);
    setAerError(null);
    try {
      setAerPlanDetail(await tariffsApi.getAERPlanDetail(plan.brand, plan.plan_id));
    } catch (error: unknown) {
      setAerError(getErrorMessage(error));
    } finally {
      setAerLoading(false);
    }
  };

  const handleSelectPreset = (preset: TariffPreset) => {
    setSelectedPreset(preset.id);
    setCustomMode(false);
    setSaved(false);
    setSaveError(null);
  };

  const handleSave = async () => {
    setIsLoading(true);
    setSaveError(null);

    try {
      if (selectedPreset) {
        // Apply preset
        await api.post(`/tariffs/from-preset/${selectedPreset}`);
      } else if (customMode) {
        if (!termsReviewed) {
          throw new Error('Review and confirm the entered tariff details before saving.');
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(customRates.effectiveFrom.trim())) {
          throw new Error('Enter the evidenced effective-from date to use this tariff in estimates.');
        }
        const parseRequiredRate = (input: string, label: string) => {
          const value = Number(input);
          if (!input.trim() || !Number.isFinite(value) || value < 0) {
            throw new Error(`${label} must be a non-negative number`);
          }
          return value;
        };
        const data: Record<string, string | number | boolean | null> = {
          tariff_type: tariffType,
          daily_supply_charge_cents: parseRequiredRate(customRates.supplyCharge, 'Supply charge'),
          feed_in_rate_cents_kwh: customRates.feedInRate.trim()
            ? parseRequiredRate(customRates.feedInRate, 'Feed-in rate')
            : null,
          effective_from: customRates.effectiveFrom.trim() || null,
          effective_to: customRates.effectiveTo.trim() || null,
          rates_include_gst: ratesIncludeGst,
          confirmed: true,
          unmodeled_components_confirmed_absent: noOtherComponents,
        };

        if (tariffType === 'flat') {
          data.flat_rate_cents_kwh = parseRequiredRate(customRates.flatRate, 'Flat rate');
        } else {
          data.peak_rate_cents_kwh = parseRequiredRate(customRates.peakRate, 'Peak rate');
          data.off_peak_rate_cents_kwh = parseRequiredRate(customRates.offPeakRate, 'Off-peak rate');
          data.shoulder_rate_cents_kwh = parseRequiredRate(customRates.shoulderRate, 'Shoulder rate');
        }

        await api.post('/tariffs', data);
      }

      if (Platform.OS === 'web') {
        setSaved(true);
      } else {
        Alert.alert('Success', 'Your tariff has been saved', [
          { text: 'OK', onPress: () => router.back() },
        ]);
      }
    } catch (error: unknown) {
      const message = getErrorMessage(error);
      setSaveError(message);
      if (Platform.OS !== 'web') {
        Alert.alert('Error', message);
      }
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
          Tariff details help estimate energy charges. Estimates are not retailer-issued bills.
        </Text>
      </View>

      {/* Info banner */}
      <View style={styles.infoBanner}>
        <Ionicons name="information-circle" size={20} color={Colors.info} />
        <Text style={styles.infoText}>
          Find your rates on your electricity bill or retailer&apos;s website.
        </Text>
      </View>

      {currentTariff && (
        <View style={styles.infoBanner}>
          <View>
            <Text style={styles.presetRetailer}>
              {currentTariff.is_confirmed ? 'Current user-confirmed tariff' : 'Unconfirmed tariff scenario'}
            </Text>
            <Text style={styles.infoText}>
              Source: {currentTariff.confirmation_source ?? 'legacy configuration'} · Effective:{' '}
              {currentTariff.effective_from ?? 'unknown'} to {currentTariff.effective_to ?? 'open-ended'}
            </Text>
            {currentTariff.unsupported_components.length > 0 && (
              <Text style={styles.presetDisclaimer}>
                Not modeled: {currentTariff.unsupported_components.join(', ')}
              </Text>
            )}
          </View>
        </View>
      )}
      {tariffHistory.length > 0 && (
        <Text style={styles.infoText}>
          {tariffHistory.length} immutable tariff revision(s) saved. New confirmed details create a new revision.
        </Text>
      )}

      <View style={styles.aerSection}>
        <Text style={styles.sectionTitle}>Browse AER generic reference plans</Text>
        <Text style={styles.presetDisclaimer}>
          Public reference offers are not evidence of your existing contract and never activate a tariff.
          Confirm the actual terms on your bill or with your retailer before entering rates below.
        </Text>
        <TextInput
          style={styles.aerInput}
          value={aerBrandSearch}
          onChangeText={setAerBrandSearch}
          placeholder="Search retailer"
          placeholderTextColor={Colors.gray400}
          autoCapitalize="none"
          accessibilityLabel="Search AER retailer"
        />
        {matchingAERRetailers.map((retailer) => (
          <TouchableOpacity
            key={retailer.brand}
            style={[styles.aerRetailer, aerBrand === retailer.brand && styles.aerRetailerSelected]}
            onPress={() => {
              setAerBrand(retailer.brand);
              setAerBrandSearch(retailer.retailer);
              setAerPlans([]);
              setAerPlanDetail(null);
            }}
          >
            <Text style={styles.aerRetailerText}>{retailer.retailer}</Text>
            <Text style={styles.aerBrandText}>{retailer.brand}</Text>
          </TouchableOpacity>
        ))}
        <View style={styles.aerSearchRow}>
          <TextInput
            style={[styles.aerInput, styles.aerPostcodeInput]}
            value={aerPostcode}
            onChangeText={setAerPostcode}
            placeholder="Victorian postcode"
            placeholderTextColor={Colors.gray400}
            keyboardType="number-pad"
            maxLength={4}
            accessibilityLabel="Victorian postcode for plan availability"
          />
          <TouchableOpacity
            style={[styles.aerButton, (aerLoading || aerPostcode.length !== 4) && styles.saveButtonDisabled]}
            onPress={handleSearchAERPlans}
            disabled={aerLoading || aerPostcode.length !== 4}
          >
            <Text style={styles.aerButtonText}>{aerLoading ? 'Loading…' : 'Find plans'}</Text>
          </TouchableOpacity>
        </View>
        {aerError && <Text style={styles.errorText}>{aerError}</Text>}
        {aerPlans.map((plan) => (
          <TouchableOpacity
            key={`${plan.brand}:${plan.plan_id}`}
            style={styles.aerPlan}
            onPress={() => handleViewAERPlan(plan)}
          >
            <Text style={styles.aerRetailerText}>{plan.display_name}</Text>
            <Text style={styles.aerBrandText}>
              {plan.brand_name ?? plan.brand} · {plan.plan_type ?? 'Plan'} · Effective{' '}
              {plan.effective_from?.slice(0, 10) ?? 'date unavailable'} to{' '}
              {plan.effective_to?.slice(0, 10) ?? 'open-ended'}
            </Text>
          </TouchableOpacity>
        ))}
        {aerPlanDetail && (
          <View style={styles.aerDetail}>
            <Text style={styles.aerRetailerText}>{aerPlanDetail.display_name}</Text>
            <Text style={styles.aerBrandText}>
              AER Generic Plan Detail v{aerPlanDetail.source_api_version} · retrieved{' '}
              {new Date(aerPlanDetail.retrieved_at).toLocaleString()}
            </Text>
            {aerPlanDetail.unsupported_components.map((component) => (
              <Text key={component} style={styles.presetDisclaimer}>• {component}</Text>
            ))}
            <Text selectable style={styles.aerTerms}>
              {JSON.stringify(aerPlanDetail.terms, null, 2)}
            </Text>
            <Text style={styles.aerBrandText}>
              Review these terms against your retailer documents. Nothing from this catalog is copied
              into your confirmed tariff.
            </Text>
          </View>
        )}
      </View>

      {/* Presets */}
      <Text style={styles.sectionTitle}>Select your plan</Text>
      <Text style={styles.presetDisclaimer}>
        These static examples are illustrative scenarios only, not AER reference plans or proof of your contract. Selecting one does not confirm it as your tariff.
      </Text>
      {saved && (
        <View style={styles.successBanner}>
          <Text style={styles.successText}>Your tariff has been saved.</Text>
          <TouchableOpacity onPress={() => router.back()}>
            <Text style={styles.successAction}>Done</Text>
          </TouchableOpacity>
        </View>
      )}
      {saveError && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{saveError}</Text>
        </View>
      )}
      {PRESETS.map(renderPreset)}

      {/* Custom option */}
      <TouchableOpacity
        style={[styles.customButton, customMode && styles.customButtonActive]}
        onPress={() => {
          setCustomMode(true);
          setSelectedPreset(null);
          setSaved(false);
          setSaveError(null);
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
          <View style={styles.inputRow}>
            <Text style={styles.inputLabel}>Feed-in rate (c/kWh, optional)</Text>
            <TextInput
              style={styles.input}
              value={customRates.feedInRate}
              onChangeText={(t) => setCustomRates({ ...customRates, feedInRate: t })}
              keyboardType="decimal-pad"
              placeholder="0"
              placeholderTextColor={Colors.gray400}
            />
          </View>
          <View style={styles.inputRow}>
            <Text style={styles.inputLabel}>Evidenced effective from (YYYY-MM-DD, required)</Text>
            <TextInput
              style={styles.input}
              value={customRates.effectiveFrom}
              onChangeText={(t) => setCustomRates({ ...customRates, effectiveFrom: t })}
              placeholder="2026-07-01"
              placeholderTextColor={Colors.gray400}
              autoCapitalize="none"
            />
          </View>
          <View style={styles.inputRow}>
            <Text style={styles.inputLabel}>Effective to (YYYY-MM-DD, optional)</Text>
            <TextInput
              style={styles.input}
              value={customRates.effectiveTo}
              onChangeText={(t) => setCustomRates({ ...customRates, effectiveTo: t })}
              placeholder="Leave blank for no end date"
              placeholderTextColor={Colors.gray400}
              autoCapitalize="none"
            />
          </View>
          <TouchableOpacity
            style={styles.gstToggle}
            onPress={() => setRatesIncludeGst(!ratesIncludeGst)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: ratesIncludeGst }}
          >
            <Ionicons
              name={ratesIncludeGst ? 'checkbox' : 'square-outline'}
              size={22}
              color={ratesIncludeGst ? Colors.primary : Colors.textSecondary}
            />
            <Text style={styles.gstToggleText}>Entered rates already include GST</Text>
          </TouchableOpacity>
          {tariffType === 'tou' && (
            <Text style={styles.presetDisclaimer}>
              Time-of-use amounts remain unpriced until exact weekday/weekend windows are confirmed. GridSense will not substitute a generic Victorian schedule.
            </Text>
          )}
          <TouchableOpacity
            style={styles.gstToggle}
            onPress={() => setNoOtherComponents(!noOtherComponents)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: noOtherComponents }}
          >
            <Ionicons
              name={noOtherComponents ? 'checkbox' : 'square-outline'}
              size={22}
              color={noOtherComponents ? Colors.primary : Colors.textSecondary}
            />
            <Text style={styles.gstToggleText}>
              I verified that no additional demand, controlled-load, discount, or other contract terms apply
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.gstToggle}
            onPress={() => setTermsReviewed(!termsReviewed)}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: termsReviewed }}
          >
            <Ionicons
              name={termsReviewed ? 'checkbox' : 'square-outline'}
              size={22}
              color={termsReviewed ? Colors.primary : Colors.textSecondary}
            />
            <Text style={styles.gstToggleText}>
              I reviewed these rates against my retailer documents and confirm they apply from the date entered
            </Text>
          </TouchableOpacity>
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
        <Text style={styles.skipText}>Skip for now — customer estimate unavailable until rates are confirmed</Text>
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
  successBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Colors.success + '15',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  successText: {
    color: Colors.text,
    fontSize: FontSize.sm,
  },
  successAction: {
    color: Colors.primary,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  errorBanner: {
    backgroundColor: Colors.error + '10',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  errorText: {
    color: Colors.error,
    fontSize: FontSize.sm,
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
  aerSection: {
    backgroundColor: Colors.gray50,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginVertical: Spacing.lg,
  },
  aerInput: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    color: Colors.text,
    fontSize: FontSize.md,
    padding: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  aerRetailer: {
    backgroundColor: Colors.white,
    borderColor: Colors.border,
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    padding: Spacing.sm,
    marginBottom: Spacing.xs,
  },
  aerRetailerSelected: {
    borderColor: Colors.primary,
  },
  aerRetailerText: {
    color: Colors.text,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  aerBrandText: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
    marginTop: Spacing.xs,
  },
  aerSearchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
  },
  aerPostcodeInput: {
    flex: 1,
    marginBottom: 0,
  },
  aerButton: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
  },
  aerButtonText: {
    color: Colors.white,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  aerPlan: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginTop: Spacing.sm,
  },
  aerDetail: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginTop: Spacing.md,
  },
  aerTerms: {
    color: Colors.text,
    fontSize: 11,
    lineHeight: 16,
    marginVertical: Spacing.md,
  },
  presetDisclaimer: {
    color: Colors.warning,
    fontSize: FontSize.sm,
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
  gstToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
  },
  gstToggleText: {
    flex: 1,
    color: Colors.text,
    fontSize: FontSize.sm,
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
