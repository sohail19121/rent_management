import React from 'react';
import { Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Chatter } from '../../components/Chatter';
import {
  AuthImage, Badge, Button, Card, confirmAction, ErrorView, IconButton, ListItem, Loading, Muted, Row, Screen, SectionTitle, run,
} from '../../components/ui';
import { api, downloadAndShare } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { date, money, STATE_TONES } from '../../lib/format';
import { useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function UnitDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: u, setData, error, loading, refreshing, refresh } = useApi<any>(`/units/${id}`);
  if (loading && !u) return <Loading />;
  if (error && !u) return <ErrorView error={error} onRetry={refresh} />;
  const toggleMaintenance = async () => {
    const saved = await run(() => api.put(`/units/${u.id}`, { under_maintenance: !u.under_maintenance }));
    if (saved) setData(saved);
  };
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen
        options={{
          title: u.display_name,
          headerRight: () => <IconButton icon="create-outline" label="Edit" onPress={() => router.push(`/unit/form?id=${u.id}`)} />,
        }}
      />
      {u.image_url ? <AuthImage path={u.image_url} style={{ width: '100%', height: 190, borderRadius: 16 }} /> : null}
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 20, fontWeight: '800', flex: 1 }}>{u.name}</Text>
          <Badge label={u.state_label} tone={STATE_TONES[u.state]} />
        </View>
        <Muted>{u.property?.name}{u.floor ? ` · Floor ${u.floor}` : ''}</Muted>
        <Row label="Type" value={u.unit_type_label} />
        <Row label="Furnishing" value={u.furnishing_label} />
        {u.bedrooms ? <Row label="Bedrooms" value={u.bedrooms} /> : null}
        {u.area_sqft ? <Row label="Area" value={`${u.area_sqft} sq ft`} /> : null}
        <Row label="Base rent" value={money(u.base_rent, u.currency)} strong />
        <Row label="Security deposit" value={money(u.deposit_amount, u.currency)} />
        <Row label="Maintenance charge" value={money(u.maintenance_charge, u.currency)} />
        <Row label="Meter no." value={u.meter_number} />
        <Row label="Current tenant" value={u.current_tenant?.name} />
      </Card>

      {u.state === 'vacant' ? (
        <Button title="Rent out this unit" icon="document-text-outline" onPress={() => router.push(`/lease/form?unit_id=${u.id}&unit_name=${encodeURIComponent(u.display_name)}`)} />
      ) : null}
      {u.current_lease ? (
        <Button title={`Open lease ${u.current_lease.name}`} variant="secondary" icon="document-text-outline" onPress={() => router.push(`/lease/${u.current_lease.id}`)} />
      ) : null}
      {u.meter_number ? (
        <>
          <Button title="Enter meter reading" variant="secondary" icon="flash-outline" onPress={() => router.push(`/meter/${u.id}`)} />
          <Button title="Print meter QR label" variant="secondary" icon="qr-code-outline" onPress={() => run(() => downloadAndShare(`/units/${u.id}/meter-label`, `Meter QR ${u.display_name}.pdf`))} />
          <Button
            title="Regenerate QR code"
            variant="ghost"
            icon="refresh"
            onPress={() => confirmAction('Regenerate QR code', 'Printed labels of this meter will stop working.', async () => setData(await api.post(`/units/${u.id}/action/regenerate_meter_qr`)), 'Regenerate')}
          />
        </>
      ) : null}
      <Button
        title={u.under_maintenance ? 'Back on the market' : 'Take off the market (repairs)'}
        variant="secondary"
        tone={u.under_maintenance ? 'success' : 'warning'}
        icon="construct-outline"
        onPress={toggleMaintenance}
      />

      <SectionTitle title="Leases" />
      {u.leases.length ? u.leases.map((l: any) => (
        <ListItem key={l.id} icon="document-text-outline" title={l.tenant?.name ?? l.name} subtitle={`${l.name} · ${date(l.start_date)} → ${date(l.end_date)}`} badge={{ label: l.state_label, tone: STATE_TONES[l.state] }} onPress={() => router.push(`/lease/${l.id}`)} />
      )) : <Muted>No lease yet.</Muted>}

      <SectionTitle title="Maintenance" action="New" onAction={() => router.push(`/maintenance/form?unit_id=${u.id}&unit_name=${encodeURIComponent(u.display_name)}`)} />
      {u.maintenance.length ? u.maintenance.map((m: any) => (
        <ListItem key={m.id} icon="construct-outline" title={`${m.category_label} · ${m.name}`} subtitle={m.summary} badge={{ label: m.state_label, tone: STATE_TONES[m.state] }} onPress={() => router.push(`/maintenance/${m.id}`)} />
      )) : <Muted>No request.</Muted>}

      {user?.role === 'admin' ? (
        <Button title="Archive unit" variant="danger" icon="archive-outline" onPress={() => confirmAction('Archive unit', `Archive ${u.display_name}?`, async () => { await api.del(`/units/${u.id}`); router.back(); }, 'Archive')} />
      ) : null}
      <Chatter model="rent.unit" id={u.id} />
    </Screen>
  );
}
