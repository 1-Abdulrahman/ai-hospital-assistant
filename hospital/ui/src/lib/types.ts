/** Unified backend response types */

export interface QuickReply {
  label: string;
  value: string;
}

export interface SelectionListItemMeta {
  isoDate?: string;
  startTime?: string;
  endTime?: string;
  timezone?: string;
}

export interface SelectionListItem {
  id: string;
  label: string;
  description?: string;
  confidence?: number;
  meta?: SelectionListItemMeta;
}

export interface SelectionList {
  type: "specialty" | "doctor" | "slot" | "date" | "medication";
  items: SelectionListItem[];
}

export interface BackendError {
  reasonCode: string;
  userMessage: string;
}

export interface ConfirmationSummary {
  bookingReferenceId?: string;
  correlationId?: string;
  doctorLabel?: string;
  specialtyLabel?: string;
  date?: string;
  slotLabel?: string;
  renewalItemLabel?: string;
}

export interface ChatResponse {
  userMessage: string;
  quickReplies?: QuickReply[];
  selectionLists?: SelectionList[];
  needsClarification?: boolean;
  isChronicContinuity?: boolean;
  showConsentNotice?: boolean;
  requiresDate?: boolean;
  correlationId?: string;
  errors?: BackendError[];
  bookingReferenceId?: string;
  confirmationType?: "appointment" | "renewal";
  confirmationSummary?: ConfirmationSummary;
}

export interface HealthResponse {
  status: string;
}

export interface OtpRequestResponse {
  message: string;
  correlationId?: string;
}

export interface OtpVerifyResponse {
  verified: boolean;
  correlationId?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  quickReplies?: QuickReply[];
  selectionLists?: SelectionList[];
  needsClarification?: boolean;
  isChronicContinuity?: boolean;
  showConsentNotice?: boolean;
  bookingReferenceId?: string;
  confirmationType?: "appointment" | "renewal";
  confirmationSummary?: ConfirmationSummary;
}

export type FlowStep = "chat" | "otp" | "confirm" | "done";
export type FlowMode = "complaint" | "direct" | "renewal";

/** Request types for structured interactions */
export interface SelectionRequest {
  tenantId: string;
  clientSessionId: string;
  correlationId?: string;
  selectionType: string;
  selectionId?: string;
  selectionValue?: string;
  action: string;
}

export interface ConfirmRequest {
  tenantId: string;
  clientSessionId: string;
  correlationId?: string;
  action: string;
  specialtyId?: string;
  doctorId?: string;
  slotId?: string;
  date?: string;
  renewalItemId?: string;
}
