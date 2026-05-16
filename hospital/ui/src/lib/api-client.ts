/**
 * API Client Module
 *
 * Provides a centralized interface for all HTTP requests to the backend API.
 * Handles:
 * - Request/response serialization and validation using Zod schemas
 * - Session and tenant management via headers
 * - Correlation ID tracking for request tracing
 * - Request timeouts and error handling
 * - Idempotency for specific operations
 */

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

/** Backend API base URL */
const BASE_URL = "http://localhost:8000";

/** Request timeout in milliseconds */
const TIMEOUT_MS = 15000;

/**
 * Constructs HTTP headers for API requests
 *
 * Includes:
 * - Content-Type: application/json
 * - X-Tenant-Id: Current tenant identifier
 * - X-Session-Id: Current session identifier
 * - X-Correlation-Id: Optional correlation ID for request tracing
 *
 * @param extra - Optional additional headers to merge in
 * @returns Headers object ready for fetch requests
 */
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

/**
 * Generic request handler with validation, timeout, and error management
 *
 * Handles:
 * - Automatic request timeout after TIMEOUT_MS
 * - Response validation using provided Zod schema
 * - Correlation ID propagation from response headers
 * - Standard error handling for common failure scenarios
 *
 * @template T - Response type after validation
 * @param path - API endpoint path (e.g., "/chat/message")
 * @param init - Fetch request options (method, headers, body, etc.)
 * @param schema - Zod schema for parsing and validating response
 * @returns Validated response object of type T
 * @throws Error with user-friendly message on timeout, connection error, or validation failure
 */
async function request<T>(
  path: string,
  init: RequestInit,
  schema: { parse: (d: unknown) => unknown },
): Promise<T> {
  // Set up abort controller and timeout for request
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    // Make the fetch request with the abort signal
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });

    // Extract correlation ID from response headers for request tracing
    const headerCorrelationId = res.headers.get("X-Correlation-Id");
    if (headerCorrelationId) setCorrelationId(headerCorrelationId);

    // Parse response body
    const body = await res.json();

    // Handle non-2xx responses with user-friendly error messages
    if (!res.ok) {
      const msg =
        body?.message ||
        body?.userMessage ||
        "Something went wrong. Please try again.";
      // Fallback to correlation ID in body if not in headers
      if (body?.correlationId && !headerCorrelationId) {
        setCorrelationId(body.correlationId);
      }
      throw new Error(msg);
    }

    // Update correlation ID from response body if not in headers
    if (!headerCorrelationId && body?.correlationId) {
      setCorrelationId(body.correlationId);
    }

    // Validate response against schema and return
    return schema.parse(body) as T;
  } catch (err: any) {
    // Handle specific error types with appropriate messages
    if (err.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error("Cannot connect to server. Is the backend running?");
    }
    throw err;
  } finally {
    // Clean up timeout to prevent memory leaks
    clearTimeout(timer);
  }
}

/**
 * Constructs the base request body for chat-related API calls
 *
 * Includes tenant ID and client session ID, which are required for all chat operations.
 * Additional properties can be merged in via the extra parameter.
 *
 * @param extra - Optional additional properties to include in the request body
 * @returns Request body object with tenantId and clientSessionId
 */
function chatBody(extra?: Record<string, unknown>) {
  const body: Record<string, unknown> = {
    tenantId: getTenantId(),
    clientSessionId: getSessionId(),
  };
  if (extra) Object.assign(body, extra);
  return body;
}

/**
 * Health check endpoint
 *
 * Verifies that the backend service is running and healthy.
 *
 * @returns Health status information
 */
export async function checkHealth(): Promise<HealthResponse> {
  return request(
    "/health",
    { method: "GET", headers: buildHeaders() },
    healthResponseSchema,
  );
}

/**
 * Send a chat message to the AI assistant
 *
 * Sends a user message and receives an AI response with next available actions.
 *
 * @param messageText - The message to send to the assistant
 * @returns Chat response with assistant message and available actions
 */
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

/**
 * Start direct scheduling flow
 *
 * Initiates the appointment scheduling dialogue with the assistant.
 *
 * @returns Chat response with initial scheduling options
 */
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

/**
 * Request medication renewal flow
 *
 * Initiates the medication renewal dialogue with the assistant.
 *
 * @returns Chat response with renewal options
 */
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

/**
 * Reset the current chat flow
 *
 * Clears conversation state and returns to the initial menu.
 *
 * @returns Chat response with reset flow
 */
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

/**
 * Send a user selection in response to chat options
 *
 * Handles user choices such as selecting from a list, making a selection with a value, or performing an action.
 *
 * @param input - Selection details
 * @param input.selectionType - Type of selection (e.g., "APPOINTMENT_TIME", "MEDICATION")
 * @param input.selectionId - Optional ID for the selected item
 * @param input.selectionValue - Optional value for the selected item
 * @param input.action - Action to perform with the selection
 * @returns Chat response with next steps based on the selection
 */
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

/**
 * Identify patient for continuity of care flow
 *
 * Validates patient identity using their national ID before proceeding with care continuity operations.
 *
 * @param nationalId - Patient's national identification number
 * @returns Chat response with patient identification status
 */
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

/**
 * Confirm a user action (e.g., appointment booking, medication renewal)
 *
 * Submits a confirmation for an action. For appointment confirmations, uses idempotency key
 * to ensure the operation can be safely retried without duplicate bookings.
 *
 * @param data - Confirmation details including action type and relevant IDs
 * @returns Chat response confirming the action
 */
export async function chatConfirm(
  data: Omit<ConfirmRequest, "tenantId" | "clientSessionId" | "correlationId">,
): Promise<ChatResponse> {
  const extra: Record<string, string> = {};
  // Add idempotency key for appointment confirmations to prevent duplicate bookings
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

/**
 * Request OTP (One-Time Password) for patient verification
 *
 * Initiates OTP generation and sends it to the provided email address.
 *
 * @param nationalId - Patient's national identification number
 * @param email - Email address where OTP will be sent
 * @returns Response confirming OTP request was processed
 */
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

/**
 * Verify OTP (One-Time Password)
 *
 * Validates the OTP provided by the patient against the one sent to their email.
 *
 * @param args - Verification details
 * @param args.nationalId - Patient's national identification number
 * @param args.email - Email address used for OTP delivery
 * @param args.otp - OTP code provided by the patient
 * @returns Response confirming OTP verification success
 */
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

/**
 * Identify patient for medication renewal flow
 *
 * Validates patient identity using their national ID before proceeding with renewal operations.
 *
 * @param nationalId - Patient's national identification number
 * @returns Chat response with patient identification status for renewal flow
 */
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
