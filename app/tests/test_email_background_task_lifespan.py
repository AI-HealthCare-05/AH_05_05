import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI
from httpx import ASGITransport, AsyncClient

from app import main as main_module
from app.core.api_timeout import ApiTimeoutMiddleware
from app.dependencies.email_background_tasks import FastAPIEmailTaskScheduler
from app.main import lifespan


class RecordingManager:
    def __init__(self) -> None:
        self.recovered = False
        self.shutdown_called = False

    async def recover(self) -> None:
        self.recovered = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.mark.asyncio
async def test_lifespan_recovers_and_shuts_down_email_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = RecordingManager()
    monkeypatch.setattr(main_module, "build_email_background_task_manager", lambda: manager)
    test_app = SimpleNamespace(state=SimpleNamespace())

    async with lifespan(test_app):
        assert manager.recovered is True
        assert test_app.state.email_background_task_manager is manager

    assert manager.shutdown_called is True
    assert not hasattr(test_app.state, "email_background_task_manager")


@pytest.mark.asyncio
async def test_background_launcher_escapes_request_timeout_and_remains_managed() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class Executor:
        async def recoverable_job_ids(self, _now):
            return []

        async def run(self, _job_id: int) -> None:
            started.set()
            await release.wait()

    from app.services.email_background_tasks import EmailBackgroundTaskManager

    manager = EmailBackgroundTaskManager(Executor())
    test_app = FastAPI()

    @test_app.post("/api/v1/test", status_code=202)
    async def launch(background_tasks: BackgroundTasks) -> None:
        FastAPIEmailTaskScheduler(background_tasks, manager).schedule(41)

    test_app.add_middleware(
        ApiTimeoutMiddleware,
        router=test_app.router,
        default_timeout_seconds=0.01,
        path_prefix="/api/v1/",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/api/v1/test")

    await asyncio.wait_for(started.wait(), timeout=0.1)
    assert response.status_code == 202
    assert manager.active_job_ids == {41}
    release.set()
    await manager.wait_until_idle()
