import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

from tortoise.contrib.test import TruncationTestCase

from app.core import config
from app.core.exceptions import ChallengeAlreadyJoinedError, ChallengePeriodEndedError
from app.dtos.challenges import VerificationActionRequest, VerificationCreateRequest
from app.models.challenges import Badge, Challenge, ChallengeProgress, ChallengeVerification, UserBadge, UserChallenge
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.services.challenge_participation import ChallengeParticipationService
from app.tests.admin_apis.conftest import create_admin, create_user


class TestChallengeConcurrency(TruncationTestCase):
    """Use independent committed transactions, not TestCase's shared rollback connection."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.user = await create_user(name="동시 요청", email="concurrent-challenge@example.com")
        codes = {}
        for group_name, detail in [
            ("CHL_TYPE", "WALK"),
            ("CHL_PERIOD", "D7"),
            ("CHK_TYPE", "SELF"),
            ("CHK_FREQ", "DAILY"),
        ]:
            group = await CommonCodeGroup.create(category="CHL", group_code=group_name, group_name=group_name)
            codes[detail] = await CommonCode.create(group=group, detail_code=detail, detail_name=detail)
        self.badge = await Badge.create(name="동시성 검증 배지", image_path="media/badges/concurrency.png")
        self.now = datetime.now(config.TIMEZONE)
        self.challenge = await Challenge.create(
            name="동시성 검증 챌린지",
            phrase="하루 한 번 걷기",
            challenge_type=codes["WALK"],
            challenge_period=codes["D7"],
            check_type=codes["SELF"],
            check_frequency=codes["DAILY"],
            recruit_start_at=self.now - timedelta(days=1),
            recruit_end_at=self.now + timedelta(days=1),
            reward_badge=self.badge,
            is_displayed=True,
        )
        self.service = ChallengeParticipationService()
        self.participation = await self.service.join(self.user, self.challenge.id)
        self.now = self.participation.started_at

    async def asyncTearDown(self) -> None:
        # The generic truncation helper deletes User first; challenge FKs intentionally RESTRICT it.
        await UserBadge.filter(user_id=self.user.id).delete()
        ids = await UserChallenge.filter(user_id=self.user.id).values_list("id", flat=True)
        await ChallengeVerification.filter(user_challenge_id__in=ids).delete()
        await ChallengeProgress.filter(user_challenge_id__in=ids).delete()
        await UserChallenge.filter(user_id=self.user.id).delete()
        await self.challenge.delete()
        await self.badge.delete()
        await super().asyncTearDown()

    async def test_concurrent_rejoins_create_exactly_one_new_attempt(self) -> None:
        await self.service.cancel(self.user, self.participation.id)
        results = await asyncio.gather(
            *[self.service.join(self.user, self.challenge.id) for _ in range(5)], return_exceptions=True
        )
        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        assert len(successes) == 1, results
        assert len(failures) == 4
        assert all(isinstance(error, ChallengeAlreadyJoinedError) for error in failures), failures
        assert successes[0].id != self.participation.id
        assert successes[0].completed_count == 0
        assert await UserChallenge.filter(user_id=self.user.id, challenge_id=self.challenge.id).count() == 2
        assert (await self.service.get(self.user, self.participation.id)).status == "CANCELLED"

    async def test_concurrent_initial_joins_create_exactly_one_attempt(self) -> None:
        other = await create_user(name="First join", email="concurrent-first@example.com")
        results = await asyncio.gather(
            *[self.service.join(other, self.challenge.id) for _ in range(5)], return_exceptions=True
        )
        try:
            assert sum(not isinstance(result, Exception) for result in results) == 1, results
            assert all(
                isinstance(result, ChallengeAlreadyJoinedError) for result in results if isinstance(result, Exception)
            ), results
            assert await UserChallenge.filter(user_id=other.id, challenge_id=self.challenge.id).count() == 1
        finally:
            ids = await UserChallenge.filter(user_id=other.id).values_list("id", flat=True)
            await ChallengeProgress.filter(user_challenge_id__in=ids).delete()
            await UserChallenge.filter(user_id=other.id).delete()

    async def test_concurrent_final_checkins_award_one_badge_and_count_once(self) -> None:
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            for offset in range(6):
                day = self.now + timedelta(days=offset)
                clock.now.return_value = day
                await self.service.submit_verification(
                    self.user,
                    self.participation.id,
                    VerificationCreateRequest(
                        verification_date=day.date(), idempotency_key=f"concurrent-previous-{offset}"
                    ),
                )
            day = self.now + timedelta(days=6)
            clock.now.return_value = day
            results = await asyncio.gather(
                *[
                    self.service.submit_verification(
                        self.user,
                        self.participation.id,
                        VerificationCreateRequest(
                            verification_date=day.date(), idempotency_key=f"concurrent-final-{index}"
                        ),
                    )
                    for index in range(5)
                ]
            )
        assert len({row.id for row in results}) == 1
        detail = await self.service.get(self.user, self.participation.id)
        assert detail.status == "COMPLETED"
        assert detail.completed_count == 7
        assert detail.progress_rate == 100
        assert await ChallengeVerification.filter(user_challenge_id=detail.id).count() == 7
        assert await UserBadge.filter(user_challenge_id=detail.id, badge_id=self.badge.id).count() == 1

    async def test_cancel_and_checkin_race_cannot_reactivate_participation(self) -> None:
        results = await asyncio.gather(
            self.service.submit_verification(
                self.user,
                self.participation.id,
                VerificationCreateRequest(
                    verification_date=self.now.date(), idempotency_key="concurrent-cancel-checkin"
                ),
            ),
            self.service.cancel(self.user, self.participation.id),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                assert isinstance(result, ChallengePeriodEndedError), repr(result)
        detail = await self.service.get(self.user, self.participation.id)
        assert detail.status == "CANCELLED"
        assert detail.can_verify is False
        assert detail.completed_count in (0, 1)
        assert await UserBadge.filter(user_challenge_id=detail.id).count() == 0

    async def test_concurrent_manual_reviews_keep_all_approved_progress(self) -> None:
        admin = await create_admin(name="검토 관리자", email="review-concurrent@example.com")
        await self.challenge.fetch_related("check_type")
        manual = await CommonCode.create(
            group_id=self.challenge.check_type.group_id,
            detail_code="MANUAL",
            detail_name="MANUAL",
        )
        self.challenge.check_type = manual
        await self.challenge.save(update_fields=["check_type_id"])
        verifications = []
        with patch("app.services.challenge_participation.datetime", wraps=datetime) as clock:
            for offset in range(5):
                day = self.now + timedelta(days=offset)
                clock.now.return_value = day
                verifications.append(
                    await self.service.submit_verification(
                        self.user,
                        self.participation.id,
                        VerificationCreateRequest(
                            verification_date=day.date(),
                            idempotency_key=f"manual-concurrent-{offset}",
                            content="걷기 증빙",
                        ),
                    )
                )
            await asyncio.gather(
                *[
                    self.service.review_verification(row.id, VerificationActionRequest(action="APPROVE"), admin.id)
                    for row in verifications
                ]
            )
        detail = await self.service.get(self.user, self.participation.id)
        assert detail.completed_count == 5
        assert sum(row.completed_count for row in detail.progress_periods) == 5
