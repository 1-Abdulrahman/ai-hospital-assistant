import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailDeliveryError(Exception):
    pass


def send_plain_text_email(*, to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
            smtp.send_message(message)
    except OSError as exc:
        raise EmailDeliveryError("Email delivery failed.") from exc


def send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
    ttl_minutes = max(1, ttl_seconds // 60)
    subject = "Your OTP Code"
    body = (
        f"Your OTP is: {otp}\n"
        f"Valid for {ttl_minutes} minutes.\n\n"
        "For demo, open MailHog at http://localhost:8025 to read the message."
    )
    send_plain_text_email(to_email=to_email, subject=subject, body=body)


def render_appointment_confirmation_email(
    *,
    booking_reference_id: str,
    correlation_id: str | None,
    doctor_label: str | None,
    specialty_label: str | None,
    date_utc: str | None,
    slot_label: str | None,
) -> tuple[str, str]:
    subject = f"Appointment Confirmation - {specialty_label or 'Hospital Visit'}"

    body = (
        "Your appointment has been booked successfully.\n\n"
        f"Booking reference: {booking_reference_id}\n"
        f"Correlation ID: {correlation_id or 'N/A'}\n"
        f"Doctor: {doctor_label or 'Assigned provider'}\n"
        f"Specialty: {specialty_label or 'N/A'}\n"
        f"Date/Time (UTC): {date_utc or 'N/A'}\n"
        f"Slot reference: {slot_label or 'N/A'}\n\n"
        "For demo, open MailHog at http://localhost:8025 to read the message."
    )

    return subject, body


def render_renewal_confirmation_email(
    *,
    renewal_item_label: str | None,
    correlation_id: str | None,
) -> tuple[str, str]:
    subject = "Medication Renewal Request Confirmation"

    body = (
        "Your medication renewal request has been recorded successfully.\n\n"
        f"Medication: {renewal_item_label or 'Selected medication'}\n"
        f"Correlation ID: {correlation_id or 'N/A'}\n\n"
        "For demo, open MailHog at http://localhost:8025 to read the message."
    )

    return subject, body