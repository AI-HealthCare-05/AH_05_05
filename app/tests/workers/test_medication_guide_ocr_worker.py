from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.workers import medication_guide_ocr_worker as worker


@pytest.mark.asyncio
async def test_process_routes_arq_job_try_to_ocr_job_service():
    service = MagicMock()
    service.process = AsyncMock()
    analyzer = object()

    await worker.process_medication_guide_ocr(
        {"ocr_job_service": service, "ocr_analyzer": analyzer, "job_try": 2},
        41,
    )

    service.process.assert_awaited_once_with(41, analyzer, job_try=2)


@pytest.mark.asyncio
async def test_cleanup_cron_delegates_to_expired_job_cleanup():
    service = MagicMock()
    service.cleanup_expired = AsyncMock(return_value=3)

    await worker.cleanup_expired_ocr_jobs({"ocr_job_service": service})

    service.cleanup_expired.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_startup_and_shutdown_manage_worker_owned_resources(monkeypatch):
    redis_pool = MagicMock()
    redis_pool.aclose = AsyncMock()
    provider = MagicMock()
    provider.aclose = AsyncMock()
    structurer = MagicMock()
    structurer.aclose = AsyncMock()
    analyzer = object()
    init = AsyncMock()
    close_connections = AsyncMock()

    monkeypatch.setattr(worker.Tortoise, "_inited", False)
    monkeypatch.setattr(worker.Tortoise, "init", init)
    monkeypatch.setattr(worker.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(worker, "create_pool", AsyncMock(return_value=redis_pool))
    clova_constructor = Mock(return_value=provider)
    structurer_constructor = Mock(return_value=structurer)
    analyzer_constructor = Mock(return_value=analyzer)
    monkeypatch.setattr(worker, "ClovaGeneralOcrProvider", clova_constructor)
    monkeypatch.setattr(worker, "OpenAIGroundedStructurer", structurer_constructor)
    monkeypatch.setattr(worker, "MedicationOcrV3Service", analyzer_constructor)
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_INVOKE_URL", "https://ocr.example/invoke")
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_SECRET", MagicMock(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(worker.config, "OPENAI_API_KEY", MagicMock(get_secret_value=lambda: "openai-key"))
    monkeypatch.setattr(worker.config, "OPENAI_MODEL", "gpt-test")

    ctx: dict[str, object] = {}
    await worker.startup(ctx)

    init.assert_awaited_once_with(config=worker.TORTOISE_ORM)
    assert ctx["ocr_redis_pool"] is redis_pool
    assert ctx["ocr_provider"] is provider
    assert ctx["ocr_structurer"] is structurer
    assert ctx["ocr_analyzer"] is analyzer
    assert ctx["ocr_job_service"].redis_pool is redis_pool
    clova_constructor.assert_called_once_with(endpoint="https://ocr.example/invoke", secret="secret")
    structurer_constructor.assert_called_once_with(api_key="openai-key", model="gpt-test")
    analyzer_constructor.assert_called_once_with(provider=provider, structurer=structurer)

    await worker.shutdown(ctx)
    await worker.shutdown(ctx)

    structurer.aclose.assert_awaited_once_with()
    provider.aclose.assert_awaited_once_with()
    redis_pool.aclose.assert_awaited_once_with()
    close_connections.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_startup_omits_optional_llm_provider_without_api_key(monkeypatch):
    redis_pool = MagicMock(aclose=AsyncMock())
    provider = MagicMock(aclose=AsyncMock())
    analyzer = object()
    monkeypatch.setattr(worker.Tortoise, "_inited", True)
    monkeypatch.setattr(worker.Tortoise, "close_connections", AsyncMock())
    monkeypatch.setattr(worker, "create_pool", AsyncMock(return_value=redis_pool))
    monkeypatch.setattr(worker, "ClovaGeneralOcrProvider", Mock(return_value=provider))
    structurer_constructor = Mock()
    monkeypatch.setattr(worker, "OpenAIGroundedStructurer", structurer_constructor)
    analyzer_constructor = Mock(return_value=analyzer)
    monkeypatch.setattr(worker, "MedicationOcrV3Service", analyzer_constructor)
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_INVOKE_URL", "https://ocr.example/invoke")
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_SECRET", MagicMock(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(worker.config, "OPENAI_API_KEY", None)

    ctx: dict[str, object] = {}
    await worker.startup(ctx)

    assert ctx["ocr_structurer"] is None
    structurer_constructor.assert_not_called()
    analyzer_constructor.assert_called_once_with(provider=provider, structurer=None)
    await worker.shutdown(ctx)


@pytest.mark.asyncio
async def test_startup_rejects_missing_general_ocr_config_before_allocating_resources(monkeypatch):
    create_pool = AsyncMock()
    monkeypatch.setattr(worker, "create_pool", create_pool)
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_INVOKE_URL", None)
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_SECRET", None)

    with pytest.raises(worker.OcrProviderConfigError):
        await worker.startup({})

    create_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_error_closes_every_allocated_resource_once(monkeypatch):
    redis_pool = MagicMock(aclose=AsyncMock())
    provider = MagicMock(aclose=AsyncMock())
    structurer = MagicMock(aclose=AsyncMock())
    close_connections = AsyncMock()
    monkeypatch.setattr(worker.Tortoise, "_inited", False)
    monkeypatch.setattr(worker.Tortoise, "init", AsyncMock())
    monkeypatch.setattr(worker.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(worker, "create_pool", AsyncMock(return_value=redis_pool))
    monkeypatch.setattr(worker, "ClovaGeneralOcrProvider", Mock(return_value=provider))
    monkeypatch.setattr(worker, "OpenAIGroundedStructurer", Mock(return_value=structurer))
    monkeypatch.setattr(worker, "MedicationOcrV3Service", Mock(side_effect=RuntimeError("startup failed")))
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_INVOKE_URL", "https://ocr.example/invoke")
    monkeypatch.setattr(worker.config, "CLOVA_GENERAL_OCR_SECRET", MagicMock(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(worker.config, "OPENAI_API_KEY", MagicMock(get_secret_value=lambda: "openai-key"))

    with pytest.raises(RuntimeError, match="startup failed"):
        await worker.startup({})

    structurer.aclose.assert_awaited_once_with()
    provider.aclose.assert_awaited_once_with()
    redis_pool.aclose.assert_awaited_once_with()
    close_connections.assert_awaited_once_with()


def test_worker_settings_exposes_processing_and_cleanup_with_two_attempt_limit():
    assert worker.WorkerSettings.functions == [worker.process_medication_guide_ocr]
    assert worker.WorkerSettings.queue_name == worker.config.OCR_QUEUE_NAME
    assert worker.WorkerSettings.max_tries == 2
    assert len(worker.WorkerSettings.cron_jobs) == 1
