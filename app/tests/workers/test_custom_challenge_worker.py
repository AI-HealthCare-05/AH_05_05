from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _worker() -> Any:
    try:
        return import_module("app.workers.custom_challenge_worker")
    except ModuleNotFoundError as error:
        pytest.fail(f"custom challenge worker is not registered: {error}")


@pytest.mark.asyncio
async def test_cron_finalizes_due_custom_challenges() -> None:
    worker = _worker()

    class RecordingLifecycle:
        async def finalize_due(self) -> int:
            return 3

    finalized = await worker.finalize_due_custom_challenges(
        {"custom_challenge_lifecycle_service": RecordingLifecycle()}
    )

    assert finalized == 3


@pytest.mark.asyncio
async def test_startup_and_shutdown_only_close_worker_owned_tortoise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _worker()
    events: list[str] = []

    async def init(*, config: object) -> None:
        assert config is worker.TORTOISE_ORM
        events.append("init")

    async def close_connections() -> None:
        events.append("close")

    monkeypatch.setattr(worker.Tortoise, "_inited", False)
    monkeypatch.setattr(worker.Tortoise, "init", init)
    monkeypatch.setattr(worker.Tortoise, "close_connections", close_connections)
    context: dict[str, object] = {}

    await worker.startup(context)
    await worker.shutdown(context)

    assert events == ["init", "close"]

    events.clear()
    monkeypatch.setattr(worker.Tortoise, "_inited", True)
    shared_context: dict[str, object] = {}
    await worker.startup(shared_context)
    await worker.shutdown(shared_context)

    assert events == []


def test_worker_settings_register_a_minutely_cron_job() -> None:
    worker = _worker()

    assert worker.WorkerSettings.queue_name == "arq:custom-challenge"
    assert worker.WorkerSettings.functions == []
    assert len(worker.WorkerSettings.cron_jobs) == 1
    cron_job = worker.WorkerSettings.cron_jobs[0]
    assert cron_job.coroutine is worker.finalize_due_custom_challenges
    assert cron_job.minute == set(range(60))
