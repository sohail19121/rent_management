import React, { useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import { Chips, Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { money, STATE_TONES } from '../../lib/format';
import { useDebounced, useList } from '../../lib/useApi';

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'vacant', label: 'Vacant' },
  { value: 'reserved', label: 'Reserved' },
  { value: 'occupied', label: 'Occupied' },
  { value: 'under_maintenance', label: 'Maintenance' },
];

export default function Units() {
  const params = useLocalSearchParams<{ state?: string; property_id?: string }>();
  const [state, setState] = useState(params.state ?? '');
  const [search, setSearch] = useState('');
  const list = useList<any>('/units', { search: useDebounced(search), state, property_id: params.property_id });
  return (
    <>
      <Stack.Screen options={{ title: 'Units' }} />
      <ListScreen
        {...list}
        onRefresh={list.refresh}
        onEndReached={list.loadMore}
        header={
          <>
            <SearchBar value={search} onChange={setSearch} placeholder="Unit, property, tenant" />
            <Chips options={FILTERS} value={state} onChange={setState} />
          </>
        }
        empty={{ title: 'No units', icon: 'home-outline' }}
        renderItem={(u) => (
          <ListItem
            image={u.image_url}
            icon="home-outline"
            title={u.display_name}
            subtitle={`${u.unit_type_label}${u.bedrooms ? ` · ${u.bedrooms} BHK` : ''}${u.area_sqft ? ` · ${u.area_sqft} sq ft` : ''}`}
            meta={u.current_tenant?.name}
            right={money(u.base_rent, u.currency, true)}
            badge={{ label: u.state_label, tone: STATE_TONES[u.state] }}
            onPress={() => router.push(`/unit/${u.id}`)}
          />
        )}
        fab={<Fab onPress={() => router.push('/unit/form')} label="Unit" />}
      />
    </>
  );
}
