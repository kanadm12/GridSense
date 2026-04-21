import { useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Dimensions,
  FlatList,
  Linking,
  ViewToken,
} from 'react-native';
import { router } from 'expo-router';
import { Colors, Spacing, BorderRadius, FontSize, FontWeight, Shadow } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

const { width } = Dimensions.get('window');

interface Retailer {
  name: string;
  url: string;
  icon: string;
}

const RETAILERS: Retailer[] = [
  { name: 'AGL', url: 'https://www.agl.com.au/myaccount', icon: '⚡' },
  { name: 'Origin Energy', url: 'https://www.originenergy.com.au/my-account/', icon: '🔆' },
  { name: 'Energy Australia', url: 'https://www.energyaustralia.com.au/myaccount', icon: '🔌' },
  { name: 'Simply Energy', url: 'https://www.simplyenergy.com.au/my-account', icon: '💡' },
  { name: 'Powershop', url: 'https://www.powershop.com.au/login', icon: '🛒' },
  { name: 'Red Energy', url: 'https://www.redenergy.com.au/my-account', icon: '🔴' },
  { name: 'Lumo Energy', url: 'https://www.lumoenergy.com.au/my-account', icon: '💫' },
];

interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  icon: keyof typeof Ionicons.glyphMap;
  showRetailers?: boolean;
}

const STEPS: OnboardingStep[] = [
  {
    id: '1',
    title: 'Welcome to GridSense',
    description: 'Your smart energy copilot that helps you save money and reduce your carbon footprint.',
    icon: 'flash',
  },
  {
    id: '2',
    title: 'Get Your Meter Data',
    description: 'Download your NEM12 smart meter data from your energy retailer. We\'ll show you how!',
    icon: 'download',
    showRetailers: true,
  },
  {
    id: '3',
    title: 'Upload & Analyze',
    description: 'Upload your data and we\'ll analyze your consumption patterns, peak usage times, and costs.',
    icon: 'analytics',
  },
  {
    id: '4',
    title: 'Get Personalized Tips',
    description: 'Receive actionable recommendations to shift your usage to cheaper times and reduce your bills.',
    icon: 'bulb',
  },
];

export default function OnboardingScreen() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);

  const onViewableItemsChanged = useRef(({ viewableItems }: { viewableItems: ViewToken[] }) => {
    if (viewableItems.length > 0 && viewableItems[0].index !== null) {
      setCurrentIndex(viewableItems[0].index);
    }
  }).current;

  const viewabilityConfig = useRef({ viewAreaCoveragePercentThreshold: 50 }).current;

  const goToNext = () => {
    if (currentIndex < STEPS.length - 1) {
      flatListRef.current?.scrollToIndex({ index: currentIndex + 1 });
    } else {
      router.replace('/(auth)/register');
    }
  };

  const skip = () => {
    router.replace('/(auth)/login');
  };

  const renderRetailerLink = (retailer: Retailer) => (
    <TouchableOpacity
      key={retailer.name}
      style={styles.retailerButton}
      onPress={() => Linking.openURL(retailer.url)}
    >
      <Text style={styles.retailerIcon}>{retailer.icon}</Text>
      <Text style={styles.retailerName}>{retailer.name}</Text>
      <Ionicons name="open-outline" size={16} color={Colors.primary} />
    </TouchableOpacity>
  );

  const renderStep = ({ item }: { item: OnboardingStep }) => (
    <View style={styles.slide}>
      <View style={styles.iconContainer}>
        <Ionicons name={item.icon} size={80} color={Colors.primary} />
      </View>

      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.description}>{item.description}</Text>

      {item.showRetailers && (
        <View style={styles.retailersContainer}>
          <Text style={styles.retailersTitle}>Quick links to download your data:</Text>
          <View style={styles.retailersList}>
            {RETAILERS.slice(0, 5).map(renderRetailerLink)}
          </View>
          <Text style={styles.retailersHint}>
            Look for "Usage Data", "Smart Meter Data", or "NEM12 Export"
          </Text>
        </View>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      {/* Skip button */}
      <TouchableOpacity style={styles.skipButton} onPress={skip}>
        <Text style={styles.skipText}>Skip</Text>
      </TouchableOpacity>

      {/* Slides */}
      <FlatList
        ref={flatListRef}
        data={STEPS}
        renderItem={renderStep}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={viewabilityConfig}
        bounces={false}
      />

      {/* Footer */}
      <View style={styles.footer}>
        {/* Pagination dots */}
        <View style={styles.pagination}>
          {STEPS.map((_, index) => (
            <View
              key={index}
              style={[
                styles.dot,
                index === currentIndex && styles.dotActive,
              ]}
            />
          ))}
        </View>

        {/* Next button */}
        <TouchableOpacity style={styles.nextButton} onPress={goToNext}>
          <Text style={styles.nextButtonText}>
            {currentIndex === STEPS.length - 1 ? 'Get Started' : 'Next'}
          </Text>
          <Ionicons
            name={currentIndex === STEPS.length - 1 ? 'checkmark' : 'arrow-forward'}
            size={20}
            color={Colors.white}
          />
        </TouchableOpacity>

        {/* Already have account */}
        {currentIndex === 0 && (
          <TouchableOpacity style={styles.loginLink} onPress={() => router.push('/(auth)/login')}>
            <Text style={styles.loginLinkText}>Already have an account? Sign in</Text>
          </TouchableOpacity>
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
  skipButton: {
    position: 'absolute',
    top: Spacing.xl + 10,
    right: Spacing.lg,
    zIndex: 10,
    padding: Spacing.sm,
  },
  skipText: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
  },
  slide: {
    width,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.xxl * 2,
    alignItems: 'center',
  },
  iconContainer: {
    width: 160,
    height: 160,
    borderRadius: 80,
    backgroundColor: Colors.primary + '15',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  title: {
    fontSize: FontSize.xxl,
    fontWeight: FontWeight.bold,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.md,
  },
  description: {
    fontSize: FontSize.md,
    color: Colors.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
    paddingHorizontal: Spacing.md,
  },
  retailersContainer: {
    width: '100%',
    marginTop: Spacing.xl,
    backgroundColor: Colors.white,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    ...Shadow.sm,
  },
  retailersTitle: {
    fontSize: FontSize.sm,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  retailersList: {
    gap: Spacing.sm,
  },
  retailerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.gray50,
    padding: Spacing.sm,
    borderRadius: BorderRadius.md,
    gap: Spacing.sm,
  },
  retailerIcon: {
    fontSize: 20,
  },
  retailerName: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.text,
  },
  retailersHint: {
    fontSize: FontSize.xs,
    color: Colors.textSecondary,
    fontStyle: 'italic',
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  footer: {
    padding: Spacing.lg,
    paddingBottom: Spacing.xl,
  },
  pagination: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginBottom: Spacing.lg,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.gray300,
    marginHorizontal: 4,
  },
  dotActive: {
    backgroundColor: Colors.primary,
    width: 24,
  },
  nextButton: {
    flexDirection: 'row',
    backgroundColor: Colors.primary,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.xl,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
  },
  nextButtonText: {
    color: Colors.white,
    fontSize: FontSize.md,
    fontWeight: FontWeight.semibold,
  },
  loginLink: {
    alignItems: 'center',
    marginTop: Spacing.md,
  },
  loginLinkText: {
    color: Colors.primary,
    fontSize: FontSize.md,
  },
});
