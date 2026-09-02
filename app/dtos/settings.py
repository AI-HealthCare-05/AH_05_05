from datetime import datetime, time

from pydantic import ConfigDict

from app.dtos.base import CamelModel


class NotifySettingsUpdateRequest(CamelModel):
    # 전 필드가 선택이라 모르는 키를 무시하면 아무것도 안 바뀌고 성공 응답이 나간다.
    model_config = ConfigDict(extra="forbid")

    notify_medication: bool | None = None
    notify_supplement: bool | None = None
    notify_schedule: bool | None = None
    morning_medication_time: time | None = None
    lunch_medication_time: time | None = None
    evening_medication_time: time | None = None
    bedtime_medication_time: time | None = None


class NotifySettingsResponse(CamelModel):
    notify_medication: bool
    notify_supplement: bool
    notify_schedule: bool
    notify_consented_at: datetime | None
    morning_medication_time: time
    lunch_medication_time: time
    evening_medication_time: time
    bedtime_medication_time: time
