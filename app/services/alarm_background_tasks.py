from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import DBConnectionError, IntegrityError, OperationalError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core import config
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.care import FollowUpVisit
from app.models.enums import (
    AccountStatus,
    AlarmEventType,
    AlarmStatus,
    AlarmType,
    BackgroundJobStatus,
    BackgroundJobType,
    SupplementStatus,
)
from app.models.medications import Medication
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import User, UserSettings
from app.services.alarm_schedule import next_occurrence
from app.services.web_push import PushResult, PushResultKind, WebPushService

logger = logging.getLogger(__name__)

ALARM_TASK_LEASE = timedelta(seconds=360)
_LEGACY_PROCESSING_TIMEOUT = timedelta(seconds=360)
_UNFINISHED_ALARM_STATUSES = (
    BackgroundJobStatus.QUEUED,
    BackgroundJobStatus.PROCESSING,
    BackgroundJobStatus.RETRY_WAITING,
)
_NOTIFICATION_SETTING_BY_ALARM_TYPE = {
    AlarmType.MEDICATION: "is_notify_medication",
    AlarmType.NUTRIENT: "is_notify_supplement",
    AlarmType.FOLLOW_UP_VISIT: "is_notify_schedule",
    AlarmType.GUIDE_CHECK: "is_notify_guide",
}


class AlarmTaskExecutor(Protocol):
    async def poll_due_alarm_job_ids(self) -> list[int]: ...

    async def recoverable_job_ids(self, now: datetime) -> list[int]: ...

    async def recover_stalled_processing(self, now: datetime) -> None: ...

    async def run(self, job_id: int) -> None: ...


