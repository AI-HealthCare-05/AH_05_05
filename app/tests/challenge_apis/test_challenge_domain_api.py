from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from tortoise.contrib.test import TestCase

from app.core import config
from app.dependencies.security import get_request_user
from app.models.challenges import Challenge, UserBadge, UserChallenge
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
            "CST_CHK_TYPE": ["COUNT", "PHOTO"],
            "CST_CHL_TYPE": ["CUSTOM", "HABIT"],
            "BDG_TYPE": ["ACHIEVEMENT", "MILESTONE"],
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

    async def test_admin_can_create_search_and_update_custom_challenge_template(self) -> None:
        badge = await self._create_badge()
        created = await request(
            "POST",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            json={
                "name": "하루 물 8잔",
                "check_type_id": self.codes["COUNT"].id,
                "challenge_type": self.codes["CUSTOM"].id,
                "reward_badge_id": badge["id"],
                "is_active": True,
            },
        )

        assert created.status_code == 201, created.text
        assert created.json()["challenge_type"] == self.codes["CUSTOM"].id
        assert created.json()["reward_badge_id"] == badge["id"]
        template_id = created.json()["id"]

        listed = await request(
            "GET",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            params={"name": "물 8", "is_active": True},
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["total_count"] == 1
        assert listed.json()["items"][0]["id"] == template_id

        updated = await request(
            "PATCH",
            f"/api/v1/admin/custom-challenge-templates/{template_id}",
            headers=self.admin_headers,
            json={
                "name": "하루 물 마시기",
                "check_type_id": self.codes["PHOTO"].id,
                "is_active": False,
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "하루 물 마시기"
        assert updated.json()["check_type_id"] == self.codes["PHOTO"].id
        assert updated.json()["is_active"] is False

    async def test_custom_challenge_template_rejects_other_common_code_group(self) -> None:
        response = await request(
            "POST",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            json={
                "name": "잘못된 인증 방식",
                "check_type_id": self.codes["SELF"].id,
                "is_active": True,
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_COMMON_CODE"

    async def test_admin_filters_custom_templates_by_reward_badge(self) -> None:
        badge = await self._create_badge()
        for name, reward_badge_id in (("배지 지정", badge["id"]), ("배지 미지정", None)):
            created = await request(
                "POST",
                "/api/v1/admin/custom-challenge-templates",
                headers=self.admin_headers,
                json={
                    "name": name,
                    "check_type_id": self.codes["COUNT"].id,
                    "reward_badge_id": reward_badge_id,
                    "is_active": True,
                },
            )
            assert created.status_code == 201, created.text

        response = await request(
            "GET",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            params={"reward_badge_id": badge["id"]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 1
        assert response.json()["items"][0]["name"] == "배지 지정"

    async def test_admin_filters_custom_templates_by_challenge_type(self) -> None:
        for name, challenge_type in (
            ("맞춤형 템플릿", self.codes["CUSTOM"].id),
            ("습관형 템플릿", self.codes["HABIT"].id),
        ):
            created = await request(
                "POST",
                "/api/v1/admin/custom-challenge-templates",
                headers=self.admin_headers,
                json={
                    "name": name,
                    "check_type_id": self.codes["COUNT"].id,
                    "challenge_type": challenge_type,
                    "is_active": True,
                },
            )
            assert created.status_code == 201, created.text

        response = await request(
            "GET",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            params={"challenge_type": self.codes["HABIT"].id},
        )

        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 1
        assert response.json()["items"][0]["name"] == "습관형 템플릿"

    async def _create_badge(self) -> dict:
        response = await request(
            "POST",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
            json={
                "name": "30일 걷기 배지",
                "description": "30일 걷기 완료",
                "image_path": "/media/badges/walk.png",
                "type": self.codes["ACHIEVEMENT"].id,
                "is_active": True,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["type"] == self.codes["ACHIEVEMENT"].id
        return response.json()

    async def test_admin_filters_badges_by_badge_type(self) -> None:
        achievement = await self._create_badge()
        milestone = await request(
            "POST",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
            json={
                "name": "누적 달성 배지",
                "description": "누적 목표 달성",
                "image_path": "/media/badges/milestone.png",
                "type": self.codes["MILESTONE"].id,
                "is_active": True,
            },
        )
        assert milestone.status_code == 201, milestone.text

        response = await request(
            "GET",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
            params={"type": self.codes["ACHIEVEMENT"].id},
        )

        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 1
        assert response.json()["items"][0]["id"] == achievement["id"]

    async def test_badge_list_marks_challenge_badge_as_not_deletable(self) -> None:
        used_badge = await self._create_badge()
        unused_badge = await request(
            "POST",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
            json={
                "name": "미사용 배지",
                "image_path": "/media/badges/unused.png",
                "type": self.codes["MILESTONE"].id,
                "is_active": True,
            },
        )
        assert unused_badge.status_code == 201, unused_badge.text
        await self._create_challenge(used_badge["id"])

        response = await request(
            "GET",
            "/api/v1/admin/badges",
            headers=self.admin_headers,
        )

        assert response.status_code == 200, response.text
        deletable_by_id = {item["id"]: item["is_deletable"] for item in response.json()["items"]}
        assert deletable_by_id == {
            used_badge["id"]: False,
            unused_badge.json()["id"]: True,
        }

    async def test_staff_can_delete_an_unused_badge(self) -> None:
        badge = await self._create_badge()
        staff = await create_admin(
            name="챌린지 스태프",
            email="challenge-staff@example.com",
            role=AdminRole.STAFF,
        )

        deleted = await request(
            "DELETE",
            f"/api/v1/admin/badges/{badge['id']}",
            headers=auth_header(staff.id),
        )
        detail = await request(
            "GET",
            f"/api/v1/admin/badges/{badge['id']}",
            headers=self.admin_headers,
        )

        assert deleted.status_code == 204, deleted.text
        assert detail.status_code == 404

    async def test_admin_cannot_delete_badge_used_by_challenge(self) -> None:
        badge = await self._create_badge()
        await self._create_challenge(badge["id"])

        response = await request(
            "DELETE",
            f"/api/v1/admin/badges/{badge['id']}",
            headers=self.admin_headers,
        )

        assert response.status_code == 409, response.text
        assert response.json() == {
            "code": "BADGE_IN_USE",
            "message": "사용 중인 배지는 삭제할 수 없습니다.",
        }

    async def test_admin_cannot_delete_badge_used_by_custom_template(self) -> None:
        badge = await self._create_badge()
        created = await request(
            "POST",
            "/api/v1/admin/custom-challenge-templates",
            headers=self.admin_headers,
            json={
                "name": "배지 참조 템플릿",
                "check_type_id": self.codes["COUNT"].id,
                "challenge_type": self.codes["CUSTOM"].id,
                "reward_badge_id": badge["id"],
                "is_active": True,
            },
        )
        assert created.status_code == 201, created.text

        response = await request(
            "DELETE",
            f"/api/v1/admin/badges/{badge['id']}",
            headers=self.admin_headers,
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "BADGE_IN_USE"

    async def test_admin_cannot_delete_badge_already_awarded_to_user(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"])
        app.dependency_overrides[get_request_user] = lambda: self.user
        joined = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        assert joined.status_code == 201, joined.text
        participation = await UserChallenge.get(id=joined.json()["id"])
        await UserBadge.create(
            user=self.user,
            badge_id=badge["id"],
            challenge_id=challenge["id"],
            user_challenge=participation,
            badge_name=badge["name"],
            badge_image_path=badge["image_path"],
        )
        await Challenge.filter(id=challenge["id"]).update(reward_badge_id=None)

        response = await request(
            "DELETE",
            f"/api/v1/admin/badges/{badge['id']}",
            headers=self.admin_headers,
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "BADGE_IN_USE"

    async def _create_challenge(
        self,
        badge_id: int,
        check_type: str = "SELF",
        period: str = "D30",
        frequency: str = "WEEKLY_3",
        reference_time: datetime | None = None,
    ) -> dict:
        now = reference_time or datetime.now(config.TIMEZONE)
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

    async def test_joined_challenge_is_not_deletable(self) -> None:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"])
        app.dependency_overrides[get_request_user] = lambda: self.user
        joined = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        assert joined.status_code == 201, joined.text

        listed = await request(
            "GET",
            "/api/v1/admin/challenges",
            headers=self.admin_headers,
        )
        deleted = await request(
            "DELETE",
            f"/api/v1/admin/challenges/{challenge['id']}",
            headers=self.admin_headers,
        )

        assert listed.status_code == 200, listed.text
        assert listed.json()["items"][0]["is_deletable"] is False
        assert deleted.status_code == 409, deleted.text
        assert deleted.json() == {
            "code": "CHALLENGE_IN_USE",
            "message": "참여자가 있는 챌린지는 삭제할 수 없습니다.",
        }

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
            # Advance the server clock; a client must not pre-certify future dates.
            day = datetime.fromisoformat(participation["started_at"]) + timedelta(days=index)
            with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
                clock.now.return_value = day
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
        assert Decimal(detail.json()["progress_rate"]) == Decimal("100.00")
        assert badges.json()["total_count"] == 1
        assert badges.json()["items"][0]["badge_id"] == badge["id"]

    async def _join_daily(
        self,
        check_type: str = "SELF",
        reference_time: datetime | None = None,
    ) -> dict:
        from app.main import app

        badge = await self._create_badge()
        challenge = await self._create_challenge(
            badge["id"],
            period="D7",
            frequency="DAILY",
            check_type=check_type,
            reference_time=reference_time,
        )
        app.dependency_overrides[get_request_user] = lambda: self.user
        response = await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")
        assert response.status_code == 201, response.text
        return response.json()

    async def test_join_requires_user_authentication(self) -> None:
        response = await request("POST", "/api/v1/user/challenges/1/join")

        assert response.status_code == 401, response.text

    async def test_my_challenge_list_requires_user_authentication(self) -> None:
        response = await request("GET", "/api/v1/user/challenges")

        assert response.status_code == 401, response.text

    async def test_my_challenge_detail_requires_user_authentication(self) -> None:
        response = await request("GET", "/api/v1/user/challenges/1")

        assert response.status_code == 401, response.text

    async def test_challenge_verification_requires_user_authentication(self) -> None:
        response = await request(
            "POST",
            "/api/v1/user/challenges/1/verifications",
            json={
                "verification_date": datetime.now(config.TIMEZONE).date().isoformat(),
                "idempotency_key": "unauthenticated-verification-304",
            },
        )

        assert response.status_code == 401, response.text

    async def test_my_badges_require_user_authentication(self) -> None:
        response = await request("GET", "/api/v1/user/badges")

        assert response.status_code == 401, response.text

    async def test_catalog_requires_user_and_hides_unpublished_data(self) -> None:
        from app.main import app
        from app.models.challenges import Challenge

        assert (await request("GET", "/api/v1/user/challenge-catalog")).status_code == 401
        badge = await self._create_badge()
        visible = await self._create_challenge(badge["id"], period="D7", frequency="DAILY")
        hidden = await self._create_challenge(badge["id"])
        await Challenge.filter(id=hidden["id"]).update(is_displayed=False)
        app.dependency_overrides[get_request_user] = lambda: self.user
        response = await request("GET", "/api/v1/user/challenge-catalog?limit=1")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total_count"] == 1
        item = data["items"][0]
        assert item["id"] == visible["id"]
        assert item["duration_days"] == 7
        assert item["frequency_code"] == "DAILY"
        assert item["reward_badge"]["image_path"] == badge["image_path"]
        assert item["can_join"] is True
        assert "created_by_admin_id" not in item
        assert (await request("GET", f"/api/v1/user/challenge-catalog/{hidden['id']}")).status_code == 404

    async def test_catalog_and_owned_detail_have_separate_visibility_and_identity(self) -> None:
        from app.main import app
        from app.models.challenges import Challenge

        participation = await self._join_daily()
        catalog_url = f"/api/v1/user/challenge-catalog/{participation['challenge_id']}"
        catalog = (await request("GET", catalog_url)).json()
        assert catalog["participation_id"] == participation["id"]
        assert catalog["can_join"] is False
        await Challenge.filter(id=participation["challenge_id"]).update(is_displayed=False, is_deleted=True)
        assert (await request("GET", catalog_url)).status_code == 404
        url = f"/api/v1/user/challenges/{participation['id']}"
        detail = await request("GET", url)
        assert detail.status_code == 200
        assert detail.json()["challenge"]["name"] == participation["challenge_name"]
        other = await create_user(name="다른 참여자", email="other-challenge@example.com")
        app.dependency_overrides[get_request_user] = lambda: other
        assert (await request("GET", url)).status_code == 404
        assert (await request("GET", "/api/v1/user/challenges")).json()["items"] == []

    async def test_other_user_cannot_submit_verification_or_mutate_progress_or_badges(self) -> None:
        from app.main import app
        from app.models.challenges import ChallengeProgress, ChallengeVerification, UserBadge, UserChallenge

        participation = await self._join_daily()
        participation_id = participation["id"]
        other = await create_user(name="다른 인증 사용자", email="other-verification@example.com")
        app.dependency_overrides[get_request_user] = lambda: other

        response = await request(
            "POST",
            f"/api/v1/user/challenges/{participation_id}/verifications",
            json={
                "verification_date": participation["today"],
                "idempotency_key": "other-user-verification-304",
            },
        )

        assert response.status_code == 404, response.text
        assert await ChallengeVerification.filter(user_challenge_id=participation_id).count() == 0
        stored = await UserChallenge.get(id=participation_id)
        assert stored.completed_count == 0
        assert stored.progress_rate == 0
        assert stored.completed_at is None
        progress_periods = await ChallengeProgress.filter(user_challenge_id=participation_id)
        assert progress_periods
        assert all(progress.completed_count == 0 for progress in progress_periods)
        assert all(progress.progress_rate == 0 for progress in progress_periods)
        assert all(progress.is_completed is False for progress in progress_periods)
        assert all(progress.completed_at is None for progress in progress_periods)
        assert await UserBadge.filter(user_challenge_id=participation_id).count() == 0

    async def test_today_state_survives_reload_and_duplicate_keys_do_not_count_twice(self) -> None:
        from app.models.challenges import ChallengeVerification

        participation = await self._join_daily()
        assert participation["can_verify"] is True
        assert participation["today_verification"] is None
        assert participation["verified_dates"] == []
        url = f"/api/v1/user/challenges/{participation['id']}"
        payload = {"verification_date": participation["today"], "idempotency_key": "same-day-first-request-304"}
        first = await request("POST", url + "/verifications", json=payload)
        assert first.status_code == 201, first.text
        payload["idempotency_key"] = "same-day-second-request-304"
        second = await request("POST", url + "/verifications", json=payload)
        assert second.status_code == 201, second.text
        assert second.json()["id"] == first.json()["id"]
        assert await ChallengeVerification.filter(user_challenge_id=participation["id"]).count() == 1
        reloaded = (await request("GET", url)).json()
        assert reloaded["completed_count"] == 1
        assert reloaded["today_verification"]["status"] == "APPROVED"
        assert reloaded["can_verify"] is False
        assert reloaded["verified_dates"] == [participation["today"]]

    async def test_future_and_past_dates_cannot_be_certified(self) -> None:
        from app.models.challenges import ChallengeVerification

        participation = await self._join_daily()
        today = datetime.now(config.TIMEZONE).date()
        for offset in (-1, 1):
            response = await request(
                "POST",
                f"/api/v1/user/challenges/{participation['id']}/verifications",
                json={
                    "verification_date": (today + timedelta(days=offset)).isoformat(),
                    "idempotency_key": f"invalid-date-{offset}-304-request",
                },
            )
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "INVALID_VERIFICATION_DATE"
        assert await ChallengeVerification.all().count() == 0

    async def test_personal_period_ends_at_midnight_after_last_calendar_day(self) -> None:
        day = datetime(2026, 9, 8, 15, 30, tzinfo=config.TIMEZONE)
        # Recruitment fixtures and participation must use the same calendar day.
        with (
            patch(f"{__name__}.datetime", wraps=datetime) as fixture_clock,
            patch("app.services.challenge_participation.datetime", wraps=datetime) as clock,
        ):
            fixture_clock.now.return_value = day
            clock.now.return_value = day
            participation = await self._join_daily(reference_time=day)
        assert datetime.fromisoformat(participation["end_at"]).astimezone(config.TIMEZONE) == datetime(
            2026, 9, 15, tzinfo=config.TIMEZONE
        )
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 9, 15, tzinfo=config.TIMEZONE)
            detail = (await request("GET", f"/api/v1/user/challenges/{participation['id']}")).json()
        assert detail["status"] == "EXPIRED"
        assert detail["can_verify"] is False

    async def test_failed_recalculation_does_not_commit_verification(self) -> None:
        from unittest.mock import AsyncMock

        from app.dtos.challenges import VerificationCreateRequest
        from app.models.challenges import ChallengeVerification
        from app.services.challenge_participation import ChallengeParticipationService

        now = datetime.now(config.TIMEZONE)
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            participation = await self._join_daily()
            with patch.object(
                ChallengeParticipationService,
                "_recalculate",
                AsyncMock(side_effect=RuntimeError("test")),
            ):
                with self.assertRaises(RuntimeError):
                    await ChallengeParticipationService().submit_verification(
                        self.user,
                        participation["id"],
                        VerificationCreateRequest(
                            verification_date=now.date(),
                            idempotency_key="rollback-verification-304",
                        ),
                    )
        assert await ChallengeVerification.filter(user_challenge_id=participation["id"]).count() == 0

    async def test_admin_review_cannot_complete_a_cancelled_participation(self) -> None:
        from app.dtos.challenges import VerificationActionRequest
        from app.main import app
        from app.services.challenge_participation import ChallengeParticipationService

        badge = await self._create_badge()
        challenge = await self._create_challenge(badge["id"], period="D7", frequency="WEEKLY_3", check_type="MANUAL")
        app.dependency_overrides[get_request_user] = lambda: self.user
        participation = (await request("POST", f"/api/v1/user/challenges/{challenge['id']}/join")).json()
        url = f"/api/v1/user/challenges/{participation['id']}"
        pending_ids = []
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            for offset in range(3):
                day = datetime.fromisoformat(participation["started_at"]) + timedelta(days=offset)
                clock.now.return_value = day
                response = await request(
                    "POST",
                    url + "/verifications",
                    json={
                        "verification_date": day.date().isoformat(),
                        "idempotency_key": f"cancelled-manual-review-{offset}",
                        "content": "걷기 완료",
                    },
                )
                assert response.status_code == 201, response.text
                pending_ids.append(response.json()["id"])
            assert (await request("POST", url + "/cancel")).status_code == 200
            for verification_id in pending_ids:
                await ChallengeParticipationService().review_verification(
                    verification_id,
                    VerificationActionRequest(action="APPROVE"),
                    self.admin.id,
                )
        detail = (await request("GET", url)).json()
        assert detail["status"] == "CANCELLED"
        assert detail["completed_at"] is None
        assert (await request("GET", "/api/v1/user/badges")).json()["total_count"] == 0

    async def test_manual_evidence_retains_previous_day_submission(self) -> None:
        participation = await self._join_daily("MANUAL")
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat(participation["started_at"]) + timedelta(days=1)
            response = await request(
                "POST",
                f"/api/v1/user/challenges/{participation['id']}/verifications",
                json={
                    "verification_date": participation["today"],
                    "idempotency_key": "manual-previous-day-304",
                    "content": "전날 걷기 증빙",
                },
            )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "PENDING"

    async def test_failed_manual_recalculation_keeps_review_pending_and_retryable(self) -> None:
        from unittest.mock import AsyncMock

        from app.dtos.challenges import VerificationActionRequest, VerificationCreateRequest
        from app.models.challenges import ChallengeVerification
        from app.services.challenge_participation import ChallengeParticipationService

        participation = await self._join_daily("MANUAL")
        service = ChallengeParticipationService()
        verification = await service.submit_verification(
            self.user,
            participation["id"],
            VerificationCreateRequest(
                verification_date=datetime.fromisoformat(participation["started_at"]).date(),
                idempotency_key="manual-rollback-review-304",
                content="걷기 완료",
            ),
        )
        action = VerificationActionRequest(action="APPROVE")
        with patch.object(ChallengeParticipationService, "_recalculate", AsyncMock(side_effect=RuntimeError("test"))):
            with self.assertRaises(RuntimeError):
                await service.review_verification(verification.id, action, self.admin.id)
        stored = await ChallengeVerification.get(id=verification.id)
        assert stored.status == "PENDING"
        await service.review_verification(verification.id, action, self.admin.id)
        assert (await service.get(self.user, participation["id"])).completed_count == 1
