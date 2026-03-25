import { v4 as uuidv4 } from "uuid";

const SESSION_KEY = "hcw-session-id";
const CORRELATION_KEY = "hcw-correlation-id";
const TENANT_KEY = "hcw-tenant-id";

export function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = uuidv4();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function resetSession(): string {
  sessionStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(CORRELATION_KEY);
  return getSessionId();
}

export function getCorrelationId(): string | null {
  return sessionStorage.getItem(CORRELATION_KEY);
}

export function setCorrelationId(id: string): void {
  sessionStorage.setItem(CORRELATION_KEY, id);
}

export function getTenantId(): string {
  return sessionStorage.getItem(TENANT_KEY) || "demo";
}

export function setTenantId(id: string): void {
  sessionStorage.setItem(TENANT_KEY, id);
}
