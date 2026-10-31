import React, { useEffect, useState } from 'react';
import { Image } from 'react-native';
import { router, Stack } from 'expo-router';

import { AuthImage, Button, Card, choosePhoto, Field, Loading, RecordField, run, Screen, SectionTitle, type Photo } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';

export default function Profile() {
  const { refreshUser } = useAuth();
  const [form, setForm] = useState<any>(null);
  const [photo, setPhoto] = useState<Photo | null>(null);
  useEffect(() => {
    api.get('/me').then(setForm);
  }, []);
  if (!form) return <Loading />;
  const set = (key: string, value: any) => setForm({ ...form, [key]: value });
  const save = async () => {
    const body: any = {
      name: form.name, email: form.email, phone: form.phone, street: form.street, street2: form.street2, city: form.city,
      zip: form.zip, state_id: form.state?.id ?? false, country_id: form.country?.id ?? false,
    };
    if (photo) body.image_1920 = photo.base64;
    if (await run(() => api.put('/me', body))) {
      await refreshUser();
      router.back();
    }
  };
  return (
    <Screen footer={<Button title="Save" icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: 'My profile' }} />
      <Card>
        {photo ? <Image source={{ uri: photo.uri }} style={{ width: 96, height: 96, borderRadius: 48, alignSelf: 'center' }} /> : form.image_url ? <AuthImage path={form.image_url} style={{ width: 96, height: 96, borderRadius: 48, alignSelf: 'center' }} /> : null}
        <Button title="Change photo" variant="secondary" icon="camera-outline" onPress={() => choosePhoto(setPhoto)} />
        <Field label="Name" value={form.name} onChangeText={(v) => set('name', v)} required />
        <Field label="Email" value={form.email} onChangeText={(v) => set('email', v)} keyboardType="email-address" autoCapitalize="none" />
        <Field label="Phone" value={form.phone} onChangeText={(v) => set('phone', v)} keyboardType="phone-pad" />
      </Card>
      <SectionTitle title="Address" />
      <Card>
        <Field label="Street" value={form.street} onChangeText={(v) => set('street', v)} />
        <Field label="Street 2" value={form.street2} onChangeText={(v) => set('street2', v)} />
        <Field label="City" value={form.city} onChangeText={(v) => set('city', v)} />
        <Field label="ZIP" value={form.zip} onChangeText={(v) => set('zip', v)} keyboardType="number-pad" />
        <RecordField label="Country" kind="countries" value={form.country} onChange={(v) => setForm({ ...form, country: v, state: null })} />
        <RecordField label="State" kind="states" value={form.state} onChange={(v) => set('state', v)} params={{ country_id: form.country?.id }} />
      </Card>
    </Screen>
  );
}
