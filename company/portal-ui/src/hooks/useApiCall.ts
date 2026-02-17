import { useState, useEffect, useCallback } from 'react';
import { getApi } from '@/api/apiClient';
import type { ApiError } from '@/api/types';

export function useApiCall<T>(fn: (api: Awaited<ReturnType<typeof getApi>>) => Promise<{ data: T }>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = await getApi();
      const res = await fn(api);
      setData(res.data);
    } catch (e: any) {
      setError(e as ApiError);
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => { execute(); }, [execute]);

  return { data, loading, error, refetch: execute };
}
