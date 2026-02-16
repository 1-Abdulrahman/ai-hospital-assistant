import { v4 as uuidv4 } from "uuid";
import { getSessionId, getTenantId, getCorrelationId, setCorrelationId } from "./session";
import { chatResponseSchema, healthResponseSchema, bookingConfirmResponseSchema, otpRequestResponseSchema, otpVerifyResponseSchema } from "./zod-schemas";
import type { ChatResponse, HealthResponse, BookingConfirmResponse, OtpRequestResponse, OtpVerifyResponse } from "./types";

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

export async function checkHealth(): Promise<HealthResponse> {
  return request("/health", { method: "GET", headers: buildHeaders() }, healthResponseSchema);
}

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  return request("/chat/message", {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({ message }),
  }, chatResponseSchema);
}

export async function confirmBooking(data: { date: string; slotId: string; specialtyId?: string; doctorId?: string }): Promise<BookingConfirmResponse> {
  return request("/booking/confirm", {
    method: "POST",
    headers: buildHeaders({ "Idempotency-Key": uuidv4() }),
    body: JSON.stringify(data),
  }, bookingConfirmResponseSchema);
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
