"""Data Transfer Objects (DTOs) used by the FHIR gateway module.

These lightweight Pydantic models represent slices of FHIR resources
that the gateway exposes to other services (appointments, patients,
medication renewals, etc.). They are intentionally simple and use
strings for timestamps and references to avoid tying the DTOs to a
specific FHIR library implementation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PatientSummaryDTO(BaseModel):
    """Summary information for a FHIR Patient resource.

    Notes:
    - `patientId` is the logical id portion of the Patient resource.
    - `patientRef` is a FHIR-style reference (e.g., "Patient/123").
    - Emails are normalized and stored as lowercase strings.
    """

    patientId: str = Field(..., description="FHIR logical id for the Patient resource.")
    patientRef: str = Field(..., description="FHIR reference, for example Patient/123.")
    tenantId: str = Field(..., description="Owning tenant id.")
    patientKeyHash: str = Field(..., description="Tenant-scoped hashed patient identity.")
    displayName: str | None = Field(
        default=None,
        description="Safe display label only. No raw identity numbers.",
    )
    emails: list[str] = Field(
        default_factory=list,
        description="Registered FHIR Patient telecom emails, normalized to lowercase.",
    )
    primaryEmail: str | None = Field(
        default=None,
        description="First registered email if available.",
    )


class ScheduleDTO(BaseModel):
    """Represents a scheduling container (FHIR Schedule).

    Only the fields required by the application are included here.
    Times are represented as UTC strings to keep the DTO serializable
    without timezone-aware datetime objects.
    """

    scheduleId: str
    scheduleRef: str
    practitionerRef: str | None = None
    practitionerDisplay: str | None = None
    specialty: str | None = None
    tenantId: str | None = None
    planningHorizonStartUtc: str | None = None
    planningHorizonEndUtc: str | None = None
    active: bool = True


class SlotDTO(BaseModel):
    """A single booked/free slot within a `ScheduleDTO`.

    `status` uses the same vocabulary as FHIR Slot status (e.g. "free").
    """

    slotId: str
    slotRef: str
    scheduleRef: str | None = None
    practitionerRef: str | None = None
    practitionerDisplay: str | None = None
    specialty: str | None = None
    startUtc: str
    endUtc: str
    status: str = "free"


class AppointmentDTO(BaseModel):
    """Lightweight view of an appointment used across services.

    Fields are intentionally permissive (many are optional) because
    different flows populate different subsets of appointment data.
    """

    appointmentId: str
    appointmentRef: str
    status: str
    startUtc: str | None = None
    endUtc: str | None = None
    specialty: str | None = None
    practitionerRef: str | None = None
    practitionerDisplay: str | None = None
    patientRef: str | None = None
    patientDisplay: str | None = None
    tenantId: str | None = None
    slotRefs: list[str] = Field(default_factory=list)


class ContinuitySignalsDTO(BaseModel):
    """Signals used to infer patient continuity and history.

    These values are used for patient-centered UX and triage"+" decisions and therefore intentionally aggregate appointment history
    into a compact shape.
    """

    hasPriorAppointments: bool = False
    totalAppointments: int = 0
    lastAppointmentStartUtc: str | None = None
    lastPractitionerRef: str | None = None
    lastPractitionerDisplay: str | None = None


class MedicationRenewalItemDTO(BaseModel):
    """A single medication renewal candidate.

    This DTO mirrors the pieces of a MedicationRequest that are
    relevant for renewal decisions (status, intent, authoredOn,
    dosing text, and supply/refill information).
    """

    medicationRequestRef: str
    medicationDisplay: str
    medicationCode: str | None = None
    status: str
    intent: str | None = None
    authoredOn: str | None = None
    dosageText: str | None = None

    # Validity period and expected supply details (all optional).
    validityPeriodStart: str | None = None
    validityPeriodEnd: str | None = None
    numberOfRepeatsAllowed: int | None = None
    quantityText: str | None = None
    expectedSupplyDurationText: str | None = None

    # Default refill status for items requiring clinician review.
    refillStatus: str = "REQUIRES_CLINICAL_REVIEW"
    refillStatusMessage: str = "Clinical review is required before fulfillment."


class MedicationRenewalSignalsDTO(BaseModel):
    """Aggregated signals for medication renewal eligibility.

    - `eligible` indicates whether the patient has any items that can
      proceed through an automated renewal flow.
    - `items` contains the candidate `MedicationRenewalItemDTO` entries.
    """

    patientRef: str | None = None
    patientFound: bool = False
    eligible: bool = False
    items: list[MedicationRenewalItemDTO] = Field(default_factory=list)
    

class MedicationRefillTaskDTO(BaseModel):
    """Represents an asynchronous task created for medication refill work.

    This maps loosely to FHIR Task resources but contains only the fields
    needed by the orchestration logic.
    """

    taskId: str
    taskRef: str
    status: str
    intent: str | None = None
    businessStatus: str | None = None
    patientRef: str | None = None
    medicationRequestRef: str | None = None