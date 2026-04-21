import { ScrollView, Text, StyleSheet, View, TouchableOpacity } from 'react-native';
import { router, Stack } from 'expo-router';
import { Colors, Spacing, FontSize, FontWeight } from '@/constants/theme';
import { Ionicons } from '@expo/vector-icons';

export default function PrivacyPolicyScreen() {
  return (
    <>
      <Stack.Screen
        options={{
          title: 'Privacy Policy',
          headerLeft: () => (
            <TouchableOpacity onPress={() => router.back()} style={{ marginLeft: Spacing.sm }}>
              <Ionicons name="arrow-back" size={24} color={Colors.text} />
            </TouchableOpacity>
          ),
        }}
      />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.lastUpdated}>Last updated: January 2025</Text>

        <Section title="1. Information We Collect">
          <Text style={styles.body}>
            GridSense collects the following information to provide our energy management services:
          </Text>
          <BulletPoint text="Account information (email, name)" />
          <BulletPoint text="Smart meter data (NEM12 files you upload)" />
          <BulletPoint text="Usage patterns and consumption data" />
          <BulletPoint text="Tariff and billing preferences" />
          <BulletPoint text="Device information for push notifications" />
        </Section>

        <Section title="2. How We Use Your Data">
          <Text style={styles.body}>
            Your data is used exclusively to:
          </Text>
          <BulletPoint text="Analyze your energy consumption patterns" />
          <BulletPoint text="Generate personalized recommendations" />
          <BulletPoint text="Calculate cost savings and comparisons" />
          <BulletPoint text="Send relevant notifications (with your consent)" />
          <BulletPoint text="Improve our services through aggregated analytics" />
        </Section>

        <Section title="3. Data Storage & Security">
          <Text style={styles.body}>
            Your data is stored securely on Australian servers. We implement industry-standard
            security measures including encryption at rest and in transit.
          </Text>
        </Section>

        <Section title="4. Data Sharing">
          <Text style={styles.body}>
            We do NOT sell your personal data. We may share data only:
          </Text>
          <BulletPoint text="With your explicit consent" />
          <BulletPoint text="To comply with legal obligations" />
          <BulletPoint text="In aggregated, anonymized form for research" />
        </Section>

        <Section title="5. Your Rights">
          <Text style={styles.body}>
            Under Australian Privacy Principles, you have the right to:
          </Text>
          <BulletPoint text="Access your personal data" />
          <BulletPoint text="Request correction of inaccurate data" />
          <BulletPoint text="Request deletion of your data" />
          <BulletPoint text="Export your data in a portable format" />
        </Section>

        <Section title="6. Data Retention">
          <Text style={styles.body}>
            We retain your data for as long as your account is active. Upon account deletion,
            all personal data is removed within 30 days. Anonymized usage statistics may be retained.
          </Text>
        </Section>

        <Section title="7. Cookies & Analytics">
          <Text style={styles.body}>
            We use minimal analytics to understand app usage and improve our service.
            No third-party advertising trackers are used.
          </Text>
        </Section>

        <Section title="8. Children's Privacy">
          <Text style={styles.body}>
            GridSense is not intended for users under 18. We do not knowingly collect
            data from children.
          </Text>
        </Section>

        <Section title="9. Changes to This Policy">
          <Text style={styles.body}>
            We may update this policy periodically. Significant changes will be communicated
            via email or in-app notification.
          </Text>
        </Section>

        <Section title="10. Contact Us">
          <Text style={styles.body}>
            For privacy inquiries or to exercise your rights, contact us at:
          </Text>
          <Text style={styles.contactInfo}>privacy@gridsense.au</Text>
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
