import type { ApiAdapter, ApiResponse, Booking, BookingsPage, AuditPage, SessionsPage, TraceEvent, NlpClassification } from './types';
import { generateUUID } from '@/lib/uuid';

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

function wrap<T>(data: T): ApiResponse<T> {
  return { data, requestCorrelationId: generateUUID() };
}

const mockBookings: Booking[] = Array.from({ length: 45 }, (_, i) => ({
  createdAt: new Date(Date.now() - i * 3600000 * 6).toISOString(),
  bookingId: `BK-${1000 + i}`,
  tenantId: 'demo',
  specialty: ['Dermatology', 'Cardiology', 'Orthopedics', 'General'][i % 4],
  slotDate: new Date(Date.now() + i * 86400000).toISOString().split('T')[0],
  slotTime: `${9 + (i % 8)}:00`,
  outcome: i % 5 === 0 ? 'FAILED' : 'SUCCESS',
  reasonCode: i % 5 === 0 ? ['SLOT_UNAVAILABLE', 'FHIR_TIMEOUT', 'DUPLICATE'][i % 3] : undefined,
  correlationId: generateUUID(),
}));

const mockAudit = Array.from({ length: 30 }, (_, i) => ({
  timestamp: new Date(Date.now() - i * 1800000).toISOString(),
  eventType: ['BOOKING_CREATED', 'BOOKING_FAILED', 'SESSION_STARTED', 'NLP_CLASSIFICATION'][i % 4],
  outcome: i % 3 === 0 ? 'FAILED' : 'SUCCESS',
  reasonCode: i % 3 === 0 ? 'SLOT_UNAVAILABLE' : undefined,
  idempotencyKey: generateUUID(),
  correlationId: generateUUID(),
  message: `Event ${i + 1} processed successfully`,
}));

const mockSessions = Array.from({ length: 25 }, (_, i) => ({
  sessionId: generateUUID(),
  startedAt: new Date(Date.now() - i * 7200000).toISOString(),
  lastEventAt: new Date(Date.now() - i * 3600000).toISOString(),
  status: (['COMPLETED', 'DROPPED', 'FAILED'] as const)[i % 3],
  finalReasonCode: i % 3 !== 0 ? ['SESSION_TIMEOUT', 'USER_ABORT'][i % 2] : undefined,
  correlationId: i % 2 === 0 ? generateUUID() : undefined,
}));

const mockTraces: TraceEvent[] = [
  { timestamp: new Date(Date.now() - 5000).toISOString(), eventType: 'SESSION_STARTED', component: 'Gateway', outcome: 'SUCCESS', message: 'Patient session initiated' },
  { timestamp: new Date(Date.now() - 4000).toISOString(), eventType: 'NLP_CLASSIFICATION', component: 'NLP Engine', outcome: 'SUCCESS', message: 'Classified as Dermatology with 0.92 confidence' },
  { timestamp: new Date(Date.now() - 3000).toISOString(), eventType: 'SLOT_SEARCH', component: 'Booking Service', outcome: 'SUCCESS', message: 'Found 3 available slots' },
  { timestamp: new Date(Date.now() - 2000).toISOString(), eventType: 'BOOKING_CREATED', component: 'FHIR Adapter', outcome: 'SUCCESS', message: 'Appointment booked successfully' },
  { timestamp: new Date(Date.now() - 1000).toISOString(), eventType: 'NOTIFICATION_SENT', component: 'Notification Service', outcome: 'SUCCESS', message: 'Confirmation sent via SMS' },
];

const mockNlpClassifications: NlpClassification[] = Array.from({ length: 20 }, (_, i) => ({
  timestamp: new Date(Date.now() - i * 900000).toISOString(),
  inputSummary: i % 4 === 0 ? undefined : `Patient inquiry about ${['skin rash', 'chest pain', 'joint pain', 'headache'][i % 4]}`,
  predictedLabel: ['Dermatology', 'Cardiology', 'Orthopedics', 'General'][i % 4],
  confidence: 0.65 + Math.random() * 0.3,
  ambiguity: i % 5 === 0,
}));

