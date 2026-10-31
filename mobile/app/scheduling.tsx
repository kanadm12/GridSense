import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, router } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  ApplianceTaskV1,
  SchedulingRequestV1,
  SchedulingResponseV1,
  ScheduleV1,
  Meter,
  UserTariff,
  getErrorMessage,
  schedulingApi,
  tariffsApi,
} from '@/services/api';
import { useMetersStore } from '@/stores';
import {
  BorderRadius,
  Colors,
  FontSize,
  FontWeight,
  Shadow,
  Spacing,
} from '@/constants/theme';

const INTERVAL_MINUTES = 30;
const DEMO_BASELINE_KW = 0.8;
const STEP_MS = INTERVAL_MINUTES * 60 * 1000;

const STATE_TIMEZONES: Record<string, string> = {
  ACT: 'Australia/Sydney',
  NSW: 'Australia/Sydney',
  NT: 'Australia/Darwin',
  QLD: 'Australia/Brisbane',
  SA: 'Australia/Adelaide',
  TAS: 'Australia/Hobart',
  VIC: 'Australia/Melbourne',
};

interface WallTimeParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

interface TaskForm {
  appliance: string;
  powerKw: string;
  durationMinutes: number;
  earliestStart: string;
  deadline: string;
  preferredStart: string;
  mandatory: boolean;
  omissionPenaltyAud: string;
}

const formatterForZone = (timeZone: string) =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });

const getWallParts = (instantMs: number, timeZone: string): WallTimeParts => {
  const parts = formatterForZone(timeZone).formatToParts(new Date(instantMs));
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value);
  return {
    year: value('year'),
    month: value('month'),
    day: value('day'),
    hour: value('hour'),
    minute: value('minute'),
  };
};

const localDateString = (instantMs: number, timeZone: string): string => {
  const parts = getWallParts(instantMs, timeZone);
  return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
};

const addLocalDays = (date: string, days: number): string => {
  const [year, month, day] = date.split('-').map(Number);
  const adjusted = new Date(Date.UTC(year, month - 1, day + days));
  return `${adjusted.getUTCFullYear()}-${String(adjusted.getUTCMonth() + 1).padStart(2, '0')}-${String(adjusted.getUTCDate()).padStart(2, '0')}`;
};

const localDateTimeToIso = (value: string, timeZone: string): string => {
  const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$/.exec(value.trim());
  if (!match) {
    throw new Error('Enter a date and time as YYYY-MM-DD HH:mm.');
  }
  const [, yearText, monthText, dayText, hourText, minuteText] = match;
  const parts: WallTimeParts = {
    year: Number(yearText),
    month: Number(monthText),
    day: Number(dayText),
    hour: Number(hourText),
    minute: Number(minuteText),
  };
  const wallEpoch = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute
  );
  const checkDate = new Date(wallEpoch);
  if (
    checkDate.getUTCFullYear() !== parts.year ||
    checkDate.getUTCMonth() + 1 !== parts.month ||
    checkDate.getUTCDate() !== parts.day ||
    parts.hour > 23 ||
    parts.minute > 59 ||
    parts.minute % INTERVAL_MINUTES !== 0
  ) {
    throw new Error(`Use a valid local time aligned to ${INTERVAL_MINUTES}-minute intervals.`);
  }

  let instantMs = wallEpoch;
  for (let iteration = 0; iteration < 4; iteration += 1) {
    const observed = getWallParts(instantMs, timeZone);
    const observedAsUtc = Date.UTC(
      observed.year,
      observed.month - 1,
      observed.day,
      observed.hour,
      observed.minute
    );
    const difference = wallEpoch - observedAsUtc;
    if (difference === 0) break;
    instantMs += difference;
  }
  const resolved = getWallParts(instantMs, timeZone);
  if (
    resolved.year !== parts.year ||
    resolved.month !== parts.month ||
    resolved.day !== parts.day ||
    resolved.hour !== parts.hour ||
    resolved.minute !== parts.minute
  ) {
    throw new Error('That local time does not exist in this timezone because of a clock change.');
  }

  const offsetMinutes =
    (Date.UTC(
      resolved.year,
      resolved.month - 1,
      resolved.day,
      resolved.hour,
      resolved.minute
    ) -
      instantMs) /
    60000;
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absoluteOffset = Math.abs(offsetMinutes);
  const offset = `${sign}${String(Math.floor(absoluteOffset / 60)).padStart(2, '0')}:${String(absoluteOffset % 60).padStart(2, '0')}`;
  return `${yearText}-${monthText}-${dayText}T${hourText}:${minuteText}:00${offset}`;
};

