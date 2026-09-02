from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

import aiohttp
import orjson
from pywebpush import WebPushException, webpush_async

from app.core import config
from app.services.follow_up_visit_alarms import follow_up_message


class PushSubscriptionData(Protocol):
    endpoint: str
    p256dh_key: str
    auth_key: str


class AlarmData(Protocol):
    id: int
    title: str
    message: str | None
    alarm_type: object
    meal_slot: object | None
    next_trigger_at: datetime | str


class MedicationData(Protocol):
    name: str


class PushResultKind(StrEnum):
    SUCCESS = "SUCCESS"
    EXPIRED = "EXPIRED"
    RETRYABLE = "RETRYABLE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"


@dataclass(frozen=True, slots=True)
class PushResult:
    kind: PushResultKind
    status_code: int | None = None
    error_code: str | None = None


class WebPushService:
    @staticmethod
    def build_payload(
        alarm: AlarmData,
        medications: list[MedicationData],
        nutrient_items: list[object] | None = None,
        follow_up_visit: object | None = None,
    ) -> dict[str, object]:
        alarm_type = alarm.alarm_type
        meal_slot = alarm.meal_slot
        message = alarm.message or alarm.title
        title = alarm.title
        medication_names = [medication.name for medication in medications]
        if str(alarm_type) == "MEDICATION" and medication_names:
            message = f"{', '.join(medication_names)} 복용 시간입니다."
        if str(alarm_type) == "NUTRIENT" and nutrient_items:
            title = "영양제 알림"
            message = "영양제 챙기실 시간이에요"
        if str(alarm_type) == "FOLLOW_UP_VISIT" and follow_up_visit is not None:
            title = "진료 일정 알림"
            message = follow_up_message(follow_up_visit)
        trigger_at = alarm.next_trigger_at
        if hasattr(trigger_at, "isoformat"):
            trigger_at = trigger_at.isoformat()
        return {
            "alarmId": alarm.id,
            "title": title,
            "body": message,
            "clickUrl": config.ALARM_CLICK_URL,
            "alarmType": str(alarm_type),
            "mealSlot": str(meal_slot) if meal_slot is not None else None,
            "triggerAt": trigger_at,
        }

    async def send(self, subscription: PushSubscriptionData, payload: dict[str, object]) -> PushResult:
        try:
            response = await webpush_async(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
                },
                data=orjson.dumps(payload).decode(),
                vapid_private_key=config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": config.VAPID_SUBJECT},
                ttl=config.ALARM_PUSH_TTL_SECONDS,
                timeout=10,
            )
        except WebPushException as exc:
            status_code = self._response_status(exc.response)
            return self._classify_failure(status_code)
        except (TimeoutError, aiohttp.ClientError):
            return PushResult(PushResultKind.RETRYABLE, error_code="PUSH_TEMPORARY_ERROR")

        status_code = self._response_status(response)
        if status_code is None or status_code <= 202:
            return PushResult(PushResultKind.SUCCESS, status_code=status_code)
        return self._classify_failure(status_code)

    @staticmethod
    def _response_status(response: object | None) -> int | None:
        if response is None:
            return None
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        status_code = getattr(response, "status", None)
        return status_code if isinstance(status_code, int) else None

    @staticmethod
    def _classify_failure(status_code: int | None) -> PushResult:
        if status_code in {404, 410}:
            return PushResult(PushResultKind.EXPIRED, status_code, "PUSH_SUBSCRIPTION_EXPIRED")
        if status_code == 429 or (status_code is not None and status_code >= 500):
            return PushResult(PushResultKind.RETRYABLE, status_code, "PUSH_TEMPORARY_ERROR")
        return PushResult(PushResultKind.PERMANENT_FAILURE, status_code, "PUSH_REJECTED")
