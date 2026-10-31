import React, { useEffect, useState } from 'react';
import { router, Stack, useLocalSearchParams } from 'expo-router';

import {
  Button, Card, choosePhoto, Field, Loading, Muted, NumberField, PhotoStrip, RecordField, run, Screen, SectionTitle, SelectField,
  type Photo,
} from '../../components/ui';
import { api } from '../../lib/api';
import { isStaff, useAuth } from '../../lib/auth';
import { selection, useMeta } from '../../lib/meta';

export default function MaintenanceForm() {
  const params = useLocalSearchParams<{ id?: string; unit_id?: string; unit_name?: string; lease_id?: string }>();
  const id = params.id;
  const { user } = useAuth();
  const staff = isStaff(user?.role);
  const meta = useMeta();
  const [loading, setLoading] = useState(!!id || !staff);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [leases, setLeases] = useState<{ value: string; label: string }[]>([]);
  const [form, setForm] = useState<any>({
    category: 'other',
    priority: '1',
    charge_to: 'owner',
    unit: params.unit_id ? { id: Number(params.unit_id), name: params.unit_name } : null,
    lease_id: params.lease_id,
  });
  const set = (key: string, value: any) => setForm((f: any) => ({ ...f, [key]: value }));

  useEffect(() => {
    if (id) {
      api.get(`/maintenance/${id}`).then((m) => {
        setForm(m);
        setLoading(false);
      });
    } else if (!staff) {
      // Tenants report on one of their running leases.
      api.get('/leases?state=running').then((r) => {
        const options = r.items.map((l: any) => ({ value: String(l.id), label: `${l.unit?.name} (${l.name})` }));
        setLeases(options);
        if (options.length) set('lease_id', params.lease_id ?? options[0].value);
        setLoading(false);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, staff]);

  if (loading) return <Loading />;

  const save = async () => {
    const body: any = staff
      ? {
          unit_id: form.unit?.id, category: form.category, priority: form.priority,
          assigned_to: form.assigned_to?.id ?? false, vendor_id: form.vendor?.id ?? false,
          cost: form.cost || 0, charge_to: form.charge_to,
        }
      : { lease_id: Number(form.lease_id), category: form.category, priority: form.priority };
    if (!id || form.description !== undefined) body.description = form.description;
    if (photos.length) body.photos = photos.map((p) => p.base64);
    const saved = await run(() => (id ? api.put(`/maintenance/${id}`, body) : api.post('/maintenance', body)));
    if (saved) {
      if (id) router.back();
      else router.replace(`/maintenance/${saved.id}`);
    }
  };

  if (!staff && !leases.length) {
    return (
      <Screen>
        <Stack.Screen options={{ title: 'Report a problem' }} />
        <Muted>You need a running lease to report a problem.</Muted>
      </Screen>
    );
  }

  return (
    <Screen footer={<Button title={id ? 'Save' : staff ? 'Create request' : 'Send to my manager'} icon="send" onPress={save} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: id ? `Edit ${form.name}` : staff ? 'New maintenance request' : 'Report a problem' }} />
      <Card>
        {staff ? (
          <RecordField label="Unit" kind="units" value={form.unit} onChange={(v) => set('unit', v)} required clearable={false} />
        ) : leases.length > 1 ? (
          <SelectField label="Home" value={form.lease_id} options={leases} onChange={(v) => set('lease_id', v)} required />
        ) : (
          <Muted>{leases[0]?.label}</Muted>
        )}
        <SelectField label="Category" value={form.category} options={selection(meta, 'maintenance_category')} onChange={(v) => set('category', v)} required />
        <SelectField label="Priority" value={form.priority} options={selection(meta, 'maintenance_priority')} onChange={(v) => set('priority', v)} />
        <Field label="What is the problem?" value={form.description} onChangeText={(v) => set('description', v)} multiline required={!staff} placeholder="The kitchen tap is leaking since yesterday…" />
      </Card>
      <SectionTitle title="Photos" />
      <PhotoStrip photos={photos} onAdd={() => choosePhoto((p) => setPhotos((list) => [...list, p]))} onRemove={(i) => setPhotos((list) => list.filter((_, j) => j !== i))} />
      {staff ? (
        <>
          <SectionTitle title="Work" />
          <Card>
            <RecordField label="Assigned to" kind="users" value={form.assigned_to} onChange={(v) => set('assigned_to', v)} />
            <RecordField label="Vendor" kind="vendors" value={form.vendor} onChange={(v) => set('vendor', v)} />
            <NumberField label="Cost" value={form.cost} onChange={(v) => set('cost', v)} />
            <SelectField label="Charge to" value={form.charge_to} options={selection(meta, 'charge_to')} onChange={(v) => set('charge_to', v)} help="Charged to the tenant: an invoice is posted when the request is done." />
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