const instantToLocalIso = (instantMs: number, timeZone: string): string => {
  const parts = getWallParts(instantMs, timeZone);
  const localAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute
  );
  const offsetMinutes = (localAsUtc - instantMs) / 60000;
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const absoluteOffset = Math.abs(offsetMinutes);
  const offset = `${sign}${String(Math.floor(absoluteOffset / 60)).padStart(2, '0')}:${String(absoluteOffset % 60).padStart(2, '0')}`;
  return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}T${String(parts.hour).padStart(2, '0')}:${String(parts.minute).padStart(2, '0')}:00${offset}`;
};

const minuteLabel = (minute: number) =>
  `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;

const formatAud = (value: number | null | undefined) =>
  value == null ? 'Unavailable' : `$${value.toFixed(2)}`;

const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const tariffWindows = (tariff: UserTariff | null, meter: Meter | null): string[] => {
  if (!tariff) return [];
  if (tariff.periods?.length) {
    return tariff.periods.map((period) => {
      const days =
        period.days.length === 7
          ? 'Every day'
          : period.days.map((day) => dayLabels[day]).join(', ');
      return `${period.name}: ${minuteLabel(period.start_minute)}–${minuteLabel(period.end_minute)} · ${period.rate_cents_kwh.toFixed(1)} c/kWh · ${days}`;
    });
  }
  if (tariff.tariff_type === 'flat' && tariff.flat_rate_cents_kwh !== null) {
    return [`All intervals · ${tariff.flat_rate_cents_kwh.toFixed(1)} c/kWh`];
  }
  if (tariff.tariff_type === 'tou' || tariff.tariff_type === 'demand') {
    const rates = [
      tariff.peak_rate_cents_kwh !== null
        ? `Peak 15:00–21:00 weekdays · ${tariff.peak_rate_cents_kwh.toFixed(1)} c/kWh`
        : null,
      tariff.shoulder_rate_cents_kwh !== null
        ? `Shoulder 07:00–15:00 and 21:00–22:00 weekdays · ${tariff.shoulder_rate_cents_kwh.toFixed(1)} c/kWh`
        : null,
      tariff.off_peak_rate_cents_kwh !== null
        ? `Off-peak 22:00–07:00 and weekends · ${tariff.off_peak_rate_cents_kwh.toFixed(1)} c/kWh`
        : null,
    ].filter((line): line is string => line !== null);
    if (meter?.state.toUpperCase() !== 'VIC') {
      return ['Time-of-use periods are not verified for this meter region.'];
    }
    return rates;
  }
  return ['No complete interval-rate windows are available.'];
};

const defaultTaskForm = (timeZone: string): TaskForm => {
  const tomorrow = addLocalDays(localDateString(Date.now(), timeZone), 1);
  return {
    appliance: 'Water heater',
    powerKw: '2.4',
    durationMinutes: 60,
    earliestStart: `${tomorrow} 08:00`,
    deadline: `${tomorrow} 12:00`,
    preferredStart: `${tomorrow} 09:00`,
    mandatory: true,
    omissionPenaltyAud: '1.00',
  };
};

const scheduleTask = (schedule: ScheduleV1 | null | undefined) =>
  schedule?.tasks[0];

const readableTime = (iso: string | null | undefined, timeZone: string) => {
  if (!iso) return 'Not scheduled';
  return new Intl.DateTimeFormat('en-AU', {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso));
};

