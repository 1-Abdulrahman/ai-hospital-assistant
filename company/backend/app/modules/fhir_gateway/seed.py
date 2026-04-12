from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.modules.fhir_gateway.client import (
    SPECIALTY_SYSTEM,
    build_patient_identifier_system,
)
from app.modules.fhir_gateway.mappers import TENANT_IDENTIFIER_SYSTEM
from app.modules.otp.service import build_patient_key_hash


BASE_DIR = Path(__file__).resolve().parents[2]
PROVIDERS_PATH = BASE_DIR / "modules" / "scheduling" / "providers_static.json"

SEED_TENANT_ID = "demo"
SEED_DAYS_AHEAD = 14
SLOT_DURATION_MINUTES = 30
PATIENT_KEY_IDENTIFIER_SYSTEM = build_patient_identifier_system(SEED_TENANT_ID)
LEGACY_PATIENT_KEY_IDENTIFIER_SYSTEM = "urn:tenant-patient-key"

CLINIC_WINDOWS: tuple[tuple[time, time], ...] = (
    (time(hour=9, minute=0), time(hour=12, minute=0)),
    (time(hour=13, minute=0), time(hour=16, minute=0)),
)

DEMO_RENEWAL_PATIENTS = [
    {
        "national_id": "5000000001",
        "identity_type": "border_id",
        "display": "Demo Renewal Patient 1",
        "medications": [
            {
                "code": "860975",
                "display": "Metformin",
                "dosageText": "500 mg twice daily",
            },
            {
                "code": "83367",
                "display": "Atorvastatin",
                "dosageText": "20 mg nightly",
            },
        ],
    },
    {
        "national_id": "5000000002",
        "identity_type": "border_id",
        "display": "Demo Renewal Patient 2",
        "medications": [
            {
                "code": "29046",
                "display": "Losartan",
                "dosageText": "50 mg daily",
            },
        ],
    },
]

DEMO_CONTINUITY_PATIENTS = [
    {
        "national_id": "5000000010",
        "identity_type": "border_id",
        "display": "Demo Continuity Patient GP",
        "specialty": "general_practice",
        "practitioner_ref": "Practitioner/prac-gp-1",
        "practitioner_display": "Dr. Mona Alqahtani",
        "days_ago": 7,
        "hour": 9,
        "minute": 30,
    },
    {
        "national_id": "5000000011",
        "identity_type": "border_id",
        "display": "Demo Continuity Patient Cardiology",
        "specialty": "cardiology",
        "practitioner_ref": "Practitioner/prac-card-1",
        "practitioner_display": "Dr. Lina Alharbi",
        "days_ago": 5,
        "hour": 10,
        "minute": 0,
    },
]


@dataclass(frozen=True)
class ProviderSeedItem:
    specialty: str
    practitioner_id: str
    practitioner_ref: str
    practitioner_display: str


def _normalize_display(value: str) -> str:
    return value.strip().replace("_", " ").title()


def _sanitize_fhir_id(value: str) -> str:
    cleaned = value.strip().replace("_", "-").replace(" ", "-")
    cleaned = re.sub(r"[^A-Za-z0-9\-.]", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:64]


def _extract_practitioner_id(practitioner_ref: str) -> str:
    cleaned = practitioner_ref.strip()
    if not cleaned:
        raise ValueError("practitionerRef cannot be empty.")
    if "/" not in cleaned:
        return cleaned

    resource_type, resource_id = cleaned.split("/", 1)
    if resource_type != "Practitioner" or not resource_id.strip():
        raise ValueError(
            f"Invalid practitionerRef '{practitioner_ref}'. Expected Practitioner/<id>."
        )
    return resource_id.strip()


def _to_utc_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _schedule_id_for(item: ProviderSeedItem) -> str:
    return _sanitize_fhir_id(f"sched-{item.specialty}-{item.practitioner_id}")


def _slot_id_for(schedule_id: str, start_dt: datetime) -> str:
    return _sanitize_fhir_id(
        f"slot-{schedule_id}-{start_dt.strftime('%Y%m%dT%H%M')}"
    )


def _patient_id_for(patient_key_hash: str) -> str:
    return _sanitize_fhir_id(f"patient-{patient_key_hash[:20]}")


