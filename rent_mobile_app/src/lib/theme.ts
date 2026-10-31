import { useColorScheme } from 'react-native';

import type { Tone } from './format';

const light = {
  bg: '#F5F4F7',
  card: '#FFFFFF',
  cardAlt: '#FAF9FB',
  text: '#1F1D24',
  muted: '#6B6775',
  faint: '#9C98A6',
  border: '#E6E3EA',
  brand: '#714B67',
  brandSoft: '#F1EAF0',
  onBrand: '#FFFFFF',
  input: '#FFFFFF',
  tones: {
    neutral: { bg: '#EEEDF1', fg: '#5B5766' },
    info: { bg: '#E3EEFB', fg: '#1F5FAD' },
    success: { bg: '#E2F4EA', fg: '#1C7A47' },
    warning: { bg: '#FDF1DC', fg: '#9A5B00' },
    danger: { bg: '#FBE5E5', fg: '#B42525' },
    brand: { bg: '#F1EAF0', fg: '#714B67' },
  } as Record<Tone, { bg: string; fg: string }>,
};

const dark: typeof light = {
  bg: '#141317',
  card: '#1E1C22',
  cardAlt: '#25232A',
  text: '#F2F0F5',
  muted: '#A9A4B3',
  faint: '#7B7684',
  border: '#34313A',
  brand: '#C49BBB',
  brandSoft: '#3A2B37',
  onBrand: '#1A1418',
  input: '#25232A',
  tones: {
    neutral: { bg: '#2F2D34', fg: '#C9C5D1' },
    info: { bg: '#1D3047', fg: '#8DBBF0' },
    success: { bg: '#173526', fg: '#7FD3A3' },
    warning: { bg: '#3B2D12', fg: '#F2C46B' },
    danger: { bg: '#40191B', fg: '#F29B9B' },
    brand: { bg: '#3A2B37', fg: '#E0B9D6' },
  },
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
