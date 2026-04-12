from __future__ import annotations

from typing import Any

from app.modules.fhir_gateway.schemas import (
    AppointmentDTO,
    ContinuitySignalsDTO,
    MedicationRenewalSignalsDTO,
    MedicationRenewalItemDTO,
    PatientSummaryDTO,
    ScheduleDTO,
    SlotDTO,
)

TENANT_IDENTIFIER_SYSTEM = "urn:ai-hospital-assistant:tenant-id"
PATIENT_IDENTIFIER_SYSTEM = "urn:tenant-patient-key"


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


def _extract_reference(
    participants: list[dict[str, Any]],
    prefix: str,
) -> tuple[str | None, str | None]:
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


def _extract_actor_reference(
    actors: list[dict[str, Any]],
    prefix: str,
) -> tuple[str | None, str | None]:
    for actor in actors:
        reference = actor.get("reference")
        if not isinstance(reference, str):
            continue

        if reference.startswith(prefix):
            display = actor.get("display")
            return reference, display if isinstance(display, str) else None

    return None, None


def _extract_codeable_concept_text_or_code(value: Any) -> str | None:
    items = value if isinstance(value, list) else [value]

    for item in items:
        if not isinstance(item, dict):
            continue

        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        coding = item.get("coding")
        if not isinstance(coding, list):
            continue

        for coded in coding:
            if not isinstance(coded, dict):
                continue

            display = coded.get("display")
            if isinstance(display, str) and display.strip():
                return display.strip()

            code = coded.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()

    return None


def _extract_specialty(resource: dict[str, Any]) -> str | None:
    specialty = _extract_codeable_concept_text_or_code(resource.get("specialty"))
    if specialty:
        return specialty

    service_type = _extract_codeable_concept_text_or_code(resource.get("serviceType"))
    if service_type:
        return service_type

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


def _extract_schedule_reference(resource: dict[str, Any]) -> str | None:
    schedule = resource.get("schedule")
    if not isinstance(schedule, dict):
        return None

    reference = schedule.get("reference")
    if isinstance(reference, str) and reference.strip():
        return reference.strip()

    return None


def _extract_slot_refs(resource: dict[str, Any]) -> list[str]:
    results: list[str] = []

    slots = resource.get("slot")
    if not isinstance(slots, list):
        return results

    for item in slots:
        if not isinstance(item, dict):
            continue
        reference = item.get("reference")
        if isinstance(reference, str) and reference.strip():
            results.append(reference.strip())

    return results


def _safe_medication_display(resource: dict[str, Any]) -> str:
    medication = resource.get("medicationCodeableConcept")
    if not isinstance(medication, dict):
        medication = {}

    text = medication.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    codings = medication.get("coding")
    if not isinstance(codings, list):
        codings = []

    for coding in codings:
        if not isinstance(coding, dict):
            continue
        display = coding.get("display")
        if isinstance(display, str) and display.strip():
            return display.strip()

    return "Unknown medication"


def _safe_medication_code(resource: dict[str, Any]) -> str | None:
    medication = resource.get("medicationCodeableConcept")
    if not isinstance(medication, dict):
        return None

    codings = medication.get("coding")
    if not isinstance(codings, list):
        return None

    for coding in codings:
        if not isinstance(coding, dict):
            continue
        code = coding.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()

    return None


def _safe_dosage_text(resource: dict[str, Any]) -> str | None:
    dosage = resource.get("dosageInstruction")
    if not isinstance(dosage, list) or not dosage:
        return None

    first = dosage[0]
    if not isinstance(first, dict):
        return None

    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

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


def map_schedule_resource_to_dto(resource: dict[str, Any]) -> ScheduleDTO:
    schedule_id = str(resource.get("id") or "").strip() or "unknown"
    schedule_ref = f"Schedule/{schedule_id}"

    actors = resource.get("actor")
    actor_list = actors if isinstance(actors, list) else []
    practitioner_ref, practitioner_display = _extract_actor_reference(
        actor_list,
        "Practitioner/",
    )

    planning_horizon = resource.get("planningHorizon")
    planning_horizon_start = None
    planning_horizon_end = None
    if isinstance(planning_horizon, dict):
        start = planning_horizon.get("start")
        end = planning_horizon.get("end")
        planning_horizon_start = start if isinstance(start, str) else None
        planning_horizon_end = end if isinstance(end, str) else None

    return ScheduleDTO(
        scheduleId=schedule_id,
        scheduleRef=schedule_ref,
        practitionerRef=practitioner_ref,
        practitionerDisplay=practitioner_display,
        specialty=_extract_specialty(resource),
        tenantId=_extract_tenant_id(resource),
        planningHorizonStartUtc=planning_horizon_start,
        planningHorizonEndUtc=planning_horizon_end,
        active=bool(resource.get("active", True)),
    )


