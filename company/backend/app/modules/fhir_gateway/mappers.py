from __future__ import annotations

from typing import Any

from app.modules.fhir_gateway.schemas import (
    AppointmentDTO,
    ContinuitySignalsDTO,
    MedicationRenewalSignalsDTO,
    PatientSummaryDTO,
    SlotDTO,
)

TENANT_IDENTIFIER_SYSTEM = "urn:ai-hospital-assistant:tenant-id"


def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = bundle.get("entry")
    if not isinstance(raw_entries, list):
        return []
    return [entry for entry in raw_entries if isinstance(entry, dict)]


def _resource_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    resource = entry.get("resource")
    if isinstance(resource, dict):
        return resource
    return {}


def _first_human_name(resource: dict[str, Any]) -> str | None:
    names = resource.get("name")
    if not isinstance(names, list) or not names:
        return None

    first = names[0]
    if not isinstance(first, dict):
        return None

    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    given = first.get("given") or []
    family = first.get("family")
    parts: list[str] = []

    if isinstance(given, list):
        parts.extend(str(x).strip() for x in given if str(x).strip())

    if isinstance(family, str) and family.strip():
        parts.append(family.strip())

    full_name = " ".join(parts).strip()
    return full_name or None


def _extract_reference(participants: list[dict[str, Any]], prefix: str) -> tuple[str | None, str | None]:
    for participant in participants:
        actor = participant.get("actor")
        if not isinstance(actor, dict):
            continue

        reference = actor.get("reference")
        if not isinstance(reference, str):
            continue

        if reference.startswith(prefix):
            display = actor.get("display")
            return reference, display if isinstance(display, str) else None

    return None, None


def _extract_specialty(resource: dict[str, Any]) -> str | None:
    service_type = resource.get("serviceType")
    if not isinstance(service_type, list) or not service_type:
        return None

    first = service_type[0]
    if not isinstance(first, dict):
        return None

    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    coding = first.get("coding")
    if not isinstance(coding, list) or not coding:
        return None

    first_coding = coding[0]
    if not isinstance(first_coding, dict):
        return None

    display = first_coding.get("display")
    if isinstance(display, str) and display.strip():
        return display.strip()

    code = first_coding.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()

    return None


def _extract_tenant_id(resource: dict[str, Any]) -> str | None:
    identifiers = resource.get("identifier")
    if not isinstance(identifiers, list):
        return None

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        if identifier.get("system") == TENANT_IDENTIFIER_SYSTEM:
            value = identifier.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def map_patient_resource_to_dto(
    resource: dict[str, Any],
    *,
    tenant_id: str,
    patient_key_hash: str,
) -> PatientSummaryDTO:
    patient_id = str(resource.get("id") or "").strip()
    patient_ref = f"Patient/{patient_id}" if patient_id else "Patient/unknown"

    return PatientSummaryDTO(
        patientId=patient_id or "unknown",
        patientRef=patient_ref,
        tenantId=tenant_id,
        patientKeyHash=patient_key_hash,
        displayName=_first_human_name(resource),
    )


def map_appointment_resource_to_dto(resource: dict[str, Any]) -> AppointmentDTO:
    appointment_id = str(resource.get("id") or "").strip()
    appointment_ref = f"Appointment/{appointment_id}" if appointment_id else "Appointment/unknown"

    participants = resource.get("participant")
    participant_list = participants if isinstance(participants, list) else []

    patient_ref, patient_display = _extract_reference(participant_list, "Patient/")
    practitioner_ref, practitioner_display = _extract_reference(participant_list, "Practitioner/")

    return AppointmentDTO(
        appointmentId=appointment_id or "unknown",
        appointmentRef=appointment_ref,
        status=str(resource.get("status") or "unknown"),
        startUtc=resource.get("start"),
        endUtc=resource.get("end"),
        specialty=_extract_specialty(resource),
        practitionerRef=practitioner_ref,
        practitionerDisplay=practitioner_display,
        patientRef=patient_ref,
        patientDisplay=patient_display,
        tenantId=_extract_tenant_id(resource),
    )


def map_appointment_bundle_to_dtos(bundle: dict[str, Any]) -> list[AppointmentDTO]:
    results: list[AppointmentDTO] = []

    for entry in _entries(bundle):
        resource = _resource_from_entry(entry)
        if resource.get("resourceType") != "Appointment":
            continue
        results.append(map_appointment_resource_to_dto(resource))

    return results


def map_appointments_to_continuity_signals(
    appointments: list[AppointmentDTO],
) -> ContinuitySignalsDTO:
    if not appointments:
        return ContinuitySignalsDTO(
            hasPriorAppointments=False,
            totalAppointments=0,
            lastAppointmentStartUtc=None,
            lastPractitionerRef=None,
        )

    sorted_items = sorted(
        appointments,
        key=lambda item: item.startUtc or "",
        reverse=True,
    )
    latest = sorted_items[0]

    return ContinuitySignalsDTO(
        hasPriorAppointments=True,
        totalAppointments=len(appointments),
        lastAppointmentStartUtc=latest.startUtc,
        lastPractitionerRef=latest.practitionerRef,
    )


def map_medication_requests_to_renewal_signals(
    medication_requests: list[dict[str, Any]] | None = None,
) -> MedicationRenewalSignalsDTO:
    if not medication_requests:
        return MedicationRenewalSignalsDTO(
            eligible=False,
            lastMedicationRequestDateUtc=None,
            note="Medication renewal analysis is not enabled in the MVP.",
        )

    authored_on_values: list[str] = []

    for item in medication_requests:
        if not isinstance(item, dict):
            continue
        authored_on = item.get("authoredOn")
        if isinstance(authored_on, str) and authored_on.strip():
            authored_on_values.append(authored_on.strip())

    latest = max(authored_on_values) if authored_on_values else None

    return MedicationRenewalSignalsDTO(
        eligible=latest is not None,
        lastMedicationRequestDateUtc=latest,
        note="Medication renewal signal is derived from local FHIR resources.",
    )


def map_slot_resource_to_dto(
    resource: dict[str, Any],
    *,
    practitioner_ref: str | None = None,
    practitioner_display: str | None = None,
    specialty: str | None = None,
) -> SlotDTO:
    slot_id = str(resource.get("id") or "").strip() or "unknown"

    return SlotDTO(
        slotId=slot_id,
        practitionerRef=practitioner_ref,
        practitionerDisplay=practitioner_display,
        specialty=specialty,
        startUtc=str(resource.get("start") or ""),
        endUtc=str(resource.get("end") or ""),
        status=str(resource.get("status") or "free"),
    )