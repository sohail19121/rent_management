import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  AuthImage, Badge, Button, Card, choosePhoto, confirmAction, DateField, ErrorView, Field, Loading, Muted, NumberField, Row, run,
  Screen, SectionTitle,
} from '../../components/ui';
import { api } from '../../lib/api';
import { isStaff, useAuth } from '../../lib/auth';
import { date, money, num, STATE_TONES } from '../../lib/format';
import { useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function ReadingDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: r, setData, error, loading, refreshing, refresh } = useApi<any>(`/readings/${id}`);
  const [edit, setEdit] = useState<any>(null);
  if (loading && !r) return <Loading />;
  if (error && !r) return <ErrorView error={error} onRetry={refresh} />;
  const cur = r.currency;
  const editing = edit ?? (r.state === 'draft' && staff ? { current_reading: r.current_reading || '', rate: r.rate, fixed_charge: r.fixed_charge, reading_date: r.reading_date, notes: r.notes } : null);

  const act = async (action: string) => {
    const result = await run(() => api.post(`/readings/${r.id}/action/${action}`));
    if (result) {
      setData(result.reading);
      setEdit(null);
      if (result.res_model === 'account.move' && result.res_ids?.length) router.push(`/invoice/${result.res_ids[0]}`);
    }
  };
  const save = async (andConfirm: boolean) => {
    const saved = await run(() => api.put(`/readings/${r.id}`, editing));
    if (!saved) return;
    setData(saved);
    setEdit(null);
    if (andConfirm) await act('confirm');
  };
  const set = (key: string, value: any) => setEdit({ ...editing, [key]: value });

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: r.name }} />
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 19, fontWeight: '800', flex: 1 }}>{r.unit?.name}</Text>
          <Badge label={r.state_label} tone={STATE_TONES[r.state]} />
        </View>
        <Muted>{r.tenant?.name} · {date(r.period_start)} → {date(r.period_end)}</Muted>
        <Row label="Meter no." value={r.meter_number} />
        <Row label="Previous reading" value={num(r.previous_reading)} />
        <Row label="Current reading" value={r.current_reading ? num(r.current_reading) : '—'} />
        <Row label="Consumption" value={`${num(r.consumption)} kWh`} strong />
        <Row label="Rate" value={`${money(r.rate, cur)} / kWh`} />
        {r.fixed_charge ? <Row label="Fixed charge" value={money(r.fixed_charge, cur)} /> : null}
        <Row label="Amount" value={money(r.amount, cur)} strong />
        <Row label="Read on" value={date(r.reading_date)} />
        {r.invoice ? <Row label="Invoice" value={r.invoice.name} /> : null}
      </Card>
      {r.photo_url ? <AuthImage path={r.photo_url} style={{ width: '100%', height: 220, borderRadius: 16 }} /> : null}

      {editing ? (
        <>
          <SectionTitle title="Enter reading" />
          <Card>
            <NumberField label="Current reading" value={editing.current_reading} onChange={(v) => set('current_reading', v)} required help={`Must be at least ${num(r.previous_reading)}`} />
            <NumberField label="Rate per kWh" value={editing.rate} onChange={(v) => set('rate', v)} />
            <NumberField label="Fixed charge" value={editing.fixed_charge} onChange={(v) => set('fixed_charge', v)} />
            <DateField label="Reading date" value={editing.reading_date} onChange={(v) => set('reading_date', v)} />
            <Field label="Notes" value={editing.notes} onChangeText={(v) => set('notes', v)} />
            <Button title="Meter photo" variant="secondary" icon="camera-outline" onPress={() => choosePhoto((p) => set('meter_photo', p.base64))} />
            {editing.meter_photo ? <Muted>Photo attached ✓</Muted> : null}
            <Button title="Save & confirm" icon="checkmark-circle-outline" onPress={() => save(true)} />
            <Button title="Save as draft" variant="secondary" onPress={() => save(false)} />
          </Card>
        </>
      ) : null}

      {staff ? (
        <>
          {r.actions.includes('invoice') ? <Button title="Invoice this reading" icon="receipt-outline" onPress={() => confirmAction('Invoice reading', `Post an electricity invoice of ${money(r.amount, cur)}?`, () => act('invoice'), 'Invoice')} /> : null}
          {r.actions.includes('reset_draft') ? <Button title="Back to draft" variant="secondary" icon="arrow-undo-outline" onPress={() => act('reset_draft')} /> : null}
          {r.actions.includes('cancel') ? <Button title="Cancel reading" variant="danger" icon="close-circle-outline" onPress={() => confirmAction('Cancel reading', 'Cancel this reading?', () => act('cancel'), 'Cancel reading')} /> : null}
        </>
      ) : null}
    </Screen>
  );
}
