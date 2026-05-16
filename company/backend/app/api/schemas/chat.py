"""
Chat API schemas for hospital appointment booking and medication renewal requests.

This module defines request and response models for the hospital chat assistant API,
including validation logic for chat messages, appointment scheduling, medication renewals,
and continuity of care workflows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class _BaseHospitalChatRequest(BaseModel):
    """
    Base request model for hospital chat interactions.
    
    Contains common fields required for all chat-related API requests including
    tenant identification and session tracking.
    """
    tenantId: str = Field(min_length=1)
    clientSessionId: str = Field(min_length=1)

    @field_validator("tenantId", "clientSessionId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        """Strip whitespace and validate that the string is not empty after stripping."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class ChatMessageRequest(_BaseHospitalChatRequest):
    """Request model for sending a message to the chat assistant.
    
    Represents a user message with normalization of whitespace for consistent
    processing and intent detection.
    """
    messageText: str = Field(min_length=1)

    @field_validator("messageText")
    @classmethod
    def strip_message(cls, value: str) -> str:
        """Normalize message text by stripping and collapsing multiple spaces into single spaces."""
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Message cannot be empty.")
        return cleaned


class ChatDirectStartRequest(_BaseHospitalChatRequest):
    """Request to initiate a direct appointment scheduling flow."""
    action: str = Field(default="START_DIRECT_SCHEDULING")


class ChatRenewalRequest(_BaseHospitalChatRequest):
    """Request to initiate a medication renewal flow."""
    action: str = Field(default="REQUEST_MEDICATION_RENEWAL")


class ChatSelectionRequest(_BaseHospitalChatRequest):
    """Request to submit a selection (e.g., appointment slot, doctor, specialty).
    
    Handles user selections from lists presented by the chat assistant, including
    appointments, doctors, specialties, and other available options.
    """
    selectionType: str
    selectionId: str | None = None
    selectionValue: str | None = None
    action: str

    @field_validator("selectionType", "action")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        """Ensure selection type and action are non-empty after whitespace removal."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty.")
        return cleaned

    @field_validator("selectionId", "selectionValue")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        """Normalize optional strings: strip whitespace and treat empty strings as None."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ChatConfirmRequest(_BaseHospitalChatRequest):
    """Request to confirm an action (appointment booking or medication renewal).
    
    Contains confirmation details including appointment slot, doctor specialty, patient
    identification, and contact information for booking completion.
    """
    action: str = Field(min_length=1)
    specialtyId: str | None = None
    slotId: str | None = None
    nationalId: str | None = None
    email: str | None = None
    renewalItemId: str | None = None

    @field_validator("action")
    @classmethod
    def strip_action(cls, value: str) -> str:
        """Ensure action field is not empty after whitespace removal."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Action cannot be empty.")
        return cleaned


class ChatContinuityIdentifyRequest(_BaseHospitalChatRequest):
    """Request to identify a patient for continuity of care workflow.
    
    Validates patient identity using national ID for accessing continuity
    records and scheduling with preferred practitioners.
    """
    nationalId: str = Field(min_length=1)

    @field_validator("nationalId")
    @classmethod
    def strip_national_id(cls, value: str) -> str:
        """Ensure national ID is not empty after whitespace removal."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("National ID cannot be empty.")
        return cleaned


class QuickReply(BaseModel):
    """Quick reply option presented to user in chat responses.
    
    Represents predefined response options that users can quickly select
    to continue the conversation flow.
    """
    label: str  # Display text shown to the user
    value: str  # Internal value/identifier for the reply
    action: str | None = None  # Optional action to trigger when selected


class SelectionListItemMeta(BaseModel):
    """Metadata for selection list items (appointments, doctors, specialties).
    
    Contains timing information, practitioner details, and display formatting
    for rendering selection options to users.
    """
    # Timing information
    isoDate: str | None = None  # ISO format date of the appointment slot
    startTime: str | None = None  # Slot start time
    endTime: str | None = None  # Slot end time
    timezone: str | None = None  # Timezone for time interpretation

    # Practitioner information
    practitionerRef: str | None = None  # FHIR reference to the practitioner
    practitionerDisplay: str | None = None  # Practitioner name for display
    specialtyId: str | None = None  # Medical specialty identifier
    specialtyDisplay: str | None = None  # Specialty name for display

    # Display formatting
    dateKey: str | None = None  # Unique key for grouping dates
    displayDate: str | None = None  # Formatted date string for UI display
    displayTime: str | None = None  # Formatted time string for UI display

    # Preferences
    isPreferredPractitioner: bool | None = None  # Whether this is the user's preferred doctor


