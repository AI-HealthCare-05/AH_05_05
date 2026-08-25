from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers import medication_guide_ocr_worker as worker


@pytest.mark.asyncio
async def test_process_routes_arq_job_try_to_ocr_job_service():
    service = MagicMock()
    service.process = AsyncMock()
    extractor = object()

    await worker.process_medication_guide_ocr(
        {"ocr_job_service": service, "ocr_extractor": extractor, "job_try": 2},
        41,
    )

    service.process.assert_awaited_once_with(41, extractor, job_try=2)


@pytest.mark.asyncio
async def test_cleanup_cron_delegates_to_expired_job_cleanup():
    service = MagicMock()
    service.cleanup_expired = AsyncMock(return_value=3)

    await worker.cleanup_expired_ocr_jobs({"ocr_job_service": service})

    service.cleanup_expired.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_startup_and_shutdown_manage_worker_owned_resources(monkeypatch):
    client = MagicMock()
    client.aclose = AsyncMock()
    redis_pool = MagicMock()
    redis_pool.aclose = AsyncMock()
    init = AsyncMock()
    close_connections = AsyncMock()

    monkeypatch.setattr(worker.Tortoise, "_inited", False)
    monkeypatch.setattr(worker.Tortoise, "init", init)
    monkeypatch.setattr(worker.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(worker.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(worker, "create_pool", AsyncMock(return_value=redis_pool))
    monkeypatch.setattr(worker.config, "CLOVA_TEMPLATE_ID", 1)

    ctx: dict[str, object] = {}
    await worker.startup(ctx)

    init.assert_awaited_once_with(config=worker.TORTOISE_ORM)
    assert ctx["ocr_redis_pool"] is redis_pool
    assert ctx["http_client"] is client
    assert ctx["ocr_job_service"].redis_pool is redis_pool

    await worker.shutdown(ctx)

    client.aclose.assert_awaited_once_with()
    redis_pool.aclose.assert_awaited_once_with()
    close_connections.assert_awaited_once_with()


def test_worker_settings_exposes_processing_and_cleanup_with_two_attempt_limit():
    assert worker.WorkerSettings.functions == [worker.process_medication_guide_ocr]
    assert worker.WorkerSettings.queue_name == worker.config.OCR_QUEUE_NAME
    assert worker.WorkerSettings.max_tries == 2
    assert len(worker.WorkerSettings.cron_jobs) == 1
