import type {
  ApiAdapter,
  ApiResponse,
  LoginResponse,
  HealthStatus,
  AnalyticsSummary,
  Booking,
  BookingsPage,
  Tenant,
  TenantDetail,
  AuditPage,
  TraceEvent,
  Session,
  SessionsPage,
  NlpStats,
  NlpClassification,
} from './types';
import { generateUUID } from '@/lib/uuid';
import { sanitizeResponse } from '@/lib/sanitize';
import { getEffectiveTenantId } from './authState';

// Base URL for backend API requests. Allows override via Vite env for local
// development; falls back to localhost for convenience when running the API
// locally (e.g., `make run` or `docker-compose up`).
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Retrieve the current JWT stored in sessionStorage (if any).
// Kept in a small helper to make replacement/testing easier.
function getJwt(): string | null {
  return sessionStorage.getItem('portal_jwt');
}

/*
 * getPortalSessionId
 *
 * Each browser session should have a stable lightweight session identifier
 * used for tracing and analytics. We persist it in sessionStorage so it resets
 * when the browser/tab is closed but remains stable across reloads.
 */
function getPortalSessionId(): string {
  let sid = sessionStorage.getItem('portal_session_id');
  if (!sid) {
    sid = generateUUID();
    sessionStorage.setItem('portal_session_id', sid);
  }
  return sid;
}

/*
 * request
 *
 * Low-level fetch wrapper used by the portal to communicate with the backend
 * API. Responsibilities:
 * - Build standard headers (content-type, correlation id, tenant, session)
 * - Optionally attach the Authorization header when a JWT is present
 * - Handle network errors and surface a user-friendly `userMessage`
 * - Parse JSON responses, normalize correlation IDs, and sanitize output
 * - Throw well-shaped errors for non-2xx responses so callers can handle them
 *
 * The wrapper also attaches two correlation identifiers:
 * - `X-Correlation-Id` sent to the backend to tag the request
 * - `backendCorrelationId` returned from the backend (if present) for
 *   cross-service tracing.
 */
async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  skipAuth = false,
): Promise<ApiResponse<T>> {
  const requestCorrelationId = generateUUID();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Correlation-Id': requestCorrelationId,
    'X-Tenant-Id': getEffectiveTenantId(),
    'X-Session-Id': getPortalSessionId(),
  };

  const jwt = getJwt();
  if (jwt && !skipAuth) {
    headers['Authorization'] = `Bearer ${jwt}`;
  }

  let res: Response;
  try {
    // Perform the fetch against the configured backend base URL
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    // Network-level failure (DNS, connection refused, CORS blocked, etc.)
    throw {
      userMessage: 'Unable to reach the backend server. Please check your connection.',
      requestCorrelationId,
    };
  }

  // Try to read any correlation id the backend echoed back for tracing
  let backendCorrelationId: string | undefined =
    res.headers.get('X-Correlation-Id') || undefined;

  // Handle authentication failures in a consistent way for the UI
  if (res.status === 401) {
    sessionStorage.removeItem('portal_jwt');
    throw {
      userMessage: 'Session expired. Please log in again.',
      requestCorrelationId,
      backendCorrelationId,
    };
  }

  let data: any;
  try {
    data = await res.json();
  } catch {
    // If parsing failed and the response was an error, surface a helpful
    // message to the UI; otherwise treat it as an empty successful payload.
    if (!res.ok) {
      throw {
        userMessage: `Request failed with status ${res.status}.`,
        requestCorrelationId,
        backendCorrelationId,
      };
    }
    data = {};
  }

  // Some backends include the correlation id in the JSON body; prefer the
  // header but fall back to any body-provided id for complete tracing info.
  if (!backendCorrelationId && data?.correlationId) {
    backendCorrelationId = data.correlationId;
  }

  // Non-2xx responses are thrown as structured errors to the caller.
  if (!res.ok) {
    throw {
      userMessage: data?.message || data?.userMessage || `Request failed with status ${res.status}.`,
      requestCorrelationId,
      backendCorrelationId,
    };
  }

  // Sanitize the backend payload to remove any unexpected or unsafe fields
  // before exposing it to the rest of the UI layer.
  return {
    data: sanitizeResponse(data) as T,
    requestCorrelationId,
    backendCorrelationId,
  };
}

// Lightweight mapper for health endpoints to keep UI code stable even if the
// backend shape changes slightly (e.g. `time` vs `timestamp`).
function mapHealth(raw: any): HealthStatus {
  return {
    status: raw?.status || 'DOWN',
    timestamp: raw?.timestamp || raw?.time,
  };
}

/*
 * apiReal
 *
 * Concrete `ApiAdapter` implementation that forwards to the real backend
 * using HTTP requests. Each method returns the same `ApiResponse<T>` shape
 * as the rest of the application expects (including correlation ids).
 *
 * Note: Keep this file focused on thin request wiring. Business logic and
 * transformation belong in higher-level services or components.
 */
export const apiReal: ApiAdapter = {
  // Authentication: returns a JWT and user/session info. `skipAuth` is true
  // because login naturally occurs before a JWT is available.
  login: (req) => request<LoginResponse>('POST', '/auth/login', req, true),

  async getHealth() {
    const res = await request<any>('GET', '/health');
    return { ...res, data: mapHealth(res.data) };
  },

  async getFhirStatus() {
    const res = await request<any>('GET', '/integrations/fhir/status');
    return { ...res, data: mapHealth(res.data) };
  },

  getAnalyticsSummary: (from, to) =>
    request<AnalyticsSummary>('GET', `/portal/analytics/summary?from=${from}&to=${to}`),

  getRecentBookings: (limit = 10) =>
    request<Booking[]>('GET', `/portal/bookings/recent?limit=${limit}`),

  getBookings: (params) => {
    const qs = new URLSearchParams(params).toString();
    return request<BookingsPage>('GET', `/portal/bookings?${qs}`);
  },

  getTenants: () => request<Tenant[]>('GET', '/portal/tenants'),
  getTenantDetail: (id) => request<TenantDetail>('GET', `/portal/tenants/${id}`),
  getAuditLogs: (params) => {
    const qs = new URLSearchParams(params).toString();
    return request<AuditPage>('GET', `/portal/audit?${qs}`);
  },

  getTracesByCorrelationId: (id) =>
    request<TraceEvent[]>('GET', `/portal/traces/${id}`),

  getTracesBySessionId: (id) =>
    request<TraceEvent[]>('GET', `/portal/traces/by-session/${id}`),

  getSessions: (params) => {
    const qs = new URLSearchParams(params).toString();
    return request<SessionsPage>('GET', `/portal/sessions?${qs}`);
  },

  getNlpStats: () => request<NlpStats>('GET', '/portal/nlp/stats'),
  getNlpRecent: (limit = 20) =>
    request<NlpClassification[]>('GET', `/portal/nlp/recent?limit=${limit}`),
};