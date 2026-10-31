import React, { useEffect, useState } from 'react';
import { Image } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  AuthImage, Button, Card, choosePhoto, Field, Loading, RecordField, run, Screen, SectionTitle, SelectField, SwitchField, type Photo,
} from '../../components/ui';
import { api } from '../../lib/api';
import { selection, useMeta } from '../../lib/meta';

export default function TenantForm() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const meta = useMeta();
  const [loading, setLoading] = useState(!!id);
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [form, setForm] = useState<any>({ name: '' });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));
  useEffect(() => {
    if (!id) return;
    api.get(`/tenants/${id}`).then((p) => {
      setForm(p);
      setLoading(false);
    });
  }, [id]);
  if (loading) return <Loading />;

  const save = async () => {
    const body: any = {
      name: form.name, email: form.email, phone: form.phone, street: form.street, street2: form.street2, city: form.city,
      zip: form.zip, state_id: form.state?.id ?? false, country_id: form.country?.id ?? false,
      kyc_id_type: form.kyc_id_type || false, kyc_id_number: form.kyc_id_number, kyc_verified: !!form.kyc_verified,
      emergency_contact_name: form.emergency_contact_name, emergency_contact_phone: form.emergency_contact_phone,
    };
    if (photo) body.image_1920 = photo.base64;
    const saved = await run(() => (id ? api.put(`/tenants/${id}`, body) : api.post('/tenants', body)));
    if (saved) {
      if (id) router.back();
      else router.replace(`/tenant/${saved.id}`);
    }
  };

  return (
    <Screen footer={<Button title={id ? 'Save' : 'Create tenant'} icon="checkmark" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: id ? 'Edit tenant' : 'New tenant' }} />
      <Card>
        {photo ? <Image source={{ uri: photo.uri }} style={{ width: 90, height: 90, borderRadius: 45, alignSelf: 'center' }} /> : form.image_url ? <AuthImage path={form.image_url} style={{ width: 90, height: 90, borderRadius: 45, alignSelf: 'center' }} /> : null}
        <Button title="Photo" variant="secondary" icon="camera-outline" onPress={() => choosePhoto(setPhoto)} />
        <Field label="Full name" required value={form.name} onChangeText={(v) => set('name', v)} />
        <Field label="Email" value={form.email} onChangeText={(v) => set('email', v)} keyboardType="email-address" autoCapitalize="none" help="Used as the tenant's app login." />
        <Field label="Phone" value={form.phone} onChangeText={(v) => set('phone', v)} keyboardType="phone-pad" />
      </Card>
      <SectionTitle title="KYC" />
      <Card>
        <SelectField label="ID type" value={form.kyc_id_type} options={selection(meta, 'kyc_id_type')} onChange={(v) => set('kyc_id_type', v)} />
        <Field label="ID number" value={form.kyc_id_number} onChangeText={(v) => set('kyc_id_number', v)} autoCapitalize="characters" />
        <SwitchField label="KYC verified" value={!!form.kyc_verified} onChange={(v) => set('kyc_verified', v)} />
      </Card>
      <SectionTitle title="Address" />
      <Card>
        <Field label="Street" value={form.street} onChangeText={(v) => set('street', v)} />
        <Field label="City" value={form.city} onChangeText={(v) => set('city', v)} />
        <Field label="ZIP" value={form.zip} onChangeText={(v) => set('zip', v)} keyboardType="number-pad" />
        <RecordField label="Country" kind="countries" value={form.country} onChange={(v) => { set('country', v); set('state', null); }} />
        <RecordField label="State" kind="states" value={form.state} onChange={(v) => set('state', v)} params={{ country_id: form.country?.id }} />
      </Card>
      <SectionTitle title="Emergency contact" />
      <Card>
        <Field label="Name" value={form.emergency_contact_name} onChangeText={(v) => set('emergency_contact_name', v)} />
        <Field label="Phone" value={form.emergency_contact_phone} onChangeText={(v) => set('emergency_contact_phone', v)} keyboardType="phone-pad" />
      </Card>
    </Screen>
  );
}
