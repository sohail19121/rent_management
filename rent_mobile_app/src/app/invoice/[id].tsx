import React from 'react';
import { Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';

import { Chatter } from '../../components/Chatter';
import { Badge, Button, Card, confirmAction, Divider, ErrorView, Loading, Muted, Row, run, Screen, SectionTitle } from '../../components/ui';
import { api, downloadAndShare } from '../../lib/api';
import { canBill, useAuth } from '../../lib/auth';
import { date, INVOICE_STATUS_LABEL, money, num, STATE_TONES } from '../../lib/format';
import { space, useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

export default function InvoiceDetail() {
  const t = useTheme();
  const { user } = useAuth();
  const billing = canBill(user?.role);
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: inv, error, loading, refreshing, refresh } = useApi<any>(`/invoices/${id}`);
  if (loading && !inv) return <Loading />;
  if (error && !inv) return <ErrorView error={error} onRetry={refresh} />;
  const cur = inv.currency;
  const statusLabel = INVOICE_STATUS_LABEL[inv.status] ?? inv.status;

  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: inv.name }} />
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: t.text, fontSize: 15, fontWeight: '700', flex: 1 }}>{inv.invoice_type_label || 'Invoice'}</Text>
          <Badge label={statusLabel} tone={STATE_TONES[inv.status]} />
        </View>
        <Text style={{ color: t.text, fontSize: 32, fontWeight: '800' }}>{money(inv.amount_total, cur)}</Text>
        {inv.amount_residual && inv.status !== 'paid' && inv.status !== 'refund' ? (
          <Text style={{ color: t.tones[inv.status === 'overdue' ? 'danger' : 'warning'].fg, fontWeight: '700' }}>
            {money(inv.amount_residual, cur)} left to pay
          </Text>
        ) : null}
        <Row label="Billed to" value={inv.partner?.name} />
        <Row label="Lease" value={inv.lease?.name} />
        <Row label="Invoice date" value={date(inv.invoice_date)} />
        <Row label="Due date" value={date(inv.invoice_date_due)} tone={inv.status === 'overdue' ? 'danger' : undefined} />
      </Card>

      {inv.pay_url && user?.role === 'tenant' ? (
        <Button title={`Pay ${money(inv.amount_residual, cur)} online`} icon="card-outline" onPress={() => WebBrowser.openBrowserAsync(inv.pay_url)} />
      ) : null}
      {billing && inv.can_register_payment ? (
        <Button title="Register payment received" icon="cash-outline" onPress={() => router.push(`/invoice/payment?id=${inv.id}&amount=${inv.amount_residual}`)} />
      ) : null}
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Button title="Invoice PDF" variant="secondary" icon="document-outline" style={{ flex: 1 }} onPress={() => run(() => downloadAndShare(`/invoices/${inv.id}/pdf`, `${inv.name.replace(/\//g, '-')}.pdf`))} />
        {inv.status === 'paid' ? (
          <Button title="Receipt" variant="secondary" icon="checkmark-done-outline" style={{ flex: 1 }} onPress={() => run(() => downloadAndShare(`/invoices/${inv.id}/receipt`, `Receipt ${inv.name.replace(/\//g, '-')}.pdf`))} />
        ) : null}
      </View>
      {billing && inv.state === 'posted' ? (
        <Button title="Email to tenant" variant="ghost" icon="mail-outline" onPress={() => confirmAction('Send invoice', `Email ${inv.name} to ${inv.partner?.name}?`, () => api.post(`/invoices/${inv.id}/send`), 'Send')} />
      ) : null}

      <SectionTitle title="Details" />
      <Card>
        {inv.lines.map((line: any, i: number) =>
          line.display_type === 'product' ? (
            <View key={i} style={{ gap: 2, paddingVertical: 4 }}>
              <Text style={{ color: t.text, fontSize: 14 }}>{line.name}</Text>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Muted>{num(line.quantity)} × {money(line.price_unit, cur)}</Muted>
                <Text style={{ color: t.text, fontWeight: '600' }}>{money(line.subtotal, cur)}</Text>
              </View>
            </View>
          ) : (
            <Text key={i} style={{ color: t.muted, fontWeight: '700', marginTop: 4 }}>{line.name}</Text>
          ),
        )}
        <Divider />
        <Row label="Untaxed" value={money(inv.amount_untaxed, cur)} />
        {inv.amount_tax ? <Row label="Tax" value={money(inv.amount_tax, cur)} /> : null}
        <Row label="Total" value={money(inv.amount_total, cur)} strong />
      </Card>

      {inv.payments.length ? (
        <>
          <SectionTitle title="Payments" />
          <Card>
            {inv.payments.map((p: any, i: number) => (
              <Row key={i} label={`${date(p.date)}${p.journal ? ` · ${p.journal}` : ''}`} value={money(p.amount, cur)} tone="success" />
            ))}
          </Card>
        </>
      ) : null}
      <Chatter model="account.move" id={inv.id} />
    </Screen>
  );
}