class SelectionListItem(BaseModel):
    """Individual item in a selection list presented to the user.
    
    Represents a selectable option like an appointment slot, doctor, or specialty
    with its display information and metadata.
    """
    id: str  # Unique identifier for this selection item
    label: str  # Display label for the item
    description: str | None = None  # Additional description text
    confidence: float | None = None  # Confidence score (0-1) for NLU matching
    meta: SelectionListItemMeta | None = None  # Additional metadata for rendering


class SelectionList(BaseModel):
    """List of items from which user can make a selection.
    
    Groups multiple selectable items (appointments, doctors, etc.) by type
    for presentation in the chat interface.
    """
    type: str  # Type of items in the list (e.g., 'appointments', 'doctors', 'specialties')
    items: list[SelectionListItem]  # Array of selectable items


class BackendError(BaseModel):
    """Error information returned in chat responses.
    
    Provides error details with both machine-readable codes and user-friendly messages.
    """
    reasonCode: str  # Machine-readable error code for handling different error types
    userMessage: str  # User-friendly error message for display


class ContinuityPayload(BaseModel):
    """Continuity of care information for patient scheduling.
    
    Contains information about continuity matches and patient preferences
    for scheduling with preferred practitioners.
    """
    matched: bool = False  # Whether a continuity record was found
    preferredPractitionerRef: str | None = None  # FHIR reference to preferred doctor
    preferredPractitionerDisplay: str | None = None  # Preferred doctor's name
    preferredPractitionerHasAvailability: bool | None = None  # Availability status of preferred doctor
    message: str | None = None  # Additional continuity-related message


class ConfirmationSummary(BaseModel):
    """Summary of a confirmed appointment or medication renewal.
    
    Displays booking/renewal details to the user for confirmation,
    including appointment or prescription information.
    """
    bookingReferenceId: str | None = None  # Appointment booking reference
    correlationId: str | None = None  # Request correlation ID for tracking
    doctorLabel: str | None = None  # Booked doctor's name
    specialtyLabel: str | None = None  # Medical specialty
    date: str | None = None  # Appointment date
    slotLabel: str | None = None  # Time slot display
    renewalItemLabel: str | None = None  # Medication name for renewals
    refillTaskRef: str | None = None  # Task reference for medication refill


class ChatResponse(BaseModel):
    """Response from the chat assistant.
    
    Main response model containing the assistant's message, user options (quick replies
    or selection lists), workflow state, and any errors that occurred during processing.
    """
    userMessage: str  # Chat assistant's text response to the user
    quickReplies: list[QuickReply] | None = None  # Predefined quick-reply options
    selectionLists: list[SelectionList] | None = None  # Lists for user selection (appointments, doctors, etc.)
    needsClarification: bool | None = None  # Whether the assistant needs clarification from the user
    isChronicContinuity: bool | None = None  # Whether this is a chronic disease continuity workflow
    continuity: ContinuityPayload | None = None  # Continuity of care information
    showConsentNotice: bool | None = None  # Whether to display a consent notice
    requiresContinuityIdentity: bool | None = None  # Whether patient identity verification is needed
    requiresDate: bool | None = None  # Whether a date selection is required
    correlationId: str | None = None  # Request correlation ID for tracking and logs
    errors: list[BackendError] | None = None  # Any errors that occurred during processing
    bookingReferenceId: str | None = None  # Confirmed booking reference if appointment was booked
    confirmationType: str | None = None  # Type of confirmation (e.g., 'appointment', 'renewal')
    confirmationSummary: ConfirmationSummary | None = None  # Summary of the confirmed action


class ChatRenewalIdentifyRequest(_BaseHospitalChatRequest):
    """Request to identify a patient for medication renewal workflow.
    
    Validates patient identity using national ID before processing medication
    renewal requests.
    """
    nationalId: str = Field(min_length=1)

    @field_validator("nationalId")
    @classmethod
    def strip_national_id(cls, value: str) -> str:
        """Ensure national ID is not empty after whitespace removal."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("National ID cannot be empty.")
        return cleaned


class ChatResetRequest(_BaseHospitalChatRequest):
    """Request to reset the chat workflow and start fresh.
    
    Clears the current conversation state and allows the user to restart
    a new workflow.
    """
    action: str = Field(default="RESET_FLOW", min_length=1)

    @field_validator("action")
    @classmethod
    def strip_action(cls, value: str) -> str:
        """Ensure action field is not empty after whitespace removal."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Action cannot be empty.")
        return cleaned