def _medication_request_id_for(patient_ref: str, medication_code: str) -> str:
    patient_id = patient_ref.split("/", 1)[1]
    return _sanitize_fhir_id(f"medreq-{patient_id}-{medication_code}")


def _appointment_id_for(
    *,
    patient_ref: str,
    practitioner_ref: str,
    specialty: str,
    start_dt: datetime,
) -> str:
    patient_id = patient_ref.split("/", 1)[1]
    practitioner_id = practitioner_ref.split("/", 1)[1]
    return _sanitize_fhir_id(
        f"appt-{patient_id}-{practitioner_id}-{specialty}-{start_dt.strftime('%Y%m%dT%H%M')}"
    )


def _build_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }


def _load_provider_seed_items() -> list[ProviderSeedItem]:
    if not PROVIDERS_PATH.exists():
        raise FileNotFoundError(f"Provider seed file not found: {PROVIDERS_PATH}")

    raw = json.loads(PROVIDERS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("providers_static.json must contain a JSON object.")

    items: list[ProviderSeedItem] = []

    for specialty, providers in raw.items():
        if not isinstance(providers, list):
            raise ValueError(f"Specialty '{specialty}' must map to a list.")

        for provider in providers:
            if not isinstance(provider, dict):
                raise ValueError(
                    f"Provider entry for specialty '{specialty}' must be an object."
                )

            practitioner_ref = str(provider.get("practitionerRef", "")).strip()
            practitioner_display = str(provider.get("practitionerDisplay", "")).strip()

            if not practitioner_ref:
                raise ValueError(
                    f"Missing practitionerRef under specialty '{specialty}'."
                )
            if not practitioner_display:
                raise ValueError(
                    f"Missing practitionerDisplay under specialty '{specialty}'."
                )

            practitioner_id = _extract_practitioner_id(practitioner_ref)

            items.append(
                ProviderSeedItem(
                    specialty=str(specialty).strip().lower(),
                    practitioner_id=practitioner_id,
                    practitioner_ref=f"Practitioner/{practitioner_id}",
                    practitioner_display=practitioner_display,
                )
            )

    return items


def _build_practitioner_resource(item: ProviderSeedItem) -> dict[str, Any]:
    return {
        "resourceType": "Practitioner",
        "id": item.practitioner_id,
        "active": True,
        "name": [
            {
                "text": item.practitioner_display,
            }
        ],
        "qualification": [
            {
                "code": {
                    "text": _normalize_display(item.specialty),
                }
            }
        ],
    }


def _build_schedule_resource(
    *,
    item: ProviderSeedItem,
    schedule_id: str,
    horizon_start_utc: str,
    horizon_end_utc: str,
) -> dict[str, Any]:
    specialty_display = _normalize_display(item.specialty)

    return {
        "resourceType": "Schedule",
        "id": schedule_id,
        "active": True,
        "identifier": [
            {
                "system": TENANT_IDENTIFIER_SYSTEM,
                "value": SEED_TENANT_ID,
            }
        ],
        "specialty": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": item.specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "serviceType": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": item.specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "actor": [
            {
                "reference": item.practitioner_ref,
                "display": item.practitioner_display,
            }
        ],
        "planningHorizon": {
            "start": horizon_start_utc,
            "end": horizon_end_utc,
        },
        "comment": f"FHIR-native schedule for {item.practitioner_display}",
    }


def _build_slot_resource(
    *,
    item: ProviderSeedItem,
    schedule_id: str,
    slot_id: str,
    start_utc: str,
    end_utc: str,
    status: str = "free",
    comment: str | None = None,
) -> dict[str, Any]:
    specialty_display = _normalize_display(item.specialty)

    resource: dict[str, Any] = {
        "resourceType": "Slot",
        "id": slot_id,
        "identifier": [
            {
                "system": TENANT_IDENTIFIER_SYSTEM,
                "value": SEED_TENANT_ID,
            }
        ],
        "serviceType": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": item.specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "specialty": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": item.specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "schedule": {
            "reference": f"Schedule/{schedule_id}",
        },
        "status": status,
        "start": start_utc,
        "end": end_utc,
    }

    if comment:
        resource["comment"] = comment

    return resource


def _build_demo_patient_resource(
    *,
    patient_id: str,
    patient_key_hash: str,
    display: str,
) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "system": TENANT_IDENTIFIER_SYSTEM,
                "value": SEED_TENANT_ID,
            },
            {
                "system": PATIENT_KEY_IDENTIFIER_SYSTEM,
                "value": patient_key_hash,
            },
            {
                "system": LEGACY_PATIENT_KEY_IDENTIFIER_SYSTEM,
                "value": patient_key_hash,
            },
        ],
        "name": [
            {
                "text": display,
            }
        ],
        "active": True,
    }


