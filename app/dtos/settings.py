from datetime import datetime

from pydantic import ConfigDict

from app.dtos.base import CamelModel


class NotifySettingsUpdateRequest(CamelModel):
    # 전 필드가 선택이라 모르는 키를 무시하면 아무것도 안 바뀌고 성공 응답이 나간다.
    model_config = ConfigDict(extra="forbid")

    notify_medication: bool | None = None
    notify_supplement: bool | None = None


class NotifySettingsResponse(CamelModel):
    notify_medication: bool
    notify_supplement: bool
    notify_consented_at: datetime | None
