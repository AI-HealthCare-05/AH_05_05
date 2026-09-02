from datetime import date, datetime, time, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.alarms import Alarm
from app.models.care import FollowUpVisit
from app.models.enums import AlarmStatus, AlarmType
from app.models.users import User
from app.tests.alarm_apis.helpers import authentication_headers


class TestFollowUpVisitCrudAPI(TestCase):
    async def test_create_list_get_update_and_delete_owned_visit(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-crud@example.com"
            headers = await authentication_headers(client, email, "01011110101")

            created = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={
                    "visit_date": "2026-09-10",
                    "visit_time": "10:30:00",
                    "hospital": "포케병원",
                },
            )
            visit_id = created.json()["id"]
            listed = await client.get("/api/v1/user/follow-up-visits", headers=headers)
            detail = await client.get(f"/api/v1/user/follow-up-visits/{visit_id}", headers=headers)
            updated = await client.patch(
                f"/api/v1/user/follow-up-visits/{visit_id}",
                headers=headers,
                json={"visit_time": None, "hospital": "포케대학병원"},
            )
            deleted = await client.delete(f"/api/v1/user/follow-up-visits/{visit_id}", headers=headers)

        assert created.status_code == status.HTTP_201_CREATED
        assert created.json()["user_id"] == (await User.get(email=email)).id
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json() == {
            "items": [created.json()],
            "total": 1,
            "offset": 0,
            "limit": 20,
        }
        assert detail.status_code == status.HTTP_200_OK
        assert detail.json() == created.json()
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["visit_time"] is None
        assert updated.json()["hospital"] == "포케대학병원"
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert await FollowUpVisit.get_or_none(id=visit_id) is None
        assert not await Alarm.filter(follow_up_visit_id=visit_id).exists()

    async def test_create_future_visit_schedules_previous_evening_alarm(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-alarm-create@example.com"
            headers = await authentication_headers(client, email, "01011110106")
            user = await User.get(email=email)
            visit_date = datetime.now(config.TIMEZONE).date() + timedelta(days=2)

            created = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={
                    "visit_date": visit_date.isoformat(),
                    "visit_time": "14:30:00",
                    "hospital": "서울성모병원",
                },
            )

        alarm = await Alarm.get(
            user=user,
            alarm_type=AlarmType.FOLLOW_UP_VISIT,
            follow_up_visit_id=created.json()["id"],
        )
        assert created.status_code == status.HTTP_201_CREATED
        assert alarm.scheduled_at == datetime.combine(
            visit_date - timedelta(days=1),
            time(19, 0),
            tzinfo=config.TIMEZONE,
        )
        assert alarm.next_trigger_at == alarm.scheduled_at
        assert alarm.recurrence_rule is None
        assert alarm.care_episode_id is None
        assert alarm.meal_slot is None

    async def test_create_visit_without_future_notification_time_does_not_create_alarm(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-alarm-past@example.com"
            headers = await authentication_headers(client, email, "01011110107")
            user = await User.get(email=email)

            created = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={"visit_date": datetime.now(config.TIMEZONE).date().isoformat()},
            )
            past_created = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={"visit_date": (datetime.now(config.TIMEZONE).date() - timedelta(days=1)).isoformat()},
            )

        assert created.status_code == status.HTTP_201_CREATED
        assert not await Alarm.filter(user=user, alarm_type=AlarmType.FOLLOW_UP_VISIT).exists()
        assert past_created.status_code == status.HTTP_201_CREATED

    async def test_update_visit_date_reschedules_alarm_but_other_fields_do_not(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-alarm-update@example.com"
            headers = await authentication_headers(client, email, "01011110108")
            user = await User.get(email=email)
            today = datetime.now(config.TIMEZONE).date()
            created = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={"visit_date": (today + timedelta(days=3)).isoformat()},
            )
            visit_id = created.json()["id"]
            alarm = await Alarm.get(user=user, follow_up_visit_id=visit_id)
            original_schedule = alarm.scheduled_at

            hospital_updated = await client.patch(
                f"/api/v1/user/follow-up-visits/{visit_id}",
                headers=headers,
                json={"hospital": "변경병원"},
            )
            await alarm.refresh_from_db()
            after_hospital_update = alarm.scheduled_at
            date_updated = await client.patch(
                f"/api/v1/user/follow-up-visits/{visit_id}",
                headers=headers,
                json={"visit_date": (today + timedelta(days=5)).isoformat()},
            )
            await alarm.refresh_from_db()

        assert hospital_updated.status_code == status.HTTP_200_OK
        assert after_hospital_update == original_schedule
        assert date_updated.status_code == status.HTTP_200_OK
        assert alarm.scheduled_at.date() == today + timedelta(days=4)

    async def test_evening_time_change_reschedules_only_future_visit_alarm(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-alarm-settings@example.com"
            headers = await authentication_headers(client, email, "01011110109")
            user = await User.get(email=email)
            today = datetime.now(config.TIMEZONE).date()
            future_visit = await FollowUpVisit.create(user=user, visit_date=today + timedelta(days=3))
            past_visit = await FollowUpVisit.create(user=user, visit_date=today - timedelta(days=2))
            future_alarm = await Alarm.create(
                user=user,
                alarm_type=AlarmType.FOLLOW_UP_VISIT,
                follow_up_visit=future_visit,
                title="진료 일정 알림",
                scheduled_at=datetime.combine(today + timedelta(days=2), time(19), tzinfo=config.TIMEZONE),
                next_trigger_at=datetime.combine(today + timedelta(days=2), time(19), tzinfo=config.TIMEZONE),
            )
            past_trigger = datetime.combine(today - timedelta(days=3), time(19), tzinfo=config.TIMEZONE)
            past_alarm = await Alarm.create(
                user=user,
                alarm_type=AlarmType.FOLLOW_UP_VISIT,
                follow_up_visit=past_visit,
                title="진료 일정 알림",
                scheduled_at=past_trigger,
                next_trigger_at=past_trigger,
                status=AlarmStatus.ACTIVE,
            )

            patched = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"eveningMedicationTime": "18:00"},
            )

        await future_alarm.refresh_from_db()
        await past_alarm.refresh_from_db()
        assert patched.status_code == status.HTTP_200_OK
        assert future_alarm.scheduled_at.time() == time(18)
        assert past_alarm.scheduled_at == past_trigger

    async def test_list_supports_date_range_and_pagination(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-list@example.com"
            headers = await authentication_headers(client, email, "01011110102")
            user = await User.get(email=email)
            for visit_date in (date(2026, 9, 1), date(2026, 9, 10), date(2026, 9, 20)):
                await FollowUpVisit.create(user=user, visit_date=visit_date)

            response = await client.get(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                params={"start_date": "2026-09-05", "end_date": "2026-09-20", "limit": 1},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] == 2
        assert response.json()["limit"] == 1
        assert response.json()["items"][0]["visit_date"] == "2026-09-10"

    async def test_other_users_visit_is_not_exposed(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "follow-up-owner@example.com", "01011110103")
            other = await User.create(
                email="follow-up-other@example.com",
                hashed_password="hashed-password",
                status="ACTIVE",
                name="다른 사용자",
            )
            visit = await FollowUpVisit.create(user=other, visit_date=date(2026, 9, 10))

            responses = (
                await client.get(f"/api/v1/user/follow-up-visits/{visit.id}", headers=headers),
                await client.patch(
                    f"/api/v1/user/follow-up-visits/{visit.id}",
                    headers=headers,
                    json={"hospital": "변경 금지"},
                ),
                await client.delete(f"/api/v1/user/follow-up-visits/{visit.id}", headers=headers),
            )

        assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * 3
        assert await FollowUpVisit.filter(id=visit.id).exists()

    async def test_api_requires_authentication_and_valid_date_range(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unauthorized = await client.get("/api/v1/user/follow-up-visits")
            headers = await authentication_headers(client, "follow-up-range@example.com", "01011110104")
            invalid_range = await client.get(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                params={"start_date": "2026-09-20", "end_date": "2026-09-10"},
            )

        assert unauthorized.status_code == status.HTTP_401_UNAUTHORIZED
        assert invalid_range.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert invalid_range.json()["detail"] == "end_date must be on or after start_date."

    async def test_department_is_not_accepted(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "follow-up-department@example.com", "01011110105")
            response = await client.post(
                "/api/v1/user/follow-up-visits",
                headers=headers,
                json={"visit_date": "2026-09-10", "department": "내과"},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
