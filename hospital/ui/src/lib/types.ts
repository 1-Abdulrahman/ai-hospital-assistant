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
  description?: string | null;
  confidence?: number | null;
  meta?: SelectionListItemMeta | null;
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
  bookingReferenceId?: string | null;
  correlationId?: string | null;
  doctorLabel?: string | null;
  specialtyLabel?: string | null;
  date?: string | null;
  slotLabel?: string | null;
  renewalItemLabel?: string | null;
}

export interface ChatResponse {
  userMessage: string;
  quickReplies?: QuickReply[] | null;
  selectionLists?: SelectionList[] | null;
  needsClarification?: boolean | null;
  isChronicContinuity?: boolean | null;
  showConsentNotice?: boolean | null;
  requiresContinuityIdentity?: boolean | null;
  requiresDate?: boolean | null;
  correlationId?: string | null;
  errors?: BackendError[] | null;
  bookingReferenceId?: string | null;
  confirmationType?: "appointment" | "renewal" | null;
  confirmationSummary?: ConfirmationSummary | null;
}

export interface HealthResponse {
  status: string;
}

export interface OtpRequestResponse {
  ok?: boolean | null;
  message: string;
  expiresIn?: number | null;
  correlationId?: string | null;
}

export interface OtpVerifyResponse {
  verified: boolean;
  message?: string | null;
  correlationId?: string | null;
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
  requiresContinuityIdentity?: boolean;
  bookingReferenceId?: string;
  confirmationType?: "appointment" | "renewal";
  confirmationSummary?: ConfirmationSummary;
}

export type FlowStep =
  | "chat"
  | "otp"
  | "confirm"
  | "done"
  | "renewal_identity"
  | "continuity_identity";

export type FlowMode = "complaint" | "direct" | "renewal";

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
  nationalId?: string;
  email?: string;
  renewalItemId?: string;
}