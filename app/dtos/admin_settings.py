from pydantic import EmailStr, Field

from app.dtos.base import CamelModel


class SmtpSettingsUpdateRequest(CamelModel):
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_user: str = Field(min_length=1, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    smtp_from_email: EmailStr


class SmtpSettingsResponse(CamelModel):
    smtp_host: str | None = None
    smtp_port: int
    smtp_user: str | None = None
    smtp_from_email: str | None = None
    smtp_password_configured: bool
