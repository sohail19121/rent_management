import React from 'react';
import { Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Chatter } from '../../components/Chatter';
import {
  AuthImage, Badge, Body, Button, Card, confirmAction, ErrorView, IconButton, Kpi, ListItem, Loading, Muted, Progress, Row, Screen,
  SectionTitle,
} from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { money, num, STATE_TONES } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function PropertyDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: p, error, loading, refreshing, refresh } = useApi<any>(`/properties/${id}`);
  if (loading && !p) return <Loading />;
  if (error && !p) return <ErrorView error={error} onRetry={refresh} />;
  const address = [p.street, p.street2, p.city, p.state?.name, p.zip, p.country?.name].filter(Boolean).join(', ');
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen
        options={{
          title: p.name,
          headerRight: () => <IconButton icon="create-outline" label="Edit" onPress={() => router.push(`/property/form?id=${p.id}`)} />,
        }}
      />
      {p.image_url ? <AuthImage path={p.image_url} style={{ width: '100%', height: 190, borderRadius: 16 }} /> : null}
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 20, fontWeight: '800', flex: 1 }}>{p.name}</Text>
          <Badge label={p.property_type_label} tone="brand" />
        </View>
        <Muted>{p.code}{address ? ` · ${address}` : ''}</Muted>
        <Row label="Manager" value={p.manager?.name} />
        <Row label="Owner" value={p.owner?.name} />
        {p.amenities.length ? <Row label="Amenities" value={p.amenities.map((a: any) => a.name).join(', ')} /> : null}
      </Card>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Kpi label="Units" value={String(p.unit_count)} icon="home-outline" />
        <Kpi label="Occupied" value={`${num(p.occupancy_rate, 0)}%`} hint={`${p.occupied_count} occupied, ${p.vacant_count} vacant`} icon="pie-chart-outline" tone="success" />
      </View>
      <Progress value={p.occupancy_rate} tone="success" />
      {p.notes ? (
        <Card>
          <Body>{p.notes}</Body>
        </Card>
      ) : null}

      <SectionTitle title={`Units (${p.units.length})`} action="Add unit" onAction={() => router.push(`/unit/form?property_id=${p.id}&property_name=${encodeURIComponent(p.name)}`)} />
      {p.units.map((u: any) => (
        <ListItem
          key={u.id}
          image={u.image_url}
          icon="home-outline"
          title={u.name}
          subtitle={`${u.unit_type_label}${u.floor ? ` · Floor ${u.floor}` : ''}${u.current_tenant ? ` · ${u.current_tenant.name}` : ''}`}
          right={money(u.base_rent, u.currency, true)}
          badge={{ label: u.state_label, tone: STATE_TONES[u.state] }}
          onPress={() => router.push(`/unit/${u.id}`)}
        />
      ))}
      <Button title="Leases of this property" variant="secondary" icon="document-text-outline" onPress={() => router.push(`/leases?property_id=${p.id}` as any)} />
      {user?.role === 'admin' ? (
        <Button
          title="Archive property"
          variant="danger"
          icon="archive-outline"
          onPress={() => confirmAction('Archive property', `Archive ${p.name}? It disappears from lists but its history is kept.`, async () => {
            await api.del(`/properties/${p.id}`);
            router.back();
          }, 'Archive')}
        />
      ) : null}
      <Chatter model="rent.property" id={p.id} />
    </Screen>
  );
}