export const apiMock: ApiAdapter = {
  async login(req) {
    await delay(500);
    if (req.username === 'admin' && req.password === 'admin') {
      return wrap({ access_token: 'mock-jwt-token-' + generateUUID(), token_type: 'bearer', expires_in: 3600, role: 'ADMIN' as const });
    }
    if (req.username === 'tenant' && req.password === 'tenant') {
      return wrap({ access_token: 'mock-jwt-token-' + generateUUID(), token_type: 'bearer', expires_in: 3600, role: 'TENANT_ADMIN' as const, tenantId: 'demo' });
    }
    throw { userMessage: 'Invalid username or password.', requestCorrelationId: generateUUID() };
  },
  async getHealth() {
    await delay();
    return wrap({ status: 'OK', timestamp: new Date().toISOString() });
  },
  async getFhirStatus() {
    await delay();
    return wrap({ status: 'OK', timestamp: new Date().toISOString() });
  },
  async getAnalyticsSummary() {
    await delay();
    return wrap({
      totalBookings: 142, bookingFailures: 8, droppedSessions: 5,
      topReasonCodes: [{ code: 'SLOT_UNAVAILABLE', count: 4 }, { code: 'FHIR_TIMEOUT', count: 3 }, { code: 'DUPLICATE', count: 1 }],
      topSpecialties: [{ code: 'Dermatology', count: 45 }, { code: 'Cardiology', count: 38 }, { code: 'Orthopedics', count: 29 }] as any,
    });
  },
  async getRecentBookings(limit = 10) {
    await delay();
    return wrap(mockBookings.slice(0, limit));
  },
  async getBookings(params) {
    await delay();
    const page = parseInt(params.page || '1');
    const pageSize = parseInt(params.pageSize || '20');
    const start = (page - 1) * pageSize;
    return wrap({ items: mockBookings.slice(start, start + pageSize), total: mockBookings.length, page, pageSize });
  },
  async getTenants() {
    await delay();
    return wrap([{ tenantId: 'demo', name: 'Demo Tenant', status: 'ACTIVE', createdAt: '2024-01-01T00:00:00Z' }]);
  },
  async getTenantDetail() {
    await delay();
    return wrap({
      tenantId: 'demo', name: 'Demo Tenant', status: 'ACTIVE', createdAt: '2024-01-01T00:00:00Z',
      allowedOrigins: ['http://localhost:3000', 'http://localhost:3001'],
      featureFlags: { nlpEnabled: true, smsNotifications: true, emailNotifications: false },
      fhirStatus: 'OK',
    });
  },
  async getAuditLogs(params) {
    await delay();
    const page = parseInt(params.page || '1');
    const pageSize = parseInt(params.pageSize || '20');
    const start = (page - 1) * pageSize;
    let filtered = mockAudit;
    if (params.correlationId) filtered = filtered.filter((a) => a.correlationId?.includes(params.correlationId));
    return wrap({ items: filtered.slice(start, start + pageSize), total: filtered.length, page, pageSize });
  },
  async getTracesByCorrelationId() {
    await delay();
    return wrap(mockTraces);
  },
  async getTracesBySessionId() {
    await delay();
    return wrap(mockTraces);
  },
  async getSessions(params) {
    await delay();
    const page = parseInt(params.page || '1');
    const pageSize = parseInt(params.pageSize || '20');
    const start = (page - 1) * pageSize;
    return wrap({ items: mockSessions.slice(start, start + pageSize), total: mockSessions.length, page, pageSize });
  },
  async getNlpStats() {
    await delay();
    return wrap({
      loadedLabels: 12, thresholds: { confidence: 0.7, ambiguity: 0.15 },
      modelName: 'SpecialtyClassifier', modelVersion: 'v2.1.0',
      lastModelLoadTime: new Date(Date.now() - 3600000).toISOString(),
    });
  },
  async getNlpRecent(limit = 20) {
    await delay();
    return wrap(mockNlpClassifications.slice(0, limit));
  },
};
