from datetime import datetime, timedelta
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from arq.cron import cron
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import (
    AlarmEventType,
    AlarmStatus,
    AlarmType,
    BackgroundJobStatus,
    BackgroundJobType,
    SupplementStatus,
)
from app.models.medications import Medication
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import UserSettings
from app.services.alarm_schedule import next_occurrence
from app.services.background_jobs import BackgroundJobService
from app.services.web_push import PushResult, PushResultKind, WebPushService

_NOTIFICATION_SETTING_BY_ALARM_TYPE = {
    AlarmType.MEDICATION: "is_notify_medication",
    AlarmType.NUTRIENT: "is_notify_supplement",
    AlarmType.FOLLOW_UP_VISIT: "is_notify_schedule",
    AlarmType.GUIDE_CHECK: "is_notify_guide",
}


async def startup(ctx: dict[str, Any]) -> None:
    if not Tortoise._inited:  # noqa: SLF001
        await Tortoise.init(config=TORTOISE_ORM)
    ctx["job_service"] = BackgroundJobService(redis_pool=ctx["redis"])
    ctx["push_service"] = WebPushService()


async def shutdown(_ctx: dict[str, Any]) -> None:
    await Tortoise.close_connections()


async def _notification_enabled(alarm: Alarm, connection: BaseDBAsyncClient) -> bool:
    user_settings = await UserSettings.filter(user_id=alarm.user_id).using_db(connection).first()
    if user_settings is None:
        return True
    setting_name = _NOTIFICATION_SETTING_BY_ALARM_TYPE[alarm.alarm_type]
    return bool(getattr(user_settings, setting_name))


async def _prepare_alarm_delivery(
    alarm: Alarm,
    trigger_at: datetime,
    now: datetime,
    job_service: BackgroundJobService,
    connection: BaseDBAsyncClient,
) -> list[tuple[BackgroundJob, int, int, datetime]]:
    if not await _notification_enabled(alarm, connection):
        await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.SKIPPED,
            event_at=now,
            payload={"reason": "USER_NOTIFICATION_DISABLED"},
        )
        return []

    subscriptions = await PushSubscription.filter(user_id=alarm.user_id, is_active=True).using_db(connection)
    if not subscriptions:
        await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.FAILED,
            event_at=now,
            error_code="NO_ACTIVE_SUBSCRIPTION",
        )
        return []

    queued: list[tuple[BackgroundJob, int, int, datetime]] = []
    for subscription in subscriptions:
        job, created = await job_service.create_alarm_job(alarm, subscription, trigger_at)
        if created or job.status in {BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING}:
            queued.append((job, alarm.id, subscription.id, trigger_at))
    return queued


async def poll_due_alarms(ctx: dict[str, Any]) -> None:
    now = datetime.now(config.TIMEZONE)
    alarm_ids = (
        await Alarm.filter(
            status=AlarmStatus.ACTIVE,
            next_trigger_at__lte=now,
        )
        .order_by("next_trigger_at", "id")
        .limit(100)
        .values_list("id", flat=True)
    )
    job_service: BackgroundJobService = ctx["job_service"]

    for alarm_id in alarm_ids:
        async with in_transaction() as connection:
            alarm = await Alarm.filter(id=alarm_id).using_db(connection).select_for_update().first()
            if alarm is None or alarm.status != AlarmStatus.ACTIVE or alarm.next_trigger_at > now:
                continue
            if alarm.last_triggered_at is not None and alarm.last_triggered_at >= alarm.next_trigger_at:
                continue

            trigger_at = alarm.next_trigger_at
            queued = await _prepare_alarm_delivery(alarm, trigger_at, now, job_service, connection)

            alarm.last_triggered_at = trigger_at
            update_fields = ["last_triggered_at"]
            if alarm.recurrence_rule:
                upcoming = next_occurrence(alarm.recurrence_rule, alarm.scheduled_at, trigger_at)
                if upcoming is not None:
                    alarm.next_trigger_at = upcoming
                    update_fields.append("next_trigger_at")
            alarm.updated_at = now
            update_fields.append("updated_at")
            await alarm.save(using_db=connection, update_fields=update_fields)

        for job, queued_alarm_id, subscription_id, trigger_at in queued:
            await job_service.enqueue(
                job,
                alarm_id=queued_alarm_id,
                subscription_id=subscription_id,
                trigger_at=trigger_at,
            )


