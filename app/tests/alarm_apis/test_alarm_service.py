import pytest
from fastapi import HTTPException, status
from tortoise.contrib.test import TestCase

from app.dtos.alarms import AlarmUpdateRequest
from app.models.alarms import AlarmEvent
from app.models.enums import AlarmEventType, AlarmStatus, MealSlot
from app.services.alarms import AlarmAction, AlarmService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request


class TestAlarmService(TestCase):
    async def test_create_alarm_writes_scheduled_event(self):
        user = await create_user("alarm-create@example.com")

        alarm = await AlarmService().create_alarm(user, medication_alarm_request())

        assert alarm.status == AlarmStatus.ACTIVE
        event = await AlarmEvent.get(alarm_id=alarm.id)
        assert event.event_type == AlarmEventType.SCHEDULED

    async def test_other_user_cannot_read_alarm(self):
        owner = await create_user("alarm-owner@example.com")
        other_user = await create_user("alarm-other@example.com")
        alarm = await AlarmService().create_alarm(owner, medication_alarm_request())

        with pytest.raises(HTTPException) as error:
            await AlarmService().get_alarm(other_user, alarm.id)

        assert error.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_soft_cancels_alarm(self):
        user = await create_user("alarm-cancel@example.com")
        alarm = await AlarmService().create_alarm(user, medication_alarm_request())

        result = await AlarmService().cancel_alarm(user, alarm.id)

        assert result.status == AlarmStatus.CANCELLED
        assert result.cancelled_at is not None
        assert await result.events.filter(event_type=AlarmEventType.SCHEDULED).exists()

    async def test_update_alarm_changes_schedule_and_title(self):
        user = await create_user("alarm-update@example.com")
        alarm = await AlarmService().create_alarm(user, medication_alarm_request())
        new_time = alarm.scheduled_at.replace(hour=9)

        result = await AlarmService().update_alarm(
            user,
            alarm.id,
            AlarmUpdateRequest(title="변경된 알람", scheduled_at=new_time),
        )

        assert result.title == "변경된 알람"
        assert result.scheduled_at == new_time
        assert result.next_trigger_at == new_time

    async def test_pause_resume_and_complete_transitions(self):
        user = await create_user("alarm-transition@example.com")
        alarm = await AlarmService().create_alarm(user, medication_alarm_request())

        paused = await AlarmService().transition(user, alarm.id, AlarmAction.PAUSE)
        resumed = await AlarmService().transition(user, alarm.id, AlarmAction.RESUME)
        completed = await AlarmService().transition(user, alarm.id, AlarmAction.COMPLETE)

        assert paused.status == AlarmStatus.PAUSED
        assert resumed.status == AlarmStatus.ACTIVE
        assert completed.status == AlarmStatus.COMPLETED
        assert completed.completed_at is not None
        assert await AlarmEvent.filter(alarm_id=alarm.id, event_type=AlarmEventType.COMPLETED).exists()

    async def test_completed_alarm_cannot_resume(self):
        user = await create_user("alarm-invalid-transition@example.com")
        alarm = await AlarmService().create_alarm(user, medication_alarm_request())
        await AlarmService().transition(user, alarm.id, AlarmAction.COMPLETE)

        with pytest.raises(HTTPException) as error:
            await AlarmService().transition(user, alarm.id, AlarmAction.RESUME)

        assert error.value.status_code == status.HTTP_409_CONFLICT

    async def test_list_alarms_filters_by_status_and_user(self):
        user = await create_user("alarm-list@example.com")
        other_user = await create_user("alarm-list-other@example.com")
        active = await AlarmService().create_alarm(user, medication_alarm_request())
        paused = await AlarmService().create_alarm(
            other_user,
            medication_alarm_request().model_copy(update={"meal_slot": MealSlot.LUNCH}),
        )
        await AlarmService().transition(other_user, paused.id, AlarmAction.PAUSE)

        items, total = await AlarmService().list_alarms(
            user,
            alarm_status=AlarmStatus.ACTIVE,
            offset=0,
            limit=20,
        )

        assert total == 1
        assert [item.id for item in items] == [active.id]
