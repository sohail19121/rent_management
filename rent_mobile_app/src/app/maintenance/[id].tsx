import React, { useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Chatter } from '../../components/Chatter';
import {
  AuthImage, Badge, Body, Button, Card, choosePhoto, confirmAction, ErrorView, Loading, Muted, Row, run, Screen, SectionTitle,
} from '../../components/ui';
import { api } from '../../lib/api';
import { isStaff, useAuth } from '../../lib/auth';
import { datetime, money, PRIORITY_TONE, STATE_TONES } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function MaintenanceDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: m, setData, error, loading, refreshing, refresh } = useApi<any>(`/maintenance/${id}`);
  const [zoom, setZoom] = useState<string | null>(null);
  if (loading && !m) return <Loading />;
  if (error && !m) return <ErrorView error={error} onRetry={refresh} />;

  const act = async (action: string) => {
    const saved = await run(() => api.post(`/maintenance/${m.id}/action/${action}`));
    if (saved) setData(saved);
  };

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: m.name }} />
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 19, fontWeight: '800', flex: 1 }}>{m.category_label}</Text>
          <Badge label={m.state_label} tone={STATE_TONES[m.state]} />
        </View>
        <Muted>{m.unit?.name} · {datetime(m.create_date)}</Muted>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          <Badge label={`Priority: ${m.priority_label}`} tone={PRIORITY_TONE[m.priority]} />
        </View>
        {m.description ? <Body>{m.description}</Body> : null}
      </Card>

      {m.photos.length ? (
        <ScrollView horizontal contentContainerStyle={{ gap: space.sm }}>
          {m.photos.map((url: string) => (
            <Pressable key={url} onPress={() => setZoom(url)}>
              <AuthImage path={url} style={{ width: 120, height: 120, borderRadius: 12 }} />
            </Pressable>
          ))}
        </ScrollView>
      ) : null}

      <Card>
        <Row label="Tenant" value={m.tenant?.name} />
        <Row label="Lease" value={m.lease?.name} />
        <Row label="Assigned to" value={m.assigned_to?.name} />
        {staff ? <Row label="Vendor" value={m.vendor?.name} /> : null}
        {m.cost ? <Row label="Cost" value={money(m.cost, m.currency)} /> : null}
        {staff ? <Row label="Charged to" value={m.charge_to_label} /> : null}
        {m.invoice ? <Row label="Tenant invoice" value={m.invoice.name} /> : null}
      </Card>

      {staff && m.actions.length ? (
        <>
          <SectionTitle title="Actions" />
          {m.actions.includes('edit') ? <Button title="Edit / assign / cost" variant="secondary" icon="create-outline" onPress={() => router.push(`/maintenance/form?id=${m.id}`)} /> : null}
          {m.actions.includes('edit') ? (
            <Button title="Add photo" variant="secondary" icon="camera-outline" onPress={() => choosePhoto(async (photo) => {
              const saved = await run(() => api.put(`/maintenance/${m.id}`, { photos: [photo.base64] }));
              if (saved) setData(saved);
            })} />
          ) : null}
          {m.actions.includes('start') ? <Button title="Start work" icon="play-outline" onPress={() => act('start')} /> : null}
          {m.actions.includes('done') ? (
            <Button
              title="Mark as done"
              icon="checkmark-done-outline"
              tone="success"
              onPress={() => confirmAction('Close request', m.charge_to === 'tenant' && m.cost ? `The tenant will be invoiced ${money(m.cost, m.currency)}.` : 'Mark this request as done?', () => act('done'))}
            />
          ) : null}
          {m.actions.includes('cancel') ? <Button title="Cancel request" variant="danger" icon="close-circle-outline" onPress={() => confirmAction('Cancel request', 'Cancel this request?', () => act('cancel'), 'Cancel request')} /> : null}
          {m.actions.includes('reset') ? <Button title="Reopen" variant="secondary" icon="refresh" onPress={() => act('reset')} /> : null}
        </>
      ) : null}

      <Chatter model="rent.maintenance.request" id={m.id} title="Conversation" />

      <Modal visible={!!zoom} transparent onRequestClose={() => setZoom(null)}>
        <Pressable style={{ flex: 1, backgroundColor: '#000e', justifyContent: 'center' }} onPress={() => setZoom(null)}>
          {zoom ? <AuthImage path={zoom} style={{ width: '100%', height: '80%' }} /> : null}
        </Pressable>
      </Modal>
    </Screen>
  );
}
