from datetime import datetime

from app.dtos.base import CamelModel


class NotifySettingsUpdateRequest(CamelModel):
    notify_medication: bool | None = None
    notify_supplement: bool | None = None


class NotifySettingsResponse(CamelModel):
    notify_medication: bool
    notify_supplement: bool
    notify_consented_at: datetime | None
