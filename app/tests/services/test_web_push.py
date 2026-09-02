from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pywebpush import WebPushException

from app.models.enums import AlarmType, MealSlot
from app.services.web_push import PushResultKind, WebPushService


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def subscription() -> SimpleNamespace:
    return SimpleNamespace(
        endpoint="https://push.example.test/web-push",
        p256dh_key="p256dh",
        auth_key="auth",
    )


@pytest.mark.asyncio
async def test_send_success(monkeypatch: pytest.MonkeyPatch):
    sender = AsyncMock(return_value=FakeResponse(201))
    monkeypatch.setattr("app.services.web_push.webpush_async", sender)

    result = await WebPushService().send(subscription(), {"title": "복약 알림"})

    assert result.kind == PushResultKind.SUCCESS


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 410])
async def test_expired_subscription(status_code: int, monkeypatch: pytest.MonkeyPatch):
    error = WebPushException("expired", response=FakeResponse(status_code))
    monkeypatch.setattr("app.services.web_push.webpush_async", AsyncMock(side_effect=error))

    result = await WebPushService().send(subscription(), {})

    assert result.kind == PushResultKind.EXPIRED


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_retryable_http_failure(status_code: int, monkeypatch: pytest.MonkeyPatch):
    error = WebPushException("temporary", response=FakeResponse(status_code))
    monkeypatch.setattr("app.services.web_push.webpush_async", AsyncMock(side_effect=error))

    result = await WebPushService().send(subscription(), {})

    assert result.kind == PushResultKind.RETRYABLE


@pytest.mark.asyncio
async def test_timeout_is_retryable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.web_push.webpush_async", AsyncMock(side_effect=TimeoutError))

    result = await WebPushService().send(subscription(), {})

    assert result.kind == PushResultKind.RETRYABLE


@pytest.mark.asyncio
async def test_other_client_error_is_permanent(monkeypatch: pytest.MonkeyPatch):
    error = WebPushException("invalid", response=FakeResponse(400))
    monkeypatch.setattr("app.services.web_push.webpush_async", AsyncMock(side_effect=error))

    result = await WebPushService().send(subscription(), {})

    assert result.kind == PushResultKind.PERMANENT_FAILURE


def test_build_medication_payload_uses_confirmed_message_when_current_medications_exist(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.services.web_push.config.ALARM_CLICK_URL", "/alarms")
    alarm = SimpleNamespace(
        id=7,
        title="아침 복약",
        message="복약 시간입니다.",
        alarm_type=AlarmType.MEDICATION,
        meal_slot=MealSlot.MORNING,
        next_trigger_at="2026-08-20T08:00:00+09:00",
    )
    medications = [SimpleNamespace(name="약A"), SimpleNamespace(name="약B")]

    payload = WebPushService().build_payload(alarm, medications)

    assert payload["alarmId"] == 7
    assert payload["body"] == "약 드실 시간이에요"
    assert payload["clickUrl"] == "/alarms"
    assert "auth_key" not in payload
