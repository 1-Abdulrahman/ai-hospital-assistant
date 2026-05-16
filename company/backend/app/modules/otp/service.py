import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import (
    RateLimitExceeded,
    build_rate_bucket,
    otp_limiter,
    otp_request_rule,
    otp_verify_rule,
)
from app.db.models import OtpRecord, Tenant
from app.modules.notification.email_sender import EmailDeliveryError, send_otp_email
from app.modules.observability.emitter import emit_event
from app.modules.otp.validators import (
    IdentityValidationError,
    validate_national_id_and_infer_type,
)

from app.modules.fhir_gateway.client import FhirClient
from app.modules.fhir_gateway.reason_codes import FhirGatewayError
from app.modules.fhir_gateway.schemas import PatientSummaryDTO


EMAIL_MISMATCH_WITH_PATIENT_RECORD = "EMAIL_MISMATCH_WITH_PATIENT_RECORD"
PATIENT_CONTACT_VERIFICATION_UNAVAILABLE = "PATIENT_CONTACT_VERIFICATION_UNAVAILABLE"


def _raise_http_error(
    *,
    status_code: int,
    message: str,
    reason_code: str,
    details: str | None = None,
) -> None:
    """Raise the API error shape used by OTP endpoints."""
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "reasonCode": reason_code,
            **({"details": details} if details else {}),
        },
    )


def _utcnow() -> datetime:
    """Return the current UTC timestamp for OTP comparisons."""
    return datetime.utcnow()


def hmac_hex(secret: str, value: str) -> str:
    """Compute a stable SHA-256 HMAC digest as a hex string."""
    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def normalize_email(email: str) -> str:
    """Normalize user input before comparing or persisting email addresses."""
    cleaned = email.strip().lower()
    if not cleaned:
        _raise_http_error(
            status_code=422,
            message="Email is required.",
            reason_code="INVALID_REQUEST",
        )
    return cleaned


def ensure_tenant_header_matches_body(*, header_tenant_id: str, body_tenant_id: str) -> None:
    """Reject requests where the tenant header and payload disagree."""
    if header_tenant_id != body_tenant_id:
        _raise_http_error(
            status_code=400,
            message="Tenant header and body must match.",
            reason_code="INVALID_REQUEST",
        )


