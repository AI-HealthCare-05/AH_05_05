from app.models.admin_settings import AdminSetting


class AdminSettingsRepository:
    async def get_smtp(self) -> AdminSetting | None:
        return await AdminSetting.get_or_none(setting_key="SMTP")

    async def get_smtp_for_update(self) -> AdminSetting | None:
        return await AdminSetting.filter(setting_key="SMTP").select_for_update().first()