def _build_demo_medication_request_resource(
    *,
    med_request_id: str,
    patient_ref: str,
    code: str,
    display: str,
    dosage_text: str,
) -> dict[str, Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": med_request_id,
        "status": "active",
        "intent": "order",
        "subject": {
            "reference": patient_ref,
        },
        "medicationCodeableConcept": {
            "coding": [
                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": code,
                    "display": display,
                }
            ],
            "text": display,
        },
        "authoredOn": datetime.now(UTC).date().isoformat(),
        "dosageInstruction": [
            {
                "text": dosage_text,
            }
        ],
    }


def _build_demo_appointment_resource(
    *,
    appointment_id: str,
    patient_ref: str,
    practitioner_ref: str,
    specialty: str,
    start_utc: str,
    end_utc: str,
    slot_ref: str,
    description: str,
) -> dict[str, Any]:
    specialty_display = _normalize_display(specialty)

    return {
        "resourceType": "Appointment",
        "id": appointment_id,
        "status": "booked",
        "description": description,
        "start": start_utc,
        "end": end_utc,
        "identifier": [
            {
                "system": TENANT_IDENTIFIER_SYSTEM,
                "value": SEED_TENANT_ID,
            }
        ],
        "serviceType": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "specialty": [
            {
                "coding": [
                    {
                        "system": SPECIALTY_SYSTEM,
                        "code": specialty,
                        "display": specialty_display,
                    }
                ],
                "text": specialty_display,
            }
        ],
        "slot": [
            {
                "reference": slot_ref,
            }
        ],
        "participant": [
            {
                "actor": {"reference": patient_ref},
                "status": "accepted",
            },
            {
                "actor": {"reference": practitioner_ref},
                "status": "accepted",
            },
        ],
    }


async def _check_fhir_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/metadata", headers={"Accept": "application/fhir+json"})
    if response.status_code != 200:
        raise RuntimeError(
            f"FHIR metadata check failed (HTTP {response.status_code}): {response.text}"
        )


async def _get_if_exists(
    client: httpx.AsyncClient,
    resource_type: str,
    resource_id: str,
) -> dict[str, Any] | None:
    response = await client.get(f"/{resource_type}/{resource_id}", headers=_build_headers())
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to read {resource_type}/{resource_id} "
            f"(HTTP {response.status_code}): {response.text}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected payload for {resource_type}/{resource_id}.")
    return payload


async def _put_resource(
    client: httpx.AsyncClient,
    resource_type: str,
    resource_id: str,
    resource: dict[str, Any],
) -> str:
    response = await client.put(
        f"/{resource_type}/{resource_id}",
        headers=_build_headers(),
        json=resource,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"Failed to upsert {resource_type}/{resource_id} "
            f"(HTTP {response.status_code}): {response.text}"
        )
    return "updated" if response.status_code == 200 else "created"


