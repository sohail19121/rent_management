import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';

import {
  Badge, BarChart, Button, Card, Chips, ErrorView, Kpi, ListItem, Loading, Muted, Progress, Row, Screen, SectionTitle,
  type IconName,
} from '../../components/ui';
import { canBill, useAuth } from '../../lib/auth';
import { date, INVOICE_STATUS_LABEL, money, num, STATE_TONES, type Tone } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function Home() {
  const { user } = useAuth();
  return user?.role === 'tenant' ? <TenantHome /> : <StaffDashboard />;
}

// ---------------------------------------------------------------------------
// Staff: owner / accountant / property manager dashboard
// ---------------------------------------------------------------------------

const PERIODS = [
  { value: 'this_month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'this_quarter', label: 'Quarter' },
  { value: 'this_year', label: 'This year' },
  { value: 'last_12_months', label: '12 months' },
];

const KPI_ICONS: Record<string, IconName> = {
  business: 'business-outline', home: 'home-outline', pie_chart: 'pie-chart-outline', key: 'key-outline',
  payments: 'cash-outline', account_balance: 'wallet-outline', receipt_long: 'receipt-outline',
  schedule: 'time-outline', warning: 'warning-outline', flash_on: 'flash-outline', event_upcoming: 'calendar-outline',
  contract: 'document-text-outline', build: 'construct-outline',
};

const KPI_LINKS: Record<string, string> = {
  properties: '/properties', units: '/unit', vacant: '/unit?state=vacant', occupancy: '/unit?state=occupied',
  rent_roll: '/leases?state=running', outstanding: '/invoices?status=to_pay', overdue: '/invoices?status=overdue',
  billed: '/invoices', collected: '/invoices?status=paid', expiring: '/leases?state=expiring',
  draft_leases: '/leases?state=draft', maintenance: '/maintenance?state=open', readings_to_enter: '/reading?state=draft',
  readings_to_bill: '/reading?state=confirmed',
};

const VARIANT_TONES: Record<string, Tone> = { primary: 'brand', success: 'success', warning: 'warning', danger: 'danger' };

function kpiValue(kpi: any, currency: string) {
  if (kpi.format === 'monetary') return money(kpi.value, currency, true);
  if (kpi.format === 'percent') return `${num(kpi.value, 1)}%`;
  return num(kpi.value, 0);
}

function StaffDashboard() {
  const t = useTheme();
  const { user } = useAuth();
  const [period, setPeriod] = useState('this_month');
  const { data, error, loading, refreshing, refresh } = useApi<any>(`/dashboard?period=${period}`);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorView error={error} onRetry={refresh} />;
  const currency = user?.company?.currency ?? '';
  const billing = canBill(user?.role);
  const monthly = data.monthly ?? {};
  const months: string[] = monthly.labels ?? monthly.months ?? [];
  const chart = months.slice(-6).map((label: string, i: number) => {
    const index = months.length - 6 + i;
    return { label: String(label).slice(0, 3), values: [monthly.billed?.[index] ?? 0, monthly.collected?.[index] ?? 0] };
  });

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Chips options={PERIODS} value={period} onChange={setPeriod} />
      <QuickActions />
      {data.sections.map((section: any) => (
        <View key={section.title} style={{ gap: space.sm }}>
          <SectionTitle title={section.title} />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {section.kpis.map((kpi: any) => (
                <Kpi
                  key={kpi.key}
                  label={kpi.label}
                  value={kpiValue(kpi, currency)}
                  hint={kpi.hint}
                  icon={KPI_ICONS[kpi.icon] ?? 'stats-chart-outline'}
                  tone={VARIANT_TONES[kpi.variant] ?? 'brand'}
                  onPress={KPI_LINKS[kpi.key] && (billing || !KPI_LINKS[kpi.key].startsWith('/invoices')) ? () => router.push(KPI_LINKS[kpi.key] as any) : undefined}
                />
              ))}
          </View>
        </View>
      ))}

      {chart.length ? (
        <>
          <SectionTitle title="Billed vs collected" />
          <Card>
            <BarChart
              data={chart}
              format={(v) => money(v, currency, true)}
              series={[{ label: 'Billed', tone: 'brand' }, { label: 'Collected', tone: 'success' }]}
            />
          </Card>
        </>
      ) : null}

      {data.overdue_tenants?.length ? (
        <>
          <SectionTitle title="Overdue tenants" />
          {data.overdue_tenants.map((row: any) => (
            <ListItem
              key={row.partner_id}
              icon="alert-circle-outline"
              title={row.tenant}
              subtitle={`${row.leases} · ${row.count} invoice(s)`}
              meta={`${row.days} days late${row.phone ? ` · ${row.phone}` : ''}`}
              right={money(row.amount, currency)}
              onPress={() => router.push(`/tenant/${row.partner_id}`)}
            />
          ))}
        </>
      ) : null}

      {data.expiring_leases?.length ? (
        <>
          <SectionTitle title="Leases ending soon" action="All" onAction={() => router.push('/leases?state=expiring' as any)} />
          {data.expiring_leases.map((lease: any) => (
            <ListItem
              key={lease.id}
              icon="calendar-outline"
              title={lease.tenant}
              subtitle={`${lease.unit} · ${lease.name}`}
              meta={`Ends ${date(lease.end_date)}`}
              badge={lease.renewal ? { label: 'Renewal', tone: 'info' } : { label: `${lease.days_left} days`, tone: lease.days_left < 15 ? 'danger' : 'warning' }}
              onPress={() => router.push(`/lease/${lease.id}`)}
            />
          ))}
        </>
      ) : null}

      {data.maintenance?.length ? (
        <>
          <SectionTitle title="Open maintenance" action="All" onAction={() => router.push('/maintenance?state=open' as any)} />
          {data.maintenance.map((m: any) => (
            <ListItem
              key={m.id}
              icon="construct-outline"
              title={`${m.category} · ${m.unit}`}
              subtitle={`${m.name}${m.assigned ? ` · ${m.assigned}` : ''}`}
              meta={`${m.age} day(s) old`}
              badge={{ label: ['Low', 'Normal', 'High', 'Urgent'][m.priority] ?? 'Normal', tone: m.priority >= 3 ? 'danger' : m.priority === 2 ? 'warning' : 'neutral' }}
              onPress={() => router.push(`/maintenance/${m.id}`)}
            />
          ))}
        </>
      ) : null}

      {data.readings_to_enter?.length ? (
        <>
          <SectionTitle title="Meter readings to enter" action="Scan" onAction={() => router.push('/meter/scan')} />
          {data.readings_to_enter.map((r: any) => (
            <ListItem
              key={r.id}
              icon="flash-outline"
              title={r.unit}
              subtitle={`${r.tenant} · ${r.period}`}
              meta={`Previous ${num(r.previous)} kWh`}
              onPress={() => router.push(`/reading/${r.id}`)}
            />
          ))}
        </>
      ) : null}

      {billing && data.recent_payments?.length ? (
        <>
          <SectionTitle title="Recent payments" />
          <Card>
            {data.recent_payments.map((p: any, i: number) => (
              <Row key={i} label={`${date(p.date)} · ${p.tenant}`} value={money(p.amount, currency)} />
            ))}
          </Card>
        </>
      ) : null}

      {data.property_rows?.length ? (
        <>
          <SectionTitle title="By property" />
          {data.property_rows.map((row: any) => (
            <Card key={row.id} onPress={() => router.push(`/property/${row.id}`)}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: t.text, fontWeight: '700', fontSize: 15 }}>{row.name}</Text>
                <Text style={{ color: t.muted }}>{row.occupied}/{row.units} occupied</Text>
              </View>
              <Progress value={row.occupancy} tone="success" />
              <Row label="Rent roll" value={money(row.rent_roll, currency)} />
              {billing ? <Row label="Outstanding" value={money(row.outstanding, currency)} tone={row.outstanding ? 'warning' : undefined} /> : null}
            </Card>
          ))}
        </>
      ) : null}
    </Screen>
  );
}

