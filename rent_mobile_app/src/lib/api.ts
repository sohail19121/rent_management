import * as SecureStore from 'expo-secure-store';
import * as Sharing from 'expo-sharing';
import { File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

export const API_PREFIX = '/rent/api/v1';
const SESSION_KEY = 'rent_session';

export type Session = {
  server: string; // e.g. https://erp.example.com
  database: string; // X-Odoo-Database
  token: string;
};

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code = 'error') {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let current: Session | null = null;
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export function getSession() {
  return current;
}

async function storeGet(key: string) {
  if (Platform.OS === 'web') return globalThis.localStorage?.getItem(key) ?? null;
  return SecureStore.getItemAsync(key);
}

async function storeSet(key: string, value: string | null) {
  if (Platform.OS === 'web') {
    if (value === null) globalThis.localStorage?.removeItem(key);
    else globalThis.localStorage?.setItem(key, value);
    return;
  }
  if (value === null) await SecureStore.deleteItemAsync(key);
  else await SecureStore.setItemAsync(key, value);
}

export async function loadSession(): Promise<Session | null> {
  try {
    const raw = await storeGet(SESSION_KEY);
    current = raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    current = null;
  }
  return current;
}

export async function saveSession(session: Session | null) {
  current = session;
  await storeSet(SESSION_KEY, session ? JSON.stringify(session) : null);
}

/** Last server/database used, to prefill the login form even after logout. */
export async function loadLastServer(): Promise<{ server: string; database: string; login: string } | null> {
  const raw = await storeGet('rent_last_server');
  return raw ? JSON.parse(raw) : null;
}

export async function saveLastServer(value: { server: string; database: string; login: string }) {
  await storeSet('rent_last_server', JSON.stringify(value));
}

export function normalizeServer(url: string) {
  let server = url.trim().replace(/\/+$/, '');
  if (server && !/^https?:\/\//i.test(server)) server = `https://${server}`;
  return server;
}

// Browsers may not send X-Odoo-Database: Odoo's CORS preflight does not allow it. The web
// version therefore needs a server limited to one database (--db-filter); native apps send it.
function databaseHeader(session: Session): Record<string, string> {
  return Platform.OS === 'web' ? {} : { 'X-Odoo-Database': session.database };
}

export function authHeaders(session: Session | null = current): Record<string, string> {
  if (!session) return {};
  return { Authorization: `Bearer ${session.token}`, ...databaseHeader(session) };
}

export function absoluteUrl(path: string, session: Session | null = current) {
  if (/^https?:\/\//.test(path)) return path;
  return `${session?.server ?? ''}${path.startsWith('/rent/') ? '' : API_PREFIX}${path}`;
}

type RequestOptions = { body?: unknown; session?: Session | null; timeoutMs?: number };

export async function request<T = any>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const session = options.session === undefined ? current : options.session;
  if (!session) throw new ApiError('Not logged in', 401, 'no_session');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 30000);
  let response: Response;
  try {
    response = await fetch(absoluteUrl(path, session), {
      method,
      headers: {
        Accept: 'application/json',
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(session.token ? authHeaders(session) : databaseHeader(session)),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (error: any) {
    throw new ApiError(
      error?.name === 'AbortError'
        ? 'The server did not answer in time. Check your connection.'
        : 'Cannot reach the server. Check the address and your connection.',
      0,
      'network',
    );
  } finally {
    clearTimeout(timer);
  }
  const text = await response.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    if (response.status === 401 && session.token && data?.error !== 'totp_required' && onUnauthorized) {
      onUnauthorized();
    }
    const message =
      data?.message ||
      (response.status === 404 ? 'Not found. Is the Rent Mobile API module installed on the server?' : `Server error (${response.status})`);
    throw new ApiError(message, response.status, data?.error || 'error');
  }
  return data as T;
}

export const api = {
  get: <T = any>(path: string) => request<T>('GET', path),
  post: <T = any>(path: string, body: unknown = {}) => request<T>('POST', path, { body }),
  put: <T = any>(path: string, body: unknown = {}) => request<T>('PUT', path, { body }),
  del: <T = any>(path: string) => request<T>('DELETE', path),
};

export async function login(server: string, database: string, loginName: string, password: string, totp?: string) {
  const session: Session = { server: normalizeServer(server), database: database.trim(), token: '' };
  const result = await request<{ token: string; user: any }>('POST', '/auth/login', {
    session,
    body: { login: loginName.trim(), password, totp, device: `${Platform.OS} app` },
  });
  const saved = { ...session, token: result.token };
  await saveSession(saved);
  await saveLastServer({ server: session.server, database: session.database, login: loginName.trim() });
  return result.user;
}

export async function logout() {
  try {
    if (current) await request('POST', '/auth/logout', { timeoutMs: 5000 });
  } catch {
    // the token is forgotten anyway
  }
  await saveSession(null);
}

/** Download a PDF (or any file) from the API and open the share sheet / viewer. */
export async function downloadAndShare(path: string, filename: string) {
  const session = current;
  if (!session) throw new ApiError('Not logged in', 401);
  const url = absoluteUrl(path, session);
  if (Platform.OS === 'web') {
    const response = await fetch(url, { headers: authHeaders(session) });
    if (!response.ok) throw new ApiError(`Download failed (${response.status})`, response.status);
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    return;
  }
  const safe = filename.replace(/[^\w\-. ]/g, '_');
  const target = new File(Paths.cache, safe);
  if (target.exists) target.delete();
  const file = await File.downloadFileAsync(url, target, { headers: authHeaders(session), idempotent: true });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf', dialogTitle: filename, UTI: 'com.adobe.pdf' });
  }
}
