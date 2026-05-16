// Core API type definitions for the Portal UI.
//
// These interfaces describe the wire-level shapes used by the UI when
// communicating with the backend and when rendering domain models in the
// admin portal. Keep them lightweight and intentionally focused on the
// fields the UI depends on.

/**
 * Standard envelope returned by API adapter methods.
 * - `data` contains the parsed payload
 * - `requestCorrelationId` is created client-side and echoed for tracing
 * - `backendCorrelationId` is optionally returned by the backend for cross-service traces
 */
export interface ApiResponse<T> {
  data: T;
  requestCorrelationId: string;
  backendCorrelationId?: string;
}

/**
 * Normalized error shape thrown by the API layer for UI consumption. The
 * `userMessage` is safe to display directly to end users.
 */
export interface ApiError {
  userMessage: string;
  requestCorrelationId: string;
  backendCorrelationId?: string;
}

/**
 * Authentication request payload used by the login form.
 */
export interface LoginRequest {
  username: string;
  password: string;
}

/** Lightweight enum of roles returned in the login response. */
export type UserRole = "ADMIN" | "TENANT_ADMIN";

/**
 * Login response from the backend. Contains an access token and optional
 * fields that help the UI decide what to show after authentication.
 */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  role?: UserRole;
  tenantId?: string;
}

/**
 * Health-check status used by small health widgets in the dashboard.
 */
export interface HealthStatus {
  status: 'OK' | 'DEGRADED' | 'DOWN';
  timestamp?: string;
}

/**
 * Aggregated analytics summary used by the dashboard cards. Shapes are
 * intentionally simple to keep the UI logic straightforward.
 */
export interface AnalyticsSummary {
  totalBookings: number;
  bookingFailures: number;
  droppedSessions: number;
  topReasonCodes: { code: string; count: number }[];
  topSpecialties: { specialty: string; count: number }[];
}

/**
 * Booking event model returned by recent activity endpoints. Fields are kept
 * intentionally narrow to what the UI needs for listing and linking.
 */
export interface Booking {
  createdAt: string;
  bookingId: string;
  tenantId: string;
  specialty: string;
  slotDate: string;
  slotTime: string;
  outcome: 'SUCCESS' | 'FAILED';
  reasonCode?: string;
  correlationId?: string; // optional trace key for diagnostics
}

/**
 * Generic paged response for listing endpoints used by the portal.
 */
export interface BookingsPage {
  items: Booking[];
  total: number;
  page: number;
  pageSize: number;
}

export interface Tenant {
  tenantId: string;
  name: string;
  status: string;
  createdAt: string;
}

export interface TenantDetail extends Tenant {
  allowedOrigins?: string[];
  featureFlags?: Record<string, boolean>;
  fhirStatus?: string;
  smtpStatus?: string;
}

/**
 * Audit log entry shape. `safeSummary` is an optional pre-sanitized summary
 * that the UI can render without further transformation.
 */
export interface AuditEntry {
  timestamp: string;
  eventType: string;
  outcome: string;
  reasonCode?: string;
  idempotencyKey?: string;
  correlationId?: string;
  message?: string;
  summary?: string;
  safeSummary?: string;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
  page: number;
  pageSize: number;
}

/**
 * Trace events are used to present request traces and diagnostic timelines
 * in the portal tracing UI.
 */
export interface TraceEvent {
  timestamp: string;
  eventType: string;
  component?: string;
  outcome: string;
  reasonCode?: string;
  message?: string;
  summary?: string;
  safeSummary?: string;
  details?: Record<string, string>;
}

export interface Session {
  sessionId: string;
  startedAt: string;
  lastEventAt: string;
  status: 'COMPLETED' | 'DROPPED' | 'FAILED' | 'ACTIVE';
  finalReasonCode?: string;
  correlationId?: string;
}

export interface SessionsPage {
  items: Session[];
  total: number;
  page: number;
  pageSize: number;
}

export interface NlpStats {
  loadedLabels: number;
  thresholds: Record<string, number>;
  modelName?: string;
  modelVersion?: string;
  lastModelLoadTime?: string;
}

export interface NlpClassification {
  timestamp: string;
  inputSummary?: string;
  predictedLabel: string;
  confidence: number;
  ambiguity: boolean;
}

/**
 * `ApiAdapter` abstracts concrete implementations (real http vs mock) used by
 * the UI to fetch data. Methods return `ApiResponse<T>` so callers receive
 * both payload and tracing metadata consistently.
 */
export interface ApiAdapter {
  login(req: LoginRequest): Promise<ApiResponse<LoginResponse>>;
  getHealth(): Promise<ApiResponse<HealthStatus>>;
  getFhirStatus(): Promise<ApiResponse<HealthStatus>>;
  getAnalyticsSummary(from: string, to: string): Promise<ApiResponse<AnalyticsSummary>>;
  getRecentBookings(limit?: number): Promise<ApiResponse<Booking[]>>;
  getBookings(params: Record<string, string>): Promise<ApiResponse<BookingsPage>>;
  getTenants(): Promise<ApiResponse<Tenant[]>>;
  getTenantDetail(tenantId: string): Promise<ApiResponse<TenantDetail>>;
  getAuditLogs(params: Record<string, string>): Promise<ApiResponse<AuditPage>>;
  getTracesByCorrelationId(correlationId: string): Promise<ApiResponse<TraceEvent[]>>;
  getTracesBySessionId(sessionId: string): Promise<ApiResponse<TraceEvent[]>>;
  getSessions(params: Record<string, string>): Promise<ApiResponse<SessionsPage>>;
  getNlpStats(): Promise<ApiResponse<NlpStats>>;
  getNlpRecent(limit?: number): Promise<ApiResponse<NlpClassification[]>>;
}
