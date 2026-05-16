from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base


def utcnow() -> datetime:
    """
    Get the current UTC datetime.
    
    Returns:
        datetime: Current time in UTC timezone.
    """
    return datetime.now(timezone.utc)


Base = declarative_base()


class Tenant(Base):
    """
    Represents a tenant/organization in the system.
    
    A tenant is a top-level organizational unit that can have multiple portal users
    and associated sessions/events.
    """
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)  # platform, demo - unique tenant identifier
    name = Column(String, nullable=False)  # Display name of the tenant


class PortalUser(Base):
    """
    Represents a user with access to the portal.
    
    Portal users can have different roles (company_admin, tenant_admin) and are
    scoped to a specific tenant. Each user has credentials for authentication.
    """
    __tablename__ = "portal_users"

    id = Column(String, primary_key=True)  # uuid hex - unique user identifier
    tenant_id = Column(String, nullable=False)  # Reference to the tenant this user belongs to
    email = Column(String, nullable=False)  # User's email address (unique per tenant)
    password_hash = Column(String, nullable=False)  # Hashed password for authentication
    role = Column(String, nullable=False)  # company_admin, tenant_admin - determines permissions
    is_active = Column(Boolean, nullable=False, default=True)  # Whether the user account is active

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_portal_email"),  # Ensure email is unique within each tenant
    )


class OtpRecord(Base):
    """
    Stores one-time password (OTP) records for patient authentication.
    
    OTPs are used as part of a secure authentication flow. Each record tracks
    the OTP generation, verification attempts, expiration, and final verification status.
    """
    __tablename__ = "otp_records"

    id = Column(String, primary_key=True)  # uuid - unique record identifier
    tenant_id = Column(String, nullable=False)  # Reference to the tenant
    session_id = Column(String, nullable=False)  # Associated session identifier
    patient_key_hash = Column(String, nullable=False)  # Hashed patient key for privacy
    email = Column(String, nullable=False)  # Email address where OTP was/will be sent
    otp_hash = Column(String, nullable=False)  # Hashed OTP code (never store plain OTP)
    expires_at = Column(DateTime, nullable=False)  # Expiration time for this OTP
    attempts = Column(Integer, nullable=False, default=0)  # Number of failed verification attempts
    verified = Column(Boolean, nullable=False, default=False)  # Whether this OTP has been successfully verified


class Event(Base):
    """
    Audit and activity log events for tracking system actions and outcomes.
    
    Events capture what happened, who performed the action, the outcome, and
    relevant contextual data. Used for audit trails, debugging, and analytics.
    """
    __tablename__ = "events"

    id = Column(String, primary_key=True)  # uuid - unique event identifier
    ts_utc = Column(DateTime, nullable=False, default=utcnow)  # Timestamp when event occurred (UTC)
    tenant_id = Column(String, nullable=False)  # Reference to the tenant
    session_id = Column(String, nullable=False)  # Associated session identifier for correlation
    correlation_id = Column(String, nullable=False)  # Used to trace related events across the system
    actor_type = Column(String, nullable=False)  # patient, system, portal_user - who triggered the action
    event_type = Column(String, nullable=False)  # Type of event (e.g., LOGIN, APPOINTMENT_BOOKED)
    outcome = Column(String, nullable=False)  # SUCCESS, FAILURE, INFO - result of the action
    reason_code = Column(String, nullable=True)  # Optional code for failure reason or additional context
    payload_json = Column(Text, nullable=True)  # Additional event-specific data in JSON format


class IdempotencyKey(Base):
    """
    Stores idempotency keys for safely handling duplicate requests.
    
    When a request is retried with the same idempotency key, the same result is
    returned instead of performing the operation again. Prevents double-processing.
    """
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)  # The idempotency key provided by the client
    tenant_id = Column(String, nullable=False)  # Reference to the tenant
    session_id = Column(String, nullable=False)  # Associated session identifier
    request_hash = Column(String, nullable=False)  # Hash of request parameters for validation
    result_json = Column(Text, nullable=False)  # Cached result to return for duplicate requests


class AssistantSession(Base):
    """
    Represents a session with the AI assistant for appointment booking and patient interactions.
    
    Tracks the conversation state, user selections, and context throughout the entire
    interaction flow. Persists appointment details, continuity checks, and clarifications.
    """
    __tablename__ = "assistant_sessions"

    id = Column(String, primary_key=True)  # uuid - unique session identifier
    tenant_id = Column(String, nullable=False)  # Reference to the tenant
    client_session_id = Column(String, nullable=False)  # Client-side session identifier
    current_state = Column(String, nullable=False, default="NEW")  # Current state in the conversation flow (e.g., NEW, AWAITING_SELECTION)
    flow_mode = Column(String, nullable=True)  # Specific flow variant (e.g., NEW_APPOINTMENT, RENEWAL)

    # Appointment selection fields - populated as user makes choices
    selected_specialty_id = Column(String, nullable=True)  # Selected medical specialty
    selected_doctor_id = Column(String, nullable=True)  # Selected practitioner/doctor
    selected_slot_id = Column(String, nullable=True)  # Selected appointment time slot
    selected_slot_label = Column(String, nullable=True)  # Human-readable slot description
    selected_slot_start_utc = Column(String, nullable=True)  # Start time of the selected slot in UTC
    selected_date = Column(String, nullable=True)  # Selected appointment date
    last_input_summary = Column(String, nullable=True)  # Summary of last user input for context

    # Renewal/continuation fields - for handling prescription renewals or follow-ups
    renewal_item_id = Column(String, nullable=True)  # ID of the item being renewed
    renewal_item_label = Column(String, nullable=True)  # Description of the item being renewed
    renewal_patient_key_hash = Column(String, nullable=True)  # Hashed patient identifier for renewal context
    renewal_patient_ref = Column(String, nullable=True)  # Reference to the patient in external system

    # Continuity of care fields - track if this is a returning patient and preferences
    continuity_checked = Column(Boolean, nullable=False, default=False)  # Whether continuity check has been performed
    continuity_patient_ref = Column(String, nullable=True)  # Reference to existing patient record
    continuity_preferred_practitioner_ref = Column(String, nullable=True)  # Preferred doctor from previous visits
    continuity_preferred_practitioner_display = Column(String, nullable=True)  # Display name of preferred practitioner
    continuity_is_returning = Column(Boolean, nullable=False, default=False)  # Whether this is a returning patient

    # Clarification context fields - used when assistant needs to ask follow-up questions
    clarification_pending = Column(Boolean, nullable=False, default=False)  # Whether clarification is being requested
    clarification_key = Column(String, nullable=True)  # Identifier for the specific clarification context
    original_complaint_text = Column(Text, nullable=True)  # Initial user complaint/request before clarification
    clarification_detail_text = Column(Text, nullable=True)  # Additional details provided during clarification
    merged_classification_text = Column(Text, nullable=True)  # Combined/refined classification after clarification

    # Timestamp fields for audit and session management
    created_at_utc = Column(DateTime(timezone=True), nullable=False, default=utcnow)  # When this session was created
    updated_at_utc = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,  # Automatically updated on any record modification
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "client_session_id",
            name="uq_assistant_session_tenant_client",  # Ensure one session per client per tenant
        ),
    )