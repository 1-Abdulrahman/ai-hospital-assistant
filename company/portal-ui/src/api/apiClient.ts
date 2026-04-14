import type { ApiAdapter } from './types';
import { apiReal } from './apiReal';

export type ApiMode = 'mock' | 'real';

const STORAGE_KEY = 'portal_api_mode';

function resolveApiMode(): ApiMode {
  // Query string override always wins for manual demo switching.
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);

    if (params.get('mock') === '1') return 'mock';
    if (params.get('mock') === '0') return 'real';

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

let cachedAdapter: ApiAdapter | null = null;
let cachedMode: ApiMode | null = null;

export function getApiMode(): ApiMode {
  if (cachedMode !== null) return cachedMode;
  cachedMode = resolveApiMode();
  return cachedMode;
}

export function getIsMockMode(): boolean {
  return getApiMode() === 'mock';
}

export function setApiMode(mode: ApiMode): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, mode);
  }
  cachedMode = mode;
  cachedAdapter = null;
}

export async function getApi(): Promise<ApiAdapter> {
  if (cachedAdapter) return cachedAdapter;

  if (getApiMode() === 'mock') {
    const { apiMock } = await import('./apiMock');
    cachedAdapter = apiMock;
  } else {
    cachedAdapter = apiReal;
  }

  return cachedAdapter;
}