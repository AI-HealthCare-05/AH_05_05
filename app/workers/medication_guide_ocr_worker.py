from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from arq.connections import RedisSettings, create_pool
from arq.cron import cron
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.core.exceptions import OcrProviderConfigError
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService, TemporaryOcrStorage
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service


def _redis_settings() -> RedisSettings:
    return RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)


async def startup(ctx: dict[str, Any]) -> None:
    endpoint, secret = _general_ocr_config()
    redis_pool: Any | None = None
    provider: ClovaGeneralOcrProvider | None = None
    structurer: OpenAIGroundedStructurer | None = None
    tortoise_active = False
    try:
        if not Tortoise._inited:  # noqa: SLF001
            await Tortoise.init(config=TORTOISE_ORM)
        tortoise_active = True
        redis_pool = await create_pool(_redis_settings())
        provider = ClovaGeneralOcrProvider(endpoint=endpoint, secret=secret)
        openai_api_key = _secret_value(config.OPENAI_API_KEY)
        if openai_api_key is not None:
            structurer = OpenAIGroundedStructurer(
                api_key=openai_api_key,
                model=config.OPENAI_MODEL,
            )
        analyzer = MedicationOcrV3Service(provider=provider, structurer=structurer)
        storage = TemporaryOcrStorage(config.OCR_TEMP_DIR)
        ctx.update(
            {
                "ocr_redis_pool": redis_pool,
                "ocr_provider": provider,
                "ocr_structurer": structurer,
                "ocr_analyzer": analyzer,
                "ocr_storage": storage,
                "ocr_job_service": MedicationGuideOcrJobService(
                    storage=storage,
                    redis_pool=redis_pool,
                ),
                "ocr_tortoise_active": tortoise_active,
            }
        )
    except Exception:
        await _close_resources(
            structurer=structurer,
            provider=provider,
            redis_pool=redis_pool,
            close_tortoise=tortoise_active,
            raise_cleanup_error=False,
        )
        raise


async def shutdown(ctx: dict[str, Any]) -> None:
    structurer = ctx.pop("ocr_structurer", None)
    provider = ctx.pop("ocr_provider", None)
    redis_pool = ctx.pop("ocr_redis_pool", None)
    close_tortoise = bool(ctx.pop("ocr_tortoise_active", False))
    ctx.pop("ocr_analyzer", None)
    ctx.pop("ocr_storage", None)
    ctx.pop("ocr_job_service", None)
    await _close_resources(
        structurer=structurer,
        provider=provider,
        redis_pool=redis_pool,
        close_tortoise=close_tortoise,
        raise_cleanup_error=True,
    )


async def _close_resources(
    *,
    structurer: Any | None,
    provider: Any | None,
    redis_pool: Any | None,
    close_tortoise: bool,
    raise_cleanup_error: bool,
) -> None:
    closers: list[Callable[[], Awaitable[None]]] = []
    for resource in (structurer, provider, redis_pool):
        close = getattr(resource, "aclose", None)
        if callable(close):
            closers.append(close)
    if close_tortoise:
        closers.append(Tortoise.close_connections)

    first_error: Exception | None = None
    for close in closers:
        try:
            await close()
        except Exception as error:
            if first_error is None:
                first_error = error
    if raise_cleanup_error and first_error is not None:
        raise first_error


def _general_ocr_config() -> tuple[str, str]:
    endpoint = config.CLOVA_GENERAL_OCR_INVOKE_URL
    normalized_endpoint = endpoint.strip() if isinstance(endpoint, str) else ""
    secret = _secret_value(config.CLOVA_GENERAL_OCR_SECRET)
    if not normalized_endpoint or secret is None:
        raise OcrProviderConfigError("General OCR 설정이 필요합니다.")
    return normalized_endpoint, secret


def _secret_value(value: object) -> str | None:
    get_secret_value = getattr(value, "get_secret_value", None)
    if not callable(get_secret_value):
        return None
    secret = get_secret_value()
    if not isinstance(secret, str) or not secret.strip():
        return None
    return secret.strip()


async def process_medication_guide_ocr(ctx: dict[str, Any], job_id: int) -> None:
    job_service = cast(MedicationGuideOcrJobService, ctx["ocr_job_service"])
    analyzer = cast(MedicationOcrV3Service, ctx["ocr_analyzer"])
    job_try = int(ctx.get("job_try", 1))
    await job_service.process(job_id, analyzer, job_try=job_try)


async def cleanup_expired_ocr_jobs(ctx: dict[str, Any]) -> None:
    job_service = cast(MedicationGuideOcrJobService, ctx["ocr_job_service"])
    await job_service.cleanup_expired()


class WorkerSettings:
    functions = [process_medication_guide_ocr]
    queue_name = config.OCR_QUEUE_NAME
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    cron_jobs = [cron(cleanup_expired_ocr_jobs, minute=set(range(0, 60, 5)))]
    max_tries = 2
