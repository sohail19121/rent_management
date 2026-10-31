import React, { useState } from 'react';
import { Alert } from 'react-native';
import { router, Stack } from 'expo-router';

import { Button, Card, Field, Muted, run, Screen } from '../components/ui';
import { api } from '../lib/api';

export default function Password() {
  const [oldPassword, setOld] = useState('');
  const [newPassword, setNew] = useState('');
  const [confirm, setConfirm] = useState('');
  const save = async () => {
    if (newPassword !== confirm) {
      Alert.alert('Passwords differ', 'Type the same new password twice.');
      return;
    }
    if (await run(() => api.post('/me/password', { old_password: oldPassword, new_password: newPassword }))) {
      Alert.alert('Password changed', 'Use it next time you sign in, here and on the website.');
      router.back();
    }
  };
  return (
    <Screen footer={<Button title="Change password" icon="key-outline" onPress={save} disabled={!oldPassword || !newPassword} style={{ flex: 1 }} />}>
      <Stack.Screen options={{ title: 'Change password' }} />
      <Card>
        <Field label="Current password" value={oldPassword} onChangeText={setOld} secureTextEntry />
        <Field label="New password" value={newPassword} onChangeText={setNew} secureTextEntry help="At least 8 characters." />
        <Field label="Confirm new password" value={confirm} onChangeText={setConfirm} secureTextEntry />
      </Card>
      <Muted>The same password is used for the Odoo website and this app.</Muted>
    </Screen>
  );
}
