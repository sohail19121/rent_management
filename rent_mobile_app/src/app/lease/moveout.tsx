import React, { useEffect, useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Button, Card, confirmAction, DateField, Divider, Field, Loading, Muted, NumberField, Row, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { money, num, today } from '../../lib/format';
import { useDebounced } from '../../lib/useApi';

/** Move-out wizard: final meter reading, damage charges, and the deposit refund computed by Odoo. */
export default function Moveout() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [form, setForm] = useState<any>({ moveout_date: today(), damage_charges: '', final_meter_reading: '', deduction_note: '' });
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState('');
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));
  const debounced = useDebounced(form, 400);

  useEffect(() => {
    api
      .post(`/leases/${id}/moveout/preview`, debounced)
      .then((p) => {
        setPreview(p);
        setError('');
      })
      .catch((e) => setError(e.message));
  }, [id, debounced]);

  if (!preview && !error) return <Loading />;
  const cur = preview?.currency;

  const confirm = () =>
    confirmAction(
      'Terminate lease',
      `The lease ends on ${form.moveout_date}. Final invoices are posted and ${money(preview?.refund_amount, cur)} of deposit is to refund. This cannot be undone.`,
      async () => {
        await api.post(`/leases/${id}/moveout`, form);
        router.back();
      },
      'Terminate',
    );

  return (
    <Screen footer={<Button title="Confirm move-out" icon="exit-outline" tone="warning" onPress={confirm} style={{ flex: 1 }} disabled={!!error} />}>
      <Stack.Screen options={{ title: 'Move-out' }} />
      <Card>
        <DateField label="Move-out date" value={form.moveout_date} onChange={(v) => set('moveout_date', v)} required />
        <NumberField label="Damage charges" value={form.damage_charges} onChange={(v) => set('damage_charges', v)} />
        {preview?.electricity_billing === 'metered' ? (
          <NumberField
            label="Final meter reading"
            value={form.final_meter_reading}
            onChange={(v) => set('final_meter_reading', v)}
            help={`Last reading: ${num(preview.previous_meter_reading)}`}
          />
        ) : null}
        <Field label="Deduction note" value={form.deduction_note} onChangeText={(v) => set('deduction_note', v)} multiline placeholder="Broken window, repainting…" />
      </Card>
      {error ? <Muted style={{ color: '#B42525' }}>{error}</Muted> : null}
      {preview ? (
        <>
          <SectionTitle title="Settlement" />
          <Card>
            <Row label="Security deposit" value={money(preview.deposit_amount, cur)} />
            <Row label="− Unpaid dues" value={money(preview.unpaid_dues, cur)} />
            <Row label="− Electricity" value={money(preview.electricity_charges, cur)} />
            <Row label="− Damage charges" value={money(preview.damage_charges, cur)} />
            <Divider />
            <Row label="Refund to tenant" value={money(preview.refund_amount, cur)} strong tone="success" />
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
