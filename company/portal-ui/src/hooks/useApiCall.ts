import { useState, useEffect, useCallback } from 'react';
import { getApi } from '@/api/apiClient';
import type { ApiError } from '@/api/types';

/*
 * useApiCall
 *
 * Generic data-fetching hook used throughout the portal UI. Wraps an API call
 * with loading, error, and data state management. Automatically executes the
 * provided function on mount and whenever deps change.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useApiCall(
 *     (api) => api.getBookings({ page: '1' }),
 *     ['1']  // re-fetch if page changes
 *   );
 *
 * Type Parameter:
 *   T - the shape of the data returned by the API (without wrapper)
 *
 * Parameters:
 *   fn - a function that receives the ApiAdapter and returns Promise<{ data: T }>
 *   deps - dependency array (default []) — when deps change, re-fetch automatically
 */
export function useApiCall<T>(fn: (api: Awaited<ReturnType<typeof getApi>>) => Promise<{ data: T }>, deps: unknown[] = []) {
  // Holds the unwrapped payload from the last successful API call (or null).
  const [data, setData] = useState<T | null>(null);
  // True while a request is in flight; false when idle or complete.
  const [loading, setLoading] = useState(true);
  // Set if the request failed; cleared on successful requests.
  const [error, setError] = useState<ApiError | null>(null);

  /*
   * execute
   *
   * Fetch function that resolves the ApiAdapter, calls the provided fn,
   * and updates state (data, loading, error). Wrapped in useCallback to
   * stabilize its identity for dependency tracking.
   */
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

  // Auto-fetch on mount and whenever execute's dependency list changes.
  // Using execute as a dependency ensures re-fetch when deps change.
  useEffect(() => { execute(); }, [execute]);

  // Return loading/error/data state plus a refetch helper for manual retries.
  return { data, loading, error, refetch: execute };
}
