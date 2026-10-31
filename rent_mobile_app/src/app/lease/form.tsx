import React, { useEffect, useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  Button, Card, DateField, Field, Loading, Muted, NumberField, RecordField, run, Screen, SectionTitle, SelectField, type Option,
} from '../../components/ui';
import { api } from '../../lib/api';
import { toIsoDate, today } from '../../lib/format';
import { selection, useMeta } from '../../lib/meta';

function plusYear(iso: string) {
  const [y, m, d] = iso.split('-').map(Number);
  const end = new Date(y + 1, m - 1, d - 1);
  return toIsoDate(end);
}

export default function LeaseForm() {
  const params = useLocalSearchParams<{ id?: string; unit_id?: string; unit_name?: string; tenant_id?: string; tenant_name?: string }>();
  const id = params.id;
  const meta = useMeta();
  const [loading, setLoading] = useState(!!id);
  const start = today();
  const [form, setForm] = useState<any>({
    unit: params.unit_id ? { id: Number(params.unit_id), name: params.unit_name } : null,
    tenant: params.tenant_id ? { id: Number(params.tenant_id), name: params.tenant_name } : null,
    start_date: start,
    end_date: plusYear(start),
    billing_frequency: 'monthly',
    billing_day: Math.min(new Date().getDate(), 28),
    notice_period_days: 30,
    grace_days: 5,
    late_fee_type: 'fixed',
    escalation_every_months: 12,
    electricity_billing: 'none',
  });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));

  useEffect(() => {
    if (!id) return;
    api.get(`/leases/${id}`).then((l) => {
      setForm(l);
      setLoading(false);
    });
  }, [id]);

  // Picking a unit fills the rent, deposit and maintenance charge from it, like the Odoo form.
  const pickUnit = (unit: Option | null) => {
    setForm((f: any) => ({
      ...f,
      unit,
      ...(unit && !id
        ? {
            rent_amount: unit.base_rent ?? f.rent_amount,
            deposit_amount: unit.deposit_amount ?? f.deposit_amount,
            maintenance_charge: unit.maintenance_charge ?? f.maintenance_charge,
            electricity_billing: unit.has_meter ? 'metered' : f.electricity_billing,
          }
        : {}),
    }));
  };

  if (loading) return <Loading />;
  const draft = !id || form.state === 'draft';

  const save = async () => {
    const body: any = {
      tenant_id: form.tenant?.id, unit_id: form.unit?.id, start_date: form.start_date, end_date: form.end_date,
      rent_amount: form.rent_amount || 0, maintenance_charge: form.maintenance_charge || 0, deposit_amount: form.deposit_amount || 0,
      billing_frequency: form.billing_frequency, billing_day: Number(form.billing_day) || 1,
      notice_period_days: Number(form.notice_period_days) || 0, late_fee_type: form.late_fee_type,
      late_fee_value: form.late_fee_value || 0, grace_days: Number(form.grace_days) || 0,
      escalation_percent: form.escalation_percent || 0, escalation_every_months: Number(form.escalation_every_months) || 0,
      electricity_billing: form.electricity_billing, notes: form.notes,
    };
    if (form.electricity_rate !== undefined && form.electricity_rate !== '') body.electricity_rate = form.electricity_rate;
    if (form.electricity_fixed_amount !== undefined) body.electricity_fixed_amount = form.electricity_fixed_amount || 0;
    if (form.electricity_opening_reading !== undefined) body.electricity_opening_reading = form.electricity_opening_reading || 0;
    if (!draft) {
      // Running leases: the parties and dates are fixed.
      delete body.tenant_id;
      delete body.unit_id;
      delete body.start_date;
    }
    const saved = await run(() => (id ? api.put(`/leases/${id}`, body) : api.post('/leases', body)));
    if (saved) {
      if (id) router.back();
      else router.replace(`/lease/${saved.id}`);
    }
  };

  return (
    <Screen footer={<Button title={id ? 'Save' : 'Create draft lease'} icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: id ? `Edit ${form.name}` : 'New lease' }} />
      <SectionTitle title="Parties" />
      <Card>
        {draft ? (
          <>
            <RecordField label="Tenant" kind="tenants" value={form.tenant} onChange={(v) => set('tenant', v)} required help="Not in the list? Create the tenant first from More › Tenants." />
            <RecordField label="Unit" kind="units" value={form.unit} onChange={pickUnit} required />
          </>
        ) : (
          <Muted>{form.tenant?.name} · {form.unit?.name}</Muted>
        )}
      </Card>
      <SectionTitle title="Term" />
      <Card>
        {draft ? (
          <DateField label="Start date" value={form.start_date} onChange={(v) => setForm((f: any) => ({ ...f, start_date: v, end_date: plusYear(v), billing_day: Math.min(Number(v.slice(8, 10)), 28) }))} required />
        ) : null}
        <DateField label="End date" value={form.end_date} onChange={(v) => set('end_date', v)} required />
        <NumberField label="Notice period (days)" value={form.notice_period_days} onChange={(v) => set('notice_period_days', v)} />
      </Card>
      <SectionTitle title="Rent & billing" />
      <Card>
        <NumberField label="Monthly rent" value={form.rent_amount} onChange={(v) => set('rent_amount', v)} required />
        <NumberField label="Maintenance charge" value={form.maintenance_charge} onChange={(v) => set('maintenance_charge', v)} />
        <NumberField label="Security deposit" value={form.deposit_amount} onChange={(v) => set('deposit_amount', v)} />
        <SelectField label="Billing frequency" value={form.billing_frequency} options={selection(meta, 'billing_frequency')} onChange={(v) => set('billing_frequency', v)} />
        <NumberField label="Billing day (1-28)" value={form.billing_day} onChange={(v) => set('billing_day', v)} help="Day of the month the rent is due." />
        <SelectField label="Late fee type" value={form.late_fee_type} options={selection(meta, 'late_fee_type')} onChange={(v) => set('late_fee_type', v)} />
        <NumberField label={form.late_fee_type === 'percent' ? 'Late fee (%)' : 'Late fee amount'} value={form.late_fee_value} onChange={(v) => set('late_fee_value', v)} />
        <NumberField label="Grace days" value={form.grace_days} onChange={(v) => set('grace_days', v)} />
        <NumberField label="Escalation (%)" value={form.escalation_percent} onChange={(v) => set('escalation_percent', v)} />
        <NumberField label="Escalate every (months)" value={form.escalation_every_months} onChange={(v) => set('escalation_every_months', v)} />
      </Card>
      <SectionTitle title="Electricity" />
      <Card>
        <SelectField label="Electricity billing" value={form.electricity_billing} options={selection(meta, 'electricity_billing')} onChange={(v) => set('electricity_billing', v)} />
        {form.electricity_billing === 'metered' ? (
          <>
            <NumberField label="Rate per kWh" value={form.electricity_rate} onChange={(v) => set('electricity_rate', v)} help="Leave empty to use the company default rate." />
            <NumberField label="Opening meter reading" value={form.electricity_opening_reading} onChange={(v) => set('electricity_opening_reading', v)} />
          </>
        ) : null}
        {form.electricity_billing !== 'none' ? (
          <NumberField label={form.electricity_billing === 'fixed' ? 'Fixed monthly amount' : 'Fixed meter charge'} value={form.electricity_fixed_amount} onChange={(v) => set('electricity_fixed_amount', v)} />
        ) : null}
      </Card>
      <Field label="Notes" value={form.notes} onChangeText={(v) => set('notes', v)} multiline />
    </Screen>
  );
}
