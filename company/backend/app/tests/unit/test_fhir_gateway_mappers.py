from __future__ import annotations

from app.modules.fhir_gateway.mappers import (
    map_appointment_resource_to_dto,
    map_appointments_to_continuity_signals,
    map_patient_resource_to_dto,
)


def test_map_patient_resource_to_dto_returns_safe_summary() -> None:
    resource = {
        "resourceType": "Patient",
        "id": "patient-123",
        "name": [{"text": "Demo Patient"}],
        "identifier": [
            {
                "system": "urn:ai-hospital-assistant:patient-key:demo",
                "value": "hashed-value",
            }
        ],
    }

    dto = map_patient_resource_to_dto(
        resource,
        tenant_id="demo",
        patient_key_hash="hashed-value",
    )

    assert dto.patientId == "patient-123"
    assert dto.patientRef == "Patient/patient-123"
    assert dto.tenantId == "demo"
    assert dto.patientKeyHash == "hashed-value"
    assert dto.displayName == "Demo Patient"


def test_map_appointment_resource_to_dto_extracts_safe_fields_only() -> None:
    resource = {
        "resourceType": "Appointment",
        "id": "appt-456",
        "status": "booked",
        "start": "2026-04-07T09:00:00Z",
        "end": "2026-04-07T09:30:00Z",
        "identifier": [
            {
                "system": "urn:ai-hospital-assistant:tenant-id",
                "value": "demo",
            }
        ],
        "serviceType": [
            {
                "coding": [
                    {
                        "system": "urn:ai-hospital-assistant:specialty",
                        "code": "cardiology",
                        "display": "Cardiology",
                    }
                ],
                "text": "Cardiology",
            }
        ],
        "participant": [
            {
                "actor": {
                    "reference": "Patient/patient-123",
                    "display": "Demo Patient",
                },
                "status": "accepted",
            },
            {
                "actor": {
                    "reference": "Practitioner/prac-1",
                    "display": "Dr. Ahmed",
                },
                "status": "accepted",
            },
        ],
    }

    dto = map_appointment_resource_to_dto(resource)

    assert dto.appointmentId == "appt-456"
    assert dto.appointmentRef == "Appointment/appt-456"
    assert dto.status == "booked"
    assert dto.startUtc == "2026-04-07T09:00:00Z"
    assert dto.endUtc == "2026-04-07T09:30:00Z"
    assert dto.specialty == "Cardiology"
    assert dto.patientRef == "Patient/patient-123"
    assert dto.practitionerRef == "Practitioner/prac-1"
    assert dto.practitionerDisplay == "Dr. Ahmed"
    assert dto.tenantId == "demo"


def test_continuity_signals_uses_latest_appointment() -> None:
    older = map_appointment_resource_to_dto(
        {
            "resourceType": "Appointment",
            "id": "a1",
            "status": "booked",
            "start": "2026-04-01T09:00:00Z",
            "participant": [
                {
                    "actor": {
                        "reference": "Practitioner/prac-1",
                        "display": "Dr. Ahmed",
                    }
                }
            ],
        }
    )
    newer = map_appointment_resource_to_dto(
        {
            "resourceType": "Appointment",
            "id": "a2",
            "status": "booked",
            "start": "2026-04-05T09:00:00Z",
            "participant": [
                {
                    "actor": {
                        "reference": "Practitioner/prac-2",
                        "display": "Dr. Sara",
                    }
                }
            ],
        }
    )

    signals = map_appointments_to_continuity_signals([older, newer])

    assert signals.hasPriorAppointments is True
    assert signals.totalAppointments == 2
    assert signals.lastAppointmentStartUtc == "2026-04-05T09:00:00Z"
    assert signals.lastPractitionerRef == "Practitioner/prac-2"