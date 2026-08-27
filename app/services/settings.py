from datetime import datetime

from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.settings import NotifySettingsUpdateRequest
from app.models.users import User, UserSettings

_SETTING_FIELD_MAP = {
    "notify_medication": "is_notify_medication",
    "notify_supplement": "is_notify_supplement",
}


class NotifySettingsService:
    async def get(self, user: User) -> UserSettings:
        settings, _ = await UserSettings.get_or_create(user=user)
        return settings

    async def update(self, user: User, data: NotifySettingsUpdateRequest) -> UserSettings:
        async with in_transaction() as connection:
            settings = await UserSettings.filter(user_id=user.id).using_db(connection).select_for_update().first()
            if settings is None:
                settings = await UserSettings.create(user_id=user.id, using_db=connection)

            update_fields: list[str] = []
            supplied = data.model_dump(exclude_unset=True)
            for request_field, model_field in _SETTING_FIELD_MAP.items():
                value = supplied.get(request_field)
                if value is not None and getattr(settings, model_field) != value:
                    setattr(settings, model_field, value)
                    update_fields.append(model_field)

            if settings.notify_consented_at is None:
                settings.notify_consented_at = datetime.now(config.TIMEZONE)
                update_fields.append("notify_consented_at")

            if update_fields:
                await settings.save(using_db=connection, update_fields=update_fields)

        return settings