async def send_alarm_push(
    ctx: dict[str, Any],
    job_id: int,
    alarm_id: int,
    subscription_id: int,
    trigger_at_value: str,
) -> None:
    started_at = datetime.now(config.TIMEZONE)
    job_service: BackgroundJobService = ctx["job_service"]
    if not await job_service.repository.claim(job_id, started_at):
        return

    job = await BackgroundJob.get(id=job_id)
    alarm = await Alarm.get_or_none(id=alarm_id)
    subscription = await PushSubscription.get_or_none(id=subscription_id)
    if alarm is None or subscription is None or not subscription.is_active or alarm.status != AlarmStatus.ACTIVE:
        await _cancel_claimed_job(job)
        return
    if await _skip_claimed_job_when_notification_disabled(job, alarm):
        return

    medications: list[Medication] = []
    if alarm.care_episode_id is not None and alarm.meal_slot is not None:
        medications = await Medication.filter(
            care_episode_id=alarm.care_episode_id,
            slots__slot=alarm.meal_slot,
        ).distinct()
    nutrient_items: list[UserSupplementNutrient] = []
    if alarm.alarm_type == AlarmType.NUTRIENT and alarm.meal_slot is not None:
        trigger_date = datetime.fromisoformat(trigger_at_value).astimezone(config.TIMEZONE).date()
        nutrient_items = await (
            UserSupplementNutrient.filter(
                user_id=alarm.user_id,
                status=SupplementStatus.ACTIVE,
                start_date__lte=trigger_date,
                slots__slot=alarm.meal_slot,
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=trigger_date))
            .distinct()
        )
        if not nutrient_items:
            await _cancel_claimed_job(job)
            return
    push_service: WebPushService = ctx["push_service"]
    payload = push_service.build_payload(alarm, medications, nutrient_items)
    payload["triggerAt"] = trigger_at_value
    result = await push_service.send(subscription, payload)

    if result.kind == PushResultKind.SUCCESS:
        await _complete_push(job, subscription, alarm, payload, result)
        return
    if result.kind == PushResultKind.RETRYABLE:
        await _retry_or_fail(job, subscription, alarm, payload, result, job_service)
        return
    await _fail_push(
        job,
        subscription,
        alarm,
        payload,
        result,
        deactivate=result.kind == PushResultKind.EXPIRED,
    )


async def _cancel_claimed_job(job: BackgroundJob) -> None:
    now = datetime.now(config.TIMEZONE)
    job.status = BackgroundJobStatus.CANCELLED
    job.completed_at = now
    job.updated_at = now
    job.duration_ms = _duration_ms(job.started_at, now)
    await job.save(update_fields=["status", "completed_at", "updated_at", "duration_ms"])


async def _skip_claimed_job_when_notification_disabled(job: BackgroundJob, alarm: Alarm) -> bool:
    now = datetime.now(config.TIMEZONE)
    async with in_transaction() as connection:
        if await _notification_enabled(alarm, connection):
            return False
        await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.SKIPPED,
            event_at=now,
            payload={"reason": "USER_NOTIFICATION_DISABLED"},
        )
        job.status = BackgroundJobStatus.CANCELLED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = _duration_ms(job.started_at, now)
        await job.save(
            using_db=connection,
            update_fields=["status", "completed_at", "updated_at", "duration_ms"],
        )
    return True


async def _complete_push(
    job: BackgroundJob,
    subscription: PushSubscription,
    alarm: Alarm,
    payload: dict[str, object],
    _result: PushResult,
) -> None:
    now = datetime.now(config.TIMEZONE)
    async with in_transaction() as connection:
        event = await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.SENT,
            push_subscription_id=subscription.id,
            event_at=now,
            payload=payload,
        )
        subscription.last_used_at = now
        await subscription.save(using_db=connection, update_fields=["last_used_at"])
        job.status = BackgroundJobStatus.COMPLETED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = _duration_ms(job.started_at, now)
        job.reference_table = "alarm_events"
        job.reference_id = event.id
        job.error_code = None
        job.error_message = None
        await job.save(
            using_db=connection,
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
                "duration_ms",
                "reference_table",
                "reference_id",
                "error_code",
                "error_message",
            ],
        )


