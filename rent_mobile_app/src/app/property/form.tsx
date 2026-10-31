import React, { useEffect, useState } from 'react';
import { Image } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  AuthImage, Button, Card, choosePhoto, Field, Loading, RecordField, run, Screen, SectionTitle, SelectField, type Option, type Photo,
} from '../../components/ui';
import { api } from '../../lib/api';
import { selection, useMeta } from '../../lib/meta';

export default function PropertyForm() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const meta = useMeta();
  const [loading, setLoading] = useState(!!id);
  const [form, setForm] = useState<any>({ name: '', property_type: 'residential' });
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [amenities, setAmenities] = useState<Option[]>([]);
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));

  useEffect(() => {
    if (!id) return;
    api.get(`/properties/${id}`).then((p) => {
      setForm(p);
      setAmenities(p.amenities);
      setLoading(false);
    });
  }, [id]);

  if (loading) return <Loading />;

  const save = async () => {
    const body: any = {
      name: form.name, property_type: form.property_type, street: form.street, street2: form.street2, city: form.city,
      zip: form.zip, state_id: form.state?.id ?? false, country_id: form.country?.id ?? false,
      manager_id: form.manager?.id ?? false, owner_id: form.owner?.id ?? false, notes: form.notes,
      amenity_ids: amenities.map((a) => a.id),
    };
    if (photo) body.image = photo.base64;
    const saved = await run(() => (id ? api.put(`/properties/${id}`, body) : api.post('/properties', body)));
    if (saved) {
      if (id) router.back();
      else router.replace(`/property/${saved.id}`);
    }
  };

  return (
    <Screen footer={<Button title={id ? 'Save' : 'Create property'} icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: id ? 'Edit property' : 'New property' }} />
      <Card>
        {photo ? (
          <Image source={{ uri: photo.uri }} style={{ width: '100%', height: 160, borderRadius: 12 }} />
        ) : form.image_url ? (
          <AuthImage path={form.image_url} style={{ width: '100%', height: 160, borderRadius: 12 }} />
        ) : null}
        <Button title={form.image_url || photo ? 'Change photo' : 'Add photo'} variant="secondary" icon="camera-outline" onPress={() => choosePhoto(setPhoto)} />
        <Field label="Name" required value={form.name} onChangeText={(v) => set('name', v)} placeholder="Green Park Residency" />
        <SelectField label="Type" value={form.property_type} options={selection(meta, 'property_type')} onChange={(v) => set('property_type', v)} required />
        <RecordField label="Property manager" kind="users" value={form.manager} onChange={(v) => set('manager', v)} help="Managers see only the properties assigned to them." />
        <RecordField label="Owner" kind="owners" value={form.owner} onChange={(v) => set('owner', v)} />
      </Card>
      <SectionTitle title="Address" />
      <Card>
        <Field label="Street" value={form.street} onChangeText={(v) => set('street', v)} />
        <Field label="Street 2" value={form.street2} onChangeText={(v) => set('street2', v)} />
        <Field label="City" value={form.city} onChangeText={(v) => set('city', v)} />
        <Field label="ZIP" value={form.zip} onChangeText={(v) => set('zip', v)} keyboardType="number-pad" />
        <RecordField label="Country" kind="countries" value={form.country} onChange={(v) => { set('country', v); set('state', null); }} />
        <RecordField label="State" kind="states" value={form.state} onChange={(v) => set('state', v)} params={{ country_id: form.country?.id }} />
      </Card>
      <SectionTitle title="Amenities" />
      <Card>
        {amenities.map((a) => (
          <Button key={a.id} title={`${a.name}  ✕`} variant="secondary" onPress={() => setAmenities(amenities.filter((x) => x.id !== a.id))} />
        ))}
        <RecordField
          label="Add amenity"
          kind="amenities"
          value={null}
          clearable={false}
          onChange={(v) => v && !amenities.some((a) => a.id === v.id) && setAmenities([...amenities, v])}
        />
      </Card>
      <Field label="Notes" value={form.notes} onChangeText={(v) => set('notes', v)} multiline />
    </Screen>
  );
}
