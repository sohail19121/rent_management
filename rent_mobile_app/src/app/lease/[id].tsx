import React from 'react';
import { Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { Chatter } from '../../components/Chatter';
import {
  Badge, Body, Button, Card, confirmAction, ErrorView, ListItem, Loading, Muted, Progress, Row, run, Screen, SectionTitle,
  type IconName,
} from '../../components/ui';
import { api, downloadAndShare } from '../../lib/api';
import { isStaff, useAuth } from '../../lib/auth';
import { date, INVOICE_STATUS_LABEL, money, num, STATE_TONES } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

type ActionDef = { label: string; icon: IconName; confirm?: string; variant?: 'primary' | 'secondary' | 'danger' };

// Buttons of the lease workflow, shown when the server lists them as available.
const ACTIONS: Record<string, ActionDef> = {
  confirm: { label: 'Confirm lease', icon: 'checkmark-circle-outline', confirm: 'Confirm this lease? The unit is reserved and the tenant is emailed.' },
  activate: { label: 'Tenant moved in (activate)', icon: 'key-outline', confirm: 'Start the lease? Rent invoicing begins.' },
  deposit_invoice: { label: 'Invoice security deposit', icon: 'wallet-outline', confirm: 'Create and post the security deposit invoice?', variant: 'secondary' },
  generate_invoice: { label: 'Generate rent invoice now', icon: 'receipt-outline', confirm: 'Create the next rent invoice of this lease now?', variant: 'secondary' },
  mark_signed: { label: 'Mark agreement as signed', icon: 'create-outline', variant: 'secondary' },
  request_signature: { label: 'Request signature', icon: 'mail-outline', variant: 'secondary' },
  renew: { label: 'Renew lease', icon: 'refresh-outline', confirm: 'Create a renewal lease starting the day after this one ends?', variant: 'secondary' },
  draft: { label: 'Reset to draft', icon: 'arrow-undo-outline', variant: 'secondary' },
  cancel: { label: 'Cancel lease', icon: 'close-circle-outline', confirm: 'Cancel this lease?', variant: 'danger' },
};

export default function LeaseDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: l, setData, error, loading, refreshing, refresh } = useApi<any>(`/leases/${id}`);
  if (loading && !l) return <Loading />;
  if (error && !l) return <ErrorView error={error} onRetry={refresh} />;
  const cur = l.currency;

  const doAction = async (name: string) => {
    const def = ACTIONS[name];
    const perform = async () => {
      const result = await api.post(`/leases/${l.id}/action/${name}`);
      setData(result.lease);
      if (name === 'renew' && result.res_ids?.length) router.push(`/lease/${result.res_ids[0]}`);
      else if (result.res_model === 'account.move' && result.res_ids?.length) router.push(`/invoice/${result.res_ids[0]}`);
    };
    if (def.confirm) await confirmAction(def.label, def.confirm, perform, def.variant === 'danger' ? 'Cancel lease' : 'Confirm');
    else await run(perform);
  };

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: l.name }} />
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 20, fontWeight: '800', flex: 1 }}>{staff ? l.tenant?.name : l.unit?.name}</Text>
          <Badge label={l.state_label} tone={STATE_TONES[l.state]} />
        </View>
        <Muted>{l.unit?.name} · {l.name}{l.signed ? ' · Signed' : ''}</Muted>
        <Progress value={l.progress} tone={l.state === 'expiring' ? 'warning' : 'brand'} />
        <Muted>{date(l.start_date)} → {date(l.end_date)} · {l.duration_months} months{l.days_left ? ` · ${l.days_left} days left` : ''}</Muted>
        {staff ? (
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <Button title="Tenant" variant="secondary" icon="person-outline" style={{ flex: 1 }} onPress={() => router.push(`/tenant/${l.tenant.id}`)} />
            <Button title="Unit" variant="secondary" icon="home-outline" style={{ flex: 1 }} onPress={() => router.push(`/unit/${l.unit.id}`)} />
          </View>
        ) : null}
      </Card>

      {staff && l.actions.some((a: string) => ACTIONS[a] || a === 'moveout' || a === 'edit') ? (
        <>
          <SectionTitle title="Actions" />
          {l.actions.includes('edit') ? (
            <Button title="Edit terms" variant="secondary" icon="create-outline" onPress={() => router.push(`/lease/form?id=${l.id}`)} />
          ) : null}
          {l.actions.filter((a: string) => ACTIONS[a]).map((a: string) => (
            <Button key={a} title={ACTIONS[a].label} icon={ACTIONS[a].icon} variant={ACTIONS[a].variant ?? 'primary'} onPress={() => doAction(a)} />
          ))}
          {l.actions.includes('moveout') ? (
            <Button title="Move-out & deposit settlement" icon="exit-outline" tone="warning" onPress={() => router.push(`/lease/moveout?id=${l.id}`)} />
          ) : null}
          {l.actions.includes('delete') ? (
            <Button title="Delete lease" variant="danger" icon="trash-outline" onPress={() => confirmAction('Delete lease', `Delete ${l.name}?`, async () => { await api.del(`/leases/${l.id}`); router.back(); }, 'Delete')} />
          ) : null}
        </>
      ) : null}

      <SectionTitle title="Rent" />
      <Card>
        <Row label="Monthly rent" value={money(l.rent_amount, cur)} strong />
        <Row label="Maintenance charge" value={money(l.maintenance_charge, cur)} />
        <Row label="Monthly total" value={money(l.monthly_total, cur)} />
        <Row label="Billing" value={`${l.billing_frequency_label}, day ${l.billing_day}`} />
        <Row label="Next invoice" value={date(l.next_invoice_date)} />
        <Row label="Amount due" value={money(l.amount_due, cur)} tone={l.amount_due ? 'danger' : 'success'} strong />
        {l.late_fee_value ? <Row label="Late fee" value={`${l.late_fee_type === 'percent' ? `${l.late_fee_value}%` : money(l.late_fee_value, cur)} after ${l.grace_days} days`} /> : null}
        {l.escalation_percent ? <Row label="Escalation" value={`+${l.escalation_percent}% every ${l.escalation_every_months} months`} /> : null}
        <Row label="Notice period" value={`${l.notice_period_days} days`} />
      </Card>

      <SectionTitle title="Deposit" />
      <Card>
        <Row label="Security deposit" value={money(l.deposit_amount, cur)} strong />
        <Row label="Status" value={l.deposit_status_label} tone={STATE_TONES[l.deposit_status]} />
        {l.deposit_invoice ? <Row label="Deposit invoice" value={l.deposit_invoice.name} /> : null}
        {l.deposit_refunded_amount ? <Row label="Refunded" value={money(l.deposit_refunded_amount, cur)} /> : null}
      </Card>

      <SectionTitle title="Electricity" />
      <Card>
        <Row label="Billing" value={l.electricity_billing_label} />
        {l.electricity_billing === 'metered' ? <Row label="Rate" value={`${money(l.electricity_rate, cur)} / kWh`} /> : null}
        {l.electricity_fixed_amount ? <Row label="Fixed charge" value={money(l.electricity_fixed_amount, cur)} /> : null}
        {l.readings.slice(0, 4).map((r: any) => (
          <Row key={r.id} label={r.name} value={`${num(r.consumption)} kWh · ${money(r.amount, cur)}`} />
        ))}
        {l.readings.length ? <Button title="All readings" variant="ghost" onPress={() => router.push(`/reading?lease_id=${l.id}`)} /> : null}
      </Card>

      {l.state === 'terminated' ? (
        <>
          <SectionTitle title="Move-out settlement" />
          <Card>
            <Row label="Moved out" value={date(l.moveout_date)} />
            <Row label="Damage charges" value={money(l.moveout_damage_charges, cur)} />
            <Row label="Unpaid dues" value={money(l.moveout_unpaid_dues, cur)} />
            <Row label="Electricity" value={money(l.moveout_electricity_charges, cur)} />
            <Row label="Deposit refund" value={money(l.deposit_refunded_amount, cur)} strong tone="success" />
            {l.moveout_deduction_note ? <Muted>{l.moveout_deduction_note}</Muted> : null}
            <Button title="Settlement PDF" variant="secondary" icon="document-outline" onPress={() => run(() => downloadAndShare(`/leases/${l.id}/settlement`, `Settlement ${l.name}.pdf`))} />
          </Card>
        </>
      ) : null}

      <Button title="Lease agreement (PDF)" variant="secondary" icon="document-text-outline" onPress={() => run(() => downloadAndShare(`/leases/${l.id}/agreement`, `Lease Agreement ${l.name}.pdf`))} />

      <SectionTitle title="Timeline" />
      <Card>
        {l.timeline.map((e: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', gap: space.md, alignItems: 'flex-start', opacity: e.state === 'done' ? 0.65 : 1 }}>
            <Ionicons name={e.state === 'done' ? 'checkmark-circle' : e.state === 'next' ? 'radio-button-on' : 'ellipse-outline'} size={18} color={e.state === 'next' ? t.brand : t.faint} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: t.text, fontWeight: '700' }}>{e.title} · {date(e.date)}</Text>
              <Muted>{e.text}</Muted>
            </View>
          </View>
        ))}
      </Card>

      <SectionTitle title="Invoices" action={staff ? undefined : 'All'} onAction={() => router.push('/invoices')} />
      {l.invoices.length ? l.invoices.map((inv: any) => (
        <ListItem
          key={inv.id}
          icon="receipt-outline"
          title={inv.name}
          subtitle={`${inv.invoice_type_label || 'Invoice'} · due ${date(inv.invoice_date_due)}`}
          right={money(inv.amount_total, inv.currency)}
          badge={{ label: INVOICE_STATUS_LABEL[inv.status] ?? inv.status, tone: STATE_TONES[inv.status] }}
          onPress={user?.role === 'manager' ? undefined : () => router.push(`/invoice/${inv.id}`)}
        />
      )) : <Muted>No invoice yet.</Muted>}

      <SectionTitle title="Maintenance" action="New" onAction={() => router.push(`/maintenance/form?lease_id=${l.id}&unit_id=${l.unit.id}&unit_name=${encodeURIComponent(l.unit.name)}`)} />
      {l.maintenance.length ? l.maintenance.map((m: any) => (
        <ListItem key={m.id} icon="construct-outline" title={`${m.category_label} · ${m.name}`} subtitle={m.summary} badge={{ label: m.state_label, tone: STATE_TONES[m.state] }} onPress={() => router.push(`/maintenance/${m.id}`)} />
      )) : <Muted>No request.</Muted>}

      {l.notes ? (
        <Card>
          <Body>{l.notes}</Body>
        </Card>
      ) : null}
      <Chatter model="rent.lease" id={l.id} />
    </Screen>
  );
}
