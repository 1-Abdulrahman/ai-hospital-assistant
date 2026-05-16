"""FHIR Resource Mappers Module.

This module provides functions to map FHIR (Fast Healthcare Interoperability Resources)
resources and bundles to domain-specific Data Transfer Objects (DTOs) used throughout
the hospital assistant application. It handles safe extraction of data from FHIR structures
with extensive type checking and validation.
"""
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

# FHIR identifier system URIs for tenant and patient identification
TENANT_IDENTIFIER_SYSTEM = "urn:ai-hospital-assistant:tenant-id"
PATIENT_IDENTIFIER_SYSTEM = "urn:tenant-patient-key"


def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract validated entries from a FHIR bundle.
    
    Args:
        bundle: FHIR bundle dictionary.
        
    Returns:
        List of valid entry dictionaries, or empty list if bundle has no entries.
    """
    raw_entries = bundle.get("entry")
    if not isinstance(raw_entries, list):
        return []
    return [entry for entry in raw_entries if isinstance(entry, dict)]


def _resource_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract the resource object from a FHIR bundle entry.
    
    Args:
        entry: A FHIR bundle entry dictionary.
        
    Returns:
        The resource dictionary if present and valid, otherwise empty dict.
    """
    resource = entry.get("resource")
    if isinstance(resource, dict):
        return resource
    return {}


def _first_human_name(resource: dict[str, Any]) -> str | None:
    """Extract the first human name from a FHIR resource.
    
    Attempts to use the pre-formatted 'text' field first, then constructs
    the name from given and family name components if needed.
    
    Args:
        resource: FHIR Patient or Practitioner resource.
        
    Returns:
        The human-readable name, or None if no name is available.
    """
    names = resource.get("name")
    if not isinstance(names, list) or not names:
        return None

    first = names[0]
    if not isinstance(first, dict):
        return None

    # Use pre-formatted text if available
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    # Otherwise construct from given and family components
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
    """Extract unique email addresses from a FHIR Patient or Practitioner resource.
    
    Normalizes emails to lowercase and removes duplicates. Only includes
    telecom entries with system='email'.
    
    Args:
        resource: FHIR Patient or Practitioner resource.
        
    Returns:
        List of unique, normalized email addresses.
    """
    telecom = resource.get("telecom")
    if not isinstance(telecom, list):
        return []

    emails: list[str] = []
    seen: set[str] = set()  # Track seen emails to avoid duplicates

    for item in telecom:
        if not isinstance(item, dict):
            continue

        # Only process email system entries
        if item.get("system") != "email":
            continue

        value = item.get("value")
        if not isinstance(value, str):
            continue

        # Normalize to lowercase and strip whitespace
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
    """Extract the first reference matching a prefix from participant list.
    
    Args:
        participants: List of FHIR participant objects.
        prefix: Resource type prefix to match (e.g., 'Patient/', 'Practitioner/').
        
    Returns:
        Tuple of (reference, display_name) or (None, None) if not found.
    """
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
    """Extract the first actor reference matching a prefix from actor list.
    
    Similar to _extract_reference but operates on actor objects directly.
    
    Args:
        actors: List of FHIR actor objects.
        prefix: Resource type prefix to match (e.g., 'Patient/', 'Practitioner/').
        
    Returns:
        Tuple of (reference, display_name) or (None, None) if not found.
    """
    for actor in actors:
        reference = actor.get("reference")
        if not isinstance(reference, str):
            continue

        if reference.startswith(prefix):
            display = actor.get("display")
            return reference, display if isinstance(display, str) else None

    return None, None


def _extract_codeable_concept_text_or_code(value: Any) -> str | None:
    """Extract text or code from FHIR CodeableConcept, with fallback priority.
    
    Search priority:
    1. Pre-formatted text field
    2. Coding code (first available)
    3. Coding display (first available)
    
    Args:
        value: A FHIR CodeableConcept object or list of CodeableConcept objects.
        
    Returns:
        Extracted text/code string or None if nothing valid found.
    """
    items = value if isinstance(value, list) else [value]

    for item in items:
        if not isinstance(item, dict):
            continue

        coding = item.get("coding")
        if isinstance(coding, list):
            # First pass: try to get code
            for coded in coding:
                if not isinstance(coded, dict):
                    continue

                code = coded.get("code")
                if isinstance(code, str) and code.strip():
                    return code.strip()

            # Second pass: try to get display
            for coded in coding:
                if not isinstance(coded, dict):
                    continue

                display = coded.get("display")
                if isinstance(display, str) and display.strip():
                    return display.strip()

        # Fallback to text field
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    return None


def _extract_specialty(resource: dict[str, Any]) -> str | None:
    """Extract specialty information from a FHIR resource.
    
    Attempts to find specialty from either specialty or serviceType field.
    
    Args:
        resource: FHIR Schedule or Appointment resource.
        
    Returns:
        Specialty text/code or None if not found.
    """
    specialty = _extract_codeable_concept_text_or_code(resource.get("specialty"))
    if specialty:
        return specialty

    service_type = _extract_codeable_concept_text_or_code(resource.get("serviceType"))
    if service_type:
        return service_type

    return None


