import React, { useState } from 'react';
import { router } from 'expo-router';

import { Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { num } from '../../lib/format';
import { useDebounced, useList } from '../../lib/useApi';

export default function Properties() {
  const [search, setSearch] = useState('');
  const list = useList<any>('/properties', { search: useDebounced(search) });
  return (
    <ListScreen
      {...list}
      onRefresh={list.refresh}
      onEndReached={list.loadMore}
      header={<SearchBar value={search} onChange={setSearch} placeholder="Search properties" />}
      empty={{ title: 'No properties', text: 'Add your first building or house.', icon: 'business-outline' }}
      renderItem={(p) => (
        <ListItem
          image={p.image_url}
          icon="business-outline"
          title={p.name}
          subtitle={[p.property_type_label, p.city].filter(Boolean).join(' · ')}
          meta={`${p.unit_count} units · ${p.vacant_count} vacant`}
          right={`${num(p.occupancy_rate, 0)}%`}
          onPress={() => router.push(`/property/${p.id}`)}
        />
      )}
      fab={<Fab onPress={() => router.push('/property/form')} label="Property" />}
    />
  );
}