def map_schedule_bundle_to_dtos(bundle: dict[str, Any]) -> list[ScheduleDTO]:
    results: list[ScheduleDTO] = []

    for entry in _entries(bundle):
        resource = _resource_from_entry(entry)
        if resource.get("resourceType") != "Schedule":
            continue
        results.append(map_schedule_resource_to_dto(resource))

    return results


def map_slot_resource_to_dto(
    resource: dict[str, Any],
    *,
    schedule: ScheduleDTO | None = None,
) -> SlotDTO:
    slot_id = str(resource.get("id") or "").strip() or "unknown"
    slot_ref = f"Slot/{slot_id}"
    schedule_ref = _extract_schedule_reference(resource)

    return SlotDTO(
        slotId=slot_id,
        slotRef=slot_ref,
        scheduleRef=schedule_ref,
        practitionerRef=schedule.practitionerRef if schedule else None,
        practitionerDisplay=schedule.practitionerDisplay if schedule else None,
        specialty=_extract_specialty(resource) or (schedule.specialty if schedule else None),
        startUtc=str(resource.get("start") or ""),
        endUtc=str(resource.get("end") or ""),
        status=str(resource.get("status") or "free"),
    )


def map_slot_bundle_to_dtos(
    bundle: dict[str, Any],
    *,
    schedule: ScheduleDTO | None = None,
) -> list[SlotDTO]:
    results: list[SlotDTO] = []

    for entry in _entries(bundle):
        resource = _resource_from_entry(entry)
        if resource.get("resourceType") != "Slot":
            continue
        results.append(map_slot_resource_to_dto(resource, schedule=schedule))

    return results


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
        slotRefs=_extract_slot_refs(resource),
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
            lastPractitionerDisplay=None,
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
        lastPractitionerDisplay=latest.practitionerDisplay,
    )


def map_medication_requests_to_renewal_signals(
    medication_requests: list[dict[str, Any]] | None = None,
) -> MedicationRenewalSignalsDTO:
    if not medication_requests:
        return MedicationRenewalSignalsDTO(
            patientRef=None,
            patientFound=False,
            eligible=False,
            items=[],
        )

    synthetic_bundle = {
        "entry": [
            {"resource": item}
            for item in medication_requests
            if isinstance(item, dict)
        ]
    }

    return map_medication_request_bundle_to_signals(
        patient_ref=None,
        bundle=synthetic_bundle,
    )


def map_medication_request_bundle_to_signals(
    *,
    patient_ref: str | None,
    bundle: dict[str, Any] | None,
) -> MedicationRenewalSignalsDTO:
    if not bundle:
        return MedicationRenewalSignalsDTO(
            patientRef=patient_ref,
            patientFound=patient_ref is not None,
            eligible=False,
            items=[],
        )

    entries = bundle.get("entry")
    if not isinstance(entries, list):
        entries = []

    items: list[MedicationRenewalItemDTO] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        if resource.get("resourceType") != "MedicationRequest":
            continue

        resource_id = resource.get("id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            continue

        items.append(
            MedicationRenewalItemDTO(
                medicationRequestRef=f"MedicationRequest/{resource_id.strip()}",
                medicationDisplay=_safe_medication_display(resource),
                medicationCode=_safe_medication_code(resource),
                status=str(resource.get("status") or "unknown"),
                intent=resource.get("intent") if isinstance(resource.get("intent"), str) else None,
                authoredOn=resource.get("authoredOn")
                if isinstance(resource.get("authoredOn"), str)
                else None,
                dosageText=_safe_dosage_text(resource),
            )
        )

    return MedicationRenewalSignalsDTO(
        patientRef=patient_ref,
        patientFound=patient_ref is not None,
        eligible=len(items) > 0,
        items=items,
    )