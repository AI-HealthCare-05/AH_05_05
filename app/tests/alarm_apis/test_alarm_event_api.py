from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.alarms import AlarmEvent
from app.models.enums import AlarmEventType
from app.tests.alarm_apis.helpers import authentication_headers, medication_alarm_payload
from app.tests.alarm_apis.test_push_subscription_api import subscription_payload


class TestAlarmEventAPI(TestCase):
    async def test_delivery_ack_is_idempotent(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "event-api@example.com", "01011110003")
            alarm = await client.post("/api/v1/alarms", json=medication_alarm_payload(), headers=headers)
            subscription = await client.put(
                "/api/v1/alarms/push-subscriptions",
                json=subscription_payload(),
                headers=headers,
            )
            await AlarmEvent.create(
                alarm_id=alarm.json()["id"],
                event_type=AlarmEventType.SENT,
                push_subscription_id=subscription.json()["id"],
            )
            payload = {"push_subscription_id": subscription.json()["id"]}

            first = await client.post(
                f"/api/v1/alarms/{alarm.json()['id']}/delivery-ack",
                json=payload,
                headers=headers,
            )
            second = await client.post(
                f"/api/v1/alarms/{alarm.json()['id']}/delivery-ack",
                json=payload,
                headers=headers,
            )

        assert first.status_code == status.HTTP_200_OK
        assert second.json()["id"] == first.json()["id"]
        assert await AlarmEvent.filter(
            alarm_id=alarm.json()["id"],
            event_type=AlarmEventType.DELIVERED,
        ).count() == 1
