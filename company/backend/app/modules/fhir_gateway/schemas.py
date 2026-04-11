from __future__ import annotations

from pydantic import BaseModel, Field


class PatientSummaryDTO(BaseModel):
    patientId: str = Field(..., description="FHIR logical id for the Patient resource.")
    patientRef: str = Field(..., description="FHIR reference, for example Patient/123.")
    tenantId: str = Field(..., description="Owning tenant id.")
    patientKeyHash: str = Field(..., description="Tenant-scoped hashed patient identity.")
    displayName: str | None = Field(
        default=None,
        description="Safe display label only. No raw identity numbers.",
    )


class ScheduleDTO(BaseModel):
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
    hasPriorAppointments: bool = False
    totalAppointments: int = 0
    lastAppointmentStartUtc: str | None = None
    lastPractitionerRef: str | None = None


class MedicationRenewalSignalsDTO(BaseModel):
    eligible: bool = False
    lastMedicationRequestDateUtc: str | None = None
    note: str | None = None