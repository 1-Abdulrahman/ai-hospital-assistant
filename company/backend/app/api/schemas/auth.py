from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    tenantId: str | None = None
    email: str | None = None
    username: str | None = None
    password: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_supported_login_shape(self) -> "LoginRequest":
        email_login = bool(self.tenantId and self.email)
        username_login = bool(self.username)

        if email_login == username_login:
            raise ValueError(
                "Provide either tenantId and email, or username and password."
            )

        return self


class CurrentUserResponse(BaseModel):
    tenantId: str
    email: str
    role: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    accessToken: str
    tokenType: str = "bearer"
    expiresIn: int = 3600
    user: CurrentUserResponse

    # Compatibility fields for the current portal UI.
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    role: str
    tenantId: str

    @classmethod
    def from_values(
        cls,
        *,
        access_token: str,
        expires_in: int,
        tenant_id: str,
        email: str,
        role: str,
        portal_role: str,
    ) -> "LoginResponse":
        return cls(
            accessToken=access_token,
            tokenType="bearer",
            expiresIn=expires_in,
            user=CurrentUserResponse(
                tenantId=tenant_id,
                email=email,
                role=role,
            ),
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            role=portal_role,
            tenantId=tenant_id,
        )


class AuthenticatedPortalUser(BaseModel):
    id: str
    tenantId: str
    email: str
    role: str
    requestTenantId: str
    isActive: bool

    def is_company_admin(self) -> bool:
        return self.role == "company_admin"


class ErrorDetail(BaseModel):
    message: str
    reasonCode: str | None = None
    details: str | None = None


def normalize_portal_role(role: str) -> str:
    mapping: dict[str, str] = {
        "company_admin": "ADMIN",
        "tenant_admin": "TENANT_ADMIN",
    }
    return mapping.get(role, role.upper())