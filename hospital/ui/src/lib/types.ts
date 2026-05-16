// Shared chat and booking payloads used by the portal UI and backend responses.

export interface QuickReply {
  label: string;
  value: string;
  action?: "SEND_MESSAGE" | "PROMPT_FOR_TEXT" | null;
}

// Metadata attached to selection items so the UI can render scheduling context.
export interface SelectionListItemMeta {
  isoDate?: string;
  startTime?: string;
  endTime?: string;
  timezone?: string;

  practitionerRef?: string;
  practitionerDisplay?: string;
  specialtyId?: string;
  specialtyDisplay?: string;

  dateKey?: string;
  displayDate?: string;
  displayTime?: string;

  isPreferredPractitioner?: boolean;
}

// Normalized items shown in specialty, doctor, slot, date, and medication pickers.
export interface SelectionListItem {
  id: string;
  label: string;
  description?: string | null;
  confidence?: number | null;
  meta?: SelectionListItemMeta | null;
}

// A typed list of suggested options returned by the assistant.
export interface SelectionList {
  type: "specialty" | "doctor" | "slot" | "date" | "medication";
  items: SelectionListItem[];
}

// Structured backend errors that can be surfaced to the user.
export interface BackendError {
  reasonCode: string;
  userMessage: string;
}

// Continuity details used when the user is booking with a preferred practitioner.
export interface ContinuityPayload {
  matched: boolean;
  preferredPractitionerRef?: string | null;
  preferredPractitionerDisplay?: string | null;
  preferredPractitionerHasAvailability?: boolean | null;
  message?: string | null;
}

// Booking confirmation data returned after a successful appointment or renewal.
export interface ConfirmationSummary {
  bookingReferenceId?: string | null;
  correlationId?: string | null;
  doctorLabel?: string | null;
  specialtyLabel?: string | null;
  date?: string | null;
  slotLabel?: string | null;
  renewalItemLabel?: string | null;
  refillTaskRef?: string | null;
}

// Canonical chat response shape consumed by the UI.
export interface ChatResponse {
  userMessage: string;
  quickReplies?: QuickReply[] | null;
  selectionLists?: SelectionList[] | null;
  needsClarification?: boolean | null;
  isChronicContinuity?: boolean | null;
  continuity?: ContinuityPayload | null;
  showConsentNotice?: boolean | null;
  requiresContinuityIdentity?: boolean | null;
  requiresDate?: boolean | null;
  correlationId?: string | null;
  errors?: BackendError[] | null;
  bookingReferenceId?: string | null;
  confirmationType?: "appointment" | "renewal" | null;
  confirmationSummary?: ConfirmationSummary | null;
}

// Lightweight service-health response.
export interface HealthResponse {
  status: string;
}

// OTP request result from the backend.
export interface OtpRequestResponse {
  ok?: boolean | null;
  message: string;
  expiresIn?: number | null;
  correlationId?: string | null;
}

// OTP verification response returned after the user submits the code.
export interface OtpVerifyResponse {
  verified: boolean;
  message?: string | null;
  correlationId?: string | null;
}

// In-memory message model used by the chat UI.
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  quickReplies?: QuickReply[];
  selectionLists?: SelectionList[];
  needsClarification?: boolean;
  isChronicContinuity?: boolean;
  continuity?: ContinuityPayload;
  showConsentNotice?: boolean;
  requiresContinuityIdentity?: boolean;
  bookingReferenceId?: string;
  confirmationType?: "appointment" | "renewal";
  confirmationSummary?: ConfirmationSummary;
}

// High-level navigation state for the assistant flow.
export type FlowStep =
  | "chat"
  | "otp"
  | "confirm"
  | "done"
  | "renewal_identity"
  | "continuity_identity";

// Operating mode for the assistant conversation.
export type FlowMode = "complaint" | "direct" | "renewal";

// Request payload sent when the user selects an option from a suggestion list.
export interface SelectionRequest {
  tenantId: string;
  clientSessionId: string;
  correlationId?: string;
  selectionType: string;
  selectionId?: string;
  selectionValue?: string;
  action: string;
}

// Request payload used to confirm an appointment or renewal flow.
export interface ConfirmRequest {
  tenantId: string;
  clientSessionId: string;
  correlationId?: string;
  action: string;
  specialtyId?: string;
  doctorId?: string;
  slotId?: string;
  date?: string;
  nationalId?: string;
  email?: string;
  renewalItemId?: string;
}