from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
COMPANY_DIR = BASE_DIR.parent
ENV_FILE = COMPANY_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="AI Health Assistant", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    hospital_origin: str = Field(default="http://localhost:3000", alias="HOSPITAL_ORIGIN")
    portal_origin: str = Field(default="http://localhost:3001", alias="PORTAL_ORIGIN")

    database_url: str = Field(default="sqlite:////data/app.db", alias="DATABASE_URL")

    jwt_secret: str = Field(default="change-me-offline", alias="JWT_SECRET")
    jwt_alg: str = Field(default="HS256", alias="JWT_ALG")

    otp_secret: str = Field(default="change-me-offline", alias="OTP_SECRET")
    otp_ttl_seconds: int = Field(default=300, alias="OTP_TTL_SECONDS")
    otp_max_attempts: int = Field(default=5, alias="OTP_MAX_ATTEMPTS")

    fhir_base_url: str = Field(default="http://fhir:8080/fhir", alias="FHIR_BASE_URL")
    fhir_timeout_connect: float = Field(default=2.0, alias="FHIR_TIMEOUT_CONNECT")
    fhir_timeout_read: float = Field(default=5.0, alias="FHIR_TIMEOUT_READ")

    smtp_host: str = Field(default="mailhog", alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, alias="SMTP_PORT")
    smtp_from: str = Field(default="no-reply@mvp.local", alias="SMTP_FROM")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()