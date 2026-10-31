import React, { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';

import { Chips, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { isStaff, useAuth } from '../../lib/auth';
import { date, INVOICE_STATUS_LABEL, money, STATE_TONES } from '../../lib/format';
import { useDebounced, useList, useParamState } from '../../lib/useApi';

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'to_pay', label: 'To pay' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'paid', label: 'Paid' },
  { value: 'credit', label: 'Credit notes' },
];

export default function Invoices() {
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const params = useLocalSearchParams<{ status?: string }>();
  const [status, setStatus] = useParamState(params.status, '');
  const [search, setSearch] = useState('');
  const list = useList<any>('/invoices', { search: useDebounced(search), status });
  return (
    <ListScreen
      {...list}
      onRefresh={list.refresh}
      onEndReached={list.loadMore}
      header={
        <>
          {staff ? <SearchBar value={search} onChange={setSearch} placeholder="Invoice, tenant, lease" /> : null}
          <Chips options={FILTERS} value={status} onChange={setStatus} />
        </>
      }
      empty={{ title: 'No invoices', text: status ? 'Nothing matches this filter.' : 'Rent invoices appear here once issued.', icon: 'receipt-outline' }}
      renderItem={(inv) => (
        <ListItem
          icon={inv.move_type === 'out_refund' ? 'return-down-back-outline' : 'receipt-outline'}
          title={staff ? `${inv.partner?.name ?? ''}` : inv.name}
          subtitle={`${staff ? `${inv.name} · ` : ''}${inv.invoice_type_label || 'Invoice'}`}
          meta={`Due ${date(inv.invoice_date_due)}${inv.amount_residual && inv.status !== 'paid' ? ` · Left ${money(inv.amount_residual, inv.currency)}` : ''}`}
          right={money(inv.amount_total, inv.currency)}
          badge={{ label: INVOICE_STATUS_LABEL[inv.status] ?? inv.status, tone: STATE_TONES[inv.status] }}
          onPress={() => router.push(`/invoice/${inv.id}`)}
        />
      )}
    />
  );
}
