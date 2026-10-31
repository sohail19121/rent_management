import { getCurrentUser } from './currentUser';

const SYMBOLS: Record<string, string> = { INR: '₹', USD: '$', EUR: '€', GBP: '£', AED: 'AED ', SAR: 'SAR ' };

export function money(amount: number | null | undefined, currency?: string, compact = false) {
  const value = Number(amount ?? 0);
  const company = getCurrentUser()?.company;
  const code = currency || company?.currency || '';
  const symbol = (code && code === company?.currency ? company?.symbol : SYMBOLS[code]) ?? `${code} `;
  const after = code === company?.currency && company?.position === 'after';
  let text: string;
  if (compact && Math.abs(value) >= 1000) {
    const units: [number, string][] = code === 'INR'
      ? [[1e7, 'Cr'], [1e5, 'L'], [1e3, 'k']]
      : [[1e9, 'B'], [1e6, 'M'], [1e3, 'k']];
    const [div, suffix] = units.find(([d]) => Math.abs(value) >= d)!;
    text = `${(value / div).toFixed(1).replace(/\.0$/, '')}${suffix}`;
  } else {
    text = value.toLocaleString(code === 'INR' ? 'en-IN' : 'en-US', {
      minimumFractionDigits: compact ? 0 : 2,
      maximumFractionDigits: compact ? 0 : 2,
    });
  }
  return after ? `${text} ${symbol.trim()}` : `${symbol}${text}`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function parseDate(value?: string | null) {
  if (!value) return null;
  const [y, m, d] = value.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function date(value?: string | null) {
  const d = parseDate(value);
  return d ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}` : '—';
}

export function datetime(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value.replace(' ', 'T') + 'Z');
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function toIsoDate(d: Date) {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function today() {
  return toIsoDate(new Date());
}

export function num(value: number | null | undefined, digits = 2) {
  return Number(value ?? 0).toLocaleString('en-IN', { maximumFractionDigits: digits });
}

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'brand';

export const STATE_TONES: Record<string, Tone> = {
  // leases
  draft: 'neutral', confirmed: 'info', active: 'success', expiring: 'warning', expired: 'neutral',
  terminated: 'neutral', renewed: 'info', cancelled: 'neutral',
  // units
  vacant: 'warning', reserved: 'info', occupied: 'success', under_maintenance: 'danger',
  // maintenance
  new: 'info', in_progress: 'warning', done: 'success',
  // readings
  invoiced: 'success',
  // invoices
  paid: 'success', due: 'info', overdue: 'danger', partial: 'warning', refund: 'neutral', posted: 'info',
  cancel: 'neutral',
  // deposit
  pending: 'warning', received: 'success', partially_refunded: 'info', refunded: 'neutral',
};

export const INVOICE_STATUS_LABEL: Record<string, string> = {
  paid: 'Paid', due: 'Due', overdue: 'Overdue', partial: 'Partly paid', refund: 'Credit note', draft: 'Draft',
  cancel: 'Cancelled',
};

export const PRIORITY_TONE: Record<string, Tone> = { '0': 'neutral', '1': 'info', '2': 'warning', '3': 'danger' };