def _extract_tenant_id(resource: dict[str, Any]) -> str | None:
    """Extract tenant ID from resource identifiers.
    
    Searches for identifier with system matching TENANT_IDENTIFIER_SYSTEM.
    
    Args:
        resource: FHIR resource with identifiers.
        
    Returns:
        Tenant ID string or None if not found.
    """
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
    """Extract schedule reference from a FHIR Slot resource.
    
    Args:
        resource: FHIR Slot resource.
        
    Returns:
        Schedule reference string or None if not found.
    """
    schedule = resource.get("schedule")
    if not isinstance(schedule, dict):
        return None

    reference = schedule.get("reference")
    if isinstance(reference, str) and reference.strip():
        return reference.strip()

    return None


def _extract_slot_refs(resource: dict[str, Any]) -> list[str]:
    """Extract all slot references from a FHIR resource.
    
    Args:
        resource: FHIR Appointment resource.
        
    Returns:
        List of slot reference strings.
    """
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
    """Extract human-readable medication display name from a MedicationRequest.
    
    Attempts to extract from text field first, then from coding display.
    Returns a safe default if extraction fails.
    
    Args:
        resource: FHIR MedicationRequest resource.
        
    Returns:
        Medication display name string (never None).
    """
    medication = resource.get("medicationCodeableConcept")
    if not isinstance(medication, dict):
        medication = {}

    # Try formatted text first
    text = medication.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    # Then try coding display
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
    """Extract medication code from a MedicationRequest.
    
    Args:
        resource: FHIR MedicationRequest resource.
        
    Returns:
        Medication code string or None if not found.
    """
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
    """Extract dosage instructions text from a MedicationRequest.
    
    Retrieves text from the first dosage instruction entry.
    
    Args:
        resource: FHIR MedicationRequest resource.
        
    Returns:
        Dosage instruction text or None if not found.
    """
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
    """Map a FHIR Patient resource to a PatientSummaryDTO.
    
    Args:
        resource: FHIR Patient resource.
        tenant_id: Associated tenant ID.
        patient_key_hash: Hash of the patient's encryption key.
        
    Returns:
        PatientSummaryDTO with extracted patient information.
    """
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
    """Map a FHIR Schedule resource to a ScheduleDTO.
    
    Args:
        resource: FHIR Schedule resource.
        
    Returns:
        ScheduleDTO with extracted schedule information.
    """
    schedule_id = str(resource.get("id") or "").strip() or "unknown"
    schedule_ref = f"Schedule/{schedule_id}"

    actors = resource.get("actor")
    actor_list = actors if isinstance(actors, list) else []
    practitioner_ref, practitioner_display = _extract_actor_reference(
        actor_list,
        "Practitioner/",
    )

    # Extract planning horizon time boundaries
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
    """Map all Schedule resources in a FHIR bundle to DTOs.
    
    Args:
        bundle: FHIR bundle containing Schedule resources.
        
    Returns:
        List of ScheduleDTOs extracted from bundle entries.
    """
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
    """Map a FHIR Slot resource to a SlotDTO.
    
    Can optionally use schedule information to fill in missing slot details
    (e.g., practitioner reference, specialty).
    
    Args:
        resource: FHIR Slot resource.
        schedule: Optional ScheduleDTO for context.
        
    Returns:
        SlotDTO with extracted slot information.
    """
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
    """Map all Slot resources in a FHIR bundle to DTOs.
    
    Args:
        bundle: FHIR bundle containing Slot resources.
        schedule: Optional ScheduleDTO context for enriching slot data.
        
    Returns:
        List of SlotDTOs extracted from bundle entries.
    """
    results: list[SlotDTO] = []

    for entry in _entries(bundle):
        resource = _resource_from_entry(entry)
        if resource.get("resourceType") != "Slot":
            continue
        results.append(map_slot_resource_to_dto(resource, schedule=schedule))

    return results


