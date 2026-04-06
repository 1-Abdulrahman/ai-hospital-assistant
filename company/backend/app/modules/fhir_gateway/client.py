from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.modules.fhir_gateway.mappers import (
    TENANT_IDENTIFIER_SYSTEM,
    map_appointment_bundle_to_dtos,
    map_appointment_resource_to_dto,
    map_patient_resource_to_dto,
)
from app.modules.fhir_gateway.reason_codes import (
    APPOINTMENT_CONFLICT,
    APPOINTMENT_CREATE_FAILED,
    FHIR_TIMEOUT,
    FHIR_UNAVAILABLE,
    INVALID_REQUEST,
    PATIENT_NOT_FOUND,
    FhirGatewayError,
)
from app.modules.fhir_gateway.schemas import AppointmentDTO, PatientSummaryDTO


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

    async def get_capability_statement(self) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/metadata",
            retry_on_read=True,
        )
        self._ensure_read_success(
            response,
            operation="read FHIR metadata",
        )
        return self._json_or_empty(response)

    async def find_patient_by_identifier(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
    ) -> PatientSummaryDTO | None:
        if not patient_key_hash.strip():
            raise FhirGatewayError(
                reason_code=INVALID_REQUEST,
                user_message="Patient key hash is required.",
                status_code=400,
            )

        params = {
            "identifier": f"{build_patient_identifier_system(tenant_id)}|{patient_key_hash}",
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
            tenant_id=tenant_id,
            patient_key_hash=patient_key_hash,
        )

    async def ensure_patient(
        self,
        *,
        tenant_id: str,
        patient_key_hash: str,
        display_name: str | None = None,
    ) -> PatientSummaryDTO:
        existing = await self.find_patient_by_identifier(
            tenant_id=tenant_id,
            patient_key_hash=patient_key_hash,
        )
        if existing is not None:
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
                tenant_id=tenant_id,
                patient_key_hash=patient_key_hash,
            )
            if retried is not None:
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
            tenant_id=tenant_id,
            patient_key_hash=patient_key_hash,
        )
        if patient is None:
            raise FhirGatewayError(
                reason_code=PATIENT_NOT_FOUND,
                user_message="Patient was not found in FHIR.",
                status_code=404,
            )
        return patient

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
            params.append(("practitioner", _reference_search_value(practitioner_ref)))

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
        self._ensure_read_success(
            response,
            operation="search appointments",
        )

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
        description: str | None = None,
    ) -> AppointmentDTO:
        patient_ref_normalized = _ensure_reference("Patient", patient_ref)
        practitioner_ref_normalized = _ensure_reference("Practitioner", practitioner_ref)

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, str]] | None = None,
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
        if not isinstance(details, dict):
            return None

        text = details.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()[:200]

        return None