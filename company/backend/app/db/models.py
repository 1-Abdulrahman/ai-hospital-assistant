from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)  # platform, demo
    name = Column(String, nullable=False)


class PortalUser(Base):
    __tablename__ = "portal_users"

    id = Column(String, primary_key=True)  # uuid hex
    tenant_id = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # company_admin, tenant_admin
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_portal_email"),
    )


class OtpRecord(Base):
    __tablename__ = "otp_records"

    id = Column(String, primary_key=True)  # uuid
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    patient_key_hash = Column(String, nullable=False)
    email = Column(String, nullable=False)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    verified = Column(Boolean, nullable=False, default=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)  # uuid
    ts_utc = Column(DateTime, nullable=False, default=utcnow)
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    correlation_id = Column(String, nullable=False)
    actor_type = Column(String, nullable=False)  # patient, system, portal_user
    event_type = Column(String, nullable=False)
    outcome = Column(String, nullable=False)  # SUCCESS, FAILURE, INFO
    reason_code = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    result_json = Column(Text, nullable=False)


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    client_session_id = Column(String, nullable=False)
    current_state = Column(String, nullable=False, default="NEW")
    flow_mode = Column(String, nullable=True)

    selected_specialty_id = Column(String, nullable=True)
    selected_doctor_id = Column(String, nullable=True)
    selected_slot_id = Column(String, nullable=True)
    selected_slot_label = Column(String, nullable=True)
    selected_slot_start_utc = Column(String, nullable=True)
    selected_date = Column(String, nullable=True)
    last_input_summary = Column(String, nullable=True)

    renewal_item_id = Column(String, nullable=True)
    renewal_item_label = Column(String, nullable=True)
    renewal_patient_key_hash = Column(String, nullable=True)
    renewal_patient_ref = Column(String, nullable=True)

    created_at_utc = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at_utc = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "client_session_id",
            name="uq_assistant_session_tenant_client",
        ),
    )