def map_appointment_resource_to_dto(resource: dict[str, Any]) -> AppointmentDTO:
    """Map a FHIR Appointment resource to an AppointmentDTO.
    
    Args:
        resource: FHIR Appointment resource.
        
    Returns:
        AppointmentDTO with extracted appointment information.
    """
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
    """Map all Appointment resources in a FHIR bundle to DTOs.
    
    Args:
        bundle: FHIR bundle containing Appointment resources.
        
    Returns:
        List of AppointmentDTOs extracted from bundle entries.
    """
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
    """Generate continuity signals from appointment history.
    
    Analyzes appointment list to extract continuity-of-care indicators,
    focusing on the most recent appointment.
    
    Args:
        appointments: List of AppointmentDTOs.
        
    Returns:
        ContinuitySignalsDTO with care continuity information.
    """
    if not appointments:
        return ContinuitySignalsDTO(
            hasPriorAppointments=False,
            totalAppointments=0,
            lastAppointmentStartUtc=None,
            lastPractitionerRef=None,
            lastPractitionerDisplay=None,
        )

    # Find most recent appointment by sorting descending
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
    """Convert medication requests to renewal signals.
    
    Wraps raw medication request resources in a synthetic FHIR bundle
    and processes them for renewal eligibility analysis.
    
    Args:
        medication_requests: List of MedicationRequest resources, or None.
        
    Returns:
        MedicationRenewalSignalsDTO with renewal information.
    """
    if not medication_requests:
        return MedicationRenewalSignalsDTO(
            patientRef=None,
            patientFound=False,
            eligible=False,
            items=[],
        )

    # Wrap raw resources in synthetic bundle format
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
    """Process MedicationRequest resources to extract renewal signals.
    
    Analyzes each medication request for refill eligibility, checking validity
    periods, repeat authorizations, and status to determine renewal readiness.
    
    Args:
        patient_ref: FHIR reference to patient, or None if unknown.
        bundle: FHIR bundle containing MedicationRequest resources.
        
    Returns:
        MedicationRenewalSignalsDTO with detailed renewal eligibility information.
    """
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

        # Extract dispense request and validity period information
        dispense_request = resource.get("dispenseRequest")
        if not isinstance(dispense_request, dict):
            dispense_request = {}

        validity_period = dispense_request.get("validityPeriod")
        if not isinstance(validity_period, dict):
            validity_period = {}

        # Determine refill eligibility status
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
    """Format medication quantity to human-readable text.
    
    Combines numeric value with unit/code to create display string.
    
    Args:
        value: FHIR Quantity object.
        
    Returns:
        Formatted quantity string (e.g., "10 mg") or None if not available.
    """
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
    """Format supply duration to human-readable text.
    
    Combines numeric duration value with time unit to create display string.
    
    Args:
        value: FHIR Duration object.
        
    Returns:
        Formatted duration string (e.g., "30 days") or None if not available.
    """
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
    """Safely extract integer value, excluding boolean type.
    
    Python's bool is a subclass of int, so we explicitly exclude it.
    
    Args:
        value: Value to convert to int.
        
    Returns:
        Integer value or None if not a valid int (or is a bool).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _refill_status_for_medication_request(resource: dict[str, Any]) -> tuple[str, str]:
    """Determine refill eligibility status and message for a MedicationRequest.
    
    Evaluates multiple factors to determine if a medication is eligible for renewal:
    - Request must be active
    - Validity period must not be expired
    - Must have available repeats authorized
    
    Args:
        resource: FHIR MedicationRequest resource.
        
    Returns:
        Tuple of (status_code, status_message) describing refill eligibility.
    """
    status = str(resource.get("status") or "").strip().lower()
    dispense_request = resource.get("dispenseRequest")
    if not isinstance(dispense_request, dict):
        dispense_request = {}

    repeats = _safe_int(dispense_request.get("numberOfRepeatsAllowed"))
    validity = dispense_request.get("validityPeriod")
    if not isinstance(validity, dict):
        validity = {}

    validity_end = validity.get("end") if isinstance(validity.get("end"), str) else None

    # Check if request is active
    if status != "active":
        return (
            "NOT_ACTIVE",
            "This medication request is not active and requires clinical review.",
        )

    # Check if request has expired
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

    # Check if repeat count is available
    if repeats is None:
        return (
            "REFILL_RULE_UNKNOWN",
            "Refill repeat rules are not available and clinical review is required.",
        )

    # Check if repeats are exhausted
    if repeats <= 0:
        return (
            "NO_REPEATS_AUTHORIZED",
            "No repeats are authorized in the source medication request.",
        )

    # Ready for refill request
    return (
        "READY_FOR_REFILL_REQUEST",
        "This medication can be submitted as a refill request pending clinical/pharmacy fulfillment.",
    )
    
    
def map_task_resource_to_refill_task_dto(resource: dict[str, Any]) -> MedicationRefillTaskDTO:
    """Map a FHIR Task resource to a MedicationRefillTaskDTO.
    
    Extracts medication refill task details including patient reference,
    medication request being fulfilled, and task status.
    
    Args:
        resource: FHIR Task resource related to medication refill.
        
    Returns:
        MedicationRefillTaskDTO with extracted task information.
    """
    task_id = str(resource.get("id") or "unknown")
    task_ref = f"Task/{task_id}"

    # Extract business status (workflow-specific status text)
    business_status = None
    raw_business_status = resource.get("businessStatus")
    if isinstance(raw_business_status, dict):
        text = raw_business_status.get("text")
        if isinstance(text, str):
            business_status = text

    # Extract patient reference
    patient_ref = None
    raw_for = resource.get("for")
    if isinstance(raw_for, dict) and isinstance(raw_for.get("reference"), str):
        patient_ref = raw_for["reference"]

    # Extract medication request reference (the resource being worked on)
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