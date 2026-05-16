import type { ApiAdapter } from './types';
import { apiReal } from './apiReal';

// Modes supported by the portal API layer. "mock" uses local in-memory or
// canned responses; "real" forwards requests to the backend API.
export type ApiMode = 'mock' | 'real';

// LocalStorage key used when persisting a user-selected mode for demos.
const STORAGE_KEY = 'portal_api_mode';

/*
 * resolveApiMode
 *
 * Decide which API mode the application should use. Precedence (highest → lowest):
 * 1. Query string override: `?mock=1` or `?mock=0` for fast manual switching
 * 2. Local storage: persisted user preference set via `setApiMode`
 * 3. Build-time env: `VITE_USE_MOCKS` allows CI/Docker to force a mode
 * 4. Default: `real` (production-safe)
 *
 * Rationale: this ordering makes it easy to demo/mock locally without changing
 * build artifacts, while still allowing an operator to force mocks at deploy
 * time via environment variables.
 */
function resolveApiMode(): ApiMode {
  // Query string override always wins for manual demo switching.
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);

    if (params.get('mock') === '1') return 'mock';
    if (params.get('mock') === '0') return 'real';

    // LocalStorage persistence is next in precedence
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'mock' || stored === 'real') {
      return stored;
    }
  }

  // Build-time override for Docker or explicit local runs.
  if (import.meta.env.VITE_USE_MOCKS === 'true') return 'mock';
  if (import.meta.env.VITE_USE_MOCKS === 'false') return 'real';

  // Final default: real backend mode.
  return 'real';
}

// Cached adapter instance and resolved mode. Keeping these at module scope
// avoids re-resolving mode or re-importing adapters on every call, improving
// runtime performance and keeping a single shared adapter instance.
let cachedAdapter: ApiAdapter | null = null;
let cachedMode: ApiMode | null = null;

// Returns the currently resolved ApiMode (uses cached value when available).
export function getApiMode(): ApiMode {
  if (cachedMode !== null) return cachedMode;
  cachedMode = resolveApiMode();
  return cachedMode;
}

// Helper boolean for quick checks in UI code
export function getIsMockMode(): boolean {
  return getApiMode() === 'mock';
}

/*
 * setApiMode
 *
 * Change the API mode at runtime and persist the choice to localStorage.
 * This clears the cached adapter so the next `getApi()` call will load the
 * adapter appropriate for the new mode (dynamic import for mocks, or the
 * real adapter instance).
 */
export function setApiMode(mode: ApiMode): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, mode);
  }
  cachedMode = mode;
  // Clear cached adapter so the new mode takes effect immediately
  cachedAdapter = null;
}

/*
 * getApi
 *
 * Returns a singleton ApiAdapter implementation matching the resolved mode.
 * - In `mock` mode the adapter is dynamically imported (`apiMock`) so that
 *   mock code is only loaded when needed (keeps prod bundles smaller).
 * - In `real` mode we use the statically imported `apiReal` adapter.
 */
export async function getApi(): Promise<ApiAdapter> {
  if (cachedAdapter) return cachedAdapter;

  if (getApiMode() === 'mock') {
    // Dynamic import keeps mock-only code out of main bundle
    const { apiMock } = await import('./apiMock');
    cachedAdapter = apiMock;
  } else {
    cachedAdapter = apiReal;
  }

  return cachedAdapter;
}