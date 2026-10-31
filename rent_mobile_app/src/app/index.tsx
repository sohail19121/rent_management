import React from 'react';
import { Redirect } from 'expo-router';

import { Button, ErrorView, Loading } from '../components/ui';
import { useAuth } from '../lib/auth';
import { View } from 'react-native';

export default function Index() {
  const { ready, user, offline, retry, logout } = useAuth();
  if (!ready) return <Loading />;
  if (offline && !user) {
    return (
      <View style={{ flex: 1 }}>
        <ErrorView error={new Error('Cannot reach the Odoo server. Check your connection.')} onRetry={retry} />
        <Button title="Sign out" variant="ghost" onPress={logout} style={{ marginBottom: 40 }} />
      </View>
    );
  }
  return <Redirect href={user ? '/home' : '/login'} />;
}
