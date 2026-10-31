import React, { useState } from 'react';
import { router, Stack } from 'expo-router';

import { Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { money } from '../../lib/format';
import { useDebounced, useList } from '../../lib/useApi';

export default function Tenants() {
  const [search, setSearch] = useState('');
  const list = useList<any>('/tenants', { search: useDebounced(search) });
  return (
    <>
      <Stack.Screen options={{ title: 'Tenants' }} />
      <ListScreen
        {...list}
        onRefresh={list.refresh}
        onEndReached={list.loadMore}
        header={<SearchBar value={search} onChange={setSearch} placeholder="Name, email, phone" />}
        empty={{ title: 'No tenants', icon: 'people-outline' }}
        renderItem={(p) => (
          <ListItem
            image={p.image_url}
            icon="person-outline"
            title={p.name}
            subtitle={[p.phone, p.email].filter(Boolean).join(' · ')}
            meta={`${p.lease_count} lease(s)${p.has_app_access ? ' · App access' : ''}`}
            right={p.rent_total_due ? money(p.rent_total_due, undefined, true) : undefined}
            badge={p.kyc_verified ? { label: 'KYC ✓', tone: 'success' } : { label: 'KYC pending', tone: 'warning' }}
            onPress={() => router.push(`/tenant/${p.id}`)}
          />
        )}
        fab={<Fab onPress={() => router.push('/tenant/form')} label="Tenant" />}
      />
    </>
  );
}
