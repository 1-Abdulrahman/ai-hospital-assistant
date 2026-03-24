from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)  # demo-tenant or demo
    name = Column(String, nullable=False)


class PortalUser(Base):
    __tablename__ = "portal_users"

    id = Column(String, primary_key=True)  # uuid
    tenant_id = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="admin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_portal_email"),
    )


class OtpRecord(Base):
    __tablename__ = "otp_records"

    id = Column(String, primary_key=True)  # uuid
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    patient_key_hash = Column(String, nullable=False)  # hashed iqama / national id surrogate
    email = Column(String, nullable=False)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    verified = Column(Boolean, nullable=False, default=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)  # uuid
    ts_utc = Column(DateTime, nullable=False, default=datetime.utcnow)
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    correlation_id = Column(String, nullable=False)
    actor_type = Column(String, nullable=False)  # patient, system, admin
    event_type = Column(String, nullable=False)
    outcome = Column(String, nullable=False)  # SUCCESS, FAILURE, INFO
    reason_code = Column(String, nullable=True)
    payload_json = Column(Text, nullable=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)  # header value
    tenant_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)
    result_json = Column(Text, nullable=False)