class AlarmBackgroundTaskManager:
    def __init__(
        self,
        executor: AlarmTaskExecutor,
        *,
        poll_seconds: float = config.ALARM_POLL_SECONDS,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.executor = executor
        self.poll_seconds = poll_seconds
        self.now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))
        self._lock = asyncio.Lock()
        self._tasks_by_job_id: dict[int, asyncio.Task[None]] = {}
        self._poll_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def active_job_ids(self) -> set[int]:
        return {job_id for job_id, task in self._tasks_by_job_id.items() if not task.done()}

    async def start(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._stop.clear()
        await self._tick()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def start_job(self, job_id: int) -> None:
        async with self._lock:
            current = self._tasks_by_job_id.get(job_id)
            if current is not None and not current.done():
                return
            self._tasks_by_job_id[job_id] = asyncio.create_task(self._run(job_id))

    async def wait_until_idle(self) -> None:
        while True:
            async with self._lock:
                tasks = [task for task in self._tasks_by_job_id.values() if not task.done()]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        self._stop.set()
        poll_task = self._poll_task
        self._poll_task = None
        if poll_task is not None and not poll_task.done():
            poll_task.cancel()
            await asyncio.gather(poll_task, return_exceptions=True)

        async with self._lock:
            tasks = list(self._tasks_by_job_id.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            self._tasks_by_job_id.clear()

    async def _poll_loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    await self._tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alarm background-task polling failed")

    async def _tick(self) -> None:
        now = self.now_provider()
        await self.executor.recover_stalled_processing(now)
        recoverable_ids = await self.executor.recoverable_job_ids(now)
        due_ids = await self.executor.poll_due_alarm_job_ids()
        for job_id in dict.fromkeys([*recoverable_ids, *due_ids]):
            await self.start_job(job_id)

    async def _run(self, job_id: int) -> None:
        current_task = asyncio.current_task()
        try:
            await self.executor.run(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alarm background task failed", extra={"job_id": job_id})
        finally:
            async with self._lock:
                if self._tasks_by_job_id.get(job_id) is current_task:
                    self._tasks_by_job_id.pop(job_id, None)


def build_alarm_background_task_manager() -> AlarmBackgroundTaskManager:
    return AlarmBackgroundTaskManager(AlarmBackgroundTaskExecutor())


class AlarmBackgroundTaskExecutor:
    def __init__(
        self,
        *,
        push_service: WebPushService | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.push_service = push_service or WebPushService()
        self.now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))

    async def poll_due_alarm_job_ids(self) -> list[int]:
        now = self.now_provider()
        alarm_ids = (
            await Alarm.filter(status=AlarmStatus.ACTIVE, next_trigger_at__lte=now)
            .order_by("next_trigger_at", "id")
            .limit(100)
            .values_list("id", flat=True)
        )
        job_ids: list[int] = []
        for alarm_id in alarm_ids:
            async with in_transaction() as connection:
                alarm = await Alarm.filter(id=alarm_id).using_db(connection).select_for_update().first()
                if alarm is None or alarm.status != AlarmStatus.ACTIVE or alarm.next_trigger_at > now:
                    continue
                if alarm.last_triggered_at is not None and alarm.last_triggered_at >= alarm.next_trigger_at:
                    continue

                trigger_at = alarm.next_trigger_at
                job_ids.extend(await self._prepare_alarm_delivery(alarm, trigger_at, now, connection))

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
        return job_ids

    async def _prepare_alarm_delivery(
        self,
        alarm: Alarm,
        trigger_at: datetime,
        now: datetime,
        connection: BaseDBAsyncClient,
    ) -> list[int]:
        if not await self._account_active(alarm, connection):
            await self._create_skipped_event(alarm, now, "USER_NOT_ACTIVE", connection)
            return []
        if not await self._notification_enabled(alarm, connection):
            await self._create_skipped_event(alarm, now, "USER_NOTIFICATION_DISABLED", connection)
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

        job_ids: list[int] = []
        for subscription in subscriptions:
            key = self.idempotency_key(alarm.id, subscription.id, trigger_at)
            job = await BackgroundJob.filter(idempotency_key=key).using_db(connection).first()
            if job is None:
                try:
                    job = await BackgroundJob.create(
                        using_db=connection,
                        idempotency_key=key,
                        job_type=BackgroundJobType.ALARM,
                        status=BackgroundJobStatus.QUEUED,
                        user_id=alarm.user_id,
                        reference_table="alarms",
                        reference_id=alarm.id,
                        retry_count=0,
                        max_retry_count=config.ALARM_MAX_RETRY_COUNT,
                    )
                except IntegrityError:
                    job = await BackgroundJob.get(idempotency_key=key)
            if job.status in {BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING}:
                job_ids.append(job.id)
        return job_ids

    async def recoverable_job_ids(self, now: datetime) -> list[int]:
        rows = (
            await BackgroundJob.filter(job_type=BackgroundJobType.ALARM)
            .filter(
                Q(status=BackgroundJobStatus.QUEUED)
                | (
                    Q(status=BackgroundJobStatus.RETRY_WAITING)
                    & (Q(next_attempt_at__lte=now) | Q(next_attempt_at=None))
                )
            )
            .order_by("requested_at", "id")
            .limit(100)
            .values_list("id", flat=True)
        )
        return list(rows)

    async def recover_stalled_processing(self, now: datetime) -> None:
        legacy_cutoff = now - _LEGACY_PROCESSING_TIMEOUT
        candidates = await (
            BackgroundJob.filter(job_type=BackgroundJobType.ALARM, status=BackgroundJobStatus.PROCESSING)
            .filter(
                Q(lease_expires_at__lte=now)
                | Q(lease_expires_at=None, started_at__lte=legacy_cutoff)
                | Q(lease_expires_at=None, started_at=None, requested_at__lte=legacy_cutoff)
            )
            .order_by("requested_at", "id")
            .limit(100)
        )
        for job in candidates:
            completed_at = self.now_provider()
            await BackgroundJob.filter(
                id=job.id,
                status=BackgroundJobStatus.PROCESSING,
                started_at=job.started_at,
                lease_expires_at=job.lease_expires_at,
            ).update(
                status=BackgroundJobStatus.FAILED,
                completed_at=completed_at,
                updated_at=completed_at,
                duration_ms=self._duration_ms(job.started_at, completed_at),
                error_code="PUSH_DELIVERY_UNKNOWN",
                error_message=(
                    "작업이 중단되어 발송 결과를 확인할 수 없습니다. "
                    "중복 알림을 방지하기 위해 자동 재발송하지 않았습니다."
                ),
                next_attempt_at=None,
                lease_expires_at=None,
            )

    async def run(self, job_id: int) -> None:  # noqa: C901 - delivery state machine is intentionally linear
        job = await BackgroundJob.get_or_none(id=job_id, job_type=BackgroundJobType.ALARM)
        if job is None or job.status not in _UNFINISHED_ALARM_STATUSES:
            return
        now = self.now_provider()
        if job.status == BackgroundJobStatus.RETRY_WAITING and job.next_attempt_at is not None:
            if job.next_attempt_at > now:
                return
        if job.status == BackgroundJobStatus.PROCESSING:
            return
        if not await self.claim(job.id, now):
            return

        job = await BackgroundJob.get(id=job.id)
        context = await self._alarm_context(job)
        if context is None:
            await self._cancel_job(job, "ALARM_CONTEXT_MISSING")
            return
        alarm_id, subscription_id, trigger_at = context
        alarm = await Alarm.get_or_none(id=alarm_id)
        subscription = await PushSubscription.get_or_none(id=subscription_id)
        if alarm is None or subscription is None or not subscription.is_active or alarm.status != AlarmStatus.ACTIVE:
            await self._cancel_job(job)
            return
        if await self._skip_when_undeliverable(job, alarm):
            return

        medications: list[Medication] = []
        if alarm.care_episode_id is not None and alarm.meal_slot is not None:
            medications = await Medication.filter(
                care_episode_id=alarm.care_episode_id,
                slots__slot=alarm.meal_slot,
            ).distinct()
        nutrient_items: list[UserSupplementNutrient] = []
        if alarm.alarm_type == AlarmType.NUTRIENT and alarm.meal_slot is not None:
            nutrient_items = await (
                UserSupplementNutrient.filter(
                    user_id=alarm.user_id,
                    status=SupplementStatus.ACTIVE,
                    start_date__lte=trigger_at.astimezone(config.TIMEZONE).date(),
                    slots__slot=alarm.meal_slot,
                )
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=trigger_at.astimezone(config.TIMEZONE).date()))
                .distinct()
            )
            if not nutrient_items:
                await self._cancel_job(job)
                return
        follow_up_visit = await self._current_follow_up_visit(alarm)
        if alarm.alarm_type == AlarmType.FOLLOW_UP_VISIT and follow_up_visit is None:
            await self._cancel_job(job)
            return

        payload = self.push_service.build_payload(alarm, medications, nutrient_items, follow_up_visit)
        payload["triggerAt"] = trigger_at.isoformat()
        result = await self.push_service.send(subscription, payload)
        if result.kind == PushResultKind.SUCCESS:
            await self._complete_push(job, subscription, alarm, payload)
        elif result.kind == PushResultKind.RETRYABLE:
            await self._retry_or_fail(job, subscription, alarm, payload, result)
        else:
            await self._fail_push(
                job,
                subscription,
                alarm,
                payload,
                result,
                deactivate=result.kind == PushResultKind.EXPIRED,
            )

    async def claim(self, job_id: int, now: datetime) -> bool:
        claimable = Q(status=BackgroundJobStatus.QUEUED)
        claimable |= Q(status=BackgroundJobStatus.RETRY_WAITING) & (
            Q(next_attempt_at__lte=now) | Q(next_attempt_at=None)
        )
        updated = await BackgroundJob.filter(Q(id=job_id, job_type=BackgroundJobType.ALARM) & claimable).update(
            status=BackgroundJobStatus.PROCESSING,
            started_at=now,
            updated_at=now,
            next_attempt_at=None,
            lease_expires_at=now + ALARM_TASK_LEASE,
        )
        return updated == 1

    async def _skip_when_undeliverable(self, job: BackgroundJob, alarm: Alarm) -> bool:
        for predicate, reason in (
            (self._account_active, "USER_NOT_ACTIVE"),
            (self._notification_enabled, "USER_NOTIFICATION_DISABLED"),
        ):
            async with in_transaction() as connection:
                if await predicate(alarm, connection):
                    continue
                await self._create_skipped_event(alarm, self.now_provider(), reason, connection)
                await self._cancel_job(job, using_db=connection)
                return True
        return False

    async def _complete_push(
        self,
        job: BackgroundJob,
        subscription: PushSubscription,
        alarm: Alarm,
        payload: dict[str, object],
    ) -> None:
        for attempt in range(3):
            try:
                await self._persist_push_completion(job, subscription, alarm, payload)
                return
            except (OperationalError, DBConnectionError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (2**attempt))

    async def _persist_push_completion(
        self,
        job: BackgroundJob,
        subscription: PushSubscription,
        alarm: Alarm,
        payload: dict[str, object],
    ) -> None:
        now = self.now_provider()
        async with in_transaction() as connection:
            locked_job = await BackgroundJob.filter(id=job.id).using_db(connection).select_for_update().first()
            if locked_job is None or locked_job.status != BackgroundJobStatus.PROCESSING:
                return
            locked_subscription = (
                await PushSubscription.filter(id=subscription.id).using_db(connection).select_for_update().first()
            )
            if locked_subscription is None:
                return
            locked_subscription.last_used_at = now
            await locked_subscription.save(using_db=connection, update_fields=["last_used_at"])
            event = await AlarmEvent.create(
                using_db=connection,
                alarm_id=alarm.id,
                event_type=AlarmEventType.SENT,
                push_subscription_id=locked_subscription.id,
                event_at=now,
                payload=payload,
            )
            locked_job.status = BackgroundJobStatus.COMPLETED
            locked_job.completed_at = now
            locked_job.updated_at = now
            locked_job.duration_ms = self._duration_ms(locked_job.started_at, now)
            locked_job.reference_table = "alarm_events"
            locked_job.reference_id = event.id
            locked_job.error_code = None
            locked_job.error_message = None
            locked_job.next_attempt_at = None
            locked_job.lease_expires_at = None
            await locked_job.save(
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
                    "next_attempt_at",
                    "lease_expires_at",
                ],
            )

    async def _retry_or_fail(
        self,
        job: BackgroundJob,
        subscription: PushSubscription,
        alarm: Alarm,
        payload: dict[str, object],
        result: PushResult,
    ) -> None:
        retry_count = job.retry_count + 1
        if retry_count > job.max_retry_count:
            await self._fail_push(
                job,
                subscription,
                alarm,
                payload,
                result,
                deactivate=False,
                retry_count=retry_count,
            )
            return
        now = self.now_provider()
        delay = config.ALARM_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
        await BackgroundJob.filter(id=job.id, status=BackgroundJobStatus.PROCESSING).update(
            status=BackgroundJobStatus.RETRY_WAITING,
            retry_count=retry_count,
            error_code=result.error_code,
            error_message=result.error_code,
            updated_at=now,
            next_attempt_at=now + timedelta(seconds=delay),
            lease_expires_at=None,
        )

    async def _fail_push(
        self,
        job: BackgroundJob,
        subscription: PushSubscription,
        alarm: Alarm,
        payload: dict[str, object],
        result: PushResult,
        *,
        deactivate: bool,
        retry_count: int | None = None,
    ) -> None:
        for attempt in range(3):
            try:
                await self._persist_push_failure(
                    job,
                    subscription,
                    alarm,
                    payload,
                    result,
                    deactivate=deactivate,
                    retry_count=retry_count,
                )
                return
            except (OperationalError, DBConnectionError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (2**attempt))

    async def _persist_push_failure(
        self,
        job: BackgroundJob,
        subscription: PushSubscription,
        alarm: Alarm,
        payload: dict[str, object],
        result: PushResult,
        *,
        deactivate: bool,
        retry_count: int | None,
    ) -> None:
        now = self.now_provider()
        event_payload = dict(payload)
        if result.status_code is not None:
            event_payload["statusCode"] = result.status_code
        async with in_transaction() as connection:
            locked_job = await BackgroundJob.filter(id=job.id).using_db(connection).select_for_update().first()
            if locked_job is None or locked_job.status != BackgroundJobStatus.PROCESSING:
                return
            locked_subscription = (
                await PushSubscription.filter(id=subscription.id).using_db(connection).select_for_update().first()
            )
            if locked_subscription is None:
                return
            event = await AlarmEvent.create(
                using_db=connection,
                alarm_id=alarm.id,
                event_type=AlarmEventType.FAILED,
                push_subscription_id=locked_subscription.id,
                event_at=now,
                payload=event_payload,
                error_code=result.error_code,
            )
            if deactivate:
                locked_subscription.is_active = False
                await locked_subscription.save(using_db=connection, update_fields=["is_active"])
            locked_job.status = BackgroundJobStatus.FAILED
            locked_job.completed_at = now
            locked_job.updated_at = now
            locked_job.duration_ms = self._duration_ms(locked_job.started_at, now)
            locked_job.reference_table = "alarm_events"
            locked_job.reference_id = event.id
            locked_job.error_code = result.error_code
            locked_job.error_message = result.error_code
            locked_job.next_attempt_at = None
            locked_job.lease_expires_at = None
            if retry_count is not None:
                locked_job.retry_count = retry_count
            update_fields = [
                "status",
                "completed_at",
                "updated_at",
                "duration_ms",
                "reference_table",
                "reference_id",
                "error_code",
                "error_message",
                "next_attempt_at",
                "lease_expires_at",
            ]
            if retry_count is not None:
                update_fields.append("retry_count")
            await locked_job.save(using_db=connection, update_fields=update_fields)

    async def _cancel_job(
        self,
        job: BackgroundJob,
        error_code: str | None = None,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        now = self.now_provider()
        job.status = BackgroundJobStatus.CANCELLED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = self._duration_ms(job.started_at, now)
        job.error_code = error_code
        job.error_message = error_code
        job.next_attempt_at = None
        job.lease_expires_at = None
        await job.save(
            using_db=using_db,
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
                "duration_ms",
                "error_code",
                "error_message",
                "next_attempt_at",
                "lease_expires_at",
            ],
        )

    @staticmethod
    async def _notification_enabled(alarm: Alarm, connection: BaseDBAsyncClient) -> bool:
        settings = await UserSettings.filter(user_id=alarm.user_id).using_db(connection).first()
        if settings is None:
            return True
        return bool(getattr(settings, _NOTIFICATION_SETTING_BY_ALARM_TYPE[alarm.alarm_type]))

    @staticmethod
    async def _account_active(alarm: Alarm, connection: BaseDBAsyncClient) -> bool:
        statuses = await User.filter(id=alarm.user_id).using_db(connection).values_list("status", flat=True)
        return bool(statuses) and statuses[0] == AccountStatus.ACTIVE

    @staticmethod
    async def _create_skipped_event(
        alarm: Alarm,
        now: datetime,
        reason: str,
        connection: BaseDBAsyncClient,
    ) -> None:
        await AlarmEvent.create(
            using_db=connection,
            alarm_id=alarm.id,
            event_type=AlarmEventType.SKIPPED,
            event_at=now,
            payload={"reason": reason},
        )

    @staticmethod
    async def _current_follow_up_visit(alarm: Alarm) -> FollowUpVisit | None:
        if alarm.alarm_type != AlarmType.FOLLOW_UP_VISIT:
            return None
        return await FollowUpVisit.get_or_none(id=alarm.follow_up_visit_id)

    @staticmethod
    def idempotency_key(alarm_id: int, subscription_id: int, trigger_at: datetime) -> str:
        return f"alarm:{alarm_id}:{subscription_id}:{trigger_at.isoformat()}"

    @staticmethod
    async def _alarm_context(job: BackgroundJob) -> tuple[int, int, datetime] | None:
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

    @staticmethod
    def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
        if started_at is None:
            return None
        return max(0, int((completed_at - started_at).total_seconds() * 1000))
