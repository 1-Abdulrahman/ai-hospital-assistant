from __future__ import annotations

import pytest

from app.db.models import Event, OtpRecord
from app.modules.otp import service


def test_build_patient_key_hash_includes_identity_type() -> None:
    h1 = service.build_patient_key_hash(
        tenant_id="demo",
        identity_type="saudi_national_id",
        normalized_identity_number="1123456780",
    )
    h2 = service.build_patient_key_hash(
        tenant_id="demo",
        identity_type="iqama",
        normalized_identity_number="1123456780",
    )

    assert h1 != h2


def test_request_otp_success_stores_hashed_otp_and_event(db_session, monkeypatch) -> None:
    sent = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        sent["to_email"] = to_email
        sent["otp"] = otp
        sent["ttl_seconds"] = ttl_seconds

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    result = service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
    )

    assert result["ok"] is True
    assert sent["to_email"] == "patient@example.com"

    record = db_session.query(OtpRecord).first()
    assert record is not None
    assert record.otp_hash != sent["otp"]
    assert record.verified is False

    event = db_session.query(Event).filter(Event.reason_code == "OTP_SENT").first()
    assert event is not None


def test_request_otp_invalid_identity_returns_422_and_logs_event(db_session) -> None:
    with pytest.raises(Exception) as exc:
        service.request_otp_code(
            db=db_session,
            header_tenant_id="demo",
            session_id="session-1",
            client_ip="127.0.0.1",
            body_tenant_id="demo",
            national_id="9999999999",
            email="patient@example.com",
        )

    http_exc = exc.value
    assert http_exc.status_code == 422
    assert http_exc.detail["reasonCode"] == "INVALID_IDENTITY_NUMBER"

    event = db_session.query(Event).filter(Event.reason_code == "INVALID_IDENTITY_NUMBER").first()
    assert event is not None


def test_verify_otp_wrong_code_increments_attempts(db_session, monkeypatch) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
    )

    with pytest.raises(Exception) as exc:
        service.verify_otp_code(
            db=db_session,
            header_tenant_id="demo",
            session_id="session-1",
            client_ip="127.0.0.1",
            body_tenant_id="demo",
            national_id="2123456788",
            email="patient@example.com",
            otp="000000",
        )

    http_exc = exc.value
    assert http_exc.status_code == 400
    assert http_exc.detail["reasonCode"] == "OTP_INVALID"

    record = db_session.query(OtpRecord).first()
    assert record.attempts == 1


def test_verify_otp_success_marks_record_verified(db_session, monkeypatch) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
    )

    result = service.verify_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        otp=captured["otp"],
    )

    assert result["ok"] is True
    assert result["verified"] is True

    record = db_session.query(OtpRecord).first()
    assert record.verified is True