import React from 'react';
import { View } from 'react-native';
import { router, Stack } from 'expo-router';

import { Button, Empty, ErrorView, ListItem, Loading, run, Screen } from '../components/ui';
import { api } from '../lib/api';
import { date } from '../lib/format';
import { space } from '../lib/theme';
import { useApi } from '../lib/useApi';

const ROUTES: Record<string, string> = {
  'rent.lease': '/lease', 'rent.maintenance.request': '/maintenance', 'rent.electricity.reading': '/reading',
  'rent.unit': '/unit', 'rent.property': '/property',
};

export default function Activities() {
  const { data, error, loading, refreshing, refresh, reload } = useApi<any>('/activities');
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorView error={error} onRetry={refresh} />;
  return (
    <Screen refreshing={refreshing} onRefresh={refresh}>
      <Stack.Screen options={{ title: 'My activities' }} />
      {data.items.length ? null : <Empty icon="checkmark-done-outline" title="All done" text="No activity is assigned to you." />}
      {data.items.map((a: any) => (
        <View key={a.id} style={{ gap: space.xs }}>
          <ListItem
            icon="checkbox-outline"
            title={a.summary}
            subtitle={a.res_name}
            meta={a.note}
            badge={{ label: date(a.date_deadline), tone: a.overdue ? 'danger' : 'info' }}
            onPress={ROUTES[a.res_model] ? () => router.push(`${ROUTES[a.res_model]}/${a.res_id}` as any) : undefined}
          />
          <Button title="Mark done" variant="ghost" icon="checkmark" onPress={async () => { if (await run(() => api.post(`/activities/${a.id}/done`))) reload(); }} />
        </View>
      ))}
    </Screen>
  );
}