async def _retry_or_fail(
    job: BackgroundJob,
    subscription: PushSubscription,
    alarm: Alarm,
    payload: dict[str, object],
    result: PushResult,
    _job_service: BackgroundJobService,
) -> None:
    retry_count = job.retry_count + 1
    if retry_count <= job.max_retry_count:
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.RETRY_WAITING
        job.retry_count = retry_count
        job.error_code = result.error_code
        job.updated_at = now
        await job.save(update_fields=["status", "retry_count", "error_code", "updated_at"])
        delay = config.ALARM_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
        raise Retry(defer=timedelta(seconds=delay))
    await _fail_push(job, subscription, alarm, payload, result, deactivate=False, retry_count=retry_count)


async def _fail_push(
    job: BackgroundJob,
    subscription: PushSubscription,
    alarm: Alarm,
    payload: dict[str, object],
    result: PushResult,
    *,
    deactivate: bool,
    retry_count: int | None = None,
) -> None:
    now = datetime.now(config.TIMEZONE)
    event_payload = dict(payload)
    if result.status_code is not None:
        event_payload["statusCode"] = result.status_code
    async with in_transaction() as connection:
        event = await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.FAILED,
            push_subscription_id=subscription.id,
            event_at=now,
            payload=event_payload,
            error_code=result.error_code,
        )
        if deactivate:
            subscription.is_active = False
            await subscription.save(using_db=connection, update_fields=["is_active"])
        job.status = BackgroundJobStatus.FAILED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = _duration_ms(job.started_at, now)
        job.reference_table = "alarm_events"
        job.reference_id = event.id
        job.error_code = result.error_code
        if retry_count is not None:
            job.retry_count = retry_count
        update_fields = [
            "status",
            "completed_at",
            "updated_at",
            "duration_ms",
            "reference_table",
            "reference_id",
            "error_code",
        ]
        if retry_count is not None:
            update_fields.append("retry_count")
        await job.save(using_db=connection, update_fields=update_fields)


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


async def recover_background_jobs(ctx: dict[str, Any]) -> None:
    now = datetime.now(config.TIMEZONE)
    queued_before = now - timedelta(seconds=max(30, config.ALARM_POLL_SECONDS * 2))
    candidates = (
        await BackgroundJob.filter(
            status__in=[BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING],
            job_type=BackgroundJobType.ALARM,
        )
        .order_by("requested_at", "id")
        .limit(100)
    )
    job_service: BackgroundJobService = ctx["job_service"]

    for job in candidates:
        if job.status == BackgroundJobStatus.QUEUED and job.requested_at > queued_before:
            continue
        if job.status == BackgroundJobStatus.RETRY_WAITING and not _retry_is_due(job, now):
            continue
        job_context = await _recover_alarm_context(job)
        if job_context is None:
            continue
        alarm_id, subscription_id, trigger_at = job_context
        await job_service.enqueue(
            job,
            alarm_id=alarm_id,
            subscription_id=subscription_id,
            trigger_at=trigger_at,
        )


def _retry_is_due(job: BackgroundJob, now: datetime) -> bool:
    if job.updated_at is None:
        return True
    delay = config.ALARM_RETRY_BASE_SECONDS * (2 ** max(0, job.retry_count - 1))
    return job.updated_at + timedelta(seconds=delay) <= now


async def _recover_alarm_context(job: BackgroundJob) -> tuple[int, int, datetime] | None:
    referenced_job = job
    if job.parent_job_id is not None:
        parent = await BackgroundJob.get_or_none(id=job.parent_job_id)
        if parent is None:
            return None
        referenced_job = parent
    if referenced_job.reference_table == "alarm_events" and referenced_job.reference_id is not None:
        event = await AlarmEvent.get_or_none(id=referenced_job.reference_id)
        if event is None or event.push_subscription_id is None:
            return None
        return event.alarm_id, event.push_subscription_id, event.event_at

    original_key = job.idempotency_key.split(":manual:", maxsplit=1)[0]
    parts = original_key.split(":", maxsplit=3)
    if len(parts) != 4 or parts[0] != "alarm":
        return None
    try:
        return int(parts[1]), int(parts[2]), datetime.fromisoformat(parts[3])
    except (TypeError, ValueError):
        return None


_poll_step = max(1, min(60, config.ALARM_POLL_SECONDS))


class WorkerSettings:
    functions = [send_alarm_push]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
    cron_jobs = [
        cron(poll_due_alarms, second=set(range(0, 60, _poll_step))),
        cron(recover_background_jobs, second={5, 35}),
    ]
