from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.correlation import correlation_id_ctx
from app.modules.notification.email_sender import (
    EmailDeliveryError,
    render_appointment_confirmation_email,
    render_renewal_confirmation_email,
    send_plain_text_email,
)
from app.modules.observability.emitter import emit_event

REASON_OK = "OK"
REASON_NOTIFICATION_SENT = "NOTIFICATION_SENT"
REASON_EMAIL_DELIVERY_RETRY = "EMAIL_DELIVERY_RETRY"
REASON_EMAIL_DELIVERY_FAILED = "EMAIL_DELIVERY_FAILED"


def _mask_email(email: str) -> str:
    """Return a privacy-preserving version of an email address for event payloads."""
    local, _, domain = email.partition("@")
    if not local or not domain:
        return "***"
    if len(local) == 1:
        return f"{local}***@{domain}"
    return f"{local[:2]}***@{domain}"


def _deliver_email_with_retry(
    *,
    db: Session,
    tenant_id: str,
    session_id: str,
    correlation_id: str | None,
    to_email: str,
    subject: str,
    body: str,
    notification_type: str,
    success_summary: str,
) -> None:
    """Send an email, emit retry/failure events, and keep correlation context intact."""
    token = correlation_id_ctx.set(correlation_id)

    try:
        try:
            send_plain_text_email(
                to_email=to_email,
                subject=subject,
                body=body,
            )
        except EmailDeliveryError:
            # The first failure is treated as transient, so we record a retry event and try once more.
            emit_event(
                db=db,
                tenant_id=tenant_id,
                session_id=session_id,
                actor_type="system",
                event_type="NOTIFICATION_RETRIED",
                outcome="INFO",
                reason_code=REASON_EMAIL_DELIVERY_RETRY,
                payload={
                    "component": "notification",
                    "channel": "email",
                    "notificationType": notification_type,
                    "recipientEmailMasked": _mask_email(to_email),
                    "safeSummary": "Retrying notification email after initial delivery failure.",
                },
            )
            db.commit()

            try:
                send_plain_text_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                )
            except EmailDeliveryError:
                # If the retry fails too, persist a terminal failure event and stop.
                emit_event(
                    db=db,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    actor_type="system",
                    event_type="NOTIFICATION_FAILED",
                    outcome="FAILURE",
                    reason_code=REASON_EMAIL_DELIVERY_FAILED,
                    payload={
                        "component": "notification",
                        "channel": "email",
                        "notificationType": notification_type,
                        "recipientEmailMasked": _mask_email(to_email),
                        "safeSummary": "Notification email delivery failed after one retry.",
                    },
                )
                db.commit()
                return

        emit_event(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_type="system",
            event_type="NOTIFICATION_SENT",
            outcome="SUCCESS",
            reason_code=REASON_NOTIFICATION_SENT,
            payload={
                "component": "notification",
                "channel": "email",
                "notificationType": notification_type,
                "recipientEmailMasked": _mask_email(to_email),
                "safeSummary": success_summary,
            },
        )
        db.commit()
    finally:
        correlation_id_ctx.reset(token)


def _queue_email_notification(
    *,
    background_tasks: BackgroundTasks | None,
    db: Session,
    tenant_id: str,
    session_id: str,
    correlation_id: str | None,
    to_email: str,
    subject: str,
    body: str,
    notification_type: str,
    queued_summary: str,
    success_summary: str,
    extra_payload: dict | None = None,
) -> None:
    """Record the request event, then deliver immediately or defer to background tasks."""
    request_payload = {
        "component": "notification",
        "channel": "email",
        "notificationType": notification_type,
        "recipientEmailMasked": _mask_email(to_email),
        "safeSummary": queued_summary,
    }
    if extra_payload:
        request_payload.update(extra_payload)

    emit_event(
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
        actor_type="system",
        event_type="NOTIFICATION_REQUESTED",
        outcome="INFO",
        reason_code=REASON_OK,
        payload=request_payload,
    )
    db.commit()

    if background_tasks is None:
        # Some callers run outside a FastAPI request lifecycle, so deliver synchronously.
        _deliver_email_with_retry(
            db=db,
            tenant_id=tenant_id,
            session_id=session_id,
            correlation_id=correlation_id,
            to_email=to_email,
            subject=subject,
            body=body,
            notification_type=notification_type,
            success_summary=success_summary,
        )
        return

    background_tasks.add_task(
        _deliver_email_with_retry,
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
        correlation_id=correlation_id,
        to_email=to_email,
        subject=subject,
        body=body,
        notification_type=notification_type,
        success_summary=success_summary,
    )


def queue_appointment_confirmation_email(
    *,
    background_tasks: BackgroundTasks | None,
    db: Session,
    tenant_id: str,
    session_id: str,
    correlation_id: str | None,
    to_email: str,
    booking_reference_id: str,
    doctor_label: str | None,
    specialty_label: str | None,
    date_utc: str | None,
    slot_label: str | None,
) -> None:
    """Queue the appointment confirmation email after the booking flow succeeds."""
    subject, body = render_appointment_confirmation_email(
        booking_reference_id=booking_reference_id,
        correlation_id=correlation_id,
        doctor_label=doctor_label,
        specialty_label=specialty_label,
        date_utc=date_utc,
        slot_label=slot_label,
    )

    _queue_email_notification(
        background_tasks=background_tasks,
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
        correlation_id=correlation_id,
        to_email=to_email,
        subject=subject,
        body=body,
        notification_type="appointment_confirmation",
        queued_summary="Appointment confirmation email queued for delivery.",
        success_summary="Appointment confirmation email sent successfully.",
        extra_payload={"bookingReferenceId": booking_reference_id},
    )


def queue_renewal_confirmation_email(
    *,
    background_tasks: BackgroundTasks | None,
    db: Session,
    tenant_id: str,
    session_id: str,
    correlation_id: str | None,
    to_email: str,
    renewal_item_label: str | None,
    refill_task_ref: str | None = None,
) -> None:
    """Queue the renewal confirmation email after a renewal task is created."""
    subject, body = render_renewal_confirmation_email(
        renewal_item_label=renewal_item_label,
        correlation_id=correlation_id,
        refill_task_ref=refill_task_ref,
    )

    _queue_email_notification(
        background_tasks=background_tasks,
        db=db,
        tenant_id=tenant_id,
        session_id=session_id,
        correlation_id=correlation_id,
        to_email=to_email,
        subject=subject,
        body=body,
        notification_type="renewal_confirmation",
        queued_summary="Renewal confirmation email queued for delivery.",
        success_summary="Renewal confirmation email sent successfully.",
        extra_payload={
            "renewalItemLabel": renewal_item_label,
            "refillTaskRef": refill_task_ref,
        },
    )