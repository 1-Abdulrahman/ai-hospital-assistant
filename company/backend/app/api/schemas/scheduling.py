from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.modules.fhir_gateway.schemas import SlotDTO


class SlotsRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    specialty: str = Field(min_length=1)

    @field_validator("tenantId", "specialty")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class SlotsResponse(BaseModel):
    ok: bool = True
    specialty: str
    reasonCode: str
    items: list[SlotDTO]


class BookingRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)
    specialty: str = Field(min_length=1)
    slotId: str = Field(min_length=1)

    @field_validator("tenantId", "nationalId", "email", "specialty", "slotId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class BookingResponse(BaseModel):
    ok: bool = True
    reasonCode: str
    appointmentId: str
    appointmentRef: str
    specialty: str
    slot: SlotDTO
    message: str