export default function SchedulingScreen() {
  const selectedMeter = useMetersStore((state) => state.selectedMeter);
  const fetchMeters = useMetersStore((state) => state.fetchMeters);
  const [meter, setMeter] = useState<Meter | null>(selectedMeter);
  const [tariff, setTariff] = useState<UserTariff | null>(null);
  const [timeZone, setTimeZone] = useState('Australia/Melbourne');
  const [form, setForm] = useState<TaskForm>(() => defaultTaskForm('Australia/Melbourne'));
  const [contextLoading, setContextLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [result, setResult] = useState<SchedulingResponseV1 | null>(null);
  const [resultError, setResultError] = useState<string | null>(null);
  const [previewChoice, setPreviewChoice] = useState<'recommended' | 'original' | null>(
    null
  );

  useFocusEffect(
    useCallback(() => {
      let active = true;
      const loadContext = async () => {
        setContextLoading(true);
        setContextError(null);
        try {
          if (!selectedMeter) {
            await fetchMeters();
          }
          const currentMeter = useMetersStore.getState().selectedMeter;
          if (!currentMeter) {
            setMeter(null);
            setTariff(null);
            setContextError(useMetersStore.getState().error || 'Add or select a meter first.');
            return;
          }
          const currentTimezone = STATE_TIMEZONES[currentMeter.state.toUpperCase()];
          if (!currentTimezone) {
            setMeter(currentMeter);
            setTariff(null);
            setContextError(
              `Scheduling does not support the meter region "${currentMeter.state}" yet.`
            );
            return;
          }
          setMeter(currentMeter);
          setTimeZone(currentTimezone);
          const currentTariff = await tariffsApi.getMine();
          if (active) {
            setTariff(currentTariff);
            if (!currentTariff) {
              setContextError('Configure a non-illustrative tariff to request a schedule.');
            }
          }
        } catch (error) {
          if (active) {
            setContextError(getErrorMessage(error));
          }
        } finally {
          if (active) setContextLoading(false);
        }
      };
      void loadContext();
      return () => {
        active = false;
      };
    }, [fetchMeters, selectedMeter?.id])
  );

  const displayedTariffWindows = useMemo(
    () => tariffWindows(tariff, meter),
    [meter, tariff]
  );

  const updateForm = <K extends keyof TaskForm>(key: K, value: TaskForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setValidationError(null);
    setResultError(null);
    setResult(null);
    setPreviewChoice(null);
  };

  const previewSchedule = async () => {
    setValidationError(null);
    setResultError(null);
    setPreviewChoice(null);
    if (!meter) {
      setValidationError('Select a meter before planning a task.');
      return;
    }
    if (!form.appliance.trim()) {
      setValidationError('Enter an appliance name.');
      return;
    }
    const powerKw = Number(form.powerKw);
    if (!Number.isFinite(powerKw) || powerKw <= 0 || powerKw > 100) {
      setValidationError('Estimated power must be a number greater than 0 and no more than 100 kW.');
      return;
    }

    let earliestStart: string;
    let deadline: string;
    let preferredStart: string | null;
    try {
      earliestStart = localDateTimeToIso(form.earliestStart, timeZone);
      deadline = localDateTimeToIso(form.deadline, timeZone);
      preferredStart = form.preferredStart.trim()
        ? localDateTimeToIso(form.preferredStart, timeZone)
        : null;
    } catch (error) {
      setValidationError(getErrorMessage(error));
      return;
    }

    const earliestMs = Date.parse(earliestStart);
    const deadlineMs = Date.parse(deadline);
    const preferredMs = preferredStart ? Date.parse(preferredStart) : null;
    if (deadlineMs <= earliestMs) {
      setValidationError('Latest finish must be later than the earliest start.');
      return;
    }
    if (deadlineMs - earliestMs > 7 * 24 * 60 * 60 * 1000) {
      setValidationError('Keep the scheduling window within seven days for this preview.');
      return;
    }
    if (preferredMs !== null) {
      const latestStartMs = deadlineMs - form.durationMinutes * 60 * 1000;
      if (preferredMs < earliestMs || preferredMs > latestStartMs) {
        setValidationError('Preferred start must fit the full task before its latest finish.');
        return;
      }
    }
    const horizonSlots = (deadlineMs - earliestMs) / STEP_MS;
    if (!Number.isInteger(horizonSlots) || horizonSlots < 1) {
      setValidationError('The available window must align to 30-minute intervals.');
      return;
    }
    const omissionPenalty = Number(form.omissionPenaltyAud);
    const hasOmissionPenalty = form.omissionPenaltyAud.trim().length > 0;
    if (
      !form.mandatory &&
      hasOmissionPenalty &&
      (!Number.isFinite(omissionPenalty) || omissionPenalty < 0)
    ) {
      setValidationError('Enter a nonnegative omission penalty in AUD, or leave it blank.');
      return;
    }

    const task: ApplianceTaskV1 = {
      task_id: 'demo-appliance-task',
      appliance: form.appliance.trim(),
      rated_power_kw: powerKw,
      duration_minutes: form.durationMinutes,
      earliest_start: earliestStart,
      deadline,
      preferred_start: preferredStart,
      mandatory: form.mandatory,
      ...(!form.mandatory && hasOmissionPenalty
        ? { omission_penalty_aud: omissionPenalty }
        : {}),
    };
    const intervals = Array.from({ length: horizonSlots }, (_, index) => ({
      interval_start: instantToLocalIso(earliestMs + index * STEP_MS, timeZone),
      demand_kw: DEMO_BASELINE_KW,
    }));
    const request: SchedulingRequestV1 = {
      schema_version: '1.0',
      meter_id: meter.id,
      tariff_id: tariff?.id ?? null,
      scenario_id: 'mobile-demo-appliance',
      interval_minutes: INTERVAL_MINUTES,
      timezone: timeZone,
      currency: 'AUD',
      preference_penalty_aud_per_interval: 0.01,
      tasks: [task],
      baseline_profile: {
        source: 'synthetic',
        profile_id: 'mobile-demo-baseline-v1',
        measurement_method: null,
        scenario_id: 'mobile-demo-appliance',
        includes_scheduled_tasks: false,
        intervals,
      },
    };

    setSubmitting(true);
    try {
      const response = await schedulingApi.previewV1(request);
      setResult(response);
    } catch (error) {
      setResult(null);
      setResultError(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const originalStart = form.preferredStart.trim() || form.earliestStart;
  const originalStartLabel = (() => {
    try {
      return readableTime(localDateTimeToIso(originalStart, timeZone), timeZone);
    } catch {
      return 'Not available';
    }
  })();
  const originalEnd = (() => {
    try {
      const start = Date.parse(localDateTimeToIso(originalStart, timeZone));
      return readableTime(
        new Date(start + form.durationMinutes * 60 * 1000).toISOString(),
        timeZone
      );
    } catch {
      return 'Not available';
    }
  })();
  const candidateTask = scheduleTask(result?.candidate_schedule);
  const referenceTask = scheduleTask(result?.reference_schedule);
  const preferenceShift = (() => {
    if (!candidateTask?.start || !form.preferredStart.trim()) return null;
    try {
      const preferredIso = localDateTimeToIso(form.preferredStart, timeZone);
      const intervals = Math.round(
        (Date.parse(candidateTask.start) - Date.parse(preferredIso)) / STEP_MS
      );
      if (intervals === 0) return 'Starts at your preferred time.';
      return `Starts ${Math.abs(intervals)} interval${Math.abs(intervals) === 1 ? '' : 's'} ${
        intervals < 0 ? 'earlier' : 'later'
      } than your preferred time.`;
    } catch {
      return null;
    }
  })();
  const choiceStatus =
    previewChoice === 'recommended'
      ? 'Recommendation selected for this preview only. No device action has been taken.'
      : previewChoice === 'original'
        ? 'Original preference retained for this preview only. No device action has been taken.'
        : null;
  const energyDelta = result?.objective_breakdown?.energy_cost_delta_aud;

  return (
    <SafeAreaView style={styles.safeArea} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={styles.backButton}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="arrow-back" size={22} color={Colors.text} />
          </TouchableOpacity>
          <View style={styles.headerText}>
            <Text style={styles.title}>Plan a task</Text>
            <Text style={styles.subtitle}>Review a schedule recommendation. Nothing is executed.</Text>
          </View>
        </View>

        <View style={styles.demoNotice}>
          <Ionicons name="information-circle-outline" size={20} color={Colors.accent} />
          <Text style={styles.demoNoticeText}>
            Demo preset: a fixed 0.8 kW synthetic baseline and an estimated appliance load.
            This is not measured household behavior.
          </Text>
        </View>

        {contextLoading ? (
          <View style={styles.loadingCard}>
            <ActivityIndicator color={Colors.primary} />
            <Text style={styles.mutedText}>Loading meter and tariff…</Text>
          </View>
        ) : (
          <>
            <View style={styles.contextCard}>
              <Text style={styles.contextLabel}>Planning for</Text>
              <Text style={styles.contextValue}>
                {meter ? meter.name || `Meter ending ${meter.nmi.slice(-4)}` : 'No meter selected'}
              </Text>
              <Text style={styles.contextDetail}>
                {meter ? `${meter.state} · ${timeZone}` : 'Upload or select a meter to continue'}
              </Text>
              {tariff && (
                <Text style={styles.contextDetail}>
                  {tariff.retailer_name || 'Configured tariff'} · {tariff.is_preset ? 'Illustrative' : 'User configured'}
                </Text>
              )}
              {contextError && <Text style={styles.warningText}>{contextError}</Text>}
              {(!tariff || tariff.is_preset) && (
                <TouchableOpacity
                  style={styles.linkButton}
                  onPress={() => router.push('/tariff-setup')}
                  accessibilityRole="button"
                >
                  <Text style={styles.linkButtonText}>
                    {tariff ? 'Set up a non-illustrative tariff' : 'Set up tariff'}
                  </Text>
                  <Ionicons name="arrow-forward" size={16} color={Colors.primaryDark} />
                </TouchableOpacity>
              )}
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Appliance task</Text>
              <Text style={styles.fieldLabel}>Appliance</Text>
              <TextInput
                accessibilityLabel="Appliance name"
                value={form.appliance}
                onChangeText={(value) => updateForm('appliance', value)}
                placeholder="e.g. Water heater"
                style={styles.input}
              />

              <View style={styles.twoColumns}>
                <View style={styles.column}>
                  <Text style={styles.fieldLabel}>Estimated power (kW)</Text>
                  <TextInput
                    accessibilityLabel="Estimated appliance power in kilowatts"
                    value={form.powerKw}
                    onChangeText={(value) => updateForm('powerKw', value)}
                    keyboardType="decimal-pad"
                    placeholder="2.4"
                    style={styles.input}
                  />
                </View>
                <View style={styles.column}>
                  <Text style={styles.fieldLabel}>Duration</Text>
                  <View style={styles.durationRow}>
                    {[30, 60, 90, 120].map((minutes) => (
                      <TouchableOpacity
                        key={minutes}
                        onPress={() => updateForm('durationMinutes', minutes)}
                        style={[
                          styles.durationButton,
                          form.durationMinutes === minutes && styles.durationButtonActive,
                        ]}
                        accessibilityRole="button"
                        accessibilityState={{ selected: form.durationMinutes === minutes }}
                      >
                        <Text
                          style={[
                            styles.durationText,
                            form.durationMinutes === minutes && styles.durationTextActive,
                          ]}
                        >
                          {minutes < 60 ? `${minutes}m` : `${minutes / 60}h`}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              </View>

              <Text style={styles.fieldLabel}>Earliest start · local meter time</Text>
              <TextInput
                accessibilityLabel="Earliest start date and time"
                value={form.earliestStart}
                onChangeText={(value) => updateForm('earliestStart', value)}
                placeholder="YYYY-MM-DD HH:mm"
                autoCapitalize="none"
                style={styles.input}
              />
              <Text style={styles.fieldLabel}>Latest finish · local meter time</Text>
              <TextInput
                accessibilityLabel="Latest finish date and time"
                value={form.deadline}
                onChangeText={(value) => updateForm('deadline', value)}
                placeholder="YYYY-MM-DD HH:mm"
                autoCapitalize="none"
                style={styles.input}
              />
              <Text style={styles.fieldLabel}>Preferred start · optional</Text>
              <TextInput
                accessibilityLabel="Preferred start date and time"
                value={form.preferredStart}
                onChangeText={(value) => updateForm('preferredStart', value)}
                placeholder="YYYY-MM-DD HH:mm"
                autoCapitalize="none"
                style={styles.input}
              />
              <Text style={styles.fieldHint}>
                All times must align to 30-minute intervals. Enter dates as YYYY-MM-DD HH:mm.
              </Text>

              <View style={styles.toggleRow}>
                <View style={styles.toggleCopy}>
                  <Text style={styles.fieldLabel}>Required task</Text>
                  <Text style={styles.fieldHint}>
                    Turn off to allow the solver to omit it.
                  </Text>
                </View>
                <Switch
                  value={form.mandatory}
                  onValueChange={(value) => updateForm('mandatory', value)}
                  trackColor={{ false: Colors.gray300, true: Colors.primaryLight }}
                  thumbColor={form.mandatory ? Colors.primaryDark : Colors.gray100}
                  accessibilityLabel="Task is required"
                />
              </View>
              {!form.mandatory && (
                <>
                  <Text style={styles.fieldLabel}>Omission penalty (AUD)</Text>
                  <TextInput
                    accessibilityLabel="Omission penalty in Australian dollars"
                    value={form.omissionPenaltyAud}
                    onChangeText={(value) => updateForm('omissionPenaltyAud', value)}
                    keyboardType="decimal-pad"
                    placeholder="Leave blank or enter AUD"
                    style={styles.input}
                  />
                  <Text style={styles.fieldHint}>
                    The solver compares this penalty with the task's energy cost. Leave blank
                    to use the no-savings treatment, which omits the optional task.
                  </Text>
                </>
              )}
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Tariff windows</Text>
              {!tariff ? (
                <Text style={styles.warningText}>
                  No configured tariff is available. The preview will be blocked until a
                  non-illustrative tariff with complete interval rates is configured.
                </Text>
              ) : (
                <>
                  <Text style={styles.tariffName}>
                    {tariff.retailer_name || `${tariff.tariff_type.toUpperCase()} tariff`}
                  </Text>
                  {displayedTariffWindows.map((line) => (
                    <Text key={line} style={styles.tariffWindow}>
                      {line}
                    </Text>
                  ))}
                  <Text style={styles.fieldHint}>
                    Daily supply and demand charges are not included in this schedule objective.
                  </Text>
                </>
              )}
            </View>

            {validationError && (
              <View style={styles.errorBanner}>
                <Ionicons name="alert-circle-outline" size={18} color={Colors.error} />
                <Text style={styles.errorText}>{validationError}</Text>
              </View>
            )}
            {resultError && (
              <View style={styles.errorBanner}>
                <Ionicons name="alert-circle-outline" size={18} color={Colors.error} />
                <Text style={styles.errorText}>{resultError}</Text>
              </View>
            )}

            <TouchableOpacity
              style={[styles.primaryButton, submitting && styles.disabledButton]}
              onPress={() => void previewSchedule()}
              disabled={submitting || !meter}
              accessibilityRole="button"
              accessibilityLabel="Preview recommended schedule"
            >
              {submitting ? (
                <ActivityIndicator color={Colors.white} />
              ) : (
                <Ionicons name="sparkles-outline" size={18} color={Colors.white} />
              )}
              <Text style={styles.primaryButtonText}>
                {submitting ? 'Evaluating schedule…' : 'Preview recommendation'}
              </Text>
            </TouchableOpacity>

            {result && (
              <View style={styles.results}>
                <View style={styles.resultsHeading}>
                  <Text style={styles.sectionTitle}>Schedule preview</Text>
                  <View
                    style={[
                      styles.statusPill,
                      result.status === 'feasible'
                        ? styles.statusPillSuccess
                        : styles.statusPillWarning,
                    ]}
                  >
                    <Text style={styles.statusText}>{result.status.replace('_', ' ')}</Text>
                  </View>
                </View>
                {result.tariff.status !== 'configured' && (
                  <Text style={styles.warningText}>
                    Tariff status: {result.tariff.status.replace(/_/g, ' ')}.
                  </Text>
                )}

                <View style={styles.scheduleCard}>
                  <Text style={styles.scheduleLabel}>Your original preference</Text>
                  <Text style={styles.scheduleTime}>{originalStartLabel}</Text>
                  <Text style={styles.scheduleDetail}>
                    {form.appliance} · {form.durationMinutes} min · estimated {form.powerKw} kW
                  </Text>
                  <Text style={styles.scheduleDetail}>Finishes {originalEnd}</Text>
                </View>

                {result.status === 'feasible' && candidateTask ? (
                  <View style={styles.recommendedCard}>
                    <View style={styles.recommendedTitleRow}>
                      <Ionicons name="checkmark-circle" size={21} color={Colors.primaryDark} />
                      <Text style={styles.scheduleLabel}>MILP recommendation</Text>
                    </View>
                    {candidateTask.omitted ? (
                      <Text style={styles.scheduleTime}>Task omitted</Text>
                    ) : (
                      <>
                        <Text style={styles.scheduleTime}>
                          {readableTime(candidateTask.start, timeZone)}
                        </Text>
                        <Text style={styles.scheduleDetail}>
                          Finishes {readableTime(candidateTask.end, timeZone)}
                        </Text>
                      </>
                    )}
                    <Text style={styles.scheduleDetail}>
                      {candidateTask.omitted
                        ? form.omissionPenaltyAud.trim()
                          ? 'The optimizer omitted this optional task; its modeled energy cost and omission penalty are reflected in the comparison.'
                          : 'No omission penalty was supplied, so the no-savings treatment leaves this optional task out.'
                        : `${candidateTask.power_kw ?? form.powerKw} kW estimated task load · preview only`}
                    </Text>
                    {preferenceShift && (
                      <Text style={styles.scheduleDetail}>
                        Comfort trade-off: {preferenceShift}
                      </Text>
                    )}
                  </View>
                ) : (
                  <View style={styles.outcomeCard}>
                    <Text style={styles.scheduleLabel}>
                      {result.status === 'blocked'
                        ? 'Missing data'
                        : result.status === 'infeasible'
                          ? 'No feasible schedule'
                          : result.status === 'timeout'
                            ? 'Solver timed out'
                            : 'Schedule not evaluated'}
                    </Text>
                    {result.blockers.map((blocker) => (
                      <Text key={blocker} style={styles.scheduleDetail}>
                        {blocker}
                      </Text>
                    ))}
                  </View>
                )}

                {referenceTask && (
                  <View style={styles.scheduleCard}>
                    <Text style={styles.scheduleLabel}>Deterministic reference</Text>
                    {referenceTask.omitted ? (
                      <Text style={styles.scheduleTime}>Optional task omitted</Text>
                    ) : (
                      <Text style={styles.scheduleTime}>
                        {readableTime(referenceTask.start, timeZone)}
                      </Text>
                    )}
                    <Text style={styles.scheduleDetail}>
                      A rule-based comparator on the same inputs; it is not an optimum.
                    </Text>
                  </View>
                )}

                {result.objective_breakdown && (
                  <View style={styles.objectiveCard}>
                    <Text style={styles.scheduleLabel}>Estimated energy-cost comparison</Text>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>Baseline, counted once</Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.baseline_energy_cost_aud)}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>Proposed total energy cost</Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.candidate_energy_cost_aud)}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>Reference energy cost</Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.reference_energy_cost_aud)}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>Candidate − reference</Text>
                      <Text style={styles.metricValue}>
                        {energyDelta == null
                          ? 'Unavailable'
                          : `${energyDelta < 0 ? '−' : '+'}$${Math.abs(energyDelta).toFixed(2)}`}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>Preference penalty</Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.preference_penalty_aud)}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>
                        Proposed weighted objective
                      </Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.total_objective_aud)}
                      </Text>
                    </View>
                    <View style={styles.metricRow}>
                      <Text style={styles.metricLabel}>
                        Reference weighted objective
                      </Text>
                      <Text style={styles.metricValue}>
                        {formatAud(result.objective_breakdown.reference_objective_aud)}
                      </Text>
                    </View>
                    <Text style={styles.fieldHint}>
                      This is a modeled energy-cost comparison against the rule-based
                      reference—not a bill or a household savings estimate. The weighted
                      objective also includes the configured preference and omission penalties.
                    </Text>
                  </View>
                )}

                {result.assumptions.map((assumption) => (
                  <View key={assumption} style={styles.assumptionRow}>
                    <Ionicons name="information-circle-outline" size={16} color={Colors.textSecondary} />
                    <Text style={styles.assumptionText}>{assumption}</Text>
                  </View>
                ))}

                {result.status === 'feasible' && candidateTask && (
                  <View style={styles.choiceRow}>
                    <TouchableOpacity
                      style={styles.primaryChoice}
                      onPress={() => setPreviewChoice('recommended')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.primaryChoiceText}>
                        {candidateTask.omitted ? 'Keep task omitted' : 'Keep recommendation'}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.secondaryChoice}
                      onPress={() => setPreviewChoice('original')}
                      accessibilityRole="button"
                    >
                      <Text style={styles.secondaryChoiceText}>Keep original</Text>
                    </TouchableOpacity>
                  </View>
                )}
                {choiceStatus && <Text style={styles.choiceStatus}>{choiceStatus}</Text>}
                <TouchableOpacity
                  style={styles.editButton}
                  onPress={() => {
                    setResult(null);
                    setPreviewChoice(null);
                  }}
                  accessibilityRole="button"
                >
                  <Ionicons name="create-outline" size={17} color={Colors.primaryDark} />
                  <Text style={styles.linkButtonText}>Edit task and preview again</Text>
                </TouchableOpacity>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    width: '100%',
    maxWidth: 760,
    alignSelf: 'center',
    padding: Spacing.md,
    paddingBottom: Spacing.xxl,
    gap: Spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  backButton: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.white,
    ...Shadow.sm,
  },
  headerText: {
    flex: 1,
  },
  title: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
  },
  subtitle: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
    marginTop: 2,
  },
  demoNotice: {
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'flex-start',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    backgroundColor: '#E8F6F4',
  },
  demoNoticeText: {
    flex: 1,
    color: Colors.gray700,
    fontSize: FontSize.sm,
    lineHeight: 20,
  },
  loadingCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    alignItems: 'center',
    gap: Spacing.sm,
  },
  mutedText: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
  },
  contextCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  contextLabel: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  contextValue: {
    color: Colors.text,
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    marginTop: 3,
  },
  contextDetail: {
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
    marginTop: Spacing.xs,
  },
  card: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  sectionTitle: {
    color: Colors.text,
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    marginBottom: Spacing.md,
  },
  fieldLabel: {
    color: Colors.gray700,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.medium,
    marginBottom: Spacing.xs,
  },
  fieldHint: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    lineHeight: 18,
    marginTop: Spacing.xs,
  },
  input: {
    minHeight: 46,
    borderWidth: 1,
    borderColor: Colors.borderStrong,
    borderRadius: BorderRadius.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    color: Colors.text,
    fontSize: FontSize.md,
    backgroundColor: Colors.white,
    marginBottom: Spacing.md,
  },
  twoColumns: {
    flexDirection: 'row',
    gap: Spacing.md,
  },
  column: {
    flex: 1,
    minWidth: 0,
  },
  durationRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
    marginBottom: Spacing.md,
  },
  durationButton: {
    minWidth: 42,
    alignItems: 'center',
    paddingVertical: 9,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: Colors.borderStrong,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surfaceAlt,
  },
  durationButtonActive: {
    backgroundColor: Colors.primarySoft,
    borderColor: Colors.primary,
  },
  durationText: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    fontWeight: FontWeight.medium,
  },
  durationTextActive: {
    color: Colors.primaryDark,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.md,
    marginTop: Spacing.xs,
  },
  toggleCopy: {
    flex: 1,
  },
  warningText: {
    color: '#92400E',
    fontSize: FontSize.sm,
    lineHeight: 20,
    marginTop: Spacing.sm,
  },
  linkButton: {
    flexDirection: 'row',
    gap: Spacing.xs,
    alignItems: 'center',
    alignSelf: 'flex-start',
    marginTop: Spacing.sm,
  },
  linkButtonText: {
    color: Colors.primaryDark,
    fontWeight: FontWeight.semibold,
    fontSize: FontSize.sm,
  },
  tariffName: {
    color: Colors.text,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    marginBottom: Spacing.sm,
  },
  tariffWindow: {
    color: Colors.gray700,
    fontSize: FontSize.sm,
    lineHeight: 21,
    paddingVertical: Spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.border,
  },
  errorBanner: {
    flexDirection: 'row',
    gap: Spacing.sm,
    alignItems: 'flex-start',
    backgroundColor: '#FEF2F2',
    borderColor: '#FECACA',
    borderWidth: 1,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
  },
  errorText: {
    color: '#991B1B',
    flex: 1,
    fontSize: FontSize.sm,
    lineHeight: 20,
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    minHeight: 52,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.primaryDark,
    ...Shadow.sm,
  },
  disabledButton: {
    opacity: 0.65,
  },
  primaryButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  results: {
    gap: Spacing.md,
  },
  resultsHeading: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  statusPill: {
    borderRadius: BorderRadius.full,
    paddingVertical: 5,
    paddingHorizontal: Spacing.sm,
  },
  statusPillSuccess: {
    backgroundColor: Colors.primarySoft,
  },
  statusPillWarning: {
    backgroundColor: '#FEF3C7',
  },
  statusText: {
    color: Colors.gray700,
    fontSize: FontSize.xs,
    fontWeight: FontWeight.semibold,
    textTransform: 'capitalize',
  },
  scheduleCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  recommendedCard: {
    backgroundColor: Colors.primarySoft,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    borderWidth: 1,
    borderColor: '#A7F3D0',
  },
  recommendedTitleRow: {
    flexDirection: 'row',
    gap: Spacing.xs,
    alignItems: 'center',
    marginBottom: Spacing.xs,
  },
  scheduleLabel: {
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    fontWeight: FontWeight.semibold,
    marginBottom: Spacing.xs,
  },
  scheduleTime: {
    color: Colors.text,
    fontSize: FontSize.lg,
    fontWeight: FontWeight.bold,
  },
  scheduleDetail: {
    color: Colors.gray700,
    fontSize: FontSize.sm,
    lineHeight: 20,
    marginTop: Spacing.xs,
  },
  outcomeCard: {
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FDE68A',
    gap: Spacing.xs,
  },
  objectiveCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    gap: Spacing.sm,
  },
  metricRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: Spacing.md,
  },
  metricLabel: {
    flex: 1,
    color: Colors.textSecondary,
    fontSize: FontSize.sm,
  },
  metricValue: {
    color: Colors.text,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
  },
  assumptionRow: {
    flexDirection: 'row',
    gap: Spacing.xs,
    alignItems: 'flex-start',
  },
  assumptionText: {
    flex: 1,
    color: Colors.textSecondary,
    fontSize: FontSize.xs,
    lineHeight: 18,
  },
  choiceRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  primaryChoice: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primaryDark,
  },
  primaryChoiceText: {
    color: Colors.white,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    textAlign: 'center',
  },
  secondaryChoice: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 46,
    paddingHorizontal: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.borderStrong,
  },
  secondaryChoiceText: {
    color: Colors.gray700,
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    textAlign: 'center',
  },
  choiceStatus: {
    color: Colors.primaryDark,
    fontSize: FontSize.sm,
    lineHeight: 20,
  },
  editButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.sm,
  },
});
