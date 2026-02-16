/** Unified backend response types */

export interface SpecialtyCandidate {
  label: string;
  p: number;
}

export interface QuickReply {
  label: string;
  value: string;
}

export interface SelectionListItem {
  id: string;
  label: string;
  description?: string;
}

export interface SelectionList {
  type: "specialty" | "doctor" | "slot";
  items: SelectionListItem[];
}

export interface BackendError {
  reasonCode: string;
  userMessage: string;
}

export interface ChatResponse {
  userMessage: string;
  candidates?: SpecialtyCandidate[];
  ambiguous?: boolean;
  quickReplies?: QuickReply[];
  selectionLists?: SelectionList[];
  needsClarification?: boolean;
  isChronicContinuity?: boolean;
  showConsentNotice?: boolean;
  correlationId?: string;
  errors?: BackendError[];
}

export interface HealthResponse {
  status: string;
}

export interface BookingConfirmResponse {
  bookingId: string;
  correlationId: string;
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
  candidates?: SpecialtyCandidate[];
  ambiguous?: boolean;
  quickReplies?: QuickReply[];
  selectionLists?: SelectionList[];
  needsClarification?: boolean;
  isChronicContinuity?: boolean;
  showConsentNotice?: boolean;
}

export type FlowStep = "chat" | "clarify" | "book" | "otp" | "confirm";