def ensure_tenant_exists(*, db: Session, tenant_id: str) -> None:
    """Confirm the tenant exists before processing any OTP work."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        _raise_http_error(
            status_code=404,
            message="Tenant was not found.",
            reason_code="TENANT_NOT_FOUND",
        )


def build_patient_key_hash(
    *,
    tenant_id: str,
    identity_type: str,
    normalized_identity_number: str,
) -> str:
    """Derive the opaque patient lookup key used across OTP and FHIR flows."""
    return hmac_hex(
        settings.otp_secret,
        f"{tenant_id}:{identity_type}:{normalized_identity_number}",
    )


async def ensure_patient_email_allows_otp_or_raise(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    patient_key_hash: str,
    normalized_email: str,
    fhir_client: FhirClient | None = None,
) -> PatientSummaryDTO | None:
    """Verify that the submitted email is allowed for the matched patient record.

    If the FHIR gateway cannot be reached, the request fails closed so OTPs are
    not issued against an unverified contact method.
    """
    client = fhir_client or FhirClient()

    try:
        patient = await client.find_patient_by_identifier(
            patient_key_hash=patient_key_hash,
            tenant_id=tenant_id,
        )
    except FhirGatewayError as exc:
        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="OTP_REQUEST",
            outcome="FAILURE",
            reason_code=PATIENT_CONTACT_VERIFICATION_UNAVAILABLE,
            payload={
                "component": "otp",
                "safeSummary": "FHIR patient contact verification could not be completed.",
                "fhirReasonCode": exc.reason_code,
            },
        )
        db.commit()
        _raise_http_error(
            status_code=503,
            message="Patient contact verification is temporarily unavailable. Please try again later.",
            reason_code=PATIENT_CONTACT_VERIFICATION_UNAVAILABLE,
        )

    if not isinstance(patient, PatientSummaryDTO):
        return None

    # Normalize the stored FHIR contacts before comparing user input against them.
    registered_emails = {
        item.strip().lower()
        for item in patient.emails
        if item and item.strip()
    }

    if registered_emails and normalized_email not in registered_emails:
        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_REQUEST",
            outcome="FAILURE",
            reason_code=EMAIL_MISMATCH_WITH_PATIENT_RECORD,
            payload={
                "component": "otp",
                "safeSummary": "Rejected OTP request because submitted email did not match registered patient contact.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=409,
            message="The email address does not match the patient profile. Please use the registered email or contact the front desk to update your contact information.",
            reason_code=EMAIL_MISMATCH_WITH_PATIENT_RECORD,
        )

    return patient


async def save_verified_email_to_patient_if_missing(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    patient_key_hash: str,
    normalized_email: str,
    fhir_client: FhirClient | None = None,
) -> None:
    """Persist the verified email back to FHIR when the profile has no match.

    This is intentionally best effort. OTP verification must succeed even when
    the downstream profile update cannot be completed.
    """
    client = fhir_client or FhirClient()

    try:
        updated = await client.save_patient_email_if_missing(
            tenant_id=tenant_id,
            patient_key_hash=patient_key_hash,
            email=normalized_email,
        )
    except FhirGatewayError as exc:
        # Verification is already complete, so the profile sync only emits telemetry.
        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="OTP_VERIFY",
            outcome="INFO",
            reason_code="PATIENT_EMAIL_SAVE_SKIPPED",
            payload={
                "component": "otp",
                "safeSummary": "OTP was verified, but patient email could not be saved to FHIR.",
                "fhirReasonCode": exc.reason_code,
            },
        )
        db.commit()
        return

    if updated is not None and normalized_email in updated.emails:
        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="OTP_VERIFY",
            outcome="INFO",
            reason_code="PATIENT_EMAIL_SAVED",
            payload={
                "component": "otp",
                "safeSummary": "Verified email was saved to FHIR patient contact details.",
            },
        )
        db.commit()


async def request_otp_code(
    *,
    db: Session,
    header_tenant_id: str,
    session_id: str,
    client_ip: str,
    body_tenant_id: str,
    national_id: str,
    email: str,
    fhir_client: FhirClient | None = None,
) -> dict:
    """Validate the request context, issue a fresh OTP, and send it by email."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    normalized_email = normalize_email(email)
    now = _utcnow()

    try:
        normalized_identity_number, identity_type = validate_national_id_and_infer_type(
            national_id
        )
    except IdentityValidationError as exc:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_REQUEST",
            outcome="FAILURE",
            reason_code="INVALID_IDENTITY_NUMBER",
            payload={
                "component": "otp",
                "safeSummary": "Rejected invalid identity number before OTP generation.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=422,
            message="National ID, iqama, or Border ID is invalid.",
            reason_code="INVALID_IDENTITY_NUMBER",
            details=exc.message,
        )

    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    await ensure_patient_email_allows_otp_or_raise(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        patient_key_hash=patient_key_hash,
        normalized_email=normalized_email,
        fhir_client=fhir_client,
    )

    rate_bucket = build_rate_bucket(
        action="otp-request",
        client_ip=client_ip,
        patient_key_hash=patient_key_hash,
    )

    try:
        otp_limiter.hit(bucket=rate_bucket, rule=otp_request_rule)
    except RateLimitExceeded as exc:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_REQUEST",
            outcome="FAILURE",
            reason_code="OTP_REQUEST_RATE_LIMITED",
            payload={
                "component": "otp",
                "safeSummary": "OTP request rate limit reached.",
                "retryAfterSeconds": exc.retry_after_seconds,
            },
        )
        db.commit()
        _raise_http_error(
            status_code=429,
            message="Too many OTP requests. Please wait and try again.",
            reason_code="OTP_REQUEST_RATE_LIMITED",
            details=f"Retry after {exc.retry_after_seconds} seconds.",
        )

    existing_open_records = (
        db.query(OtpRecord)
        .filter(
            OtpRecord.tenant_id == body_tenant_id,
            OtpRecord.session_id == session_id,
            OtpRecord.patient_key_hash == patient_key_hash,
            OtpRecord.email == normalized_email,
            OtpRecord.verified.is_(False),
            OtpRecord.expires_at > now,
        )
        .all()
    )

    # Retire any still-open OTPs so only the newest code can be used.
    for rec in existing_open_records:
        rec.expires_at = now

    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hmac_hex(settings.otp_secret, f"{patient_key_hash}:{otp}")

    new_record = OtpRecord(
        id=uuid.uuid4().hex,
        tenant_id=body_tenant_id,
        session_id=session_id,
        patient_key_hash=patient_key_hash,
        email=normalized_email,
        otp_hash=otp_hash,
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        attempts=0,
        verified=False,
    )

    db.add(new_record)
    db.commit()

    try:
        send_otp_email(
            to_email=normalized_email,
            otp=otp,
            ttl_seconds=settings.otp_ttl_seconds,
        )
    except EmailDeliveryError:
        new_record.expires_at = now

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="OTP_REQUEST",
            outcome="FAILURE",
            reason_code="EMAIL_DELIVERY_FAILED",
            payload={
                "component": "notification",
                "safeSummary": "OTP email delivery failed.",
            },
        )
        db.commit()

        _raise_http_error(
            status_code=503,
            message="OTP could not be delivered. Please try again.",
            reason_code="EMAIL_DELIVERY_FAILED",
        )

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        actor_type="system",
        event_type="OTP_REQUEST",
        outcome="SUCCESS",
        reason_code="OTP_SENT",
        payload={
            "component": "notification",
            "safeSummary": "OTP email sent successfully.",
        },
    )
    db.commit()

    return {
        "ok": True,
        "message": "OTP sent. For demo, open MailHog at http://localhost:8025.",
        "expiresIn": settings.otp_ttl_seconds,
    }


