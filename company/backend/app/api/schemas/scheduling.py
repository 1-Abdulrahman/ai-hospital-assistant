from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.modules.fhir_gateway.schemas import SlotDTO


class SlotsRequest(BaseModel):
    """Request schema for retrieving available appointment slots.
    
    Attributes:
        tenantId: Unique identifier for the healthcare organization/tenant.
        specialty: Medical specialty for which to search available slots.
    """
    tenantId: str = Field(min_length=1)
    specialty: str = Field(min_length=1)

    @field_validator("tenantId", "specialty")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        """Validate and normalize string fields.
        
        Trims surrounding whitespace and rejects blank input to ensure
        all request identifiers are canonical and non-empty.
        
        Args:
            value: The string value to validate.
            
        Returns:
            The trimmed string value.
            
        Raises:
            ValueError: If the value is empty after stripping whitespace.
        """
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class SlotsResponse(BaseModel):
    """Response schema for available appointment slots query.
    
    Contains the list of available slots for a given specialty and tenant,
    along with status information.
    
    Attributes:
        ok: Success status flag (always True for valid responses).
        specialty: The medical specialty corresponding to the returned slots.
        reasonCode: Status code providing additional context about the response.
        items: List of available appointment slots.
    """
    ok: bool = True
    specialty: str
    reasonCode: str
    items: list[SlotDTO]


class BookingRequest(BaseModel):
    """Request schema for creating a new appointment booking.
    
    Contains patient information and appointment slot selection details
    required to successfully book an appointment.
    
    Attributes:
        tenantId: Unique identifier for the healthcare organization.
        nationalId: Patient's national identification number.
        email: Patient's email address for appointment confirmation.
        specialty: Medical specialty for the appointment.
        slotId: Unique identifier of the selected appointment slot.
    """
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)
    specialty: str = Field(min_length=1)
    slotId: str = Field(min_length=1)

    @field_validator("tenantId", "nationalId", "email", "specialty", "slotId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        """Validate and normalize all string booking fields.
        
        Ensures all string fields are trimmed of whitespace and non-empty.
        This preprocessing keeps all request data in canonical form before
        being passed to downstream service logic.
        
        Args:
            value: The string value to validate.
            
        Returns:
            The trimmed string value.
            
        Raises:
            ValueError: If the value is empty after stripping whitespace.
        """
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class BookingResponse(BaseModel):
    """Response schema for a successfully created appointment booking.
    
    Provides confirmation details of the newly created appointment including
    appointment identifiers, specialty, slot information, and status message.
    
    Attributes:
        ok: Success status flag (always True for valid responses).
        reasonCode: Status code providing context about the booking result.
        appointmentId: System-generated unique identifier for the appointment.
        appointmentRef: Reference identifier for the appointment (e.g., confirmation number).
        specialty: Medical specialty of the booked appointment.
        slot: The appointment slot details that was booked.
        message: Human-readable confirmation message.
    """
    ok: bool = True
    reasonCode: str
    appointmentId: str
    appointmentRef: str
    specialty: str
    slot: SlotDTO
    message: str