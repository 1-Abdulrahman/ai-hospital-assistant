from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.modules.fhir_gateway.mappers import (
    PATIENT_IDENTIFIER_SYSTEM,
    TENANT_IDENTIFIER_SYSTEM,
    map_appointment_bundle_to_dtos,
    map_appointment_resource_to_dto,
    map_appointments_to_continuity_signals,
    map_medication_request_bundle_to_signals,
    map_patient_resource_to_dto,
    map_schedule_bundle_to_dtos,
    map_schedule_resource_to_dto,
    map_slot_bundle_to_dtos,
    map_slot_resource_to_dto,
)
from app.modules.fhir_gateway.reason_codes import (
    APPOINTMENT_CONFLICT,
    APPOINTMENT_CREATE_FAILED,
    FHIR_TIMEOUT,
    FHIR_UNAVAILABLE,
    INVALID_REQUEST,
    PATIENT_NOT_FOUND,
    SLOT_NO_LONGER_AVAILABLE,
    FhirGatewayError,
)
from app.modules.fhir_gateway.schemas import (
    AppointmentDTO,
    ContinuitySignalsDTO,
    MedicationRenewalSignalsDTO,
    PatientSummaryDTO,
    ScheduleDTO,
    SlotDTO,
)

SPECIALTY_SYSTEM = "urn:ai-hospital-assistant:specialty"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_patient_identifier_system(tenant_id: str) -> str:
    cleaned = tenant_id.strip()
    if not cleaned:
        raise FhirGatewayError(
            reason_code=INVALID_REQUEST,
            user_message="Tenant id is required for FHIR patient operations.",
            status_code=400,
        )
    return f"urn:ai-hospital-assistant:patient-key:{cleaned}"


