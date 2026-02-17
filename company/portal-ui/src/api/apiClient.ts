import type { ApiAdapter } from './types';
import { apiReal } from './apiReal';

function isMockMode(): boolean {
  if (import.meta.env.VITE_USE_MOCKS === 'true') return true;
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.get('mock') === '1') return true;
  }
  // In dev mode without a real backend, default to mocks for preview
  if (import.meta.env.DEV) return true;
  return false;
}

let cachedAdapter: ApiAdapter | null = null;
let cachedIsMock: boolean | null = null;

export function getIsMockMode(): boolean {
  if (cachedIsMock !== null) return cachedIsMock;
  cachedIsMock = isMockMode();
  return cachedIsMock;
}

export async function getApi(): Promise<ApiAdapter> {
  if (cachedAdapter) return cachedAdapter;
  if (getIsMockMode()) {
    const { apiMock } = await import('./apiMock');
    cachedAdapter = apiMock;
  } else {
    cachedAdapter = apiReal;
  }
  return cachedAdapter;
}
