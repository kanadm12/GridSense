import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { uploadApi } from '@/services/api';
import { useMetersStore } from '@/stores';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

type UploadState = 'idle' | 'selected' | 'uploading' | 'success' | 'error';

export default function UploadScreen() {
  const [state, setState] = useState<UploadState>('idle');
  const [selectedFile, setSelectedFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [result, setResult] = useState<{
    metersCreated: number;
    readingsImported: number;
    warnings: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { fetchMeters } = useMetersStore();

  const pickFile = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['text/csv', 'text/plain', 'application/octet-stream'],
        copyToCacheDirectory: true,
      });

      if (!result.canceled && result.assets[0]) {
        setSelectedFile(result.assets[0]);
        setState('selected');
        setError(null);
      }
    } catch (err) {
      Alert.alert('Error', 'Failed to pick file');
    }
  };

  const uploadFile = async () => {
    if (!selectedFile) return;

    setState('uploading');
    setError(null);

    try {
      const response = await uploadApi.uploadNem12(
        selectedFile.uri,
        selectedFile.name || 'meter_data.csv'
      );

      setResult({
        metersCreated: response.meters_created,
        readingsImported: response.readings_imported,
        warnings: response.warnings,
      });
      setState('success');

      // Refresh meters list
      await fetchMeters();
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail || 'Failed to upload file. Please try again.';
      setError(errorMessage);
      setState('error');
    }
  };

  const reset = () => {
    setState('idle');
    setSelectedFile(null);
    setResult(null);
    setError(null);
  };

  const done = () => {
    router.back();
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.closeButton}>
          <Ionicons name="close" size={28} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>Upload NEM12 Data</Text>
        <View style={styles.placeholder} />
      </View>

      <View style={styles.content}>
        {/* Idle State - File picker */}
        {state === 'idle' && (
          <>
            <TouchableOpacity style={styles.uploadArea} onPress={pickFile}>
              <View style={styles.uploadIcon}>
                <Ionicons name="cloud-upload-outline" size={48} color={Colors.primary} />
              </View>
              <Text style={styles.uploadTitle}>Select NEM12 File</Text>
              <Text style={styles.uploadSubtitle}>
                Tap to browse for your smart meter data file
              </Text>
            </TouchableOpacity>

            <View style={styles.infoCard}>
              <Ionicons name="information-circle" size={24} color={Colors.info} />
              <View style={styles.infoContent}>
                <Text style={styles.infoTitle}>Where to get your NEM12 file?</Text>
                <Text style={styles.infoText}>
                  • Log into your energy retailer's website{'\n'}
                  • Look for "Usage data" or "Smart meter data"{'\n'}
                  • Download as NEM12 or CSV format
                </Text>
              </View>
            </View>
          </>
        )}

        {/* Selected State - Ready to upload */}
        {state === 'selected' && selectedFile && (
          <>
            <View style={styles.fileCard}>
              <View style={styles.fileIcon}>
                <Ionicons name="document" size={32} color={Colors.primary} />
              </View>
              <View style={styles.fileInfo}>
                <Text style={styles.fileName} numberOfLines={1}>
                  {selectedFile.name}
                </Text>
                <Text style={styles.fileSize}>
                  {selectedFile.size
                    ? `${(selectedFile.size / 1024).toFixed(1)} KB`
                    : 'Unknown size'}
                </Text>
              </View>
              <TouchableOpacity onPress={reset}>
                <Ionicons name="close-circle" size={24} color={Colors.gray400} />
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={styles.primaryButton} onPress={uploadFile}>
              <Ionicons name="cloud-upload" size={20} color={Colors.white} />
              <Text style={styles.primaryButtonText}>Upload File</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.secondaryButton} onPress={reset}>
              <Text style={styles.secondaryButtonText}>Choose Different File</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Uploading State */}
        {state === 'uploading' && (
          <View style={styles.centerContent}>
            <ActivityIndicator size="large" color={Colors.primary} />
            <Text style={styles.statusText}>Uploading and processing...</Text>
            <Text style={styles.statusSubtext}>This may take a moment</Text>
          </View>
        )}

        {/* Success State */}
        {state === 'success' && result && (
          <>
            <View style={styles.successIcon}>
              <Ionicons name="checkmark-circle" size={64} color={Colors.success} />
            </View>
            <Text style={styles.successTitle}>Upload Complete!</Text>

            <View style={styles.resultCard}>
              <View style={styles.resultRow}>
                <Text style={styles.resultLabel}>Meters Added</Text>
                <Text style={styles.resultValue}>{result.metersCreated}</Text>
              </View>
              <View style={styles.resultRow}>
                <Text style={styles.resultLabel}>Readings Imported</Text>
                <Text style={styles.resultValue}>
                  {result.readingsImported.toLocaleString()}
                </Text>
              </View>
            </View>

            {result.warnings.length > 0 && (
              <View style={styles.warningsCard}>
                <Ionicons name="warning" size={20} color={Colors.warning} />
                <View style={styles.warningsContent}>
                  <Text style={styles.warningsTitle}>
                    {result.warnings.length} warning(s)
                  </Text>
                  {result.warnings.slice(0, 3).map((warning: string, i: number) => (
                    <Text key={i} style={styles.warningText}>
                      • {warning}
                    </Text>
                  ))}
                </View>
              </View>
            )}

            <TouchableOpacity style={styles.primaryButton} onPress={done}>
              <Text style={styles.primaryButtonText}>View Dashboard</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Error State */}
        {state === 'error' && (
          <>
            <View style={styles.errorIcon}>
              <Ionicons name="alert-circle" size={64} color={Colors.error} />
            </View>
            <Text style={styles.errorTitle}>Upload Failed</Text>
            <Text style={styles.errorText}>{error}</Text>

            <TouchableOpacity style={styles.primaryButton} onPress={reset}>
              <Text style={styles.primaryButtonText}>Try Again</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: Spacing.md,
    paddingTop: Spacing.xl,
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  closeButton: {
    padding: Spacing.xs,
  },
  title: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
  },
  placeholder: {
    width: 36,
  },
  content: {
    flex: 1,
    padding: Spacing.lg,
  },
  uploadArea: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: Colors.primary,
    padding: Spacing.xxl,
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  uploadIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.primary + '10',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  uploadTitle: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.xs,
  },
  uploadSubtitle: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  infoCard: {
    flexDirection: 'row',
    backgroundColor: Colors.info + '10',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
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
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    lineHeight: 20,
  },
  fileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    gap: Spacing.md,
    ...Shadow.md,
  },
  fileIcon: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary + '10',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fileInfo: {
    flex: 1,
  },
  fileName: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.medium,
    color: Colors.text,
  },
  fileSize: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
  },
  primaryButton: {
    flexDirection: 'row',
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  primaryButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  secondaryButton: {
    alignItems: 'center',
    padding: Spacing.md,
  },
  secondaryButtonText: {
    color: Colors.primary,
    fontSize: FontSize.md,
    fontWeight: FontWeight.medium,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  statusText: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginTop: Spacing.lg,
  },
  statusSubtext: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  successIcon: {
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  successTitle: {
    fontSize: FontSize.xl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
  resultCard: {
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    ...Shadow.sm,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
  },
  resultLabel: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
  },
  resultValue: {
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
  },
  warningsCard: {
    flexDirection: 'row',
    backgroundColor: Colors.warning + '10',
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
    gap: Spacing.sm,
  },
  warningsContent: {
    flex: 1,
  },
  warningsTitle: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.warning,
    marginBottom: Spacing.xs,
  },
  warningText: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
  },
  errorIcon: {
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  errorTitle: {
    fontSize: FontSize.xl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.sm,
  },
  errorText: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginBottom: Spacing.lg,
  },
});