def _ensure_reference(resource_type: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise FhirGatewayError(
            reason_code=INVALID_REQUEST,
            user_message=f"{resource_type} reference is required.",
            status_code=400,
        )
    if "/" in cleaned:
        return cleaned
    return f"{resource_type}/{cleaned}"


def _reference_search_value(reference: str) -> str:
    cleaned = reference.strip()
    if "/" in cleaned:
        return cleaned.split("/", 1)[1]
    return cleaned

def _normalize_specialty_token(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().replace("_", " ").lower()


def _specialty_matches(appointment_specialty: str | None, selected_specialty: str | None) -> bool:
    return _normalize_specialty_token(appointment_specialty) == _normalize_specialty_token(selected_specialty)


class FhirClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self.base_url = (base_url or settings.fhir_base_url).rstrip("/")
        self.timeout = timeout or httpx.Timeout(
            connect=settings.fhir_timeout_connect,
            read=settings.fhir_timeout_read,
            write=settings.fhir_timeout_read,
            pool=settings.fhir_timeout_read,
        )

    async def get_status_payload(self) -> dict[str, Any]:
        try:
            await self.get_capability_statement()
            return {
                "status": "OK",
                "fhirBaseUrl": self.base_url,
                "time": _utc_now_iso(),
            }
        except FhirGatewayError as exc:
            return {
                "status": "DEGRADED",
                "fhirBaseUrl": self.base_url,
                "time": _utc_now_iso(),
                "reasonCode": exc.reason_code,
            }

    async def get_continuity_signals(
        self,
        *,
        patient_ref: str,
        specialty: str | None = None,
    ) -> ContinuitySignalsDTO:
        appointments = await self.search_appointments(
            patient_ref=patient_ref,
            status="booked",
        )

        if specialty and specialty.strip():
            appointments = [
                appointment
                for appointment in appointments
                if _specialty_matches(appointment.specialty, specialty)
            ]

        return map_appointments_to_continuity_signals(appointments)

    async def get_capability_statement(self) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/metadata",
            retry_on_read=True,
        )
        self._ensure_read_success(response, operation="read FHIR metadata")
        return self._json_or_empty(response)

    async def find_patient_by_identifier(
        self,
        patient_key_hash: str,
        tenant_id: str | None = None,
    ) -> PatientSummaryDTO | str | None:
        if not patient_key_hash.strip():
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Patient key hash is required.",
                status_code=400,
            )

        cleaned_tenant_id = (tenant_id or "").strip()
        if cleaned_tenant_id:
            params = {
                "identifier": f"{build_patient_identifier_system(cleaned_tenant_id)}|{patient_key_hash}",
            }

            response = await self._request(
                "GET",
                "/Patient",
                params=params,
                retry_on_read=True,
            )
            self._ensure_read_success(
                response,
                operation="search patient by tenant-scoped identifier",
            )

            bundle = self._json_or_empty(response)
            entries = bundle.get("entry") or []
            if not isinstance(entries, list) or not entries:
                return None

            first_entry = entries[0]
            if not isinstance(first_entry, dict):
                return None

            resource = first_entry.get("resource")
            if not isinstance(resource, dict):
                return None

            return map_patient_resource_to_dto(
                resource,
                tenant_id=cleaned_tenant_id,
                patient_key_hash=patient_key_hash,
            )

        identifier_value = quote(
            f"{PATIENT_IDENTIFIER_SYSTEM}|{patient_key_hash}",
            safe="",
        )
        response = await self._request(
            "GET",
            f"/Patient?identifier={identifier_value}&_count=1",
            retry_on_read=True,
        )
        self._ensure_read_success(
            response,
            operation="search patient by identifier",
        )

        bundle = self._json_or_empty(response)
        entries = bundle.get("entry") or []
        if not isinstance(entries, list) or not entries:
            return None

        first_entry = entries[0]
        if not isinstance(first_entry, dict):
            return None

        resource = first_entry.get("resource")
        if not isinstance(resource, dict):
            return None

        patient_id = resource.get("id")
        if not isinstance(patient_id, str) or not patient_id.strip():
            return None

        return f"Patient/{patient_id.strip()}"

    async def ensure_patient(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
        display_name: str | None = None,
    ) -> PatientSummaryDTO:
        existing = await self.find_patient_by_identifier(
            patient_key_hash=patient_key_hash,
            tenant_id=tenant_id,
        )
        if isinstance(existing, PatientSummaryDTO):
            return existing

        resource: dict[str, Any] = {
            "resourceType": "Patient",
            "identifier": [
                {
                    "system": build_patient_identifier_system(tenant_id),
                    "value": patient_key_hash,
                }
            ],
        }

        if display_name and display_name.strip():
            resource["name"] = [{"text": display_name.strip()}]

        response = await self._request(
            "POST",
            "/Patient",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
            retry_on_read=False,
        )

        if response.status_code in {200, 201}:
            return map_patient_resource_to_dto(
                self._json_or_empty(response),
                tenant_id=tenant_id,
                patient_key_hash=patient_key_hash,
            )

        if response.status_code == 409:
            retried = await self.find_patient_by_identifier(
                patient_key_hash=patient_key_hash,
                tenant_id=tenant_id,
            )
            if isinstance(retried, PatientSummaryDTO):
                return retried

        if response.status_code == 503:
            raise FhirGatewayError(
                reason_code=FHIR_UNAVAILABLE,
                user_message="FHIR service is unavailable while creating patient.",
                status_code=503,
                details=self._operation_outcome_text(response),
            )

        if 400 <= response.status_code < 500:
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Patient request was rejected by FHIR.",
                status_code=response.status_code,
                details=self._operation_outcome_text(response),
            )

        raise FhirGatewayError(
            reason_code=FHIR_UNAVAILABLE,
            user_message="FHIR patient creation failed.",
            status_code=503,
            details=self._operation_outcome_text(response),
        )

    async def get_patient_or_raise(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
    ) -> PatientSummaryDTO:
        patient = await self.find_patient_by_identifier(
            patient_key_hash=patient_key_hash,
            tenant_id=tenant_id,
        )
        if not isinstance(patient, PatientSummaryDTO):
            raise FhirGatewayError(
                reason_code=PATIENT_NOT_FOUND,
                user_message="Patient was not found in FHIR.",
                status_code=404,
            )
        return patient

    async def get_medication_requests_for_patient(self, patient_ref: str) -> dict[str, Any]:
        patient_ref_q = quote(patient_ref, safe="")
        response = await self._request(
            "GET",
            f"/MedicationRequest?subject={patient_ref_q}&status=active&_count=50",
            retry_on_read=True,
        )
        self._ensure_read_success(
            response,
            operation="search medication requests for patient",
        )
        return self._json_or_empty(response)

    async def get_medication_renewal_signals(
        self,
        *,
        patient_key_hash: str,
    ) -> MedicationRenewalSignalsDTO:
        patient_ref = await self.find_patient_by_identifier(patient_key_hash=patient_key_hash)
        if not isinstance(patient_ref, str):
            return MedicationRenewalSignalsDTO(
                patientRef=None,
                patientFound=False,
                eligible=False,
                items=[],
            )

        med_bundle = await self.get_medication_requests_for_patient(patient_ref)
        return map_medication_request_bundle_to_signals(
            patient_ref=patient_ref,
            bundle=med_bundle,
        )

    async def search_schedules(
        self,
        *,
        tenant_id: str,
        specialty: str,
        active: bool = True,
    ) -> list[ScheduleDTO]:
        if not specialty.strip():
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Specialty is required for schedule search.",
                status_code=400,
            )

        params: list[tuple[str, str]] = [
            ("identifier", f"{TENANT_IDENTIFIER_SYSTEM}|{tenant_id}"),
            ("specialty", specialty.strip()),
        ]
        if active:
            params.append(("active", "true"))

        response = await self._request(
            "GET",
            "/Schedule",
            params=params,
            retry_on_read=True,
        )
        self._ensure_read_success(response, operation="search schedules")

        return map_schedule_bundle_to_dtos(self._json_or_empty(response))

    async def get_schedule_or_raise(self, schedule_ref: str) -> ScheduleDTO:
        resource = await self._read_resource_or_raise(
            resource_type="Schedule",
            resource_id_or_ref=schedule_ref,
            not_found_reason_code=INVALID_REQUEST,
            not_found_message="Schedule was not found in FHIR.",
        )
        return map_schedule_resource_to_dto(resource)

    async def search_slots(
        self,
        *,
        schedule_ref: str,
        status: str = "free",
        start_from_utc: str | None = None,
    ) -> list[SlotDTO]:
        schedule = await self.get_schedule_or_raise(schedule_ref)

        params: list[tuple[str, str]] = [
            ("schedule", _reference_search_value(schedule_ref)),
        ]
        if status.strip():
            params.append(("status", status.strip()))

        response = await self._request(
            "GET",
            "/Slot",
            params=params,
            retry_on_read=True,
        )
        self._ensure_read_success(response, operation="search slots")

        items = map_slot_bundle_to_dtos(
            self._json_or_empty(response), schedule=schedule)

        if start_from_utc:
            filtered: list[SlotDTO] = []
            for item in items:
                if item.startUtc and item.startUtc >= start_from_utc:
                    filtered.append(item)
            return filtered

        return items

    async def get_slot_or_raise(self, slot_id: str) -> SlotDTO:
        resource = await self._read_resource_or_raise(
            resource_type="Slot",
            resource_id_or_ref=slot_id,
            not_found_reason_code=SLOT_NO_LONGER_AVAILABLE,
            not_found_message="Selected slot is no longer available.",
        )

        schedule_ref = None
        schedule_obj = resource.get("schedule")
        if isinstance(schedule_obj, dict):
            schedule_ref_value = schedule_obj.get("reference")
            if isinstance(schedule_ref_value, str) and schedule_ref_value.strip():
                schedule_ref = schedule_ref_value.strip()

        schedule = await self.get_schedule_or_raise(schedule_ref or "")
        return map_slot_resource_to_dto(resource, schedule=schedule)

    async def update_slot_status(
        self,
        *,
        slot_id: str,
        new_status: str,
        comment: str | None = None,
    ) -> SlotDTO:
        resource = await self._read_resource_or_raise(
            resource_type="Slot",
            resource_id_or_ref=slot_id,
            not_found_reason_code=SLOT_NO_LONGER_AVAILABLE,
            not_found_message="Selected slot is no longer available.",
        )

        resource["status"] = new_status.strip()

        if comment is not None:
            resource["comment"] = comment

        response = await self._request(
            "PUT",
            f"/Slot/{_reference_search_value(slot_id)}",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
            retry_on_read=False,
        )

        if response.status_code in {200, 201}:
            updated = self._json_or_empty(response)

            schedule_ref = None
            schedule_obj = updated.get("schedule")
            if isinstance(schedule_obj, dict):
                schedule_ref_value = schedule_obj.get("reference")
                if isinstance(schedule_ref_value, str) and schedule_ref_value.strip():
                    schedule_ref = schedule_ref_value.strip()

            schedule = await self.get_schedule_or_raise(schedule_ref or "")
            return map_slot_resource_to_dto(updated, schedule=schedule)

        if response.status_code in {404, 409, 412}:
            raise FhirGatewayError(
                reason_code=SLOT_NO_LONGER_AVAILABLE,
                user_message="Selected slot is no longer available.",
                status_code=409,
                details=self._operation_outcome_text(response),
            )

        if response.status_code == 503:
            raise FhirGatewayError(
                reason_code=FHIR_UNAVAILABLE,
                user_message="FHIR service is unavailable while updating slot status.",
                status_code=503,
                details=self._operation_outcome_text(response),
            )

        if 400 <= response.status_code < 500:
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Slot update request was rejected by FHIR.",
                status_code=response.status_code,
                details=self._operation_outcome_text(response),
            )

        raise FhirGatewayError(
            reason_code=FHIR_UNAVAILABLE,
            user_message="Slot status update failed.",
            status_code=503,
            details=self._operation_outcome_text(response),
        )

    async def search_appointments(
        self,
        *,
        patient_ref: str | None = None,
        practitioner_ref: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
        status: str | None = None,
    ) -> list[AppointmentDTO]:
        params: list[tuple[str, str]] = []

        if patient_ref:
            params.append(("patient", _reference_search_value(patient_ref)))

        if practitioner_ref:
            params.append(
                ("practitioner", _reference_search_value(practitioner_ref)))

        if start_utc:
            params.append(("date", f"ge{start_utc}"))

        if end_utc:
            params.append(("date", f"lt{end_utc}"))

        if status:
            params.append(("status", status))

        response = await self._request(
            "GET",
            "/Appointment",
            params=params,
            retry_on_read=True,
        )
        self._ensure_read_success(response, operation="search appointments")

        bundle = self._json_or_empty(response)
        return map_appointment_bundle_to_dtos(bundle)

    async def create_appointment(
        self,
        *,
        tenant_id: str,
        patient_ref: str,
        practitioner_ref: str,
        specialty_code: str,
        specialty_display: str,
        start_utc: str,
        end_utc: str,
        slot_ref: str,
        description: str | None = None,
    ) -> AppointmentDTO:
        patient_ref_normalized = _ensure_reference("Patient", patient_ref)
        practitioner_ref_normalized = _ensure_reference(
            "Practitioner", practitioner_ref)
        slot_ref_normalized = _ensure_reference("Slot", slot_ref)

        if not specialty_code.strip():
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Specialty code is required for appointment creation.",
                status_code=400,
            )

        resource: dict[str, Any] = {
            "resourceType": "Appointment",
            "status": "booked",
            "description": (description or specialty_display or specialty_code).strip(),
            "start": start_utc,
            "end": end_utc,
            "identifier": [
                {
                    "system": TENANT_IDENTIFIER_SYSTEM,
                    "value": tenant_id,
                }
            ],
            "serviceType": [
                {
                    "coding": [
                        {
                            "system": SPECIALTY_SYSTEM,
                            "code": specialty_code.strip(),
                            "display": specialty_display.strip() or specialty_code.strip(),
                        }
                    ],
                    "text": specialty_display.strip() or specialty_code.strip(),
                }
            ],
            "specialty": [
                {
                    "coding": [
                        {
                            "system": SPECIALTY_SYSTEM,
                            "code": specialty_code.strip(),
                            "display": specialty_display.strip() or specialty_code.strip(),
                        }
                    ],
                    "text": specialty_display.strip() or specialty_code.strip(),
                }
            ],
            "slot": [
                {
                    "reference": slot_ref_normalized,
                }
            ],
            "participant": [
                {
                    "actor": {"reference": patient_ref_normalized},
                    "status": "accepted",
                },
                {
                    "actor": {"reference": practitioner_ref_normalized},
                    "status": "accepted",
                },
            ],
        }

        response = await self._request(
            "POST",
            "/Appointment",
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
            retry_on_read=False,
        )

        if response.status_code in {200, 201}:
            return map_appointment_resource_to_dto(self._json_or_empty(response))

        if response.status_code == 409:
            raise FhirGatewayError(
                reason_code=APPOINTMENT_CONFLICT,
                user_message="Selected slot is no longer available.",
                status_code=409,
                details=self._operation_outcome_text(response),
            )

        if response.status_code == 503:
            raise FhirGatewayError(
                reason_code=FHIR_UNAVAILABLE,
                user_message="FHIR service is unavailable while creating appointment.",
                status_code=503,
                details=self._operation_outcome_text(response),
            )

        if 400 <= response.status_code < 500:
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Appointment request was rejected by FHIR.",
                status_code=response.status_code,
                details=self._operation_outcome_text(response),
            )

        raise FhirGatewayError(
            reason_code=APPOINTMENT_CREATE_FAILED,
            user_message="Appointment could not be created.",
            status_code=503,
            details=self._operation_outcome_text(response),
        )

    async def _read_resource_or_raise(
        self,
        *,
        resource_type: str,
        resource_id_or_ref: str,
        not_found_reason_code: str,
        not_found_message: str,
    ) -> dict[str, Any]:
        resource_id = _reference_search_value(resource_id_or_ref)
        if not resource_id.strip():
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message=f"{resource_type} id is required.",
                status_code=400,
            )

        response = await self._request(
            "GET",
            f"/{resource_type}/{resource_id}",
            retry_on_read=True,
        )

        if response.status_code == 404:
            raise FhirGatewayError(
                reason_code=not_found_reason_code,
                user_message=not_found_message,
                status_code=404,
                details=self._operation_outcome_text(response),
            )

        self._ensure_read_success(response, operation=f"read {resource_type}")
        return self._json_or_empty(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_on_read: bool = False,
    ) -> httpx.Response:
        method_upper = method.upper()
        attempts = 2 if retry_on_read and method_upper == "GET" else 1

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method_upper,
                        url=self._url(path),
                        params=params,
                        json=json,
                        headers=headers,
                    )
            except httpx.TimeoutException as exc:
                if attempt < attempts - 1:
                    continue
                raise FhirGatewayError(
                    reason_code=FHIR_TIMEOUT,
                    user_message="FHIR request timed out.",
                    status_code=503,
                    details=str(exc),
                ) from exc
            except httpx.RequestError as exc:
                raise FhirGatewayError(
                    reason_code=FHIR_UNAVAILABLE,
                    user_message="FHIR service is unavailable.",
                    status_code=503,
                    details=str(exc),
                ) from exc

            if retry_on_read and response.status_code == 503 and attempt < attempts - 1:
                continue

            return response

        raise FhirGatewayError(
            reason_code=FHIR_UNAVAILABLE,
            user_message="FHIR service is unavailable.",
            status_code=503,
        )

    def _url(self, path: str) -> str:
        if path.startswith("/"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/{path}"

    def _ensure_read_success(self, response: httpx.Response, *, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return

        if response.status_code == 503:
            raise FhirGatewayError(
                reason_code=FHIR_UNAVAILABLE,
                user_message=f"FHIR service is unavailable during {operation}.",
                status_code=503,
                details=self._operation_outcome_text(response),
            )

        if 400 <= response.status_code < 500:
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message=f"FHIR request was invalid during {operation}.",
                status_code=response.status_code,
                details=self._operation_outcome_text(response),
            )

        raise FhirGatewayError(
            reason_code=FHIR_UNAVAILABLE,
            user_message=f"FHIR service failed during {operation}.",
            status_code=503,
            details=self._operation_outcome_text(response),
        )

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _operation_outcome_text(self, response: httpx.Response) -> str | None:
        body = self._json_or_empty(response)
        issues = body.get("issue")
        if not isinstance(issues, list) or not issues:
            return None

        first_issue = issues[0]
        if not isinstance(first_issue, dict):
            return None

        details = first_issue.get("details")
        if isinstance(details, dict):
            text = details.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()[:200]

        diagnostics = first_issue.get("diagnostics")
        if isinstance(diagnostics, str) and diagnostics.strip():
            return diagnostics.strip()[:200]

        return None
