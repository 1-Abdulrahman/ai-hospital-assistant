from __future__ import annotations

from app.modules.fhir_gateway.mappers import (
    map_appointment_bundle_to_dtos,
    map_appointment_resource_to_dto,
    map_appointments_to_continuity_signals,
    map_patient_resource_to_dto,
    map_schedule_bundle_to_dtos,
    map_schedule_resource_to_dto,
    map_slot_bundle_to_dtos,
    map_slot_resource_to_dto,
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
        "telecom": [
            {
                "system": "email",
                "value": "Demo.Patient@Example.com",
                "use": "home",
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
    assert dto.emails == ["demo.patient@example.com"]
    assert dto.primaryEmail == "demo.patient@example.com"

def test_map_schedule_resource_to_dto_extracts_safe_fields() -> None:
    resource = {
        "resourceType": "Schedule",
        "id": "sched-cardiology-prac-card-1",
        "active": True,
        "identifier": [
            {
                "system": "urn:ai-hospital-assistant:tenant-id",
                "value": "demo",
            }
        ],
        "specialty": [
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
        "actor": [
            {
                "reference": "Practitioner/prac-card-1",
                "display": "Dr. Lina Alharbi",
            }
        ],
        "planningHorizon": {
            "start": "2026-04-08T00:00:00Z",
            "end": "2026-04-21T23:59:00Z",
        },
    }

    dto = map_schedule_resource_to_dto(resource)

    assert dto.scheduleId == "sched-cardiology-prac-card-1"
    assert dto.scheduleRef == "Schedule/sched-cardiology-prac-card-1"
    assert dto.practitionerRef == "Practitioner/prac-card-1"
    assert dto.practitionerDisplay == "Dr. Lina Alharbi"
    assert dto.specialty == "cardiology"
    assert dto.tenantId == "demo"
    assert dto.planningHorizonStartUtc == "2026-04-08T00:00:00Z"
    assert dto.planningHorizonEndUtc == "2026-04-21T23:59:00Z"
    assert dto.active is True


def test_map_schedule_bundle_to_dtos_handles_empty_bundle() -> None:
    assert map_schedule_bundle_to_dtos({"resourceType": "Bundle"}) == []


def test_map_slot_resource_to_dto_extracts_safe_fields() -> None:
    schedule = map_schedule_resource_to_dto(
        {
            "resourceType": "Schedule",
            "id": "sched-cardiology-prac-card-1",
            "identifier": [
                {
                    "system": "urn:ai-hospital-assistant:tenant-id",
                    "value": "demo",
                }
            ],
            "specialty": [
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
            "actor": [
                {
                    "reference": "Practitioner/prac-card-1",
                    "display": "Dr. Lina Alharbi",
                }
            ],
        }
    )

    resource = {
        "resourceType": "Slot",
        "id": "slot-sched-cardiology-prac-card-1-20260408T0900",
        "schedule": {"reference": "Schedule/sched-cardiology-prac-card-1"},
        "status": "free",
        "start": "2026-04-08T09:00:00Z",
        "end": "2026-04-08T09:30:00Z",
        "specialty": [
            {
                "coding": [{"code": "cardiology", "display": "Cardiology"}],
                "text": "Cardiology",
            }
        ],
    }

    dto = map_slot_resource_to_dto(resource, schedule=schedule)

    assert dto.slotId == "slot-sched-cardiology-prac-card-1-20260408T0900"
    assert dto.slotRef == "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"
    assert dto.scheduleRef == "Schedule/sched-cardiology-prac-card-1"
    assert dto.practitionerRef == "Practitioner/prac-card-1"
    assert dto.practitionerDisplay == "Dr. Lina Alharbi"
    assert dto.specialty == "cardiology"
    assert dto.status == "free"
    assert dto.startUtc == "2026-04-08T09:00:00Z"
    assert dto.endUtc == "2026-04-08T09:30:00Z"


def test_map_slot_bundle_to_dtos_handles_empty_bundle() -> None:
    schedule = map_schedule_resource_to_dto(
        {
            "resourceType": "Schedule",
            "id": "sched-cardiology-prac-card-1",
            "actor": [{"reference": "Practitioner/prac-card-1"}],
        }
    )
    assert map_slot_bundle_to_dtos({"resourceType": "Bundle"}, schedule=schedule) == []


def test_map_appointment_resource_to_dto_extracts_safe_fields_only() -> None:
    resource = {
        "resourceType": "Appointment",
        "id": "appt-456",
        "status": "booked",
        "start": "2026-04-08T09:00:00Z",
        "end": "2026-04-08T09:30:00Z",
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
        "slot": [
            {
                "reference": "Slot/slot-sched-cardiology-prac-card-1-20260408T0900"
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
                    "reference": "Practitioner/prac-card-1",
                    "display": "Dr. Lina Alharbi",
                },
                "status": "accepted",
            },
        ],
    }

    dto = map_appointment_resource_to_dto(resource)

    assert dto.appointmentId == "appt-456"
    assert dto.appointmentRef == "Appointment/appt-456"
    assert dto.status == "booked"
    assert dto.startUtc == "2026-04-08T09:00:00Z"
    assert dto.endUtc == "2026-04-08T09:30:00Z"
    assert dto.specialty == "cardiology"
    assert dto.patientRef == "Patient/patient-123"
    assert dto.practitionerRef == "Practitioner/prac-card-1"
    assert dto.practitionerDisplay == "Dr. Lina Alharbi"
    assert dto.tenantId == "demo"
    assert dto.slotRefs == ["Slot/slot-sched-cardiology-prac-card-1-20260408T0900"]


def test_map_appointment_bundle_to_dtos_handles_empty_bundle() -> None:
    assert map_appointment_bundle_to_dtos({"resourceType": "Bundle"}) == []


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