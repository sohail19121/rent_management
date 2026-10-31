import React from 'react';
import { Text, View } from 'react-native';
import { router } from 'expo-router';

import { AuthImage, Button, Card, confirmAction, ListItem, Muted, Progress, Screen, SectionTitle, type IconName } from '../../components/ui';
import { getSession } from '../../lib/api';
import { isStaff, useAuth, type Role } from '../../lib/auth';
import { space, useTheme } from '../../lib/theme';

const ROLE_LABELS: Record<Role, string> = {
  admin: 'Rent Administrator', accountant: 'Rent Accountant', manager: 'Property Manager', tenant: 'Tenant',
};

export default function More() {
  const t = useTheme();
  const { user, logout } = useAuth();
  if (!user) return null;
  const role = user.role;
  const items: { icon: IconName; title: string; subtitle?: string; href: string; show: boolean }[] = [
    { icon: 'business-outline', title: 'Properties', href: '/properties', show: role === 'admin' || role === 'accountant' },
    { icon: 'home-outline', title: 'Units', subtitle: 'Flats, shops, offices and their status', href: '/unit', show: isStaff(role) },
    { icon: 'people-outline', title: 'Tenants', subtitle: 'KYC, contacts, app access', href: '/tenant', show: isStaff(role) },
    { icon: 'flash-outline', title: 'Meter readings', subtitle: 'Electricity readings and billing', href: '/reading', show: true },
    { icon: 'qr-code-outline', title: 'Scan meter QR', subtitle: 'Enter a reading on site', href: '/meter/scan', show: isStaff(role) },
    { icon: 'checkbox-outline', title: 'My activities', subtitle: 'To-dos assigned to you', href: '/activities', show: isStaff(role) },
    { icon: 'settings-outline', title: 'Rent settings', subtitle: 'Billing days, reminders, electricity rate', href: '/settings', show: role === 'admin' },
    { icon: 'person-circle-outline', title: 'My profile', subtitle: 'Contact details and photo', href: '/profile', show: true },
    { icon: 'key-outline', title: 'Change password', href: '/password', show: true },
  ];
  const profile = user.profile;
  return (
    <Screen>
      <Card style={{ flexDirection: 'row', alignItems: 'center', gap: space.md }} onPress={() => router.push('/profile')}>
        {user.image_url ? (
          <AuthImage path={user.image_url} style={{ width: 56, height: 56, borderRadius: 28 }} />
        ) : (
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: t.brandSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: t.brand, fontSize: 22, fontWeight: '800' }}>{user.name.slice(0, 1)}</Text>
          </View>
        )}
        <View style={{ flex: 1 }}>
          <Text style={{ color: t.text, fontSize: 17, fontWeight: '800' }}>{user.name}</Text>
          <Muted>{ROLE_LABELS[role]} · {user.company?.name}</Muted>
          <Muted>{user.email || user.login}</Muted>
        </View>
      </Card>

      {profile ? (
        <Card>
          <Text style={{ color: t.text, fontWeight: '700' }}>Profile {profile.pct}% complete</Text>
          <Progress value={profile.pct} tone="success" />
          {profile.checks.filter((c: any) => !c.done).map((c: any) => (
            <Muted key={c.label}>• {c.label}{c.hint ? ` — ${c.hint}` : ''}</Muted>
          ))}
        </Card>
      ) : null}

      <SectionTitle title="Menu" />
      {items.filter((i) => i.show).map((item) => (
        <ListItem key={item.title} icon={item.icon} title={item.title} subtitle={item.subtitle} onPress={() => router.push(item.href as any)} />
      ))}

      <Button
        title="Sign out"
        icon="log-out-outline"
        variant="danger"
        style={{ marginTop: space.lg }}
        onPress={() => confirmAction('Sign out', 'You will need your password to sign in again.', logout, 'Sign out')}
      />
      <Muted style={{ textAlign: 'center' }}>{getSession()?.server.replace(/^https?:\/\//, '')} · {getSession()?.database}</Muted>
    </Screen>
  );
}
