from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.alarms import PushSubscription
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
