import { v4 as uuidv4 } from "uuid";
import { getSessionId, getTenantId, getCorrelationId, setCorrelationId } from "./session";
import { chatResponseSchema, healthResponseSchema, otpRequestResponseSchema, otpVerifyResponseSchema } from "./zod-schemas";
import type { ChatResponse, HealthResponse, OtpRequestResponse, OtpVerifyResponse, SelectionRequest, ConfirmRequest } from "./types";

const BASE_URL = "http://localhost:8000";
const TIMEOUT_MS = 15000;

function buildHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Tenant-Id": getTenantId(),
    "X-Session-Id": getSessionId(),
  };
  const corrId = getCorrelationId();
  if (corrId) headers["X-Correlation-Id"] = corrId;
  if (extra) Object.assign(headers, extra);
  return headers;
}

async function request<T>(path: string, init: RequestInit, schema: { parse: (d: unknown) => unknown }): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
    const body = await res.json();
    if (!res.ok) {
      const msg = body?.userMessage || body?.message || "Something went wrong. Please try again.";
      if (body?.reasonCode) console.debug("[API reasonCode]", body.reasonCode);
      throw new Error(msg);
    }
    if (body.correlationId) setCorrelationId(body.correlationId);
    return schema.parse(body) as T;
  } catch (err: any) {
    if (err.name === "AbortError") throw new Error("Request timed out. Please try again.");
    if (err instanceof TypeError && err.message === "Failed to fetch") throw new Error("Cannot connect to server. Is the backend running?");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Build common body fields for chat endpoints */
function chatBody(extra?: Record<string, unknown>) {
  const body: Record<string, unknown> = {
    tenantId: getTenantId(),
    clientSessionId: getSessionId(),
  };
  const corrId = getCorrelationId();
  if (corrId) body.correlationId = corrId;
  if (extra) Object.assign(body, extra);
  return body;
}

export async function checkHealth(): Promise<HealthResponse> {
  return request("/health", { method: "GET", headers: buildHeaders() }, healthResponseSchema);
}

export async function sendChatMessage(messageText: string): Promise<ChatResponse> {
  return request("/chat/message", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(chatBody({ messageText })),
  }, chatResponseSchema);
}

export async function chatDirectStart(): Promise<ChatResponse> {
  return request("/chat/direct/start", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(chatBody({ action: "START_DIRECT_SCHEDULING" })),
  }, chatResponseSchema);
}

export async function chatRenewalRequest(): Promise<ChatResponse> {
  return request("/chat/renewal/request", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(chatBody({ action: "REQUEST_MEDICATION_RENEWAL" })),
  }, chatResponseSchema);
}

export async function chatSelection(data: Omit<SelectionRequest, "tenantId" | "clientSessionId" | "correlationId">): Promise<ChatResponse> {
  return request("/chat/selection", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(chatBody(data)),
  }, chatResponseSchema);
}

export async function chatConfirm(data: Omit<ConfirmRequest, "tenantId" | "clientSessionId" | "correlationId">): Promise<ChatResponse> {
  const extra: Record<string, string> = {};
  if (data.action === "CONFIRM_APPOINTMENT") {
    extra["Idempotency-Key"] = uuidv4();
  }
  return request("/chat/confirm", {
    method: "POST",
    headers: buildHeaders(extra),
    body: JSON.stringify(chatBody(data)),
  }, chatResponseSchema);
}

export async function requestOtp(): Promise<OtpRequestResponse> {
  return request("/auth/request-otp", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({}),
  }, otpRequestResponseSchema);
}

export async function verifyOtp(otp: string): Promise<OtpVerifyResponse> {
  return request("/auth/verify-otp", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({ otp }),
  }, otpVerifyResponseSchema);
}
