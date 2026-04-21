export interface ApiResponse<T> {
  data: T;
  requestCorrelationId: string;
  backendCorrelationId?: string;
}

export interface ApiError {
  userMessage: string;
  requestCorrelationId: string;
  backendCorrelationId?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export type UserRole = "ADMIN" | "TENANT_ADMIN";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  role?: UserRole;
  tenantId?: string;
}

export interface HealthStatus {
  status: 'OK' | 'DEGRADED' | 'DOWN';
  timestamp?: string;
}

export interface AnalyticsSummary {
  totalBookings: number;
  bookingFailures: number;
  droppedSessions: number;
  topReasonCodes: { code: string; count: number }[];
  topSpecialties: { specialty: string; count: number }[];
}

export interface Booking {
  createdAt: string;
  bookingId: string;
  tenantId: string;
  specialty: string;
  slotDate: string;
  slotTime: string;
  outcome: 'SUCCESS' | 'FAILED';
  reasonCode?: string;
  correlationId?: string;
}

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
