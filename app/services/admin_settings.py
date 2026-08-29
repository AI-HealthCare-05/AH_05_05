from dataclasses import dataclass

from pydantic import SecretStr
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import SmtpPasswordRequiredError
from app.core.smtp_settings_encryption import decrypt_smtp_password, encrypt_smtp_password
from app.dtos.admin_settings import SmtpSettingsResponse, SmtpSettingsUpdateRequest
from app.models.admin_settings import AdminSetting
from app.repositories.admin_settings_repository import AdminSettingsRepository


@dataclass(frozen=True)
class SmtpRuntimeSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str


class SmtpSettingsService:
    def __init__(self, repository: AdminSettingsRepository | None = None) -> None:
        self.repository = repository or AdminSettingsRepository()

    async def get(self) -> SmtpSettingsResponse:
        setting = await self.repository.get_smtp()
        if setting is not None:
            return self._response(setting)
        return SmtpSettingsResponse(
            smtp_host=config.SMTP_HOST,
            smtp_port=config.SMTP_PORT,
            smtp_user=config.SMTP_USER,
            smtp_from_email=config.SMTP_FROM_EMAIL,
            smtp_password_configured=bool(self._secret_value(config.SMTP_PASSWORD)),
        )

    async def update(
        self,
        request: SmtpSettingsUpdateRequest,
        *,
        actor_admin_id: int,
    ) -> SmtpSettingsResponse:
        password = (request.smtp_password or "").strip()
        async with in_transaction():
            setting = await self.repository.get_smtp_for_update()
            if setting is None:
                if not password:
                    raise SmtpPasswordRequiredError()
                setting = await AdminSetting.create(
                    setting_key="SMTP",
                    smtp_host=request.smtp_host,
                    smtp_port=request.smtp_port,
                    smtp_user=request.smtp_user,
                    smtp_password_enc=encrypt_smtp_password(password),
                    smtp_from_email=str(request.smtp_from_email),
                    updated_by_admin_id=actor_admin_id,
                )
            else:
                setting.smtp_host = request.smtp_host
                setting.smtp_port = request.smtp_port
                setting.smtp_user = request.smtp_user
                setting.smtp_from_email = str(request.smtp_from_email)
                setting.updated_by_admin_id = actor_admin_id
                update_fields = [
                    "smtp_host",
                    "smtp_port",
                    "smtp_user",
                    "smtp_from_email",
                    "updated_by_admin_id",
                    "updated_at",
                ]
                if password:
                    setting.smtp_password_enc = encrypt_smtp_password(password)
                    update_fields.append("smtp_password_enc")
                await setting.save(update_fields=update_fields)
        return self._response(setting)

    async def get_runtime_settings(self) -> SmtpRuntimeSettings:
        setting = await self.repository.get_smtp()
        if setting is not None:
            return SmtpRuntimeSettings(
                host=setting.smtp_host,
                port=setting.smtp_port,
                username=setting.smtp_user,
                password=decrypt_smtp_password(setting.smtp_password_enc),
                from_email=setting.smtp_from_email,
            )
        return SmtpRuntimeSettings(
            host=self._required("SMTP_HOST", config.SMTP_HOST),
            port=config.SMTP_PORT,
            username=self._required("SMTP_USER", config.SMTP_USER),
            password=self._required("SMTP_PASSWORD", config.SMTP_PASSWORD),
            from_email=self._required("SMTP_FROM_EMAIL", config.SMTP_FROM_EMAIL),
        )

    @staticmethod
    def _response(setting: AdminSetting) -> SmtpSettingsResponse:
        return SmtpSettingsResponse(
            smtp_host=setting.smtp_host,
            smtp_port=setting.smtp_port,
            smtp_user=setting.smtp_user,
            smtp_from_email=setting.smtp_from_email,
            smtp_password_configured=True,
        )

    @staticmethod
    def _secret_value(value: str | SecretStr | None) -> str | None:
        return value.get_secret_value() if isinstance(value, SecretStr) else value

    @classmethod
    def _required(cls, name: str, value: str | SecretStr | None) -> str:
        resolved = cls._secret_value(value)
        if not resolved:
            raise RuntimeError(f"email-worker 필수 설정이 비어 있습니다: {name}")
        return resolved
