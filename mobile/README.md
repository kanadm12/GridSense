# GridSense Mobile

React Native (Expo) mobile app for GridSense - Grid-Aware Energy Copilot.

## Quick Start

### Prerequisites
- Node.js 18+
- Expo CLI (`npm install -g expo-cli`)
- iOS Simulator (macOS) or Android Emulator

### Installation

```bash
cd mobile
npm install
```

### Running the App

```bash
# Start Expo development server
npx expo start

# Run on iOS Simulator
npx expo start --ios

# Run on Android Emulator
npx expo start --android
```

### Configuration

Create a `.env` file:

```env
EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1
```

For physical devices, use your machine's local IP:
```env
EXPO_PUBLIC_API_URL=http://192.168.1.100:8000/api/v1
```

## Project Structure

```
mobile/
├── app/                    # Expo Router file-based navigation
│   ├── (auth)/             # Authentication screens
│   │   ├── login.tsx
│   │   └── register.tsx
│   ├── (tabs)/             # Main tab navigation
│   │   ├── index.tsx       # Dashboard
│   │   ├── usage.tsx       # Usage charts
│   │   ├── recommendations.tsx
│   │   └── settings.tsx
│   └── upload.tsx          # NEM12 upload modal
├── components/             # Reusable components
├── constants/
│   └── theme.ts            # Colors, spacing, typography
├── services/
│   └── api.ts              # API client
├── stores/
│   └── index.ts            # Zustand state stores
└── assets/                 # Images, fonts
```

## Features

- **Authentication**: JWT-based login/register
- **NEM12 Upload**: File picker for smart meter data
- **Dashboard**: Key metrics and quick actions
- **Usage Charts**: Daily and hourly consumption visualizations
- **Recommendations**: Personalized energy-saving tips
- **Multi-meter Support**: Switch between meters

## Building for Production

```bash
# Build for iOS
npx expo build:ios

# Build for Android
npx expo build:android

# Or with EAS Build (recommended)
npx eas build --platform ios
npx eas build --platform android
```

## Tech Stack

- **Expo SDK 50** - React Native framework
- **Expo Router** - File-based navigation
- **Zustand** - State management
- **react-native-gifted-charts** - Charts library
- **Axios** - HTTP client
- **expo-secure-store** - Secure token storage
