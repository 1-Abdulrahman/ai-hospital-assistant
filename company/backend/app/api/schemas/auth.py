from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    tenantId: str | None = None
    email: str | None = None
    username: str | None = None
    password: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_supported_login_shape(self) -> "LoginRequest":
        """Allow only one supported login shape.

        Accepted forms:
        - `tenantId` + `email` + `password`
        - `username` + `password`
        """
        email_login = bool(self.tenantId and self.email)
        username_login = bool(self.username)

        # Exactly one shape must be selected, otherwise request is ambiguous/invalid.
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
        """Build a response that serves both API and current portal naming contracts."""
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
        """Return whether the authenticated user has company-level admin privileges."""
        return self.role == "company_admin"


class ErrorDetail(BaseModel):
    message: str
    reasonCode: str | None = None
    details: str | None = None


def normalize_portal_role(role: str) -> str:
    """Map backend role values to portal role labels expected by the UI."""
    mapping: dict[str, str] = {
        "company_admin": "ADMIN",
        "tenant_admin": "TENANT_ADMIN",
    }
    # Fall back to upper-cased passthrough for roles without an explicit mapping.
    return mapping.get(role, role.upper())