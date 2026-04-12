from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("Email cannot be empty.")
    if not _EMAIL_RE.fullmatch(cleaned):
        raise ValueError("Email must be a valid email address.")
    return cleaned


class OtpRequestIn(BaseModel):
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)

    @field_validator("tenantId", "nationalId")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class OtpRequestOut(BaseModel):
    ok: bool = True
    message: str
    expiresIn: int


class OtpVerifyIn(BaseModel):
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)
    otp: str = Field(pattern=r"^\d{6}$")

    @field_validator("tenantId", "nationalId", "otp")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class OtpVerifyOut(BaseModel):
    ok: bool = True
    verified: bool = True
    message: str