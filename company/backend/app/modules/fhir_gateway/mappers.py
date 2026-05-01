from __future__ import annotations

from datetime import datetime, timezone

from typing import Any

from app.modules.fhir_gateway.schemas import (
    AppointmentDTO,
    ContinuitySignalsDTO,
    MedicationRenewalSignalsDTO,
    MedicationRenewalItemDTO,
    PatientSummaryDTO,
    ScheduleDTO,
    SlotDTO,
    MedicationRefillTaskDTO,
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

def extract_patient_emails(resource: dict[str, Any]) -> list[str]:
    telecom = resource.get("telecom")
    if not isinstance(telecom, list):
        return []

    emails: list[str] = []
    seen: set[str] = set()

    for item in telecom:
        if not isinstance(item, dict):
            continue

        if item.get("system") != "email":
            continue

        value = item.get("value")
        if not isinstance(value, str):
            continue

        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        emails.append(normalized)

    return emails

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

        coding = item.get("coding")
        if isinstance(coding, list):
            for coded in coding:
                if not isinstance(coded, dict):
                    continue

                code = coded.get("code")
                if isinstance(code, str) and code.strip():
                    return code.strip()

            for coded in coding:
                if not isinstance(coded, dict):
                    continue

                display = coded.get("display")
                if isinstance(display, str) and display.strip():
                    return display.strip()

        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

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

    emails = extract_patient_emails(resource)

    return PatientSummaryDTO(
        patientId=patient_id or "unknown",
        patientRef=patient_ref,
        tenantId=tenant_id,
        patientKeyHash=patient_key_hash,
        displayName=_first_human_name(resource),
        emails=emails,
        primaryEmail=emails[0] if emails else None,
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

        dispense_request = resource.get("dispenseRequest")
        if not isinstance(dispense_request, dict):
            dispense_request = {}

        validity_period = dispense_request.get("validityPeriod")
        if not isinstance(validity_period, dict):
            validity_period = {}

        refill_status, refill_status_message = _refill_status_for_medication_request(resource)

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
                validityPeriodStart=validity_period.get("start")
                if isinstance(validity_period.get("start"), str)
                else None,
                validityPeriodEnd=validity_period.get("end")
                if isinstance(validity_period.get("end"), str)
                else None,
                numberOfRepeatsAllowed=_safe_int(
                    dispense_request.get("numberOfRepeatsAllowed")
                ),
                quantityText=_safe_quantity_text(dispense_request.get("quantity")),
                expectedSupplyDurationText=_safe_duration_text(
                    dispense_request.get("expectedSupplyDuration")
                ),
                refillStatus=refill_status,
                refillStatusMessage=refill_status_message,
            )
        )

    return MedicationRenewalSignalsDTO(
        patientRef=patient_ref,
        patientFound=patient_ref is not None,
        eligible=len(items) > 0,
        items=items,
    )
    
    
def _safe_quantity_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    quantity_value = value.get("value")
    unit = value.get("unit") or value.get("code")

    if quantity_value is None and not unit:
        return None

    if quantity_value is None:
        return str(unit)

    if unit:
        return f"{quantity_value} {unit}"

    return str(quantity_value)


def _safe_duration_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    duration_value = value.get("value")
    unit = value.get("unit") or value.get("code")

    if duration_value is None and not unit:
        return None

    if duration_value is None:
        return str(unit)

    if unit:
        return f"{duration_value} {unit}"

    return str(duration_value)


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _refill_status_for_medication_request(resource: dict[str, Any]) -> tuple[str, str]:
    status = str(resource.get("status") or "").strip().lower()
    dispense_request = resource.get("dispenseRequest")
    if not isinstance(dispense_request, dict):
        dispense_request = {}

    repeats = _safe_int(dispense_request.get("numberOfRepeatsAllowed"))
    validity = dispense_request.get("validityPeriod")
    if not isinstance(validity, dict):
        validity = {}

    validity_end = validity.get("end") if isinstance(validity.get("end"), str) else None

    if status != "active":
        return (
            "NOT_ACTIVE",
            "This medication request is not active and requires clinical review.",
        )

    if validity_end:
        try:
            validity_end_dt = datetime.fromisoformat(validity_end.replace("Z", "+00:00"))
            if validity_end_dt < datetime.now(timezone.utc):
                return (
                    "EXPIRED_REQUEST",
                    "The source medication request appears expired and requires clinical review.",
                )
        except ValueError:
            return (
                "REQUIRES_CLINICAL_REVIEW",
                "The validity period could not be interpreted and requires clinical review.",
            )

    if repeats is None:
        return (
            "REFILL_RULE_UNKNOWN",
            "Refill repeat rules are not available and clinical review is required.",
        )

    if repeats <= 0:
        return (
            "NO_REPEATS_AUTHORIZED",
            "No repeats are authorized in the source medication request.",
        )

    return (
        "READY_FOR_REFILL_REQUEST",
        "This medication can be submitted as a refill request pending clinical/pharmacy fulfillment.",
    )
    
    
def map_task_resource_to_refill_task_dto(resource: dict[str, Any]) -> MedicationRefillTaskDTO:
    task_id = str(resource.get("id") or "unknown")
    task_ref = f"Task/{task_id}"

    business_status = None
    raw_business_status = resource.get("businessStatus")
    if isinstance(raw_business_status, dict):
        text = raw_business_status.get("text")
        if isinstance(text, str):
            business_status = text

    patient_ref = None
    raw_for = resource.get("for")
    if isinstance(raw_for, dict) and isinstance(raw_for.get("reference"), str):
        patient_ref = raw_for["reference"]

    medication_request_ref = None
    raw_focus = resource.get("focus")
    if isinstance(raw_focus, dict) and isinstance(raw_focus.get("reference"), str):
        medication_request_ref = raw_focus["reference"]

    return MedicationRefillTaskDTO(
        taskId=task_id,
        taskRef=task_ref,
        status=str(resource.get("status") or "unknown"),
        intent=resource.get("intent") if isinstance(resource.get("intent"), str) else None,
        businessStatus=business_status,
        patientRef=patient_ref,
        medicationRequestRef=medication_request_ref,
    )