from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class _BaseHospitalChatRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    clientSessionId: str = Field(min_length=1)

    @field_validator("tenantId", "clientSessionId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class ChatMessageRequest(_BaseHospitalChatRequest):
    messageText: str = Field(min_length=1)

    @field_validator("messageText")
    @classmethod
    def strip_message(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        return cleaned


class ChatDirectStartRequest(_BaseHospitalChatRequest):
    action: str = Field(default="START_DIRECT_SCHEDULING")


class ChatRenewalRequest(_BaseHospitalChatRequest):
    action: str = Field(default="REQUEST_MEDICATION_RENEWAL")


class ChatSelectionRequest(_BaseHospitalChatRequest):
    selectionType: str
    selectionId: str | None = None
    selectionValue: str | None = None
    action: str

    @field_validator("selectionType", "action")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty.")
        return cleaned

    @field_validator("selectionId", "selectionValue")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ChatConfirmRequest(_BaseHospitalChatRequest):
    action: str = Field(min_length=1)
    specialtyId: str | None = None
    slotId: str | None = None
    nationalId: str | None = None
    email: str | None = None
    renewalItemId: str | None = None

    @field_validator("action")
    @classmethod
    def strip_action(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Action cannot be empty.")
        return cleaned


class QuickReply(BaseModel):
    label: str
    value: str


class SelectionListItemMeta(BaseModel):
    isoDate: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    timezone: str | None = None


class SelectionListItem(BaseModel):
    id: str
    label: str
    description: str | None = None
    confidence: float | None = None
    meta: SelectionListItemMeta | None = None


class SelectionList(BaseModel):
    type: str
    items: list[SelectionListItem]


class BackendError(BaseModel):
    reasonCode: str
    userMessage: str


class ConfirmationSummary(BaseModel):
    bookingReferenceId: str | None = None
    correlationId: str | None = None
    doctorLabel: str | None = None
    specialtyLabel: str | None = None
    date: str | None = None
    slotLabel: str | None = None
    renewalItemLabel: str | None = None


class ChatResponse(BaseModel):
    userMessage: str
    quickReplies: list[QuickReply] | None = None
    selectionLists: list[SelectionList] | None = None
    needsClarification: bool | None = None
    isChronicContinuity: bool | None = None
    showConsentNotice: bool | None = None
    requiresDate: bool | None = None
    correlationId: str | None = None
    errors: list[BackendError] | None = None
    bookingReferenceId: str | None = None
    confirmationType: str | None = None
    confirmationSummary: ConfirmationSummary | None = None
    
    
class ChatRenewalIdentifyRequest(_BaseHospitalChatRequest):
    nationalId: str = Field(min_length=1)

    @field_validator("nationalId")
    @classmethod
    def strip_national_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("National ID cannot be empty.")
        return cleaned