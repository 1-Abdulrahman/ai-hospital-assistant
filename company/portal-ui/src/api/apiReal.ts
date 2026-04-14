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

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function getJwt(): string | null {
  return sessionStorage.getItem('portal_jwt');
}

function getPortalSessionId(): string {
  let sid = sessionStorage.getItem('portal_session_id');
  if (!sid) {
    sid = generateUUID();
    sessionStorage.setItem('portal_session_id', sid);
  }
  return sid;
}

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
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw {
      userMessage: 'Unable to reach the backend server. Please check your connection.',
      requestCorrelationId,
    };
  }

  let backendCorrelationId: string | undefined =
    res.headers.get('X-Correlation-Id') || undefined;

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
    if (!res.ok) {
      throw {
        userMessage: `Request failed with status ${res.status}.`,
        requestCorrelationId,
        backendCorrelationId,
      };
    }
    data = {};
  }

  if (!backendCorrelationId && data?.correlationId) {
    backendCorrelationId = data.correlationId;
  }

  if (!res.ok) {
    throw {
      userMessage: data?.message || data?.userMessage || `Request failed with status ${res.status}.`,
      requestCorrelationId,
      backendCorrelationId,
    };
  }

  return {
    data: sanitizeResponse(data) as T,
    requestCorrelationId,
    backendCorrelationId,
  };
}

function mapHealth(raw: any): HealthStatus {
  return {
    status: raw?.status || 'DOWN',
    timestamp: raw?.timestamp || raw?.time,
  };
}

export const apiReal: ApiAdapter = {
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