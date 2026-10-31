import React, { useEffect, useState } from 'react';
import { Stack, router } from 'expo-router';

import { Button, Card, Loading, Muted, NumberField, Row, run, Screen, SectionTitle, SwitchField } from '../components/ui';
import { api } from '../lib/api';

/** Rent Management settings of the company (administrators). */
export default function Settings() {
  const [form, setForm] = useState<any>(null);
  useEffect(() => {
    api.get('/settings').then(setForm);
  }, []);
  if (!form) return <Loading />;
  const set = (key: string, value: any) => setForm({ ...form, [key]: value });
  const save = async () => {
    const saved = await run(() => api.put('/settings', form));
    if (saved) router.back();
  };
  return (
    <Screen footer={<Button title="Save settings" icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: 'Rent settings' }} />
      <Muted>{form.company}</Muted>
      <SectionTitle title="Billing" />
      <Card>
        <NumberField label="Invoice days in advance" value={form.rent_invoice_advance_days} onChange={(v) => set('rent_invoice_advance_days', v)} help="Rent invoices are created this many days before the due date." />
        <NumberField label="Reminder days before due" value={form.rent_reminder_days_before} onChange={(v) => set('rent_reminder_days_before', v)} />
        <SwitchField label="Send overdue notices" value={!!form.rent_send_overdue_notice} onChange={(v) => set('rent_send_overdue_notice', v)} />
        <NumberField label="Lease expiry notice (days)" value={form.rent_expiry_notice_days} onChange={(v) => set('rent_expiry_notice_days', v)} />
        <NumberField label="Default electricity rate per kWh" value={form.rent_electricity_rate} onChange={(v) => set('rent_electricity_rate', v)} />
      </Card>
      <SectionTitle title="Accounting (set in Odoo)" />
      <Card>
        <Row label="Rent income account" value={form.rent_income_account?.name} />
        <Row label="Security deposit account" value={form.rent_deposit_account?.name} />
        <Row label="Rent journal" value={form.rent_journal?.name} />
      </Card>
    </Screen>
  );
}
