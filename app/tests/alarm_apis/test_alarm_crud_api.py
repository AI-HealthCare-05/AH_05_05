from datetime import date, datetime, time, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.alarms import Alarm
from app.models.care import CareEpisode, FollowUpVisit
from app.models.enums import AlarmStatus
from app.models.users import User
from app.tests.alarm_apis.helpers import authentication_headers, medication_alarm_payload


def follow_up_alarm_payload(care_episode_id: int, follow_up_visit_id: int) -> dict[str, object]:
    scheduled_at = datetime.fromisoformat("2026-08-25T10:00:00+09:00")
    return {
        "care_episode_id": care_episode_id,
        "follow_up_visit_id": follow_up_visit_id,
        "alarm_type": "FOLLOW_UP_VISIT",
        "meal_slot": None,
        "title": "외래 진료 알람",
        "message": "외래 진료 예정입니다.",
        "scheduled_at": scheduled_at.isoformat(),
        "recurrence_rule": None,
        "timezone": "Asia/Seoul",
    }


class TestAlarmCrudAPI(TestCase):
    async def test_create_get_and_cancel_alarm(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "alarm-api@example.com", "01011110001")

            created = await client.post("/api/v1/alarms", json=medication_alarm_payload(), headers=headers)
            detail = await client.get(f"/api/v1/alarms/{created.json()['id']}", headers=headers)
            cancelled = await client.delete(f"/api/v1/alarms/{created.json()['id']}", headers=headers)

        assert created.status_code == status.HTTP_201_CREATED
        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["title"] == "아침약"
        assert cancelled.status_code == status.HTTP_204_NO_CONTENT
        alarm = await Alarm.get(id=created.json()["id"])
        assert alarm.status == AlarmStatus.CANCELLED

    async def test_alarm_api_requires_authentication(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/alarms")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_follow_up_visit_can_be_created_updated_returned_and_filtered(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-alarm@example.com"
            headers = await authentication_headers(client, email, "01011110004")
            user = await User.get(email=email)
            care_episode = await CareEpisode.create(user=user, title="외래 진료 테스트")
            first_visit = await FollowUpVisit.create(
                care_episode=care_episode,
                visit_date=date(2026, 8, 25),
                visit_time=time(10, 0),
            )
            second_visit = await FollowUpVisit.create(
                care_episode=care_episode,
                visit_date=first_visit.visit_date + timedelta(days=7),
                visit_time=first_visit.visit_time,
            )

            created = await client.post(
                "/api/v1/alarms",
                json=follow_up_alarm_payload(care_episode.id, first_visit.id),
                headers=headers,
            )
            updated = await client.patch(
                f"/api/v1/alarms/{created.json()['id']}",
                json={"follow_up_visit_id": second_visit.id},
                headers=headers,
            )
            detail = await client.get(f"/api/v1/alarms/{created.json()['id']}", headers=headers)
            listed = await client.get(
                "/api/v1/alarms",
                params={"follow_up_visit_id": second_visit.id},
                headers=headers,
            )

        assert created.status_code == status.HTTP_201_CREATED
        assert created.json()["follow_up_visit_id"] == first_visit.id
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["follow_up_visit_id"] == second_visit.id
        assert detail.json()["follow_up_visit_id"] == second_visit.id
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["follow_up_visit_id"] == second_visit.id

    async def test_follow_up_visit_must_belong_to_current_user(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "owner@example.com", "01011110005")
            owner = await User.get(email="owner@example.com")
            other = await User.create(
                email="other@example.com",
                hashed_password="hashed-password",
                status="ACTIVE",
                name="다른 사용자",
            )
            owner_episode = await CareEpisode.create(user=owner, title="소유자 에피소드")
            other_episode = await CareEpisode.create(user=other, title="다른 사용자 에피소드")
            other_visit = await FollowUpVisit.create(
                care_episode=other_episode,
                visit_date=date(2026, 8, 25),
                visit_time=time(10, 0),
            )

            response = await client.post(
                "/api/v1/alarms",
                json=follow_up_alarm_payload(owner_episode.id, other_visit.id),
                headers=headers,
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["detail"] == "Follow-up visit not found."

    async def test_follow_up_visit_must_match_care_episode(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "follow-up-mismatch@example.com"
            headers = await authentication_headers(client, email, "01011110006")
            user = await User.get(email=email)
            first_episode = await CareEpisode.create(user=user, title="첫 번째 에피소드")
            second_episode = await CareEpisode.create(user=user, title="두 번째 에피소드")
            visit = await FollowUpVisit.create(
                care_episode=second_episode,
                visit_date=date(2026, 8, 25),
                visit_time=time(10, 0),
            )

            response = await client.post(
                "/api/v1/alarms",
                json=follow_up_alarm_payload(first_episode.id, visit.id),
                headers=headers,
            )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["detail"] == "Follow-up visit does not match care episode."

    async def test_actions_endpoint_performs_supported_alarm_transitions(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "alarm-actions@example.com", "01011110002")
            created = await client.post("/api/v1/alarms", json=medication_alarm_payload(), headers=headers)
            alarm_id = created.json()["id"]

            responses = [
                await client.post(
                    f"/api/v1/alarms/{alarm_id}/actions",
                    json={"action": action},
                    headers=headers,
                )
                for action in ("pause", "resume", "skip", "complete")
            ]

        assert [response.status_code for response in responses] == [status.HTTP_200_OK] * 4
        assert [response.json()["status"] for response in responses] == [
            "PAUSED",
            "ACTIVE",
            "ACTIVE",
            "COMPLETED",
        ]

    async def test_actions_endpoint_rejects_unsupported_action(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "alarm-invalid-action@example.com", "01011110003")
            created = await client.post("/api/v1/alarms", json=medication_alarm_payload(), headers=headers)

            response = await client.post(
                f"/api/v1/alarms/{created.json()['id']}/actions",
                json={"action": "cancel"},
                headers=headers,
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
