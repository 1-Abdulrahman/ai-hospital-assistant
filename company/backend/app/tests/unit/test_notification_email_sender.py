from app.modules.notification.email_sender import (
    render_appointment_confirmation_email,
    render_renewal_confirmation_email,
)


def test_render_appointment_confirmation_email_contains_expected_fields() -> None:
    subject, body = render_appointment_confirmation_email(
        booking_reference_id="Appointment/appt-1",
        correlation_id="corr-123",
        doctor_label="Dr. Lina Alharbi",
        specialty_label="Cardiology",
        date_utc="2026-04-12T09:00:00Z",
        slot_label="Slot/slot-1",
    )

    assert "Appointment Confirmation" in subject
    assert "Appointment/appt-1" in body
    assert "corr-123" in body
    assert "Dr. Lina Alharbi" in body
    assert "Cardiology" in body
    assert "2026-04-12T09:00:00Z" in body
    assert "Slot/slot-1" in body


def test_render_renewal_confirmation_email_contains_expected_fields() -> None:
    subject, body = render_renewal_confirmation_email(
        renewal_item_label="Metformin",
        correlation_id="corr-456",
    )

    assert "Medication Renewal Request Confirmation" in subject
    assert "Metformin" in body
    assert "corr-456" in body