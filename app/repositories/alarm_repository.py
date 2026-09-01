from typing import Any

from tortoise.backends.base.client import BaseDBAsyncClient

from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.care import CareEpisode, FollowUpVisit
from app.models.enums import AlarmStatus, AlarmType
from app.models.recovery import RecoveryGuide


class AlarmRepository:
    async def get_owned_alarm(self, alarm_id: int, user_id: int) -> Alarm | None:
        return await Alarm.get_or_none(id=alarm_id, user_id=user_id)

    async def list_owned_alarms(
        self,
        user_id: int,
        *,
        alarm_status: AlarmStatus | None = None,
        alarm_type: AlarmType | None = None,
        care_episode_id: int | None = None,
        follow_up_visit_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Alarm], int]:
        query = Alarm.filter(user_id=user_id)
        if alarm_status is not None:
            query = query.filter(status=alarm_status)
        if alarm_type is not None:
            query = query.filter(alarm_type=alarm_type)
        if care_episode_id is not None:
            query = query.filter(care_episode_id=care_episode_id)
        if follow_up_visit_id is not None:
            query = query.filter(follow_up_visit_id=follow_up_visit_id)
        total = await query.count()
        items = await query.order_by("next_trigger_at", "id").offset(offset).limit(limit)
        return items, total

    async def get_owned_care_episode(self, care_episode_id: int, user_id: int) -> CareEpisode | None:
        return await CareEpisode.get_or_none(id=care_episode_id, user_id=user_id)

    async def get_owned_recovery_guide(self, guide_id: int, user_id: int) -> RecoveryGuide | None:
        return await RecoveryGuide.get_or_none(id=guide_id, care_episode__user_id=user_id).prefetch_related(
            "care_episode"
        )

    async def get_owned_follow_up_visit(self, visit_id: int, user_id: int) -> FollowUpVisit | None:
        return await FollowUpVisit.get_or_none(id=visit_id, user_id=user_id)

    async def create_alarm(
        self,
        data: dict[str, Any],
        connection: BaseDBAsyncClient,
    ) -> Alarm:
        return await Alarm.create(using_db=connection, **data)

    async def create_event(
        self,
        data: dict[str, Any],
        connection: BaseDBAsyncClient | None = None,
    ) -> AlarmEvent:
        return await AlarmEvent.create(using_db=connection, **data)

    async def get_owned_subscription(self, subscription_id: int, user_id: int) -> PushSubscription | None:
        return await PushSubscription.get_or_none(id=subscription_id, user_id=user_id)

    async def get_subscription_by_endpoint(self, endpoint: str) -> PushSubscription | None:
        return await PushSubscription.get_or_none(endpoint=endpoint)

    async def list_owned_subscriptions(self, user_id: int) -> list[PushSubscription]:
        return await PushSubscription.filter(user_id=user_id).order_by("-created_at", "-id")

    async def list_events(
        self,
        alarm_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AlarmEvent], int]:
        query = AlarmEvent.filter(alarm_id=alarm_id)
        total = await query.count()
        items = await query.order_by("-event_at", "-id").offset(offset).limit(limit)
        return items, total

    async def get_delivery_event(self, alarm_id: int, subscription_id: int) -> AlarmEvent | None:
        return await AlarmEvent.filter(
            alarm_id=alarm_id,
            push_subscription_id=subscription_id,
            event_type="DELIVERED",
        ).first()

    async def has_sent_event(self, alarm_id: int, subscription_id: int) -> bool:
        return await AlarmEvent.filter(
            alarm_id=alarm_id,
            push_subscription_id=subscription_id,
            event_type="SENT",
        ).exists()
