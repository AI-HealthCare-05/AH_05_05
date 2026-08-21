from datetime import datetime
from enum import StrEnum

from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.alarms import AlarmCreateRequest, AlarmUpdateRequest, DeliveryAckRequest, PushSubscriptionUpsertRequest
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.enums import AlarmEventType, AlarmStatus, AlarmType
from app.models.users import User
from app.repositories.alarm_repository import AlarmRepository
from app.services.alarm_schedule import next_occurrence, validate_alarm_shape


class AlarmAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    COMPLETE = "complete"
    SKIP = "skip"
    CANCEL = "cancel"


class AlarmService:
    def __init__(self, repository: AlarmRepository | None = None):
        self.repository = repository or AlarmRepository()

    async def get_alarm(self, user: User, alarm_id: int) -> Alarm:
        alarm = await self.repository.get_owned_alarm(alarm_id, user.id)
        if alarm is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found.")
        return alarm

    async def list_alarms(
        self,
        user: User,
        *,
        alarm_status: AlarmStatus | None = None,
        alarm_type: AlarmType | None = None,
        care_episode_id: int | None = None,
        follow_up_visit_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Alarm], int]:
        return await self.repository.list_owned_alarms(
            user.id,
            alarm_status=alarm_status,
            alarm_type=alarm_type,
            care_episode_id=care_episode_id,
            follow_up_visit_id=follow_up_visit_id,
            offset=offset,
            limit=limit,
        )

    async def create_alarm(self, user: User, data: AlarmCreateRequest) -> Alarm:
        await self._validate_references(
            user,
            data.care_episode_id,
            data.source_guide_id,
            data.follow_up_visit_id,
        )

        payload = data.model_dump()
        payload["user_id"] = user.id
        payload["next_trigger_at"] = data.scheduled_at

        try:
            async with in_transaction() as connection:
                alarm = await self.repository.create_alarm(payload, connection)
                await self.repository.create_event(
                    {
                        "alarm_id": alarm.id,
                        "event_type": AlarmEventType.SCHEDULED,
                        "event_at": datetime.now(config.TIMEZONE),
                    },
                    connection,
                )
        except IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm already exists.") from exc

        return alarm

    async def _validate_references(
        self,
        user: User,
        care_episode_id: int | None,
        source_guide_id: int | None,
        follow_up_visit_id: int | None,
    ) -> None:
        if care_episode_id is not None:
            care_episode = await self.repository.get_owned_care_episode(care_episode_id, user.id)
            if care_episode is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Care episode not found.")

        if source_guide_id is not None:
            guide = await self.repository.get_owned_recovery_guide(source_guide_id, user.id)
            if guide is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery guide not found.")
            if care_episode_id is not None and guide.care_episode_id != care_episode_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recovery guide does not match care episode.")

        if follow_up_visit_id is not None:
            visit = await self.repository.get_owned_follow_up_visit(follow_up_visit_id, user.id)
            if visit is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up visit not found.")
            if care_episode_id is not None and visit.care_episode_id != care_episode_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Follow-up visit does not match care episode.",
                )

    async def update_alarm(self, user: User, alarm_id: int, data: AlarmUpdateRequest) -> Alarm:
        alarm = await self.get_alarm(user, alarm_id)
        if alarm.status in {AlarmStatus.COMPLETED, AlarmStatus.CANCELLED}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Terminal alarm cannot be updated.")

        changes = data.model_dump(exclude_unset=True)
        care_episode_id = changes.get("care_episode_id", alarm.care_episode_id)
        source_guide_id = changes.get("source_guide_id", alarm.source_guide_id)
        follow_up_visit_id = changes.get("follow_up_visit_id", alarm.follow_up_visit_id)
        await self._validate_references(user, care_episode_id, source_guide_id, follow_up_visit_id)

        alarm_type = changes.get("alarm_type", alarm.alarm_type)
        meal_slot = changes.get("meal_slot", alarm.meal_slot)
        try:
            validate_alarm_shape(alarm_type, meal_slot)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

        update_fields: list[str] = []
        for field_name, value in changes.items():
            setattr(alarm, field_name, value)
            update_fields.append(field_name)

        if "scheduled_at" in changes:
            alarm.next_trigger_at = changes["scheduled_at"]
            alarm.last_triggered_at = None
            update_fields.extend(["next_trigger_at", "last_triggered_at"])

        if update_fields:
            alarm.updated_at = datetime.now(config.TIMEZONE)
            update_fields.append("updated_at")
        try:
            if update_fields:
                await alarm.save(update_fields=update_fields)
        except IntegrityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm already exists.") from exc
        return alarm

    async def transition(self, user: User, alarm_id: int, action: AlarmAction) -> Alarm:
        if action == AlarmAction.CANCEL:
            return await self.cancel_alarm(user, alarm_id)

        alarm = await self.get_alarm(user, alarm_id)
        now = datetime.now(config.TIMEZONE)

        if action == AlarmAction.PAUSE:
            self._require_status(alarm, {AlarmStatus.ACTIVE}, action)
            alarm.status = AlarmStatus.PAUSED
            await alarm.save(update_fields=["status"])
            return alarm

        if action == AlarmAction.RESUME:
            self._require_status(alarm, {AlarmStatus.PAUSED}, action)
            alarm.status = AlarmStatus.ACTIVE
            await alarm.save(update_fields=["status"])
            return alarm

        if action == AlarmAction.COMPLETE:
            if alarm.status == AlarmStatus.COMPLETED:
                return alarm
            self._require_status(alarm, {AlarmStatus.ACTIVE, AlarmStatus.PAUSED}, action)
            async with in_transaction() as connection:
                alarm.status = AlarmStatus.COMPLETED
                alarm.completed_at = now
                alarm.updated_at = now
                await alarm.save(
                    using_db=connection,
                    update_fields=["status", "completed_at", "updated_at"],
                )
                await self.repository.create_event(
                    {
                        "alarm_id": alarm.id,
                        "event_type": AlarmEventType.COMPLETED,
                        "event_at": now,
                    },
                    connection,
                )
            return alarm

        if action == AlarmAction.SKIP:
            self._require_status(alarm, {AlarmStatus.ACTIVE}, action)
            async with in_transaction() as connection:
                alarm.last_triggered_at = alarm.next_trigger_at
                update_fields = ["last_triggered_at"]
                if alarm.recurrence_rule:
                    upcoming = next_occurrence(alarm.recurrence_rule, alarm.scheduled_at, alarm.next_trigger_at)
                    if upcoming is not None:
                        alarm.next_trigger_at = upcoming
                        update_fields.append("next_trigger_at")
                alarm.updated_at = now
                update_fields.append("updated_at")
                await alarm.save(using_db=connection, update_fields=update_fields)
                await self.repository.create_event(
                    {
                        "alarm_id": alarm.id,
                        "event_type": AlarmEventType.SKIPPED,
                        "event_at": now,
                    },
                    connection,
                )
            return alarm

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown alarm action.")

    @staticmethod
    def _require_status(alarm: Alarm, allowed: set[AlarmStatus], action: AlarmAction) -> None:
        if alarm.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Alarm cannot {action.value} from {alarm.status.value}.",
            )

    async def cancel_alarm(self, user: User, alarm_id: int) -> Alarm:
        alarm = await self.get_alarm(user, alarm_id)
        if alarm.status == AlarmStatus.CANCELLED:
            return alarm
        if alarm.status == AlarmStatus.COMPLETED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed alarm cannot be cancelled.")

        now = datetime.now(config.TIMEZONE)
        alarm.status = AlarmStatus.CANCELLED
        alarm.cancelled_at = now
        alarm.updated_at = now
        await alarm.save(update_fields=["status", "cancelled_at", "updated_at"])
        return alarm

    async def upsert_subscription(self, user: User, data: PushSubscriptionUpsertRequest) -> PushSubscription:
        subscription = await self.repository.get_subscription_by_endpoint(data.endpoint)
        if subscription is not None and subscription.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Push endpoint is already registered.")

        if subscription is None:
            return await PushSubscription.create(user_id=user.id, is_active=True, **data.model_dump())

        changes = data.model_dump(exclude={"endpoint"})
        for field_name, value in changes.items():
            setattr(subscription, field_name, value)
        subscription.is_active = True
        await subscription.save(update_fields=[*changes.keys(), "is_active"])
        return subscription

    async def list_subscriptions(self, user: User) -> list[PushSubscription]:
        return await self.repository.list_owned_subscriptions(user.id)

    async def deactivate_subscription(self, user: User, subscription_id: int) -> None:
        subscription = await self.repository.get_owned_subscription(subscription_id, user.id)
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Push subscription not found.")
        if subscription.is_active:
            subscription.is_active = False
            await subscription.save(update_fields=["is_active"])

    async def list_events(
        self,
        user: User,
        alarm_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AlarmEvent], int]:
        alarm = await self.get_alarm(user, alarm_id)
        return await self.repository.list_events(alarm.id, offset=offset, limit=limit)

    async def acknowledge_delivery(self, user: User, alarm_id: int, data: DeliveryAckRequest) -> AlarmEvent:
        alarm = await self.get_alarm(user, alarm_id)
        subscription = await self.repository.get_owned_subscription(data.push_subscription_id, user.id)
        if subscription is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Push subscription not found.")

        existing = await self.repository.get_delivery_event(alarm.id, subscription.id)
        if existing is not None:
            return existing
        if not await self.repository.has_sent_event(alarm.id, subscription.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Push notification was not sent.")

        return await self.repository.create_event(
            {
                "alarm_id": alarm.id,
                "event_type": AlarmEventType.DELIVERED,
                "push_subscription_id": subscription.id,
                "event_at": datetime.now(config.TIMEZONE),
                "payload": data.payload,
            }
        )
