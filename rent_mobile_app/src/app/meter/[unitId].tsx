import React, { useState } from 'react';
import { Image, Text } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  Button, Card, choosePhoto, ErrorView, Loading, Muted, NumberField, Row, run, Screen, SwitchField, type Photo,
} from '../../components/ui';
import { api } from '../../lib/api';
import { date, money, num } from '../../lib/format';
import { useTheme } from '../../lib/theme';
import { useApi } from '../../lib/useApi';

/** Enter this month's meter reading of a unit, on site, with a photo of the meter. */
export default function MeterEntry() {
  const t = useTheme();
  const { unitId } = useLocalSearchParams<{ unitId: string }>();
  const { data: e, error, loading, refresh } = useApi<any>(`/units/${unitId}/meter`);
  const [current, setCurrent] = useState('');
  const [rateInput, setRate] = useState<string | null>(null);
  const [applyRate, setApplyRate] = useState(false);
  const [photo, setPhoto] = useState<Photo | null>(null);
  const rate = rateInput ?? (e?.rate !== undefined ? String(e.rate) : '');
  if (loading && !e) return <Loading />;
  if (error && !e) return <ErrorView error={error} onRetry={refresh} />;

  if (!e.lease) {
    return (
      <Screen>
        <Stack.Screen options={{ title: e.unit.display_name }} />
        <Card>
          <Text style={{ color: t.text, fontWeight: '700' }}>No metered lease</Text>
          <Muted>
            {e.unmetered_lease
              ? `Lease ${e.unmetered_lease.name} does not bill electricity by meter reading.`
              : 'This unit has no running lease: there is nobody to bill.'}
          </Muted>
        </Card>
      </Screen>
    );
  }

  const consumption = Math.max(Number(current || 0) - e.previous_reading, 0);
  const save = async () => {
    const reading = await run(() =>
      api.post(`/units/${unitId}/meter`, { current_reading: current, rate, apply_rate: applyRate, photo: photo?.base64 }),
    );
    if (reading) router.replace(`/reading/${reading.id}`);
  };

  return (
    <Screen footer={<Button title="Save reading" icon="checkmark-circle-outline" onPress={save} disabled={!current} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: e.unit.display_name }} />
      <Card>
        <Row label="Tenant" value={e.tenant?.name} />
        <Row label="Lease" value={e.lease.name} />
        <Row label="Meter no." value={e.meter_number} />
        <Row label="Period" value={`${date(e.period_start)} → ${date(e.period_end)}`} />
        <Row label="Previous reading" value={num(e.previous_reading)} strong />
      </Card>
      <Card>
        <NumberField label="Current reading" value={current} onChange={setCurrent} required placeholder={num(e.previous_reading)} />
        <NumberField label="Rate per kWh" value={rate} onChange={setRate} />
        {Number(rate) !== e.lease_rate ? (
          <SwitchField label="Use this rate for the next months" value={applyRate} onChange={setApplyRate} />
        ) : null}
        {photo ? <Image source={{ uri: photo.uri }} style={{ width: '100%', height: 200, borderRadius: 12 }} /> : null}
        <Button title={photo ? 'Retake meter photo' : 'Take meter photo'} variant="secondary" icon="camera-outline" onPress={() => choosePhoto(setPhoto)} />
      </Card>
      {current ? (
        <Card>
          <Row label="Consumption" value={`${num(consumption)} kWh`} strong />
          <Row label="Estimated amount" value={money(consumption * Number(rate || 0))} />
          {Number(current) < e.previous_reading ? (
            <Text style={{ color: t.tones.danger.fg }}>The reading is lower than the previous one.</Text>
          ) : null}
        </Card>
      ) : null}
    </Screen>
  );
}
