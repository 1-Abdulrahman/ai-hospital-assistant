from __future__ import annotations

import pytest

from app.db.models import Event, OtpRecord
from app.modules.otp import service
from app.modules.fhir_gateway.schemas import PatientSummaryDTO


class FakeFhirClient:
    def __init__(self, patient: PatientSummaryDTO | None = None) -> None:
        self.patient = patient
        self.saved_email_calls: list[dict[str, str]] = []

    async def find_patient_by_identifier(
        self,
        *,
        patient_key_hash: str,
        tenant_id: str | None = None,
    ):
        return self.patient

    async def save_patient_email_if_missing(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
        email: str,
    ):
        self.saved_email_calls.append(
            {
                "tenant_id": tenant_id,
                "patient_key_hash": patient_key_hash,
                "email": email,
            }
        )

        if self.patient is None:
            return None

        if self.patient.emails:
            return self.patient

        updated = self.patient.model_copy(
            update={
                "emails": [email],
                "primaryEmail": email,
            }
        )
        self.patient = updated
        return updated


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


@pytest.mark.asyncio
async def test_request_otp_success_stores_hashed_otp_and_event(db_session, monkeypatch) -> None:
    sent = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        sent["to_email"] = to_email
        sent["otp"] = otp
        sent["ttl_seconds"] = ttl_seconds

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    result = await service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        fhir_client=FakeFhirClient(patient=None),
    )

    assert result["ok"] is True
    assert sent["to_email"] == "patient@example.com"

    record = db_session.query(OtpRecord).first()
    assert record is not None
    assert record.otp_hash != sent["otp"]
    assert record.verified is False

    event = db_session.query(Event).filter(Event.reason_code == "OTP_SENT").first()
    assert event is not None

@pytest.mark.asyncio
async def test_request_otp_invalid_identity_returns_422_and_logs_event(db_session) -> None:
    with pytest.raises(Exception) as exc:
        await service.request_otp_code(
            db=db_session,
            header_tenant_id="demo",
            session_id="session-1",
            client_ip="127.0.0.1",
            body_tenant_id="demo",
            national_id="9999999999",
            email="patient@example.com",
            fhir_client=FakeFhirClient(patient=None),
        )

    http_exc = exc.value
    assert http_exc.status_code == 422
    assert http_exc.detail["reasonCode"] == "INVALID_IDENTITY_NUMBER"

    event = db_session.query(Event).filter(Event.reason_code == "INVALID_IDENTITY_NUMBER").first()
    assert event is not None

@pytest.mark.asyncio
async def test_verify_otp_wrong_code_increments_attempts(db_session, monkeypatch) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    await service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        fhir_client=FakeFhirClient(patient=None),
    )

    with pytest.raises(Exception) as exc:
        await service.verify_otp_code(
            db=db_session,
            header_tenant_id="demo",
            session_id="session-1",
            client_ip="127.0.0.1",
            body_tenant_id="demo",
            national_id="2123456788",
            email="patient@example.com",
            otp="000000",
            fhir_client=FakeFhirClient(patient=None),
        )

    http_exc = exc.value
    assert http_exc.status_code == 400
    assert http_exc.detail["reasonCode"] == "OTP_INVALID"

    record = db_session.query(OtpRecord).first()
    assert record.attempts == 1

@pytest.mark.asyncio
async def test_verify_otp_success_marks_record_verified(db_session, monkeypatch) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    await service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        fhir_client=FakeFhirClient(patient=None),
    )

    result = await service.verify_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        otp=captured["otp"],
        fhir_client=FakeFhirClient(patient=None),
    )


    assert result["ok"] is True
    assert result["verified"] is True

    record = db_session.query(OtpRecord).first()
    assert record.verified is True
    
    
@pytest.mark.asyncio
async def test_request_otp_blocks_mismatched_registered_patient_email(
    db_session,
    monkeypatch,
) -> None:
    sent = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        sent["to_email"] = to_email

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    patient = PatientSummaryDTO(
        patientId="patient-1",
        patientRef="Patient/patient-1",
        tenantId="demo",
        patientKeyHash="hash-value",
        displayName="Demo Patient",
        emails=["registered@example.com"],
        primaryEmail="registered@example.com",
    )

    with pytest.raises(Exception) as exc:
        await service.request_otp_code(
            db=db_session,
            header_tenant_id="demo",
            session_id="session-1",
            client_ip="127.0.0.1",
            body_tenant_id="demo",
            national_id="2123456788",
            email="wrong@example.com",
            fhir_client=FakeFhirClient(patient=patient),
        )

    http_exc = exc.value
    assert http_exc.status_code == 409
    assert http_exc.detail["reasonCode"] == service.EMAIL_MISMATCH_WITH_PATIENT_RECORD
    assert sent == {}

    event = (
        db_session.query(Event)
        .filter(Event.reason_code == service.EMAIL_MISMATCH_WITH_PATIENT_RECORD)
        .first()
    )
    assert event is not None
    
@pytest.mark.asyncio
async def test_request_otp_allows_matching_registered_patient_email(
    db_session,
    monkeypatch,
) -> None:
    sent = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        sent["to_email"] = to_email

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    patient = PatientSummaryDTO(
        patientId="patient-1",
        patientRef="Patient/patient-1",
        tenantId="demo",
        patientKeyHash="hash-value",
        displayName="Demo Patient",
        emails=["patient@example.com"],
        primaryEmail="patient@example.com",
    )

    result = await service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="Patient@Example.com",
        fhir_client=FakeFhirClient(patient=patient),
    )

    assert result["ok"] is True
    assert sent["to_email"] == "patient@example.com"
    
@pytest.mark.asyncio
async def test_verify_otp_saves_email_to_existing_patient_when_missing(
    db_session,
    monkeypatch,
) -> None:
    captured = {}

    def fake_send_otp_email(*, to_email: str, otp: str, ttl_seconds: int) -> None:
        captured["otp"] = otp

    monkeypatch.setattr(service, "send_otp_email", fake_send_otp_email)

    patient = PatientSummaryDTO(
        patientId="patient-1",
        patientRef="Patient/patient-1",
        tenantId="demo",
        patientKeyHash="hash-value",
        displayName="Demo Patient",
        emails=[],
        primaryEmail=None,
    )
    fake_fhir = FakeFhirClient(patient=patient)

    await service.request_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        fhir_client=fake_fhir,
    )

    result = await service.verify_otp_code(
        db=db_session,
        header_tenant_id="demo",
        session_id="session-1",
        client_ip="127.0.0.1",
        body_tenant_id="demo",
        national_id="2123456788",
        email="patient@example.com",
        otp=captured["otp"],
        fhir_client=fake_fhir,
    )

    assert result["verified"] is True
    assert fake_fhir.saved_email_calls
    assert fake_fhir.saved_email_calls[0]["email"] == "patient@example.com"