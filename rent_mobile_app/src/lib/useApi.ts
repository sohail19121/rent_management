import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { api, ApiError } from './api';

/**
 * Load an API path, reload it whenever the screen comes back into focus (so a list shows the
 * changes made on a detail screen) and on pull-to-refresh.
 */
export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const pathRef = useRef(path);

  const load = useCallback(async (mode: 'refresh' | 'silent' = 'silent') => {
    const current = pathRef.current;
    if (!current) return;
    if (mode === 'refresh') setRefreshing(true);
    try {
      const result = await api.get<T>(current);
      if (pathRef.current === current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (pathRef.current === current) setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      if (pathRef.current === current) setLoadedPath(current);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    pathRef.current = path;
    if (!path) return;
    let alive = true;
    api
      .get<T>(path)
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e : new ApiError(String(e), 0)))
      .finally(() => alive && setLoadedPath(path));
    return () => {
      alive = false;
    };
  }, [path]);

  const first = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (first.current) {
        first.current = false;
        return;
      }
      load();
    }, [load]),
  );

  return {
    data,
    setData,
    error,
    loading: !!path && loadedPath !== path,
    refreshing,
    reload: () => load('silent'),
    refresh: () => load('refresh'),
  };
}

/** Paginated list with search and filters; loads more on scroll. */
export function useList<T = any>(basePath: string, params: Record<string, string | number | undefined | null>) {
  const query = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  const path = `${basePath}${basePath.includes('?') ? '&' : '?'}${query}`;
  const result = useApi<{ items: T[]; total: number; limit: number; offset: number }>(path);
  // Extra pages belong to the first page they were loaded after: a reload drops them.
  const [pages, setPages] = useState<{ base: unknown; items: T[] }>({ base: null, items: [] });
  const [loadingMore, setLoadingMore] = useState(false);

  const more = useMemo(() => (pages.base === result.data ? pages.items : []), [pages, result.data]);
  const items = [...(result.data?.items ?? []), ...more];
  const total = result.data?.total ?? 0;

  const loadMore = useCallback(async () => {
    if (loadingMore || !result.data || items.length >= total) return;
    const base = result.data;
    setLoadingMore(true);
    try {
      const next = await api.get<{ items: T[] }>(`${path}&offset=${items.length}`);
      setPages({ base, items: [...more, ...next.items] });
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, result.data, items.length, total, path, more]);

  return { ...result, items, total, loadMore, loadingMore };
}

export function useDebounced<T>(value: T, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/**
 * State initialised from a route parameter, that follows the parameter when another screen
 * navigates here with a new value (e.g. a dashboard tile opening a tab with a filter).
 */
export function useParamState(param: string | undefined, fallback: string) {
  const [value, setValue] = useState(param ?? fallback);
  const [lastParam, setLastParam] = useState(param);
  if (param !== lastParam) {
    setLastParam(param);
    if (param !== undefined) setValue(param);
  }
  return [value, setValue] as const;
}
