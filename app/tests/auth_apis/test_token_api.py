from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app


@pytest.fixture(autouse=True)
def enable_user_refresh():
    """이 파일은 사용자 리프레시 흐름 자체를 검증하므로 플래그를 켠 상태로 돌린다.

    USER_REFRESH_ENABLED 기본값은 False 다(자동 로그인 미사용). 끈 상태의 동작은
    test_token_refresh_disabled.py 가 따로 확인한다.
    """
    with patch.object(config, "USER_REFRESH_ENABLED", True):
        yield


class TestJWTTokenRefreshAPI(TestCase):
    async def test_token_refresh_success(self):
        # 사용자 등록 및 로그인하여 리프레시 토큰 획득
        signup_data = {
            "email": "refresh@example.com",
            "password": "Password123!",
            "name": "리프레시테스터",
            "phone_number": "01099998888",
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            login_response = await client.post(
                "/api/v1/auth/login", json={"email": "refresh@example.com", "password": "Password123!"}
            )

            # 쿠키에서 refresh_token 추출
            set_cookie = login_response.headers.get("set-cookie")
            refresh_token = ""
            if set_cookie:
                import re

                match = re.search(r"refresh_token=([^;]+)", set_cookie)
                if match:
                    refresh_token = match.group(1)

            # 토큰 갱신 시도
            client.cookies["refresh_token"] = refresh_token
            response = await client.get("/api/v1/auth/token/refresh")
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    async def test_token_refresh_missing_token(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/token/refresh")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Refresh token is missing."
