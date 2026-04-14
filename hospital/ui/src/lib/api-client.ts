import { v4 as uuidv4 } from "uuid";
import {
  getSessionId,
  getTenantId,
  getCorrelationId,
  setCorrelationId,
} from "./session";
import {
  chatResponseSchema,
  healthResponseSchema,
  otpRequestResponseSchema,
  otpVerifyResponseSchema,
} from "./zod-schemas";
import type {
  ChatResponse,
  HealthResponse,
  OtpRequestResponse,
  OtpVerifyResponse,
  ConfirmRequest,
} from "./types";

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

async function request<T>(
  path: string,
  init: RequestInit,
  schema: { parse: (d: unknown) => unknown },
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });

    const headerCorrelationId = res.headers.get("X-Correlation-Id");
    if (headerCorrelationId) setCorrelationId(headerCorrelationId);

    const body = await res.json();

    if (!res.ok) {
      const msg =
        body?.message ||
        body?.userMessage ||
        "Something went wrong. Please try again.";
      if (body?.correlationId && !headerCorrelationId) {
        setCorrelationId(body.correlationId);
      }
      throw new Error(msg);
    }

    if (!headerCorrelationId && body?.correlationId) {
      setCorrelationId(body.correlationId);
    }

    return schema.parse(body) as T;
  } catch (err: any) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error("Cannot connect to server. Is the backend running?");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function chatBody(extra?: Record<string, unknown>) {
  const body: Record<string, unknown> = {
    tenantId: getTenantId(),
    clientSessionId: getSessionId(),
  };
  if (extra) Object.assign(body, extra);
  return body;
}

export async function checkHealth(): Promise<HealthResponse> {
  return request(
    "/health",
    { method: "GET", headers: buildHeaders() },
    healthResponseSchema,
  );
}

export async function sendChatMessage(messageText: string): Promise<ChatResponse> {
  return request(
    "/chat/message",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ messageText })),
    },
    chatResponseSchema,
  );
}

export async function chatDirectStart(): Promise<ChatResponse> {
  return request(
    "/chat/direct/start",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ action: "START_DIRECT_SCHEDULING" })),
    },
    chatResponseSchema,
  );
}

export async function chatRenewalRequest(): Promise<ChatResponse> {
  return request(
    "/chat/renewal/request",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ action: "REQUEST_MEDICATION_RENEWAL" })),
    },
    chatResponseSchema,
  );
}

export async function chatReset(): Promise<ChatResponse> {
  return request(
    "/chat/reset",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ action: "RESET_FLOW" })),
    },
    chatResponseSchema,
  );
}


export async function chatSelection(input: {
  selectionType: string;
  selectionId?: string;
  selectionValue?: string;
  action: string;
}): Promise<ChatResponse> {
  return request(
    "/chat/selection",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(
        chatBody({
          selectionType: input.selectionType,
          selectionId: input.selectionId,
          selectionValue: input.selectionValue,
          action: input.action,
        }),
      ),
    },
    chatResponseSchema,
  );
}

export async function chatContinuityIdentify(
  nationalId: string,
): Promise<ChatResponse> {
  return request(
    "/chat/continuity/identify",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ nationalId })),
    },
    chatResponseSchema,
  );
}

export async function chatConfirm(
  data: Omit<ConfirmRequest, "tenantId" | "clientSessionId" | "correlationId">,
): Promise<ChatResponse> {
  const extra: Record<string, string> = {};
  if (data.action === "CONFIRM_APPOINTMENT") {
    extra["Idempotency-Key"] = uuidv4();
  }
  return request(
    "/chat/confirm",
    {
      method: "POST",
      headers: buildHeaders(extra),
      body: JSON.stringify(chatBody(data as Record<string, unknown>)),
    },
    chatResponseSchema,
  );
}

export async function requestOtp(
  nationalId: string,
  email: string,
): Promise<OtpRequestResponse> {
  return request(
    "/otp/request",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify({
        tenantId: getTenantId(),
        nationalId,
        email,
      }),
    },
    otpRequestResponseSchema,
  );
}

export async function verifyOtp(args: {
  nationalId: string;
  email: string;
  otp: string;
}): Promise<OtpVerifyResponse> {
  return request(
    "/otp/verify",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify({
        tenantId: getTenantId(),
        nationalId: args.nationalId,
        email: args.email,
        otp: args.otp,
      }),
    },
    otpVerifyResponseSchema,
  );
}

export async function chatRenewalIdentify(
  nationalId: string,
): Promise<ChatResponse> {
  return request(
    "/chat/renewal/identify",
    {
      method: "POST",
      headers: buildHeaders(),
      body: JSON.stringify(chatBody({ nationalId })),
    },
    chatResponseSchema,
  );
}
