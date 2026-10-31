/**
 * Theme constants for GridSense
 *
 * A single source of truth for colour, spacing, type and elevation. Screens
 * reference these tokens rather than hard-coding values, so tuning the design
 * language here cascades across the whole app.
 */

export const Colors = {
  // Primary - Emerald (energy / eco identity)
  primary: '#10B981',
  primaryDark: '#059669',
  primaryDarker: '#047857',
  primaryLight: '#34D399',
  primarySoft: '#ECFDF5', // tinted surface for primary-flavoured backgrounds

  // Accent - Teal (pairs with primary for gradients & highlights)
  accent: '#0D9488',
  accentLight: '#2DD4BF',

  // Secondary - Blue
  secondary: '#3B82F6',
  secondaryDark: '#2563EB',
  secondaryLight: '#60A5FA',

  // Status colors
  success: '#10B981',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#3B82F6',

  // Neutrals
  white: '#FFFFFF',
  black: '#000000',
  gray50: '#F9FAFB',
  gray100: '#F3F4F6',
  gray200: '#E5E7EB',
  gray300: '#D1D5DB',
  gray400: '#9CA3AF',
  gray500: '#6B7280',
  gray600: '#4B5563',
  gray700: '#374151',
  gray800: '#1F2937',
  gray900: '#111827',

  // Background / surfaces
  background: '#F4F6FB', // cool, slightly tinted canvas so white cards lift off it
  card: '#FFFFFF',
  surfaceAlt: '#F8FAFC',
  border: '#E9EDF3',
  borderStrong: '#DCE2EA',

  // Text
  text: '#0F172A',
  textSecondary: '#64748B',
  textLight: '#94A3B8',

  // On-gradient / dark-surface text
  onPrimary: '#FFFFFF',

  // Chart colors
  chartPeak: '#EF4444',
  chartOffPeak: '#10B981',
  chartShoulder: '#F59E0B',
};

/**
 * Multi-stop gradients (consumed by expo-linear-gradient). Use `start`/`end`
 * of {x:0,y:0} → {x:1,y:1} for the diagonal look these were tuned against.
 */
export const Gradients = {
  primary: ['#10B981', '#059669'] as const, // primary buttons / CTAs
  hero: ['#047857', '#0D9488'] as const, // emerald → teal headers
  emeraldTeal: ['#10B981', '#0D9488'] as const, // feature stat cards
  ocean: ['#0EA5E9', '#2563EB'] as const, // informational accents
  sunrise: ['#FBBF24', '#F59E0B'] as const, // peak / warning accents
  slate: ['#1E293B', '#0F172A'] as const, // dark panels
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const BorderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  xxl: 28,
  full: 9999,
};

export const FontSize = {
  xs: 12,
  sm: 14,
  md: 16,
  lg: 18,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  display: 40,
};

export const FontWeight = {
  normal: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
  extrabold: '800' as const,
};

/**
 * Elevation presets. On native these map to iOS shadow* + Android elevation;
 * react-native-web translates the shadow* props to box-shadow. Kept soft and
 * diffuse for a modern, layered feel.
 */
export const Shadow = {
  sm: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  md: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 16,
    elevation: 5,
  },
  lg: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.12,
    shadowRadius: 24,
    elevation: 9,
  },
  xl: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 18 },
    shadowOpacity: 0.16,
    shadowRadius: 32,
    elevation: 14,
  },
  /** Coloured glow used under primary/gradient hero cards. */
  primaryGlow: {
    shadowColor: '#059669',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.35,
    shadowRadius: 22,
    elevation: 10,
  },
};
