import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailDeliveryError(Exception):
    """Raised when SMTP delivery fails.

    Wraps OSError and other SMTP-related exceptions to provide a consistent error
    interface for the rest of the application.
    """


def send_plain_text_email(*, to_email: str, subject: str, body: str) -> None:
    """Send a plain-text email through the configured SMTP server.

    Constructs an EmailMessage, configures it with the app's SMTP settings,
    and sends it with a 5-second timeout to prevent hanging on network issues.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject line.
        body (str): Plain-text email body.

    Raises:
        EmailDeliveryError: If SMTP connection fails or message cannot be sent.
    """

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
    """Send an OTP email with a human-friendly validity window message.

    Converts the raw TTL in seconds to minutes and rounds up for readability.
    Includes a note for demo/local testing to open MailHog for message verification.

    Args:
        to_email (str): Recipient email address.
        otp (str): One-time password to send.
        ttl_seconds (int): Time-to-live in seconds for the OTP.
    """

    # Round up to at least one minute so very short OTP windows still read cleanly.
    ttl_minutes = max(1, ttl_seconds // 60)
    subject = "Your OTP Code"
    body = (
        f"Your OTP is: {otp}\n"
        f"Valid for {ttl_minutes} minutes.\n\n"
        # The MailHog hint keeps local demo flows easy to verify without external SMTP.
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
    """Build the subject and body for an appointment confirmation email.

    Formats booking details into a readable confirmation message. Handles optional
    fields gracefully by providing fallback labels when details are missing.

    Args:
        booking_reference_id (str): Unique identifier for the booking.
        correlation_id (str | None): Optional correlation ID for tracking.
        doctor_label (str | None): Doctor or provider name if assigned.
        specialty_label (str | None): Medical specialty or department.
        date_utc (str | None): Appointment date/time in UTC.
        slot_label (str | None): Time slot reference.

    Returns:
        tuple[str, str]: (subject, body) ready to send via send_plain_text_email().
    """

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
    refill_task_ref: str | None = None,
) -> tuple[str, str]:
    """Build the subject and body for a medication renewal confirmation email.

    Informs the user that their medication refill request has been submitted
    and is pending clinical/pharmacy fulfillment. Emphasizes that the AI assistant
    does not prescribe or dispense medication.

    Args:
        renewal_item_label (str | None): Name of the medication being renewed.
        correlation_id (str | None): Optional correlation ID for tracking.
        refill_task_ref (str | None): Optional FHIR Task reference.

    Returns:
        tuple[str, str]: (subject, body) ready to send via send_plain_text_email().
    """

    subject = "Medication Renewal Refill Request Confirmation"

    body = (
        "Your medication refill request has been submitted successfully and is pending "
        "clinical/pharmacy fulfillment.\n\n"
        f"Medication: {renewal_item_label or 'Selected medication'}\n"
        f"FHIR Task Reference: {refill_task_ref or 'N/A'}\n"
        f"Correlation ID: {correlation_id or 'N/A'}\n\n"
    # Include a message making clear that the AI assistant does not prescribe medication
    "The assistant did not approve, prescribe, or dispense medication. "
    "Clinical/pharmacy fulfillment will continue outside the assistant.\n\n"
        "For demo, open MailHog at http://localhost:8025 to read the message."
    )

    return subject, body