async def verify_otp_code(
    *,
    db: Session,
    header_tenant_id: str,
    session_id: str,
    client_ip: str,
    body_tenant_id: str,
    national_id: str,
    email: str,
    otp: str,
    fhir_client: FhirClient | None = None,
) -> dict:
    """Validate an OTP submission and mark the matching record as verified."""
    ensure_tenant_header_matches_body(
        header_tenant_id=header_tenant_id,
        body_tenant_id=body_tenant_id,
    )
    ensure_tenant_exists(db=db, tenant_id=body_tenant_id)

    normalized_email = normalize_email(email)
    now = _utcnow()

    try:
        normalized_identity_number, identity_type = validate_national_id_and_infer_type(
            national_id
        )
    except IdentityValidationError as exc:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="INVALID_IDENTITY_NUMBER",
            payload={
                "component": "otp",
                "safeSummary": "Rejected invalid identity number during OTP verification.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=422,
            message="National ID, iqama, or Border ID is invalid.",
            reason_code="INVALID_IDENTITY_NUMBER",
            details=exc.message,
        )

    patient_key_hash = build_patient_key_hash(
        tenant_id=body_tenant_id,
        identity_type=identity_type,
        normalized_identity_number=normalized_identity_number,
    )

    rate_bucket = build_rate_bucket(
        action="otp-verify",
        client_ip=client_ip,
        patient_key_hash=patient_key_hash,
    )

    try:
        otp_limiter.hit(bucket=rate_bucket, rule=otp_verify_rule)
    except RateLimitExceeded as exc:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="OTP_VERIFY_RATE_LIMITED",
            payload={
                "component": "otp",
                "safeSummary": "OTP verification rate limit reached.",
                "retryAfterSeconds": exc.retry_after_seconds,
            },
        )
        db.commit()
        _raise_http_error(
            status_code=429,
            message="Too many OTP verification attempts. Please wait and try again.",
            reason_code="OTP_VERIFY_RATE_LIMITED",
            details=f"Retry after {exc.retry_after_seconds} seconds.",
        )

    latest_record = (
        db.query(OtpRecord)
        .filter(
            OtpRecord.tenant_id == body_tenant_id,
            OtpRecord.session_id == session_id,
            OtpRecord.patient_key_hash == patient_key_hash,
            OtpRecord.email == normalized_email,
        )
        .order_by(OtpRecord.expires_at.desc())
        .first()
    )

    if latest_record is None:
        # No record means the caller is outside the active OTP window.
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="OTP_NOT_FOUND",
            payload={
                "component": "otp",
                "safeSummary": "No OTP record found for the submitted patient context.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=400,
            message="OTP is invalid or expired.",
            reason_code="OTP_NOT_FOUND",
        )

    if latest_record.verified:
        # Idempotent success keeps repeated submits from surfacing as errors.
        return {
            "ok": True,
            "verified": True,
            "message": "OTP already verified.",
        }

    if now > latest_record.expires_at:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="OTP_EXPIRED",
            payload={
                "component": "otp",
                "safeSummary": "Submitted OTP has expired.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=400,
            message="OTP has expired. Request a new code.",
            reason_code="OTP_EXPIRED",
        )

    if latest_record.attempts >= settings.otp_max_attempts:
        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="OTP_MAX_ATTEMPTS_REACHED",
            payload={
                "component": "otp",
                "safeSummary": "Maximum OTP attempts reached.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=429,
            message="Too many OTP attempts. Request a new code.",
            reason_code="OTP_MAX_ATTEMPTS_REACHED",
        )

    expected_hash = hmac_hex(settings.otp_secret, f"{patient_key_hash}:{otp.strip()}")

    if not hmac.compare_digest(expected_hash, latest_record.otp_hash):
        latest_record.attempts += 1

        emit_event(
            db=db,
            tenant_id=body_tenant_id,
            session_id=session_id,
            actor_type="patient",
            event_type="OTP_VERIFY",
            outcome="FAILURE",
            reason_code="OTP_INVALID",
            payload={
                "component": "otp",
                "safeSummary": "Submitted OTP did not match the latest active OTP.",
            },
        )
        db.commit()
        _raise_http_error(
            status_code=400,
            message="OTP is invalid or expired.",
            reason_code="OTP_INVALID",
        )

    latest_record.verified = True

    emit_event(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        actor_type="patient",
        event_type="OTP_VERIFY",
        outcome="SUCCESS",
        reason_code="OTP_VERIFIED",
        payload={
            "component": "otp",
            "safeSummary": "OTP verified successfully.",
        },
    )
    db.commit()

    # Updating the patient email is a post-verification convenience, not part of auth.
    await save_verified_email_to_patient_if_missing(
        db=db,
        tenant_id=body_tenant_id,
        session_id=session_id,
        patient_key_hash=patient_key_hash,
        normalized_email=normalized_email,
        fhir_client=fhir_client,
    )

    return {
        "ok": True,
        "verified": True,
        "message": "OTP verified.",
    }