function QuickActions() {
  const t = useTheme();
  const { user } = useAuth();
  const actions: { icon: IconName; label: string; href: string; show?: boolean }[] = [
    { icon: 'qr-code-outline', label: 'Scan meter', href: '/meter/scan' },
    { icon: 'document-text-outline', label: 'New lease', href: '/lease/form' },
    { icon: 'person-add-outline', label: 'New tenant', href: '/tenant/form' },
    { icon: 'construct-outline', label: 'New request', href: '/maintenance/form' },
    { icon: 'cash-outline', label: 'Collect', href: '/invoices?status=to_pay', show: canBill(user?.role) },
  ];
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
      {actions.filter((a) => a.show !== false).map((a) => (
        <Pressable key={a.label} onPress={() => router.push(a.href as any)} style={{ alignItems: 'center', gap: 6, flex: 1 }}>
          <View style={{ width: 50, height: 50, borderRadius: 16, backgroundColor: t.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={a.icon} size={22} color={t.brand} />
          </View>
          <Text style={{ color: t.text, fontSize: 11, fontWeight: '600', textAlign: 'center' }}>{a.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Tenant home
// ---------------------------------------------------------------------------

const ALERT_TONES: Record<string, Tone> = { danger: 'danger', warning: 'warning', info: 'info' };

function TenantHome() {
  const t = useTheme();
  const [leaseId, setLeaseId] = useState<number | null>(null);
  const { data, error, loading, refreshing, refresh } = useApi<any>(`/dashboard${leaseId ? `?lease_id=${leaseId}` : ''}`);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorView error={error} onRetry={refresh} />;
  const cur = data.currency;
  const lease = data.lease;
  const pay = data.pay_invoice;

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      {data.leases.length > 1 ? (
        <Chips
          options={data.leases.map((l: any) => ({ value: String(l.id), label: `${l.unit?.name ?? l.name}` }))}
          value={String(lease?.id ?? '')}
          onChange={(v) => setLeaseId(Number(v))}
        />
      ) : null}

      {!lease ? (
        <Card>
          <Text style={{ color: t.text, fontWeight: '700', fontSize: 16 }}>No lease yet</Text>
          <Muted>Your lease will appear here once your property manager confirms it.</Muted>
        </Card>
      ) : null}

      {data.alerts.map((alert: any, i: number) => (
        <Card key={i} style={{ backgroundColor: t.tones[ALERT_TONES[alert.level] ?? 'info'].bg, borderWidth: 0 }}>
          <Text style={{ color: t.tones[ALERT_TONES[alert.level] ?? 'info'].fg, fontWeight: '800', fontSize: 15 }}>{alert.title}</Text>
          <Text style={{ color: t.text }}>{alert.text}</Text>
          {alert.url && alert.cta ? (
            <Button title={alert.amount ? `${alert.cta} · ${money(alert.amount, cur)}` : alert.cta} icon="card-outline" onPress={() => WebBrowser.openBrowserAsync(alert.url)} />
          ) : null}
        </Card>
      ))}

      <Card style={{ backgroundColor: t.brand, borderWidth: 0 }}>
        <Text style={{ color: t.onBrand, opacity: 0.85, fontSize: 13, fontWeight: '600' }}>Amount due</Text>
        <Text style={{ color: t.onBrand, fontSize: 34, fontWeight: '800' }}>{money(data.amount_due, cur)}</Text>
        {data.overdue_amount ? <Text style={{ color: t.onBrand }}>Overdue: {money(data.overdue_amount, cur)}</Text> : null}
        {data.next_payment ? (
          <Text style={{ color: t.onBrand, opacity: 0.9 }}>
            Next payment {data.next_payment.estimate ? '(estimate) ' : ''}{money(data.next_payment.amount, cur)} on {date(data.next_payment.date)}
          </Text>
        ) : null}
        {pay?.pay_url ? (
          <Button
            title={`Pay ${pay.name}`}
            icon="card-outline"
            variant="secondary"
            onPress={() => WebBrowser.openBrowserAsync(pay.pay_url)}
            style={{ marginTop: space.sm }}
          />
        ) : null}
      </Card>

      {lease ? (
        <Card onPress={() => router.push(`/lease/${lease.id}`)}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ color: t.text, fontWeight: '800', fontSize: 16 }}>{data.unit?.name}</Text>
            <Badge label={lease.state_label} tone={STATE_TONES[lease.state]} />
          </View>
          <Muted>{lease.name} · {date(lease.start_date)} → {date(lease.end_date)}</Muted>
          <Progress value={data.lease_progress} />
          <Muted>{data.days_left > 0 ? `${data.months_left} month(s) / ${data.days_left} days left` : 'Lease ended'}</Muted>
          <Row label="Monthly rent" value={money(lease.rent_amount, cur)} strong />
          <Row label="Deposit" value={lease.deposit_status_label} />
        </Card>
      ) : null}

      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Kpi label="Paid this year" value={money(data.paid_this_year, cur, true)} icon="checkmark-circle-outline" tone="success" />
        <Kpi label="Open requests" value={String(data.open_request_count)} icon="construct-outline" tone="warning" onPress={() => router.push('/maintenance')} />
      </View>

      {data.trend?.some((p: any) => p.value) ? (
        <>
          <SectionTitle title="Payments, last 6 months" />
          <Card>
            <BarChart data={data.trend.map((p: any) => ({ label: p.month, values: [p.value] }))} format={(v) => money(v, cur, true)} series={[{ label: 'Paid', tone: 'success' }]} />
          </Card>
        </>
      ) : null}

      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Button title="Report a problem" icon="construct-outline" onPress={() => router.push('/maintenance/form')} style={{ flex: 1 }} />
      </View>

      {data.invoices.length ? (
        <>
          <SectionTitle title="Recent invoices" action="All" onAction={() => router.push('/invoices')} />
          {data.invoices.slice(0, 4).map((inv: any) => (
            <ListItem
              key={inv.id}
              icon="receipt-outline"
              title={inv.name}
              subtitle={`${inv.invoice_type_label || 'Invoice'} · due ${date(inv.invoice_date_due)}`}
              right={money(inv.amount_total, inv.currency)}
              badge={{ label: INVOICE_STATUS_LABEL[inv.status] ?? inv.status, tone: STATE_TONES[inv.status] }}
              onPress={() => router.push(`/invoice/${inv.id}`)}
            />
          ))}
        </>
      ) : null}

      {data.readings.length ? (
        <>
          <SectionTitle title="Electricity" />
          <Card>
            <BarChart
              data={[...data.readings].reverse().map((r: any) => ({ label: r.period_start.slice(5, 7) + '/' + r.period_start.slice(2, 4), values: [r.consumption] }))}
              format={(v) => `${num(v, 0)} kWh`}
              series={[{ label: 'kWh', tone: 'warning' }]}
            />
            <Row label="Last reading" value={`${num(data.readings[0].current_reading)} (${num(data.readings[0].consumption)} kWh)`} />
            <Row label="Amount" value={money(data.readings[0].amount, cur)} />
          </Card>
        </>
      ) : null}

      {data.manager ? (
        <>
          <SectionTitle title="Your property manager" />
          <Card>
            <Text style={{ color: t.text, fontWeight: '700', fontSize: 15 }}>{data.manager.name}</Text>
            {data.manager.phone ? <Row label="Phone" value={data.manager.phone} /> : null}
            {data.manager.email ? <Row label="Email" value={data.manager.email} /> : null}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
