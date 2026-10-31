import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import * as Api from './api';
import { setCurrentUser } from './currentUser';

export type Role = 'admin' | 'accountant' | 'manager' | 'tenant';

export type User = {
  id: number;
  name: string;
  login: string;
  email: string;
  phone: string;
  role: Role;
  partner_id: number;
  image_url: string | null;
  company: { id: number; name: string; currency: string; symbol: string; position: 'before' | 'after'; color: string };
  [key: string]: any;
};

type AuthState = {
  ready: boolean;
  offline: boolean;
  retry: () => Promise<void>;
  user: User | null;
  login: (server: string, database: string, login: string, password: string, totp?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [offline, setOffline] = useState(false);

  const logout = useCallback(async () => {
    await Api.logout();
    setUser(null);
  }, []);

  // Restore the saved session at startup (and on "retry" when the server was unreachable).
  const resume = useCallback(async (session: Api.Session | null) => {
    setOffline(false);
    if (session) {
      try {
        setUser(await Api.api.get<User>('/me'));
      } catch (error) {
        if (error instanceof Api.ApiError && error.status === 0) {
          // Server unreachable at startup: keep the session and let the user retry.
          setOffline(true);
        } else {
          await Api.saveSession(null);
        }
      }
    }
    setReady(true);
  }, []);

  useEffect(() => {
    Api.setUnauthorizedHandler(() => {
      // Token expired or revoked in Odoo (Preferences > Account Security): back to the login screen.
      Api.saveSession(null).finally(() => setUser(null));
    });
    Api.loadSession().then(resume);
  }, [resume]);

  useEffect(() => setCurrentUser(user), [user]);

  const value = useMemo<AuthState>(
    () => ({
      ready,
      offline,
      retry: () => Api.loadSession().then(resume),
      user,
      login: async (server, database, login, password, totp) => {
        await Api.login(server, database, login, password, totp);
        setUser(await Api.api.get<User>('/me'));
      },
      logout,
      refreshUser: async () => setUser(await Api.api.get<User>('/me')),
    }),
    [ready, offline, resume, user, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth outside AuthProvider');
  return context;
}

export const isStaff = (role?: Role | null) => role === 'admin' || role === 'accountant' || role === 'manager';
export const canBill = (role?: Role | null) => role === 'admin' || role === 'accountant';
