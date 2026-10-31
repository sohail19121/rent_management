import React, { useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Button, Chips, confirmAction, Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { api } from '../../lib/api';
import { canBill, isStaff, useAuth } from '../../lib/auth';
import { money, num, STATE_TONES } from '../../lib/format';
import { useDebounced, useList } from '../../lib/useApi';

export default function Readings() {
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const params = useLocalSearchParams<{ state?: string; lease_id?: string; unit_id?: string }>();
  const [state, setState] = useState(params.state ?? '');
  const [search, setSearch] = useState('');
  const list = useList<any>('/readings', { search: useDebounced(search), state, lease_id: params.lease_id, unit_id: params.unit_id });
  const filters = staff
    ? [
        { value: '', label: 'All' },
        { value: 'draft', label: 'To enter' },
        { value: 'confirmed', label: 'To invoice' },
        { value: 'invoiced', label: 'Invoiced' },
      ]
    : [];
  const invoiceAll = () =>
    confirmAction('Invoice readings', `Create electricity invoices for the ${list.items.length} confirmed reading(s) shown?`, async () => {
      await api.post('/readings/invoice', { ids: list.items.map((r: any) => r.id) });
      list.reload();
    }, 'Invoice');
  return (
    <>
      <Stack.Screen options={{ title: 'Meter readings' }} />
      <ListScreen
        {...list}
        onRefresh={list.refresh}
        onEndReached={list.loadMore}
        header={
          <>
            {staff ? <SearchBar value={search} onChange={setSearch} placeholder="Unit, tenant, property" /> : null}
            {filters.length ? <Chips options={filters} value={state} onChange={setState} /> : null}
            {canBill(user?.role) && state === 'confirmed' && list.items.length ? (
              <Button title={`Invoice ${list.items.length} reading(s)`} icon="receipt-outline" onPress={invoiceAll} />
            ) : null}
          </>
        }
        empty={{ title: 'No readings', icon: 'flash-outline' }}
        renderItem={(r) => (
          <ListItem
            icon="flash-outline"
            title={staff ? `${r.unit?.name} · ${r.tenant?.name ?? ''}` : r.name}
            subtitle={`${r.name} · ${num(r.previous_reading)} → ${r.current_reading ? num(r.current_reading) : '…'}`}
            meta={r.consumption ? `${num(r.consumption)} kWh` : 'Reading to enter'}
            right={r.amount ? money(r.amount, r.currency) : undefined}
            badge={{ label: r.state_label, tone: STATE_TONES[r.state] }}
            onPress={() => router.push(`/reading/${r.id}`)}
          />
        )}
        fab={staff ? <Fab icon="qr-code-outline" label="Scan meter" onPress={() => router.push('/meter/scan')} /> : undefined}
      />
    </>
  );
}
