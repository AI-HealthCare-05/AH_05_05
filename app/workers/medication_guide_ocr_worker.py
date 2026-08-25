from typing import Any, cast

import httpx
from arq.connections import RedisSettings, create_pool
from arq.cron import cron
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.core.exceptions import OcrProviderConfigError
from app.services.clova_template_ocr import ClovaTemplateProvider
from app.services.medication_guide_ocr import MedicationGuideService
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService, TemporaryOcrStorage


def _redis_settings() -> RedisSettings:
    return RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)


async def startup(ctx: dict[str, Any]) -> None:
    if not Tortoise._inited:  # noqa: SLF001
        await Tortoise.init(config=TORTOISE_ORM)

    client = httpx.AsyncClient()
    redis_pool = await create_pool(_redis_settings())
    try:
        template_id = config.CLOVA_TEMPLATE_ID
        if template_id is None:
            raise OcrProviderConfigError()
        provider = ClovaTemplateProvider(config, client)
        extractor = MedicationGuideService(
            provider=provider,
            template_id=template_id,
            review_threshold=config.OCR_REVIEW_CONFIDENCE_THRESHOLD,
        )
        storage = TemporaryOcrStorage(config.OCR_TEMP_DIR)
        ctx.update(
            {
                "http_client": client,
                "ocr_redis_pool": redis_pool,
                "ocr_provider": provider,
                "ocr_extractor": extractor,
                "ocr_storage": storage,
                "ocr_job_service": MedicationGuideOcrJobService(storage=storage, redis_pool=redis_pool),
            }
        )
    except Exception:
        await redis_pool.aclose()
        await client.aclose()
        raise


async def shutdown(ctx: dict[str, Any]) -> None:
    client = ctx.pop("http_client", None)
    redis_pool = ctx.pop("ocr_redis_pool", None)
    try:
        if client is not None:
            await client.aclose()
    finally:
        try:
            if redis_pool is not None:
                await redis_pool.aclose()
        finally:
            await Tortoise.close_connections()


async def process_medication_guide_ocr(ctx: dict[str, Any], job_id: int) -> None:
    job_service = cast(MedicationGuideOcrJobService, ctx["ocr_job_service"])
    extractor = cast(MedicationGuideService, ctx["ocr_extractor"])
    job_try = int(ctx.get("job_try", 1))
    await job_service.process(job_id, extractor, job_try=job_try)


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
