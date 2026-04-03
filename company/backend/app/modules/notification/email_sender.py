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