async def run_async() -> None:
    provider_items = _load_provider_seed_items()
    provider_by_ref = {item.practitioner_ref: item for item in provider_items}

    timeout = httpx.Timeout(
        connect=settings.fhir_timeout_connect,
        read=settings.fhir_timeout_read,
        write=settings.fhir_timeout_read,
        pool=settings.fhir_timeout_read,
    )

    created = 0
    updated = 0
    first_day = datetime.now(UTC).date() + timedelta(days=1)

    async with httpx.AsyncClient(
        base_url=settings.fhir_base_url.rstrip("/"),
        timeout=timeout,
    ) as client:
        await _check_fhir_ready(client)

        # Seed demo renewal patients and their active medication requests
        for patient_def in DEMO_RENEWAL_PATIENTS:
            patient_key_hash = build_patient_key_hash(
                tenant_id=SEED_TENANT_ID,
                identity_type=patient_def["identity_type"],
                normalized_identity_number=patient_def["national_id"],
            )

            patient_id = _patient_id_for(patient_key_hash)
            patient_ref = f"Patient/{patient_id}"

            patient_resource = _build_demo_patient_resource(
                patient_id=patient_id,
                patient_key_hash=patient_key_hash,
                display=patient_def["display"],
            )
            patient_outcome = await _put_resource(
                client,
                "Patient",
                patient_id,
                patient_resource,
            )
            print(
                f"[{patient_outcome.upper()}] {patient_ref} | "
                f"{patient_def['display']} | renewal demo patient"
            )
            created += 1 if patient_outcome == "created" else 0
            updated += 1 if patient_outcome == "updated" else 0

            for med in patient_def["medications"]:
                med_request_id = _medication_request_id_for(
                    patient_ref,
                    med["code"],
                )
                med_request_resource = _build_demo_medication_request_resource(
                    med_request_id=med_request_id,
                    patient_ref=patient_ref,
                    code=med["code"],
                    display=med["display"],
                    dosage_text=med["dosageText"],
                )

                med_request_outcome = await _put_resource(
                    client,
                    "MedicationRequest",
                    med_request_id,
                    med_request_resource,
                )
                print(
                    f"[{med_request_outcome.upper()}] MedicationRequest/{med_request_id} | "
                    f"{med['display']} | {patient_ref}"
                )
                created += 1 if med_request_outcome == "created" else 0
                updated += 1 if med_request_outcome == "updated" else 0

        # Seed practitioners, schedules, and slots
        for item in provider_items:
            practitioner_resource = _build_practitioner_resource(item)
            practitioner_outcome = await _put_resource(
                client,
                "Practitioner",
                item.practitioner_id,
                practitioner_resource,
            )
            print(
                f"[{practitioner_outcome.upper()}] {item.practitioner_ref} | "
                f"{item.practitioner_display} | {item.specialty}"
            )
            created += 1 if practitioner_outcome == "created" else 0
            updated += 1 if practitioner_outcome == "updated" else 0

            schedule_id = _schedule_id_for(item)
            horizon_start = datetime.combine(first_day, time(hour=0, minute=0), tzinfo=UTC)
            horizon_end = datetime.combine(
                first_day + timedelta(days=SEED_DAYS_AHEAD - 1),
                time(hour=23, minute=59),
                tzinfo=UTC,
            )

            schedule_resource = _build_schedule_resource(
                item=item,
                schedule_id=schedule_id,
                horizon_start_utc=_to_utc_z(horizon_start),
                horizon_end_utc=_to_utc_z(horizon_end),
            )
            schedule_outcome = await _put_resource(
                client,
                "Schedule",
                schedule_id,
                schedule_resource,
            )
            print(
                f"[{schedule_outcome.upper()}] Schedule/{schedule_id} | "
                f"{item.practitioner_display} | {item.specialty}"
            )
            created += 1 if schedule_outcome == "created" else 0
            updated += 1 if schedule_outcome == "updated" else 0

            for day_offset in range(SEED_DAYS_AHEAD):
                current_date = first_day + timedelta(days=day_offset)

                for window_start, window_end in CLINIC_WINDOWS:
                    cursor = datetime.combine(current_date, window_start, tzinfo=UTC)
                    window_end_dt = datetime.combine(current_date, window_end, tzinfo=UTC)

                    while cursor < window_end_dt:
                        slot_end = cursor + timedelta(minutes=SLOT_DURATION_MINUTES)
                        if slot_end > window_end_dt:
                            break

                        slot_id = _slot_id_for(schedule_id, cursor)
                        existing_slot = await _get_if_exists(client, "Slot", slot_id)

                        status = "free"
                        comment = None

                        if existing_slot is not None:
                            existing_status = existing_slot.get("status")
                            if isinstance(existing_status, str) and existing_status.strip():
                                status = existing_status.strip()

                            existing_comment = existing_slot.get("comment")
                            if isinstance(existing_comment, str) and existing_comment.strip():
                                comment = existing_comment.strip()

                        slot_resource = _build_slot_resource(
                            item=item,
                            schedule_id=schedule_id,
                            slot_id=slot_id,
                            start_utc=_to_utc_z(cursor),
                            end_utc=_to_utc_z(slot_end),
                            status=status,
                            comment=comment,
                        )

                        slot_outcome = await _put_resource(
                            client,
                            "Slot",
                            slot_id,
                            slot_resource,
                        )
                        created += 1 if slot_outcome == "created" else 0
                        updated += 1 if slot_outcome == "updated" else 0

                        cursor = slot_end

        # Seed continuity-of-care demo patients and historical booked appointments
        for patient_def in DEMO_CONTINUITY_PATIENTS:
            patient_key_hash = build_patient_key_hash(
                tenant_id=SEED_TENANT_ID,
                identity_type=patient_def["identity_type"],
                normalized_identity_number=patient_def["national_id"],
            )

            patient_id = _patient_id_for(patient_key_hash)
            patient_ref = f"Patient/{patient_id}"

            patient_resource = _build_demo_patient_resource(
                patient_id=patient_id,
                patient_key_hash=patient_key_hash,
                display=patient_def["display"],
            )
            patient_outcome = await _put_resource(
                client,
                "Patient",
                patient_id,
                patient_resource,
            )
            print(
                f"[{patient_outcome.upper()}] {patient_ref} | "
                f"{patient_def['display']} | continuity demo patient"
            )
            created += 1 if patient_outcome == "created" else 0
            updated += 1 if patient_outcome == "updated" else 0

            practitioner_ref = patient_def["practitioner_ref"]
            provider_item = provider_by_ref.get(practitioner_ref)
            if provider_item is None:
                print(
                    f"[SKIPPED] {patient_ref} | "
                    f"{patient_def['display']} | missing provider {practitioner_ref} for continuity demo"
                )
                continue

            schedule_id = _schedule_id_for(provider_item)

            start_dt = datetime.combine(
                datetime.now(UTC).date() - timedelta(days=patient_def["days_ago"]),
                time(hour=patient_def["hour"], minute=patient_def["minute"]),
                tzinfo=UTC,
            )
            end_dt = start_dt + timedelta(minutes=SLOT_DURATION_MINUTES)

            continuity_slot_id = _slot_id_for(schedule_id, start_dt)
            continuity_slot_ref = f"Slot/{continuity_slot_id}"

            continuity_slot_resource = _build_slot_resource(
                item=provider_item,
                schedule_id=schedule_id,
                slot_id=continuity_slot_id,
                start_utc=_to_utc_z(start_dt),
                end_utc=_to_utc_z(end_dt),
                status="busy",
                comment="Historical booked slot seeded for continuity-of-care demo.",
            )

            continuity_slot_outcome = await _put_resource(
                client,
                "Slot",
                continuity_slot_id,
                continuity_slot_resource,
            )
            print(
                f"[{continuity_slot_outcome.upper()}] {continuity_slot_ref} | "
                f"{patient_def['display']} | {patient_def['specialty']} historical slot"
            )
            created += 1 if continuity_slot_outcome == "created" else 0
            updated += 1 if continuity_slot_outcome == "updated" else 0

            appointment_id = _appointment_id_for(
                patient_ref=patient_ref,
                practitioner_ref=practitioner_ref,
                specialty=patient_def["specialty"],
                start_dt=start_dt,
            )
            appointment_resource = _build_demo_appointment_resource(
                appointment_id=appointment_id,
                patient_ref=patient_ref,
                practitioner_ref=practitioner_ref,
                specialty=patient_def["specialty"],
                start_utc=_to_utc_z(start_dt),
                end_utc=_to_utc_z(end_dt),
                slot_ref=continuity_slot_ref,
                description=f"Historical {patient_def['specialty']} follow-up seeded for continuity demo",
            )

            appointment_outcome = await _put_resource(
                client,
                "Appointment",
                appointment_id,
                appointment_resource,
            )
            print(
                f"[{appointment_outcome.upper()}] Appointment/{appointment_id} | "
                f"{patient_def['display']} | {patient_def['practitioner_display']} | "
                f"{patient_def['specialty']}"
            )
            created += 1 if appointment_outcome == "created" else 0
            updated += 1 if appointment_outcome == "updated" else 0

    print("")
    print("FHIR scheduling seed complete.")
    print(f"FHIR base URL : {settings.fhir_base_url.rstrip('/')}")
    print(f"Tenant        : {SEED_TENANT_ID}")
    print(f"Created       : {created}")
    print(f"Updated       : {updated}")


def run() -> None:
    asyncio.run(run_async())


if __name__ == "__main__":
    run()