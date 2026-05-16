"""
OTP (One-Time Password) request and verification schemas.

This module provides Pydantic models for OTP request/verification workflows,
including email validation and field sanitization.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Email regex pattern: one or more non-whitespace/non-@ chars, @, domain, dot, TLD
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(value: str) -> str:
    """
    Validate and normalize an email address.

    Args:
        value: The email address to validate.

    Returns:
        The normalized (stripped and lowercased) email address.

    Raises:
        ValueError: If email is empty or doesn't match the email pattern.
    """
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("Email cannot be empty.")
    if not _EMAIL_RE.fullmatch(cleaned):
        raise ValueError("Email must be a valid email address.")
    return cleaned


class OtpRequestIn(BaseModel):
    """
    Schema for requesting an OTP.

    Attributes:
        tenantId: Unique identifier for the tenant.
        nationalId: User's national identification number.
        email: User's email address where OTP will be sent.
    """
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)

    @field_validator("tenantId", "nationalId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        """Strip whitespace and ensure value is not empty."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate and normalize email address."""
        return _validate_email(value)


class OtpRequestOut(BaseModel):
    """
    Schema for OTP request response.

    Attributes:
        ok: Indicates successful request processing.
        message: Human-readable response message (e.g., confirmation or error details).
        expiresIn: Time in seconds until the OTP expires.
    """
    ok: bool = True
    message: str
    expiresIn: int


class OtpVerifyIn(BaseModel):
    """
    Schema for OTP verification request.

    Attributes:
        tenantId: Unique identifier for the tenant.
        nationalId: User's national identification number.
        email: User's email address used during OTP request.
        otp: 6-digit OTP code received by the user.
    """
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)
    otp: str = Field(pattern=r"^\d{6}$")  # Exactly 6 digits

    @field_validator("tenantId", "nationalId", "otp")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        """Strip whitespace and ensure value is not empty."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        """Validate and normalize email address."""
        return _validate_email(value)


class OtpVerifyOut(BaseModel):
    """
    Schema for OTP verification response.

    Attributes:
        ok: Indicates successful verification processing.
        verified: Whether the OTP was successfully verified.
        message: Human-readable response message (e.g., success or error details).
    """
    ok: bool = True
    verified: bool = True
    message: str