import React from 'react';
import { Linking, Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Chatter } from '../../components/Chatter';
import {
  AuthImage, Badge, Button, Card, confirmAction, ErrorView, IconButton, ListItem, Loading, Muted, Row, run, Screen, SectionTitle,
} from '../../components/ui';
import { api, downloadAndShare } from '../../lib/api';
import { canBill, useAuth } from '../../lib/auth';
import { date, money, STATE_TONES } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function TenantDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: p, setData, error, loading, refreshing, refresh } = useApi<any>(`/tenants/${id}`);
  if (loading && !p) return <Loading />;
  if (error && !p) return <ErrorView error={error} onRetry={refresh} />;
  const address = [p.street, p.street2, p.city, p.state?.name, p.zip, p.country?.name].filter(Boolean).join(', ');
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: p.name, headerRight: () => <IconButton icon="create-outline" onPress={() => router.push(`/tenant/form?id=${p.id}`)} /> }} />
      <Card style={{ alignItems: 'center' }}>
        {p.image_url ? <AuthImage path={p.image_url} style={{ width: 84, height: 84, borderRadius: 42 }} /> : (
          <View style={{ width: 84, height: 84, borderRadius: 42, backgroundColor: t.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: t.brand, fontSize: 32, fontWeight: '800' }}>{p.name.slice(0, 1)}</Text>
          </View>
        )}
        <Text style={{ color: t.text, fontSize: 20, fontWeight: '800' }}>{p.name}</Text>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          <Badge label={p.kyc_verified ? 'KYC verified' : 'KYC pending'} tone={p.kyc_verified ? 'success' : 'warning'} />
          <Badge label={p.has_app_access ? 'Has app access' : 'No app access'} tone={p.has_app_access ? 'info' : 'neutral'} />
        </View>
        <View style={{ flexDirection: 'row', gap: space.sm, alignSelf: 'stretch' }}>
          {p.phone ? <Button title="Call" icon="call-outline" variant="secondary" style={{ flex: 1 }} onPress={() => Linking.openURL(`tel:${p.phone}`)} /> : null}
          {p.phone ? <Button title="WhatsApp" icon="logo-whatsapp" variant="secondary" style={{ flex: 1 }} onPress={() => Linking.openURL(`https://wa.me/${p.phone.replace(/[^0-9]/g, '')}`)} /> : null}
          {p.email ? <Button title="Email" icon="mail-outline" variant="secondary" style={{ flex: 1 }} onPress={() => Linking.openURL(`mailto:${p.email}`)} /> : null}
        </View>
      </Card>
      <Card>
        <Row label="Email" value={p.email} />
        <Row label="Phone" value={p.phone} />
        <Row label="Address" value={address} />
        <Row label="Rent due" value={money(p.rent_total_due)} tone={p.rent_total_due ? 'danger' : undefined} strong />
      </Card>
      <SectionTitle title="KYC" />
      <Card>
        <Row label="ID type" value={p.kyc_id_type_label} />
        <Row label="ID number" value={p.kyc_id_number} />
        <Row label="Verified" value={p.kyc_verified ? 'Yes' : 'No'} tone={p.kyc_verified ? 'success' : 'warning'} />
        {!p.kyc_verified && p.kyc_id_number ? (
          <Button title="Mark KYC as verified" icon="shield-checkmark-outline" tone="success" onPress={async () => {
            const saved = await run(() => api.put(`/tenants/${p.id}`, { kyc_verified: true }));
            if (saved) setData(saved);
          }} />
        ) : null}
      </Card>
      <SectionTitle title="Emergency contact" />
      <Card>
        <Row label="Name" value={p.emergency_contact_name} />
        <Row label="Phone" value={p.emergency_contact_phone} />
      </Card>

      <Button
        title={p.has_app_access ? 'Resend app invitation' : 'Give access to the tenant app'}
        icon="phone-portrait-outline"
        variant={p.has_app_access ? 'secondary' : 'primary'}
        onPress={() => confirmAction(
          'Tenant app access',
          `${p.name} will receive an email at ${p.email || '(no email)'} to set a password. They can then sign in to this app and the portal to pay rent and report problems.`,
          async () => setData(await api.post(`/tenants/${p.id}/invite`)),
          'Send invitation',
        )}
      />
      <Button title="New lease for this tenant" variant="secondary" icon="document-text-outline" onPress={() => router.push(`/lease/form?tenant_id=${p.id}&tenant_name=${encodeURIComponent(p.name)}`)} />
      {canBill(user?.role) ? (
        <Button title="Tenant statement (PDF)" variant="secondary" icon="document-outline" onPress={() => run(() => downloadAndShare(`/tenants/${p.id}/statement`, `Statement ${p.name}.pdf`))} />
      ) : null}

      <SectionTitle title="Leases" />
      {p.leases.length ? p.leases.map((l: any) => (
        <ListItem key={l.id} icon="document-text-outline" title={l.unit?.name ?? l.name} subtitle={`${l.name} · ${date(l.start_date)} → ${date(l.end_date)}`} right={money(l.rent_amount, l.currency, true)} badge={{ label: l.state_label, tone: STATE_TONES[l.state] }} onPress={() => router.push(`/lease/${l.id}`)} />
      )) : <Muted>No lease yet.</Muted>}
      <Chatter model="res.partner" id={p.id} title="Notes & messages" />
    </Screen>
  );
}
