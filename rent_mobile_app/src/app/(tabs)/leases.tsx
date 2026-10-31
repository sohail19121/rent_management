import React, { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';

import { Chips, Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { isStaff, useAuth } from '../../lib/auth';
import { date, money, STATE_TONES } from '../../lib/format';
import { useDebounced, useList, useParamState } from '../../lib/useApi';

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'draft', label: 'Draft' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'expiring', label: 'Expiring' },
  { value: 'expired', label: 'Expired' },
  { value: 'terminated', label: 'Ended' },
];

export default function Leases() {
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const params = useLocalSearchParams<{ state?: string; property_id?: string; tenant_id?: string }>();
  const [state, setState] = useParamState(params.state, '');
  const [search, setSearch] = useState('');
  const list = useList<any>('/leases', { search: useDebounced(search), state, property_id: params.property_id, tenant_id: params.tenant_id });


  return (
    <ListScreen
      {...list}
      onRefresh={list.refresh}
      onEndReached={list.loadMore}
      header={
        <>
          {staff ? <SearchBar value={search} onChange={setSearch} placeholder="Tenant, unit, reference" /> : null}
          {staff ? <Chips options={FILTERS} value={state} onChange={setState} /> : null}
        </>
      }
      empty={{ title: 'No leases', text: staff ? 'Create a lease to rent out a unit.' : 'Your leases appear here.', icon: 'document-text-outline' }}
      renderItem={(lease) => (
        <ListItem
          icon="document-text-outline"
          title={staff ? lease.tenant?.name ?? lease.name : lease.unit?.name ?? lease.name}
          subtitle={`${lease.unit?.name ?? ''} · ${lease.name}`}
          meta={`${date(lease.start_date)} → ${date(lease.end_date)}${lease.amount_due ? ` · Due ${money(lease.amount_due, lease.currency)}` : ''}`}
          right={money(lease.rent_amount, lease.currency, true)}
          badge={{ label: lease.state_label, tone: STATE_TONES[lease.state] }}
          onPress={() => router.push(`/lease/${lease.id}`)}
        />
      )}
      fab={staff ? <Fab onPress={() => router.push('/lease/form')} label="Lease" /> : undefined}
    />
  );
}
