from pydantic import BaseModel, Field, field_validator


class OtpRequestIn(BaseModel):
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)

    @field_validator("tenantId", "nationalId", "email")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class OtpRequestOut(BaseModel):
    ok: bool = True
    message: str
    expiresIn: int


class OtpVerifyIn(BaseModel):
    tenantId: str = Field(min_length=1)
    nationalId: str = Field(min_length=1)
    email: str = Field(min_length=3)
    otp: str = Field(pattern=r"^\d{6}$")

    @field_validator("tenantId", "nationalId", "email", "otp")
    @classmethod
    def strip_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty.")
        return cleaned


class OtpVerifyOut(BaseModel):
    ok: bool = True
    verified: bool = True
    message: str