from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette import status

from app.apis.v1.auth_routers import get_email_verification_service
from app.main import app


class StubEmailVerificationService:
    async def request(self, email: str):
        assert email == "user@example.com"
        return SimpleNamespace(verification_id=41, expires_in=180, resend_available_in=60)

    async def verify(self, verification_id: int, code: str):
        assert verification_id == 41
        assert code == "123456"
        return SimpleNamespace(verification_token="verification-token", expires_in=600)


async def test_request_email_verification_returns_async_contract() -> None:
    app.dependency_overrides[get_email_verification_service] = StubEmailVerificationService
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/email-verifications",
                json={"email": "user@example.com"},
            )
    finally:
        app.dependency_overrides.pop(get_email_verification_service, None)

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json() == {
        "verification_id": 41,
        "expires_in": 180,
        "resend_available_in": 60,
    }


async def test_verify_email_code_returns_one_time_token() -> None:
    app.dependency_overrides[get_email_verification_service] = StubEmailVerificationService
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/email-verifications/41/verify",
                json={"code": "123456"},
            )
    finally:
        app.dependency_overrides.pop(get_email_verification_service, None)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"verification_token": "verification-token", "expires_in": 600}


async def test_verify_email_code_rejects_non_six_digit_value() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/email-verifications/41/verify",
            json={"code": "12345a"},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["field"] == "code"
