import React, { useEffect, useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';
import { Redirect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button, Card, Field, Muted, Screen } from '../components/ui';
import { ApiError, loadLastServer } from '../lib/api';
import { useAuth } from '../lib/auth';
import { clearMeta } from '../lib/meta';
import { space, useTheme } from '../lib/theme';

/** Server preset at build time (.env); in a browser, Odoo on the same host as the page. */
function defaultServer() {
  let server = process.env.EXPO_PUBLIC_ODOO_URL ?? '';
  if (Platform.OS === 'web' && typeof window !== 'undefined' && server) {
    const port = server.match(/:(\d+)$/)?.[1];
    server = `${window.location.protocol}//${window.location.hostname}${port ? `:${port}` : ''}`;
  }
  return { server, database: process.env.EXPO_PUBLIC_ODOO_DB ?? '' };
}

export default function Login() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const { user, login } = useAuth();
  const [server, setServer] = useState('');
  const [database, setDatabase] = useState('');
  const [loginName, setLoginName] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [needTotp, setNeedTotp] = useState(false);
  const [showServer, setShowServer] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadLastServer().then((last) => {
      if (last) {
        setServer(last.server);
        setDatabase(last.database);
        setLoginName(last.login);
        setShowServer(false);
        return;
      }
      const defaults = defaultServer();
      if (defaults.server && defaults.database) {
        setServer(defaults.server);
        setDatabase(defaults.database);
        setShowServer(false);
      }
    });
  }, []);

  if (user) return <Redirect href="/home" />;

  const submit = async () => {
    setError('');
    if (!server || !database || !loginName || !password) {
      setError('Fill in the server, database, login and password.');
      setShowServer(true);
      return;
    }
    try {
      clearMeta();
      await login(server, database, loginName, password, needTotp ? totp : undefined);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'totp_required') {
        setNeedTotp(true);
        setError('');
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: space.sm, marginTop: insets.top + space.xl, marginBottom: space.lg }}>
        <View style={{ width: 76, height: 76, borderRadius: 22, backgroundColor: t.brand, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="business" size={38} color={t.onBrand} />
        </View>
        <Text style={{ color: t.text, fontSize: 26, fontWeight: '800' }}>Rent Manager</Text>
        <Muted>Sign in with your Odoo account</Muted>
      </View>
      <Card style={{ gap: space.md }}>
        {showServer ? (
          <>
            <Field
              label="Server address"
              value={server}
              onChangeText={setServer}
              placeholder="https://erp.yourcompany.com"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              help="The address you open Odoo with in the browser."
            />
            <Field label="Database" value={database} onChangeText={setDatabase} placeholder="odoo20_comm" autoCapitalize="none" autoCorrect={false} />
          </>
        ) : (
          <Pressable onPress={() => setShowServer(true)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="server-outline" size={16} color={t.muted} />
            <Muted style={{ flex: 1 }} >{server.replace(/^https?:\/\//, '')} · {database}</Muted>
            <Text style={{ color: t.brand, fontWeight: '600' }}>Change</Text>
          </Pressable>
        )}
        <Field label="Email / login" value={loginName} onChangeText={setLoginName} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" textContentType="username" />
        <View>
          <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry={!showPassword} textContentType="password" onSubmitEditing={submit} />
          <Pressable onPress={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: 12, bottom: 12 }} hitSlop={10}>
            <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={20} color={t.faint} />
          </Pressable>
        </View>
        {needTotp ? (
          <Field label="Authentication code" value={totp} onChangeText={setTotp} keyboardType="number-pad" maxLength={6} help="Two-factor authentication is on: enter the 6-digit code of your authenticator app." />
        ) : null}
        {error ? (
          <View style={{ backgroundColor: t.tones.danger.bg, borderRadius: 10, padding: space.md }}>
            <Text style={{ color: t.tones.danger.fg }}>{error}</Text>
          </View>
        ) : null}
        <Button title="Sign in" icon="log-in-outline" onPress={submit} />
      </Card>
      <Muted style={{ textAlign: 'center', marginTop: space.md }}>
        Tenants: use the login sent by your property manager. Forgot your password? Reset it from the Odoo login page.
      </Muted>
    </Screen>
  );
}
