import React, { useState } from 'react';
import { router, useLocalSearchParams } from 'expo-router';

import { Chips, Fab, ListItem, ListScreen, SearchBar } from '../../components/ui';
import { isStaff, useAuth } from '../../lib/auth';
import { date, STATE_TONES } from '../../lib/format';
import { useDebounced, useList, useParamState } from '../../lib/useApi';

const CATEGORY_ICONS: Record<string, any> = {
  plumbing: 'water-outline', electrical: 'flash-outline', cleaning: 'sparkles-outline', appliance: 'tv-outline', other: 'construct-outline',
};

export default function Maintenance() {
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const params = useLocalSearchParams<{ state?: string }>();
  const [state, setState] = useParamState(params.state, staff ? 'open' : '');
  const [search, setSearch] = useState('');
  const filters = [
    { value: 'open', label: 'Open' },
    ...(staff ? [{ value: 'mine', label: 'Assigned to me' }] : []),
    { value: 'new', label: 'New' },
    { value: 'in_progress', label: 'In progress' },
    { value: 'done', label: 'Done' },
    { value: '', label: 'All' },
  ];
  const list = useList<any>('/maintenance', {
    search: useDebounced(search),
    state: state === 'mine' ? 'open' : state,
    mine: state === 'mine' ? 1 : undefined,
  });
  return (
    <ListScreen
      {...list}
      onRefresh={list.refresh}
      onEndReached={list.loadMore}
      header={
        <>
          {staff ? <SearchBar value={search} onChange={setSearch} placeholder="Reference, unit, tenant" /> : null}
          <Chips options={filters} value={state} onChange={setState} />
        </>
      }
      empty={{ title: 'No requests', text: staff ? 'Nothing to fix right now.' : 'Report a problem in your home with the + button.', icon: 'construct-outline' }}
      renderItem={(m) => (
        <ListItem
          icon={CATEGORY_ICONS[m.category] ?? 'construct-outline'}
          title={`${m.category_label} · ${m.unit?.name ?? ''}`}
          subtitle={m.summary || m.name}
          meta={`${m.name} · ${date(m.create_date)}${m.assigned_to ? ` · ${m.assigned_to.name}` : ''}`}
          badge={{ label: m.state_label, tone: STATE_TONES[m.state] }}
          right={m.priority >= '2' ? m.priority_label : undefined}
          onPress={() => router.push(`/maintenance/${m.id}`)}
        />
      )}
      fab={<Fab onPress={() => router.push('/maintenance/form')} label={staff ? 'Request' : 'Report'} />}
    />
  );
}

