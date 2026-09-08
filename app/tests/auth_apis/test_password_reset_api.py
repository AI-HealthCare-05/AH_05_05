from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core.utils.security import hash_password, verify_password
from app.main import app
from app.models.enums import AccountStatus
from app.models.users import User
from app.services.email_jobs import EmailJobService

PASSWORD_RESET_URL = "/api/v1/auth/password-reset"


class TestPasswordResetAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.original_password = "Original123!"
        self.user = await User.create(
            email="reset@example.com",
            hashed_password=hash_password(self.original_password),
            name="재설정 사용자",
            status=AccountStatus.ACTIVE,
        )

    async def request(self, email: str):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(PASSWORD_RESET_URL, json={"email": email})

    async def test_active_user_queues_reset_without_changing_password_in_api(self) -> None:
        enqueue = AsyncMock()

        with patch.object(EmailJobService, "enqueue_user_password_reset", new=enqueue):
            response = await self.request(self.user.email)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json() == {"detail": "입력한 이메일이 등록되어 있으면 임시비밀번호를 발송합니다."}
        enqueue.assert_awaited_once()
        arguments = enqueue.await_args.kwargs
        assert arguments["user_id"] == self.user.id
        assert arguments["recipient_email"] == self.user.email
        assert arguments["temporary_password"] not in response.text
        await self.user.refresh_from_db()
        assert verify_password(self.original_password, self.user.hashed_password)

    async def test_unknown_and_inactive_users_return_same_response_without_queueing(self) -> None:
        inactive = await User.create(
            email="inactive@example.com",
            hashed_password=hash_password("Original123!"),
            name="정지 사용자",
            status=AccountStatus.SUSPENDED,
        )
        enqueue = AsyncMock()

        with patch.object(EmailJobService, "enqueue_user_password_reset", new=enqueue):
            unknown_response = await self.request("unknown@example.com")
            inactive_response = await self.request(inactive.email)

        assert unknown_response.status_code == status.HTTP_202_ACCEPTED
        assert inactive_response.status_code == status.HTTP_202_ACCEPTED
        assert unknown_response.json() == inactive_response.json()
        enqueue.assert_not_awaited()
