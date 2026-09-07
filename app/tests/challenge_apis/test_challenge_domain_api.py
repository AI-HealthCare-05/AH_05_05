from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from tortoise.contrib.test import TestCase

from app.core import config
from app.dependencies.security import get_request_user
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.enums import AdminRole
from app.tests.admin_apis.conftest import auth_header, create_admin, create_user, request


class TestChallengeDomainAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(
            name="챌린지 관리자",
            email="challenge-admin@example.com",
            role=AdminRole.ADMIN,
        )
        self.user = await create_user(name="참여자", email="challenge-user@example.com")
        self.admin_headers = auth_header(self.admin.id)
        self.codes = await self._create_codes()

    async def asyncTearDown(self) -> None:
        from app.main import app

        app.dependency_overrides.pop(get_request_user, None)
        await super().asyncTearDown()

    async def _create_codes(self) -> dict[str, CommonCode]:
        values = {
            "CHL_TYPE": ["WALK"],
            "CHL_PERIOD": ["D7", "D30"],
            "CHK_TYPE": ["SELF", "MANUAL"],
            "CHK_FREQ": ["DAILY", "WEEKLY_3"],
        }
        result: dict[str, CommonCode] = {}
        for group_code, detail_codes in values.items():
            group = await CommonCodeGroup.create(
                category="CHL",
                group_code=group_code,
                group_name=group_code,
            )
            for detail_code in detail_codes:
                result[detail_code] = await CommonCode.create(
                    group=group,
                    detail_code=detail_code,
                    detail_name=detail_code,
                )
        return result

    async def _create_badge(self) -> dict:
        response = await request(
            "POST",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
            json={
                "name": "30일 걷기 배지",
                "description": "30일 걷기 완료",
                "image_path": "/media/badges/walk.png",
                "is_active": True,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def _create_challenge(
        self,
        badge_id: int,
        check_type: str = "SELF",
        period: str = "D30",
        frequency: str = "WEEKLY_3",
    ) -> dict:
        now = datetime.now(config.TIMEZONE)
        response = await request(
            "POST",
            "/api/v1/admin/challenges",
            headers=self.admin_headers,
            json={
                "name": f"30일 걷기 {check_type}",
                "challenge_type_id": self.codes["WALK"].id,
                "phrase": "매일 걸어요",
                "description": "건강한 걷기 습관",
                "recruit_start_at": (now - timedelta(days=1)).isoformat(),
                "recruit_end_at": (now + timedelta(days=1)).isoformat(),
                "challenge_period_id": self.codes[period].id,
                "check_type_id": self.codes[check_type].id,
                "check_frequency_id": self.codes[frequency].id,
                "reward_badge_id": badge_id,
                "is_displayed": True,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def test_admin_crud_and_user_join_create_expected_weekly_periods(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"])
        app.dependency_overrides[get_request_user] = lambda: self.user

        joined = await request(
            "POST",
            f"/api/v1/user/challenges/{challenge['id']}/join",
        )

        assert joined.status_code == 201, joined.text
        body = joined.json()
        assert body["target_count"] == 12
        assert len(body["progress_periods"]) == 4
        assert body["status"] == "ACTIVE"

    async def test_admin_uploads_badge_image(self) -> None:
        buffer = BytesIO()
        Image.new("RGB", (1, 1), "teal").save(buffer, format="PNG")
        png = buffer.getvalue()
        with TemporaryDirectory() as directory:
            with patch("app.apis.v1.admin_challenge_router.BADGE_IMAGE_DIR", Path(directory)):
                response = await request(
                    "POST",
                    "/api/v1/admin/badge-images",
                    headers=self.admin_headers,
                    files={"image": ("badge.png", png, "image/png")},
                )

            assert response.status_code == 201, response.text
            body = response.json()
            assert body["image_path"].startswith("media/badges/")
            assert len(list(Path(directory).glob("*.png"))) == 1

    async def test_self_verification_is_approved_and_updates_progress(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"])
        app.dependency_overrides[get_request_user] = lambda: self.user
        joined = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        participation = joined.json()

        verified = await request(
            "POST",
            f"/api/v1/user/challenges/{participation['id']}/verifications",
            json={
                "verification_date": participation["progress_periods"][0]["period_start"],
                "idempotency_key": "self-verification-000000000000000000000000000000000000000001",
                "content": "오늘 걷기 완료",
            },
        )

        assert verified.status_code == 201, verified.text
        assert verified.json()["status"] == "APPROVED"

        detail = await request("GET", f"/api/v1/user/challenges/{participation['id']}")
        assert detail.json()["completed_count"] == 1
        assert detail.json()["progress_periods"][0]["completed_count"] == 1

    async def test_manual_verification_waits_for_admin_review(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"], check_type="MANUAL")
        app.dependency_overrides[get_request_user] = lambda: self.user
        joined = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        participation = joined.json()
        submitted = await request(
            "POST",
            f"/api/v1/user/challenges/{participation['id']}/verifications",
            json={
                "verification_date": participation["progress_periods"][0]["period_start"],
                "idempotency_key": "manual-verification-0000000000000000000000000000000000000001",
                "content": "걷기 인증",
            },
        )

        assert submitted.status_code == 201, submitted.text
        assert submitted.json()["status"] == "PENDING"

        pending = await request(
            "GET",
            "/api/v1/admin/challenge-verifications",
            headers=self.admin_headers,
            params={"status": "PENDING"},
        )
        assert pending.status_code == 200, pending.text
        assert pending.json()["total_count"] == 1
        assert pending.json()["items"][0]["id"] == submitted.json()["id"]

        approved = await request(
            "POST",
            f"/api/v1/admin/challenge-verifications/{submitted.json()['id']}/actions",
            headers=self.admin_headers,
            json={"action": "APPROVE"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "APPROVED"

    async def test_completed_challenge_awards_badge_once(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"], period="D7", frequency="DAILY")
        app.dependency_overrides[get_request_user] = lambda: self.user
        joined = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        participation = joined.json()

        for index, progress in enumerate(participation["progress_periods"]):
            verified = await request(
                "POST",
                f"/api/v1/user/challenges/{participation['id']}/verifications",
                json={
                    "verification_date": progress["period_start"],
                    "idempotency_key": f"daily-verification-{index:02d}-000000000000000000000000000000",
                },
            )
            assert verified.status_code == 201, verified.text

        detail = await request("GET", f"/api/v1/user/challenges/{participation['id']}")
        badges = await request("GET", "/api/v1/user/badges")

        assert detail.json()["status"] == "COMPLETED"
        assert detail.json()["progress_rate"] == "100.00"
        assert badges.json()["total_count"] == 1
        assert badges.json()["items"][0]["badge_id"] == badge["id"]
