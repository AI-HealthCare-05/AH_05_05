from types import SimpleNamespace

import pytest

from app import main as main_module
from app.main import lifespan


class RecordingAlarmManager:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def start(self) -> None:
        self.calls.append("alarm-start")

    async def shutdown(self) -> None:
        self.calls.append("alarm-shutdown")


class RecordingEmailManager:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def recover(self) -> None:
        self.calls.append("email-recover")

    async def shutdown(self) -> None:
        self.calls.append("email-shutdown")


@pytest.mark.asyncio
async def test_lifespan_starts_and_shuts_down_alarm_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    alarm_manager = RecordingAlarmManager(calls)
    email_manager = RecordingEmailManager(calls)
    monkeypatch.setattr(main_module, "build_alarm_background_task_manager", lambda: alarm_manager)
    monkeypatch.setattr(main_module, "build_email_background_task_manager", lambda: email_manager)
    test_app = SimpleNamespace(state=SimpleNamespace())

    async with lifespan(test_app):
        assert test_app.state.alarm_background_task_manager is alarm_manager
        assert test_app.state.email_background_task_manager is email_manager
        assert calls == ["email-recover", "alarm-start"]

    assert calls == ["email-recover", "alarm-start", "alarm-shutdown", "email-shutdown"]
    assert not hasattr(test_app.state, "alarm_background_task_manager")
    assert not hasattr(test_app.state, "email_background_task_manager")
