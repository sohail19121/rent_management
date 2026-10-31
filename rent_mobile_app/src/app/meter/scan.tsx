import React, { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { router, Stack } from 'expo-router';
import { CameraView, useCameraPermissions } from 'expo-camera';

import { Button, Card, Field, Muted, RecordField, Screen, SectionTitle } from '../../components/ui';
import { api } from '../../lib/api';
import { space, useTheme } from '../../lib/theme';

/** Scan the QR label stuck on a meter to open its reading form. */
export default function MeterScan() {
  const t = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [error, setError] = useState('');
  const [code, setCode] = useState('');
  const busy = useRef(false);

  const open = async (value: string) => {
    if (busy.current || !value) return;
    busy.current = true;
    try {
      const entry = await api.post('/meter/scan', { code: value });
      router.replace(`/meter/${entry.unit.id}`);
    } catch (e: any) {
      setError(e.message);
      setTimeout(() => (busy.current = false), 2000);
    }
  };

  return (
    <Screen>
      <Stack.Screen options={{ title: 'Scan meter' }} />
      {!permission ? null : permission.granted ? (
        <View style={{ height: 340, borderRadius: 20, overflow: 'hidden', backgroundColor: '#000' }}>
          <CameraView
            style={{ flex: 1 }}
            facing="back"
            barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onBarcodeScanned={({ data }) => open(data)}
          />
          <View pointerEvents="none" style={{ position: 'absolute', top: 70, left: 60, right: 60, bottom: 70, borderWidth: 3, borderColor: '#fff', borderRadius: 18, opacity: 0.8 }} />
        </View>
      ) : (
        <Card>
          <Text style={{ color: t.text, fontWeight: '700' }}>Camera access needed</Text>
          <Muted>The camera reads the QR code printed on the meter label.</Muted>
          <Button title="Allow camera" icon="camera-outline" onPress={requestPermission} />
        </Card>
      )}
      <Muted style={{ textAlign: 'center' }}>Point the camera at the QR label of the meter.</Muted>
      {error ? <Text style={{ color: t.tones.danger.fg, textAlign: 'center' }}>{error}</Text> : null}

      <SectionTitle title="No label?" />
      <Card style={{ gap: space.md }}>
        <RecordField label="Pick the unit" kind="units" value={null} clearable={false} onChange={(u) => u && router.replace(`/meter/${u.id}`)} />
        <Field label="Or paste the QR link" value={code} onChangeText={setCode} autoCapitalize="none" />
        <Button title="Open" variant="secondary" onPress={() => { busy.current = false; open(code); }} disabled={!code} />
      </Card>
    </Screen>
  );
}
