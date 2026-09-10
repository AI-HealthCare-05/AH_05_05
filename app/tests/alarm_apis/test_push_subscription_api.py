from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.alarms import PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.models.users import User
from app.tests.alarm_apis.helpers import authentication_headers


def subscription_payload() -> dict[str, str]:
    return {
        "endpoint": "https://push.example.test/subscription-1",
        "p256dh_key": "p256dh-key",
        "auth_key": "auth-key",
        "platform": "desktop",
        "user_agent": "pytest",
    }


class TestPushSubscriptionAPI(TestCase):
    async def test_upsert_and_soft_delete_subscription(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "push-api@example.com", "01011110002")
            created = await client.put(
                "/api/v1/alarms/push-subscriptions",
                json=subscription_payload(),
                headers=headers,
            )
            updated_payload = subscription_payload() | {"auth_key": "rotated-auth-key"}
            updated = await client.put(
                "/api/v1/alarms/push-subscriptions",
                json=updated_payload,
                headers=headers,
            )
            deleted = await client.delete(
                f"/api/v1/alarms/push-subscriptions/{created.json()['id']}",
                headers=headers,
            )

        assert created.status_code == status.HTTP_200_OK
        assert updated.json()["id"] == created.json()["id"]
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        subscription = await PushSubscription.get(id=created.json()["id"])
        assert subscription.auth_key == "rotated-auth-key"
        assert subscription.is_active is False

    async def test_upsert_moves_browser_subscription_to_current_user_and_cancels_old_jobs(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first_headers = await authentication_headers(client, "push-first@example.com", "01011110003")
            created = await client.put(
                "/api/v1/alarms/push-subscriptions",
                json=subscription_payload(),
                headers=first_headers,
            )
            subscription_id = created.json()["id"]
            queued_job = await BackgroundJob.create(
                idempotency_key=f"alarm:91:{subscription_id}:2026-09-10T08:00:00+09:00",
                job_type=BackgroundJobType.ALARM,
                status=BackgroundJobStatus.QUEUED,
                user_id=(await User.get(email="push-first@example.com")).id,
            )

            second_headers = await authentication_headers(client, "push-second@example.com", "01011110004")
            moved = await client.put(
                "/api/v1/alarms/push-subscriptions",
                json=subscription_payload() | {"auth_key": "second-user-auth-key"},
                headers=second_headers,
            )

        assert moved.status_code == status.HTTP_200_OK
        old_subscription = await PushSubscription.get(id=subscription_id)
        subscription = await PushSubscription.get(id=moved.json()["id"])
        second_user = await User.get(email="push-second@example.com")
        await queued_job.refresh_from_db()
        assert subscription.id != old_subscription.id
        assert subscription.user_id == second_user.id
        assert subscription.auth_key == "second-user-auth-key"
        assert subscription.is_active is True
        assert old_subscription.is_active is False
        assert old_subscription.endpoint != subscription_payload()["endpoint"]
        assert queued_job.status == BackgroundJobStatus.CANCELLED
