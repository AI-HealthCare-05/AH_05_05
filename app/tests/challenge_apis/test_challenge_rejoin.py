"""Attempt history regressions using the repository transaction test fixture."""

from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.exceptions import (
    ChallengeAlreadyJoinedError,
    ChallengeNotFoundError,
    ChallengeNotRecruitingError,
    ChallengePeriodEndedError,
)
from app.dtos.challenges import VerificationCreateRequest
from app.models.challenges import Badge, Challenge, ChallengeVerification, UserBadge, UserChallenge
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.enums import ChallengeParticipationStatus
from app.models.users import User
from app.services.challenge_catalog import ChallengeCatalogService
from app.services.challenge_participation import ChallengeParticipationService

NOW = datetime(2026, 9, 9, 9, tzinfo=config.TIMEZONE)


class TestChallengeRejoin(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.patchers = [
            patch("app.services.challenge_participation.datetime", wraps=datetime),
            patch("app.services.challenge_catalog.datetime", wraps=datetime),
        ]
        self.clocks = [patcher.start() for patcher in self.patchers]
        for clock in self.clocks:
            clock.now.return_value = NOW
        self.scenario = await self._create_scenario()

    async def asyncTearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        await super().asyncTearDown()

    async def _create_scenario(self):
        user = await User.create(email="rejoin@example.com", hashed_password="unused", name="Rejoin")
        group = await CommonCodeGroup.create(category="CHL", group_code="REJOIN", group_name="Rejoin")
        codes = {
            code: await CommonCode.create(group=group, detail_code=code, detail_name=code)
            for code in ("WALK", "D7", "SELF", "DAILY")
        }
        badge = await Badge.create(name="Rejoin badge", image_path="media/badges/rejoin.png")
        challenge = await Challenge.create(
            name="Walk again",
            phrase="Walk daily",
            challenge_type=codes["WALK"],
            challenge_period=codes["D7"],
            check_type=codes["SELF"],
            check_frequency=codes["DAILY"],
            recruit_start_at=NOW - timedelta(days=1),
            recruit_end_at=NOW + timedelta(days=3),
            reward_badge=badge,
            is_displayed=True,
        )
        return user, challenge, ChallengeParticipationService()

    async def test_rejoin_starts_new_zero_progress_attempt_and_preserves_history(self):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        verification = await service.submit_verification(
            user, first.id, VerificationCreateRequest(verification_date=NOW.date(), idempotency_key="first-attempt-key")
        )
        cancelled = await service.cancel(user, first.id)
        later = NOW + timedelta(days=1, hours=2)
        for clock in self.clocks:
            clock.now.return_value = later
        second = await service.join(user, challenge.id)

        assert second.id != first.id
        assert second.started_at == later
        assert second.end_at == datetime(2026, 9, 17, tzinfo=config.TIMEZONE)
        assert second.status == "ACTIVE"
        assert second.completed_count == 0
        assert second.progress_rate == 0
        assert second.completed_at is None
        assert second.cancelled_at is None
        assert second.verified_dates == []
        assert second.today_verification is None
        assert second.can_verify is True
        assert len(second.progress_periods) == 7
        assert second.progress_periods[0].period_start.isoformat() == "2026-09-10"
        assert second.progress_periods[-1].period_end.isoformat() == "2026-09-16"
        assert all(row.completed_count == 0 and row.progress_rate == 0 for row in second.progress_periods)
        old = await service.get(user, first.id)
        assert old.status == "CANCELLED"
        assert old.cancelled_at == cancelled.cancelled_at
        assert old.completed_count == 1
        assert old.verified_dates == [NOW.date()]
        assert await ChallengeVerification.filter(id=verification.id, user_challenge_id=first.id).exists()
        assert await UserBadge.filter(user_challenge_id=second.id).count() == 0
        assert old.challenge.participation_id == second.id
        assert old.challenge.can_join is False
        assert {row.id for row in await service.list(user)} == {first.id, second.id}

    async def test_cancelled_catalog_allows_rejoin_and_latest_attempt_controls_eligibility(self):
        user, challenge, service = self.scenario
        catalog = ChallengeCatalogService()
        first = await service.join(user, challenge.id)
        await service.cancel(user, first.id)
        for response in [await catalog.get(user.id, challenge.id), (await catalog.list(user.id, 0, 10))[0][0]]:
            assert response.participation_id == first.id
            assert response.can_join is True
        second = await service.join(user, challenge.id)
        for response in [await catalog.get(user.id, challenge.id), (await catalog.list(user.id, 0, 10))[0][0]]:
            assert response.participation_id == second.id
            assert response.can_join is False
        await service.cancel(user, second.id)
        third = await service.join(user, challenge.id)
        assert third.id not in (first.id, second.id)
        with pytest.raises(ChallengeAlreadyJoinedError):
            await service.join(user, challenge.id)

    async def test_non_cancelled_attempt_blocks_join_active(self):
        await self._test_non_cancelled_attempt_blocks_join("ACTIVE")

    async def test_non_cancelled_attempt_blocks_join_completed(self):
        await self._test_non_cancelled_attempt_blocks_join("COMPLETED")

    async def test_non_cancelled_attempt_blocks_join_expired(self):
        await self._test_non_cancelled_attempt_blocks_join("EXPIRED")

    async def test_elapsed_active_attempt_blocks_join_even_when_recruitment_is_open(self):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        await UserChallenge.filter(id=first.id).update(end_at=NOW)
        with pytest.raises(ChallengeAlreadyJoinedError):
            await service.join(user, challenge.id)
        assert (await service.get(user, first.id)).status == "EXPIRED"
        assert (await ChallengeCatalogService().get(user.id, challenge.id)).can_join is False

    async def test_rejoin_obeys_inclusive_recruitment_bounds_start(self):
        await self._test_rejoin_obeys_inclusive_recruitment_bounds("start")

    async def test_rejoin_obeys_inclusive_recruitment_bounds_end(self):
        await self._test_rejoin_obeys_inclusive_recruitment_bounds("end")

    async def test_rejoin_obeys_inclusive_recruitment_bounds_before(self):
        await self._test_rejoin_obeys_inclusive_recruitment_bounds("before")

    async def test_rejoin_obeys_inclusive_recruitment_bounds_after(self):
        await self._test_rejoin_obeys_inclusive_recruitment_bounds("after")

    async def test_same_day_rejoin_has_its_own_verification_and_old_attempt_stays_cancelled(self):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        await service.submit_verification(
            user, first.id, VerificationCreateRequest(verification_date=NOW.date(), idempotency_key="before-cancel-key")
        )
        await service.cancel(user, first.id)
        second = await service.join(user, challenge.id)
        assert second.can_verify is True
        await service.submit_verification(
            user,
            second.id,
            VerificationCreateRequest(verification_date=NOW.date(), idempotency_key="after-rejoin-key1"),
        )
        assert (await service.get(user, second.id)).completed_count == 1
        with pytest.raises(ChallengePeriodEndedError):
            await service.cancel(user, first.id)
        assert (await service.get(user, second.id)).status == "ACTIVE"

    async def test_another_users_attempt_cannot_be_cancelled(self):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        other = await User.create(email="other@example.com", hashed_password="unused", name="Other")
        with pytest.raises(ChallengeNotFoundError):
            await service.cancel(other, first.id)
        assert (await service.get(user, first.id)).status == "ACTIVE"

    async def _test_non_cancelled_attempt_blocks_join(self, status: str):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        await UserChallenge.filter(id=first.id).update(status=ChallengeParticipationStatus(status))
        with pytest.raises(ChallengeAlreadyJoinedError):
            await service.join(user, challenge.id)
        assert (await ChallengeCatalogService().get(user.id, challenge.id)).can_join is False
        assert await UserChallenge.filter(user_id=user.id, challenge_id=challenge.id).count() == 1

    async def _test_rejoin_obeys_inclusive_recruitment_bounds(self, boundary: str):
        user, challenge, service = self.scenario
        first = await service.join(user, challenge.id)
        await service.cancel(user, first.id)
        check_time = {
            "start": challenge.recruit_start_at,
            "end": challenge.recruit_end_at,
            "before": challenge.recruit_start_at - timedelta(microseconds=1),
            "after": challenge.recruit_end_at + timedelta(microseconds=1),
        }[boundary]
        for clock in self.clocks:
            clock.now.return_value = check_time
        catalog = await ChallengeCatalogService().get(user.id, challenge.id)
        assert catalog.can_join is (boundary in ("start", "end"))
        if boundary in ("start", "end"):
            rejoined = await service.join(user, challenge.id)
            assert rejoined.id != first.id
            assert rejoined.started_at == check_time
            assert rejoined.end_at == datetime.combine(check_time.date() + timedelta(days=7), time.min, config.TIMEZONE)
        else:
            with pytest.raises(ChallengeNotRecruitingError):
                await service.join(user, challenge.id)
