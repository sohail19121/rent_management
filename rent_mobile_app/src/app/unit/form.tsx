import React, { useEffect, useState } from 'react';
import { Image } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  AuthImage, Button, Card, choosePhoto, Field, Loading, NumberField, RecordField, run, Screen, SectionTitle, SelectField, SwitchField,
  type Photo,
} from '../../components/ui';
import { api } from '../../lib/api';
import { selection, useMeta } from '../../lib/meta';

export default function UnitForm() {
  const params = useLocalSearchParams<{ id?: string; property_id?: string; property_name?: string }>();
  const id = params.id;
  const meta = useMeta();
  const [loading, setLoading] = useState(!!id);
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [form, setForm] = useState<any>({
    unit_type: 'flat',
    furnishing: 'unfurnished',
    property: params.property_id ? { id: Number(params.property_id), name: params.property_name } : null,
  });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));

  useEffect(() => {
    if (!id) return;
    api.get(`/units/${id}`).then((u) => {
      setForm(u);
      setLoading(false);
    });
  }, [id]);
  if (loading) return <Loading />;

  const save = async () => {
    const body: any = {
      name: form.name, property_id: form.property?.id, floor: form.floor, unit_type: form.unit_type,
      area_sqft: form.area_sqft || 0, bedrooms: form.bedrooms || 0, furnishing: form.furnishing,
      base_rent: form.base_rent || 0, deposit_amount: form.deposit_amount || 0,
      maintenance_charge: form.maintenance_charge || 0, meter_number: form.meter_number,
      under_maintenance: !!form.under_maintenance,
    };
    if (photo) body.image = photo.base64;
    const saved = await run(() => (id ? api.put(`/units/${id}`, body) : api.post('/units', body)));
    if (saved) {
      if (id) router.back();
      else router.replace(`/unit/${saved.id}`);
    }
  };

  return (
    <Screen footer={<Button title={id ? 'Save' : 'Create unit'} icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: id ? 'Edit unit' : 'New unit' }} />
      <Card>
        {photo ? <Image source={{ uri: photo.uri }} style={{ width: '100%', height: 160, borderRadius: 12 }} /> : form.image_url ? <AuthImage path={form.image_url} style={{ width: '100%', height: 160, borderRadius: 12 }} /> : null}
        <Button title="Photo" variant="secondary" icon="camera-outline" onPress={() => choosePhoto(setPhoto)} />
        <RecordField label="Property" kind="properties" value={form.property} onChange={(v) => set('property', v)} required clearable={false} />
        <Field label="Unit name / number" required value={form.name} onChangeText={(v) => set('name', v)} placeholder="A-101" />
        <Field label="Floor" value={form.floor} onChangeText={(v) => set('floor', v)} />
        <SelectField label="Type" value={form.unit_type} options={selection(meta, 'unit_type')} onChange={(v) => set('unit_type', v)} required />
        <SelectField label="Furnishing" value={form.furnishing} options={selection(meta, 'furnishing')} onChange={(v) => set('furnishing', v)} />
        <NumberField label="Bedrooms" value={form.bedrooms} onChange={(v) => set('bedrooms', v)} />
        <NumberField label="Area (sq ft)" value={form.area_sqft} onChange={(v) => set('area_sqft', v)} />
      </Card>
      <SectionTitle title="Rent" />
      <Card>
        <NumberField label="Base rent (per month)" value={form.base_rent} onChange={(v) => set('base_rent', v)} />
        <NumberField label="Security deposit" value={form.deposit_amount} onChange={(v) => set('deposit_amount', v)} />
        <NumberField label="Maintenance charge (per month)" value={form.maintenance_charge} onChange={(v) => set('maintenance_charge', v)} />
        <Field label="Electricity meter no." value={form.meter_number} onChangeText={(v) => set('meter_number', v)} help="With a meter number, new leases bill electricity by meter reading." />
        <SwitchField label="Under maintenance" value={!!form.under_maintenance} onChange={(v) => set('under_maintenance', v)} help="Takes the unit off the market." />
      </Card>
    </Screen>
  );
}
