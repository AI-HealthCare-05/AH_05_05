from __future__ import annotations

from typing import Any, cast

from arq.connections import RedisSettings
from arq.cron import cron
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.services.custom_challenge_lifecycle import CustomChallengeLifecycleService


async def startup(ctx: dict[str, Any]) -> None:
    owns_tortoise = not Tortoise._inited  # noqa: SLF001
    if owns_tortoise:
        await Tortoise.init(config=TORTOISE_ORM)
    ctx["custom_challenge_worker_owns_tortoise"] = owns_tortoise
    ctx["custom_challenge_lifecycle_service"] = CustomChallengeLifecycleService()


async def shutdown(ctx: dict[str, Any]) -> None:
    ctx.pop("custom_challenge_lifecycle_service", None)
    if ctx.pop("custom_challenge_worker_owns_tortoise", False):
        await Tortoise.close_connections()


async def finalize_due_custom_challenges(ctx: dict[str, Any]) -> int:
    service = cast(
        CustomChallengeLifecycleService,
        ctx["custom_challenge_lifecycle_service"],
    )
    return await service.finalize_due()


class WorkerSettings:
    queue_name = "arq:custom-challenge"
    functions: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        database=config.REDIS_DB,
    )
    cron_jobs = [
        cron(finalize_due_custom_challenges, minute=set(range(60))),
    ]
