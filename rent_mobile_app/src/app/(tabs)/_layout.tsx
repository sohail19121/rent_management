import React from 'react';
import { Redirect } from 'expo-router';
import { Tabs } from 'expo-router/tabs';
import { Ionicons } from '@expo/vector-icons';

import { useAuth, type Role } from '../../lib/auth';
import { useTheme } from '../../lib/theme';

type TabDef = { name: string; title: string; icon: React.ComponentProps<typeof Ionicons>['name']; roles: Role[]; tenantTitle?: string };

// Each role gets the five tabs it uses most; everything else is under "More".
const TABS: TabDef[] = [
  { name: 'home', title: 'Dashboard', tenantTitle: 'Home', icon: 'grid-outline', roles: ['admin', 'accountant', 'manager', 'tenant'] },
  { name: 'properties', title: 'Properties', icon: 'business-outline', roles: ['manager'] },
  { name: 'invoices', title: 'Invoices', tenantTitle: 'Payments', icon: 'receipt-outline', roles: ['admin', 'accountant', 'tenant'] },
  { name: 'leases', title: 'Leases', tenantTitle: 'My Lease', icon: 'document-text-outline', roles: ['admin', 'accountant', 'manager', 'tenant'] },
  { name: 'maintenance', title: 'Maintenance', tenantTitle: 'Requests', icon: 'construct-outline', roles: ['admin', 'accountant', 'manager', 'tenant'] },
  { name: 'more', title: 'More', tenantTitle: 'Profile', icon: 'ellipsis-horizontal-circle-outline', roles: ['admin', 'accountant', 'manager', 'tenant'] },
];

export default function TabsLayout() {
  const t = useTheme();
  const { user } = useAuth();
  if (!user) return <Redirect href="/login" />;
  const role = user.role;
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: t.brand,
        tabBarInactiveTintColor: t.faint,
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border },
        headerStyle: { backgroundColor: t.card },
        headerTitleStyle: { color: t.text, fontWeight: '800' },
        sceneStyle: { backgroundColor: t.bg },
      }}
    >
      {TABS.map((tab) => {
        const title = role === 'tenant' && tab.tenantTitle ? tab.tenantTitle : tab.title;
        return (
          <Tabs.Screen
            key={tab.name}
            name={tab.name}
            options={{
              title,
              href: tab.roles.includes(role) ? undefined : null,
              tabBarIcon: ({ color, size }) => <Ionicons name={tab.icon} size={size} color={color as string} />,
              headerTitle: tab.name === 'home' ? (role === 'tenant' ? `Hi, ${user.name.split(' ')[0]}` : user.company?.name ?? 'Dashboard') : title,
            }}
          />
        );
      })}
    </Tabs>
  );
}

