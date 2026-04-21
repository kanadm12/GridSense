/**
 * Home Automation Screen
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Alert,
  Switch,
  TextInput,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { api, getErrorMessage } from '../../services/api';

interface SmartDevice {
  id: number;
  name: string;
  device_type: string;
  brand: string | null;
  location: string | null;
  is_online: boolean;
  is_enabled: boolean;
  current_state: Record<string, any> | null;
  power_rating_watts: number | null;
}

interface Automation {
  id: number;
  device_id: number;
  name: string;
  trigger_type: string;
  is_enabled: boolean;
  last_triggered: string | null;
  estimated_savings_dollars: number | null;
}

interface AutomationSuggestion {
  device_type: string;
  suggestion_title: string;
  description: string;
  potential_savings_dollars: number;
  confidence: number;
}

interface GridSignal {
  signal_type: string;
  value: number;
  unit: string;
  recommendation: string;
}

const DEVICE_ICONS: Record<string, string> = {
  hvac: 'thermometer',
  water_heater: 'water',
  ev_charger: 'car',
  pool_pump: 'water',
  solar_inverter: 'sunny',
  battery: 'battery-charging',
  smart_plug: 'flash',
  smart_switch: 'toggle',
  other: 'hardware-chip',
};

const DEVICE_TYPE_LABELS: Record<string, string> = {
  hvac: 'HVAC/Air Con',
  water_heater: 'Water Heater',
  ev_charger: 'EV Charger',
  pool_pump: 'Pool Pump',
  solar_inverter: 'Solar Inverter',
  battery: 'Home Battery',
  smart_plug: 'Smart Plug',
  smart_switch: 'Smart Switch',
  other: 'Other Device',
};

export default function AutomationScreen() {
  const [devices, setDevices] = useState<SmartDevice[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [suggestions, setSuggestions] = useState<AutomationSuggestion[]>([]);
  const [gridSignal, setGridSignal] = useState<GridSignal | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [newDevice, setNewDevice] = useState({
    name: '',
    device_type: 'smart_plug',
    location: '',
    power_rating_watts: '',
  });

  const fetchData = useCallback(async () => {
    try {
      const [devicesRes, automationsRes, suggestionsRes, gridRes] = await Promise.all([
        api.get('/automation/devices'),
        api.get('/automation/rules'),
        api.get('/automation/suggestions'),
        api.get('/automation/grid-signal'),
      ]);
      setDevices(devicesRes.data);
      setAutomations(automationsRes.data);
      setSuggestions(suggestionsRes.data);
      setGridSignal(gridRes.data);
    } catch (error) {
      Alert.alert('Error', getErrorMessage(error));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchData();
  }, [fetchData]);

  const toggleDevice = async (device: SmartDevice, command: 'on' | 'off') => {
    try {
      await api.post(`/automation/devices/${device.id}/command`, { command });
      fetchData();
    } catch (error) {
      Alert.alert('Device Control Failed', getErrorMessage(error));
    }
  };

  const toggleAutomation = async (automation: Automation) => {
    try {
      await api.patch(`/automation/rules/${automation.id}`, {
        is_enabled: !automation.is_enabled,
      });
      fetchData();
    } catch (error) {
      Alert.alert('Automation Update Failed', getErrorMessage(error));
    }
  };

  const addDevice = async () => {
    if (!newDevice.name.trim()) {
      Alert.alert('Validation Error', 'Please enter a device name');
      return;
    }

    try {
      await api.post('/automation/devices', {
        name: newDevice.name,
        device_type: newDevice.device_type,
        location: newDevice.location || null,
        power_rating_watts: newDevice.power_rating_watts
          ? parseFloat(newDevice.power_rating_watts)
          : null,
      });
      setShowAddDevice(false);
      setNewDevice({ name: '', device_type: 'smart_plug', location: '', power_rating_watts: '' });
      Alert.alert('Success', 'Device added successfully');
      fetchData();
    } catch (error) {
      Alert.alert('Failed to Add Device', getErrorMessage(error));
    }
  };

  const deleteDevice = async (deviceId: number) => {
    Alert.alert('Delete Device', 'Are you sure you want to delete this device?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.delete(`/automation/devices/${deviceId}`);
            Alert.alert('Success', 'Device deleted');
            fetchData();
          } catch (error) {
            Alert.alert('Failed to Delete Device', getErrorMessage(error));
          }
        },
      },
    ]);
  };

  const getGridSignalColor = () => {
    if (!gridSignal) return '#6B7280';
    switch (gridSignal.recommendation) {
      case 'reduce':
        return '#EF4444';
      case 'increase':
        return '#10B981';
      default:
        return '#F59E0B';
    }
  };

  const getGridSignalText = () => {
    if (!gridSignal) return 'Loading...';
    switch (gridSignal.recommendation) {
      case 'reduce':
        return 'Peak Pricing - Reduce Usage';
      case 'increase':
        return 'Off-Peak - Good Time to Use';
      default:
        return 'Normal Pricing';
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <Text style={styles.loadingText}>Loading automation...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Home Automation</Text>
          <TouchableOpacity
            style={styles.addButton}
            onPress={() => setShowAddDevice(true)}
          >
            <Ionicons name="add" size={24} color="#2563EB" />
          </TouchableOpacity>
        </View>

        {/* Grid Signal Card */}
        <LinearGradient
          colors={[getGridSignalColor(), getGridSignalColor() + '99']}
          style={styles.gridSignalCard}
        >
          <View style={styles.gridSignalContent}>
            <Ionicons name="flash" size={32} color="#FFF" />
            <View style={styles.gridSignalText}>
              <Text style={styles.gridSignalTitle}>{getGridSignalText()}</Text>
              <Text style={styles.gridSignalValue}>
                Current Rate: ${gridSignal?.value.toFixed(2)}/kWh
              </Text>
            </View>
          </View>
        </LinearGradient>

        {/* Smart Devices Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Smart Devices</Text>
          {devices.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="hardware-chip-outline" size={48} color="#9CA3AF" />
              <Text style={styles.emptyText}>No devices added yet</Text>
              <Text style={styles.emptySubtext}>
                Add your smart devices to start automating
              </Text>
            </View>
          ) : (
            devices.map((device) => (
              <TouchableOpacity
                key={device.id}
                style={styles.deviceCard}
                onLongPress={() => deleteDevice(device.id)}
              >
                <View style={styles.deviceInfo}>
                  <View
                    style={[
                      styles.deviceIcon,
                      { backgroundColor: device.is_online ? '#DBEAFE' : '#F3F4F6' },
                    ]}
                  >
                    <Ionicons
                      name={DEVICE_ICONS[device.device_type] as any || 'hardware-chip'}
                      size={24}
                      color={device.is_online ? '#2563EB' : '#9CA3AF'}
                    />
                  </View>
                  <View style={styles.deviceDetails}>
                    <Text style={styles.deviceName}>{device.name}</Text>
                    <Text style={styles.deviceType}>
                      {DEVICE_TYPE_LABELS[device.device_type] || device.device_type}
                      {device.location ? ` • ${device.location}` : ''}
                    </Text>
                    {device.power_rating_watts && (
                      <Text style={styles.devicePower}>
                        {device.power_rating_watts}W
                      </Text>
                    )}
                  </View>
                </View>
                <View style={styles.deviceControls}>
                  <View
                    style={[
                      styles.statusDot,
                      { backgroundColor: device.is_online ? '#10B981' : '#EF4444' },
                    ]}
                  />
                  <Switch
                    value={device.current_state?.power === 'on'}
                    onValueChange={(value) =>
                      toggleDevice(device, value ? 'on' : 'off')
                    }
                    trackColor={{ false: '#D1D5DB', true: '#93C5FD' }}
                    thumbColor={
                      device.current_state?.power === 'on' ? '#2563EB' : '#F3F4F6'
                    }
                  />
                </View>
              </TouchableOpacity>
            ))
          )}
        </View>

        {/* Active Automations Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Active Automations</Text>
          {automations.length === 0 ? (
            <View style={styles.emptyState}>
              <Ionicons name="timer-outline" size={48} color="#9CA3AF" />
              <Text style={styles.emptyText}>No automations yet</Text>
              <Text style={styles.emptySubtext}>
                Set up automations to save energy automatically
              </Text>
            </View>
          ) : (
            automations.map((automation) => (
              <View key={automation.id} style={styles.automationCard}>
                <View style={styles.automationInfo}>
                  <Text style={styles.automationName}>{automation.name}</Text>
                  <Text style={styles.automationTrigger}>
                    Trigger: {automation.trigger_type}
                  </Text>
                  {automation.estimated_savings_dollars && (
                    <Text style={styles.automationSavings}>
                      Est. savings: ${automation.estimated_savings_dollars.toFixed(2)}/month
                    </Text>
                  )}
                </View>
                <Switch
                  value={automation.is_enabled}
                  onValueChange={() => toggleAutomation(automation)}
                  trackColor={{ false: '#D1D5DB', true: '#93C5FD' }}
                  thumbColor={automation.is_enabled ? '#2563EB' : '#F3F4F6'}
                />
              </View>
            ))
          )}
        </View>

        {/* Suggestions Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Suggested Automations</Text>
          {suggestions.map((suggestion, index) => (
            <View key={index} style={styles.suggestionCard}>
              <View style={styles.suggestionHeader}>
                <Ionicons
                  name={DEVICE_ICONS[suggestion.device_type] as any || 'bulb'}
                  size={24}
                  color="#2563EB"
                />
                <Text style={styles.suggestionTitle}>{suggestion.suggestion_title}</Text>
              </View>
              <Text style={styles.suggestionDescription}>{suggestion.description}</Text>
              <View style={styles.suggestionFooter}>
                <Text style={styles.suggestionSavings}>
                  Save up to ${suggestion.potential_savings_dollars.toFixed(2)}/month
                </Text>
                <TouchableOpacity style={styles.applyButton}>
                  <Text style={styles.applyButtonText}>Apply</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.bottomPadding} />
      </ScrollView>

      {/* Add Device Modal */}
      <Modal visible={showAddDevice} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add Smart Device</Text>
              <TouchableOpacity onPress={() => setShowAddDevice(false)}>
                <Ionicons name="close" size={24} color="#6B7280" />
              </TouchableOpacity>
            </View>

            <TextInput
              style={styles.input}
              placeholder="Device Name"
              value={newDevice.name}
              onChangeText={(text) => setNewDevice({ ...newDevice, name: text })}
            />

            <View style={styles.deviceTypeSelector}>
              <Text style={styles.inputLabel}>Device Type</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {Object.entries(DEVICE_TYPE_LABELS).map(([type, label]) => (
                  <TouchableOpacity
                    key={type}
                    style={[
                      styles.deviceTypeOption,
                      newDevice.device_type === type && styles.deviceTypeSelected,
                    ]}
                    onPress={() => setNewDevice({ ...newDevice, device_type: type })}
                  >
                    <Ionicons
                      name={DEVICE_ICONS[type] as any}
                      size={20}
                      color={newDevice.device_type === type ? '#FFF' : '#6B7280'}
                    />
                    <Text
                      style={[
                        styles.deviceTypeLabel,
                        newDevice.device_type === type && styles.deviceTypeLabelSelected,
                      ]}
                    >
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>

            <TextInput
              style={styles.input}
              placeholder="Location (e.g., Living Room)"
              value={newDevice.location}
              onChangeText={(text) => setNewDevice({ ...newDevice, location: text })}
            />

            <TextInput
              style={styles.input}
              placeholder="Power Rating (Watts)"
              value={newDevice.power_rating_watts}
              onChangeText={(text) =>
                setNewDevice({ ...newDevice, power_rating_watts: text })
              }
              keyboardType="numeric"
            />

            <TouchableOpacity style={styles.submitButton} onPress={addDevice}>
              <Text style={styles.submitButtonText}>Add Device</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
  scrollView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 16,
    color: '#6B7280',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 10,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#111827',
  },
  addButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#EFF6FF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  gridSignalCard: {
    marginHorizontal: 20,
    marginTop: 16,
    borderRadius: 16,
    padding: 20,
  },
  gridSignalContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  gridSignalText: {
    marginLeft: 16,
  },
  gridSignalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFF',
  },
  gridSignalValue: {
    fontSize: 14,
    color: '#FFF',
    opacity: 0.9,
    marginTop: 4,
  },
  section: {
    marginTop: 24,
    paddingHorizontal: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#111827',
    marginBottom: 12,
  },
  emptyState: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    fontWeight: '500',
    color: '#374151',
    marginTop: 12,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
    textAlign: 'center',
  },
  deviceCard: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  deviceInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  deviceIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  deviceDetails: {
    marginLeft: 12,
    flex: 1,
  },
  deviceName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#111827',
  },
  deviceType: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 2,
  },
  devicePower: {
    fontSize: 12,
    color: '#9CA3AF',
    marginTop: 2,
  },
  deviceControls: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 12,
  },
  automationCard: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  automationInfo: {
    flex: 1,
  },
  automationName: {
    fontSize: 16,
    fontWeight: '500',
    color: '#111827',
  },
  automationTrigger: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
  },
  automationSavings: {
    fontSize: 13,
    color: '#10B981',
    marginTop: 4,
  },
  suggestionCard: {
    backgroundColor: '#FFF',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderLeftWidth: 4,
    borderLeftColor: '#2563EB',
  },
  suggestionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  suggestionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#111827',
    marginLeft: 10,
    flex: 1,
  },
  suggestionDescription: {
    fontSize: 14,
    color: '#6B7280',
    lineHeight: 20,
  },
  suggestionFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
  },
  suggestionSavings: {
    fontSize: 14,
    fontWeight: '600',
    color: '#10B981',
  },
  applyButton: {
    backgroundColor: '#2563EB',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  applyButtonText: {
    color: '#FFF',
    fontWeight: '600',
    fontSize: 14,
  },
  bottomPadding: {
    height: 100,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#FFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    paddingBottom: 40,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#111827',
  },
  input: {
    backgroundColor: '#F3F4F6',
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: '#374151',
    marginBottom: 8,
  },
  deviceTypeSelector: {
    marginBottom: 16,
  },
  deviceTypeOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#F3F4F6',
    marginRight: 8,
  },
  deviceTypeSelected: {
    backgroundColor: '#2563EB',
  },
  deviceTypeLabel: {
    fontSize: 13,
    color: '#6B7280',
    marginLeft: 6,
  },
  deviceTypeLabelSelected: {
    color: '#FFF',
  },
  submitButton: {
    backgroundColor: '#2563EB',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  submitButtonText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '600',
  },
});
