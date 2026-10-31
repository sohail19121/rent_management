import { useEffect, useState } from 'react';

import { api } from './api';

export type SelectionOption = { value: string; label: string };
export type Meta = { selections: Record<string, SelectionOption[]> };

let cache: Meta | null = null;
let pending: Promise<Meta> | null = null;

export function clearMeta() {
  cache = null;
  pending = null;
}

/** Labels of the selection fields (states, categories...), translated by the server, loaded once. */
export function useMeta() {
  const [meta, setMeta] = useState<Meta | null>(cache);
  useEffect(() => {
    if (cache) return;
    pending ??= api.get<Meta>('/meta');
    pending
      .then((m) => {
        cache = m;
        setMeta(m);
      })
      .catch(() => {
        pending = null;
      });
  }, []);
  return meta;
}

export function selection(meta: Meta | null, key: string): SelectionOption[] {
  return meta?.selections[key] ?? [];
}
