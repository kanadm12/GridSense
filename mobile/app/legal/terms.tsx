import { ScrollView, Text, StyleSheet, View, TouchableOpacity } from 'react-native';
import { router, Stack } from 'expo-router';
import { Colors, Spacing, FontSize, FontWeight } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

export default function TermsOfServiceScreen() {
  return (
    <>
      <Stack.Screen
        options={{
          title: 'Terms of Service',
          headerLeft: () => (
            <TouchableOpacity onPress={() => router.back()} style={{ marginLeft: Spacing.sm }}>
              <Ionicons name="arrow-back" size={24} color={Colors.text} />
            </TouchableOpacity>
          ),
        }}
      />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.lastUpdated}>Last updated: January 2025</Text>

        <Section title="1. Acceptance of Terms">
          <Text style={styles.body}>
            By accessing or using GridSense ("the App"), you agree to be bound by these
            Terms of Service. If you do not agree, please do not use the App.
          </Text>
        </Section>

        <Section title="2. Description of Service">
          <Text style={styles.body}>
            GridSense provides energy consumption analysis and recommendations for Victorian
            households. The service analyzes your smart meter data to help you understand
            and optimize your electricity usage.
          </Text>
        </Section>

        <Section title="3. User Accounts">
          <Text style={styles.body}>
            You must register for an account to use GridSense. You are responsible for:
          </Text>
          <BulletPoint text="Providing accurate registration information" />
          <BulletPoint text="Maintaining the security of your account credentials" />
          <BulletPoint text="All activities that occur under your account" />
        </Section>

        <Section title="4. User Data & Upload">
          <Text style={styles.body}>
            You may upload your NEM12 smart meter data to the App. By uploading data, you:
          </Text>
          <BulletPoint text="Confirm you have the right to share this data" />
          <BulletPoint text="Grant us permission to process it for analysis" />
          <BulletPoint text="Understand data is stored per our Privacy Policy" />
        </Section>

        <Section title="5. Acceptable Use">
          <Text style={styles.body}>
            You agree NOT to:
          </Text>
          <BulletPoint text="Upload data that is not yours without permission" />
          <BulletPoint text="Attempt to gain unauthorized access to our systems" />
          <BulletPoint text="Use the App for any illegal purpose" />
          <BulletPoint text="Interfere with the proper functioning of the App" />
          <BulletPoint text="Reverse engineer or decompile the App" />
        </Section>

        <Section title="6. Disclaimer of Warranties">
          <Text style={styles.body}>
            GridSense is provided "as is" without warranties of any kind. We do not guarantee:
          </Text>
          <BulletPoint text="Accuracy of savings estimates or recommendations" />
          <BulletPoint text="Uninterrupted or error-free service" />
          <BulletPoint text="Compatibility with all energy retailers" />
          <Text style={styles.body}>
            {"\n"}Our recommendations are informational only and should not be considered
            financial advice.
          </Text>
        </Section>

        <Section title="7. Limitation of Liability">
          <Text style={styles.body}>
            To the maximum extent permitted by law, GridSense and its operators shall not
            be liable for any indirect, incidental, special, consequential, or punitive
            damages arising from your use of the App.
          </Text>
        </Section>

        <Section title="8. Intellectual Property">
          <Text style={styles.body}>
            The App, including its design, features, and content, is protected by copyright
            and other intellectual property laws. You may not copy, modify, or distribute
            any part of the App without our written consent.
          </Text>
        </Section>

        <Section title="9. Termination">
          <Text style={styles.body}>
            We may suspend or terminate your account if you violate these Terms. You may
            delete your account at any time through the App settings. Upon termination,
            your data will be handled per our Privacy Policy.
          </Text>
        </Section>

        <Section title="10. Changes to Terms">
          <Text style={styles.body}>
            We may modify these Terms at any time. Continued use after changes constitutes
            acceptance. Material changes will be notified via email or in-app notification.
          </Text>
        </Section>

        <Section title="11. Governing Law">
          <Text style={styles.body}>
            These Terms are governed by the laws of Victoria, Australia. Any disputes
            shall be resolved in the courts of Victoria.
          </Text>
        </Section>

        <Section title="12. Contact">
          <Text style={styles.body}>
            For questions about these Terms, contact us at:
          </Text>
          <Text style={styles.contactInfo}>legal@gridsense.au</Text>
        </Section>
      </ScrollView>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function BulletPoint({ text }: { text: string }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={styles.bullet}>•</Text>
      <Text style={styles.bulletText}>{text}</Text>
    </View>
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
  lastUpdated: {
    fontSize: FontSize.sm,
    color: Colors.textSecondary,
    fontStyle: 'italic',
    marginBottom: Spacing.lg,
  },
  section: {
    marginBottom: Spacing.xl,
  },
  sectionTitle: {
    fontSize: FontSize.lg,
    fontWeight: FontWeight.semibold,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  body: {
    fontSize: FontSize.md,
    color: Colors.text,
    lineHeight: 24,
    marginBottom: Spacing.sm,
  },
  bulletRow: {
    flexDirection: 'row',
    marginLeft: Spacing.md,
    marginBottom: Spacing.xs,
  },
  bullet: {
    fontSize: FontSize.md,
    color: Colors.primary,
    marginRight: Spacing.sm,
  },
  bulletText: {
    flex: 1,
    fontSize: FontSize.md,
    color: Colors.text,
    lineHeight: 22,
  },
  contactInfo: {
    fontSize: FontSize.md,
    color: Colors.primary,
    fontWeight: FontWeight.medium,
    marginTop: Spacing.sm,
  },
});
