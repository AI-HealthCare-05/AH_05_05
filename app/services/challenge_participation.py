from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import (
    ChallengeAlreadyJoinedError,
    ChallengeNotFoundError,
    ChallengeNotRecruitingError,
    ChallengePeriodEndedError,
    ChallengeVerificationConflictError,
    ChallengeVerificationNotFoundError,
    InvalidChallengeConfigurationError,
    InvalidVerificationDateError,
    VerificationAlreadyReviewedError,
    VerificationEvidenceRequiredError,
    VerificationPeriodNotFoundError,
)
from app.dtos.challenges import (
    ProgressResponse,
    UserBadgeResponse,
    UserChallengeResponse,
    VerificationActionRequest,
    VerificationCreateRequest,
    VerificationResponse,
)
from app.models.challenges import (
    Challenge,
    ChallengeProgress,
    ChallengeVerification,
    UserBadge,
    UserChallenge,
)
from app.models.enums import (
    BadgeAwardStatus,
    ChallengeParticipationStatus,
    ChallengeVerificationStatus,
)
from app.models.users import User
from app.repositories.challenge_participation_repository import ChallengeParticipationRepository
from app.services.challenge_catalog import CATALOG_RELATIONS, ChallengeCatalogService
from app.services.challenge_periods import build_progress_periods


class ChallengeParticipationService:
    def __init__(self) -> None:
        self.repository = ChallengeParticipationRepository()

    async def join(self, user: User, challenge_id: int) -> UserChallengeResponse:
        challenge = await Challenge.get_or_none(
            id=challenge_id,
            is_deleted=False,
            is_displayed=True,
        ).prefetch_related("challenge_period", "check_frequency")
        if challenge is None:
            raise ChallengeNotFoundError()
        now = datetime.now(config.TIMEZONE)
        if not (challenge.recruit_start_at <= now <= challenge.recruit_end_at):
            raise ChallengeNotRecruitingError()
        try:
            periods = build_progress_periods(
                now,
                challenge.challenge_period.detail_code,
                challenge.check_frequency.detail_code,
            )
        except ValueError as error:
            raise InvalidChallengeConfigurationError() from error
        if any(period.target_count > (period.period_end - period.period_start).days + 1 for period in periods):
            raise InvalidChallengeConfigurationError()
        duration_days = int(challenge.challenge_period.detail_code.removeprefix("D"))
        try:
            async with in_transaction() as connection:
                participation = await UserChallenge.create(
                    user_id=user.id,
                    challenge_id=challenge.id,
                    started_at=now,
                    end_at=datetime.combine(
                        now.date() + timedelta(days=duration_days), time.min, tzinfo=config.TIMEZONE
                    ),
                    target_count=sum(period.target_count for period in periods),
                    using_db=connection,
                )
                await ChallengeProgress.bulk_create(
                    [
                        ChallengeProgress(
                            user_challenge_id=participation.id,
                            period_start=period.period_start,
                            period_end=period.period_end,
                            target_count=period.target_count,
                        )
                        for period in periods
                    ],
                    using_db=connection,
                )
        except IntegrityError as error:
            raise ChallengeAlreadyJoinedError() from error
        return await self.get(user, participation.id)

    async def list(self, user: User) -> list[UserChallengeResponse]:
        return [await self._response(item) for item in await self.repository.list_owned(user.id)]

    async def get(self, user: User, participation_id: int) -> UserChallengeResponse:
        participation = await self.repository.get_owned(participation_id, user.id)
        if participation is None:
            raise ChallengeNotFoundError()
        return await self._response(participation)

    async def cancel(self, user: User, participation_id: int) -> UserChallengeResponse:
        async with in_transaction() as connection:
            participation = (
                await UserChallenge.filter(id=participation_id, user_id=user.id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if participation is None:
                raise ChallengeNotFoundError()
            now = datetime.now(config.TIMEZONE)
            if self._effective_status(participation, now) != ChallengeParticipationStatus.ACTIVE:
                raise ChallengePeriodEndedError()
            participation.status = ChallengeParticipationStatus.CANCELLED
            participation.cancelled_at = now
            await participation.save(using_db=connection)
        return await self._response(participation)

    async def submit_verification(
        self,
        user: User,
        participation_id: int,
        data: VerificationCreateRequest,
    ) -> VerificationResponse:
        try:
            async with in_transaction() as connection:
                participation = (
                    await UserChallenge.filter(id=participation_id, user_id=user.id)
                    .using_db(connection)
                    .select_for_update()
                    .first()
                )
                if participation is None:
                    raise ChallengeNotFoundError()
                return await self._submit_locked(participation, data)
        except IntegrityError as error:
            # Includes a global idempotency key used concurrently on another participation.
            raise ChallengeVerificationConflictError() from error

    async def _submit_locked(
        self,
        participation: UserChallenge,
        data: VerificationCreateRequest,
    ) -> VerificationResponse:
        existing = await ChallengeVerification.get_or_none(idempotency_key=data.idempotency_key)
        if existing is not None:
            if existing.user_challenge_id != participation.id:
                raise ChallengeVerificationNotFoundError()
            if existing.verification_date != data.verification_date:
                raise ChallengeVerificationConflictError()
            return self.verification_response(existing)
        now = datetime.now(config.TIMEZONE)
        await participation.fetch_related("challenge__check_type")
        if participation.challenge.check_type.detail_code == "SELF" and data.verification_date != now.date():
            raise InvalidVerificationDateError()
        same_day = await ChallengeVerification.get_or_none(
            user_challenge_id=participation.id, verification_date=data.verification_date
        )
        if same_day is not None:
            return self.verification_response(same_day)
        return await self._create_verification(participation, data, now)

    async def _create_verification(
        self,
        participation: UserChallenge,
        data: VerificationCreateRequest,
        now: datetime,
    ) -> VerificationResponse:
        if (
            self._effective_status(participation, now) != ChallengeParticipationStatus.ACTIVE
            or now < participation.started_at
        ):
            raise ChallengePeriodEndedError()
        progress = await ChallengeProgress.get_or_none(
            user_challenge_id=participation.id,
            period_start__lte=data.verification_date,
            period_end__gte=data.verification_date,
        )
        if progress is None:
            raise VerificationPeriodNotFoundError()
        if progress.is_completed:
            raise ChallengeVerificationConflictError()
        is_self = participation.challenge.check_type.detail_code == "SELF"
        if not is_self and not (data.content or "").strip() and not data.image_path:
            raise VerificationEvidenceRequiredError()
        verification = await ChallengeVerification.create(
            user_challenge_id=participation.id,
            progress_id=progress.id,
            status=(ChallengeVerificationStatus.APPROVED if is_self else ChallengeVerificationStatus.PENDING),
            reviewed_at=now if is_self else None,
            **data.model_dump(),
        )
        if is_self:
            await self._recalculate(participation.id, progress.id)
        return self.verification_response(verification)

    async def review_verification(
        self,
        verification_id: int,
        data: VerificationActionRequest,
        admin_id: int,
    ) -> VerificationResponse:
        candidate = await ChallengeVerification.get_or_none(id=verification_id)
        if candidate is None:
            raise ChallengeVerificationNotFoundError()
        async with in_transaction() as connection:
            # Serialize reviews with submit/cancel: participation must be locked first.
            # Keep the lookup above outside this transaction so a waiting review does not
            # retain an older REPEATABLE READ snapshot for its progress aggregation.
            await UserChallenge.filter(id=candidate.user_challenge_id).using_db(connection).select_for_update().get()
            verification = (
                await ChallengeVerification.filter(id=verification_id).using_db(connection).select_for_update().first()
            )
            if verification is None:
                raise ChallengeVerificationNotFoundError()
            if verification.status != ChallengeVerificationStatus.PENDING:
                raise VerificationAlreadyReviewedError()
            verification.status = (
                ChallengeVerificationStatus.APPROVED
                if data.action == "APPROVE"
                else ChallengeVerificationStatus.REJECTED
            )
            verification.rejection_reason = (
                data.rejection_reason.strip() if data.action == "REJECT" and data.rejection_reason else None
            )
            verification.reviewed_by_admin_id = admin_id
            verification.reviewed_at = datetime.now(config.TIMEZONE)
            await verification.save(using_db=connection)
            if verification.status == ChallengeVerificationStatus.APPROVED:
                await self._recalculate(verification.user_challenge_id, verification.progress_id)
        return self.verification_response(verification)

    async def list_verifications(
        self,
        *,
        status: ChallengeVerificationStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[VerificationResponse], int]:
        query = ChallengeVerification.all()
        if status is not None:
            query = query.filter(status=status)
        total = await query.count()
        rows = await query.order_by("submitted_at", "id").offset(offset).limit(limit)
        return [self.verification_response(row) for row in rows], total

    async def list_badges(self, user: User) -> list[UserBadgeResponse]:
        return [UserBadgeResponse.model_validate(item) for item in await self.repository.list_badges(user.id)]

    async def _recalculate(self, participation_id: int, progress_id: int) -> None:
        async with in_transaction() as connection:
            participation = (
                await UserChallenge.filter(id=participation_id).using_db(connection).select_for_update().get()
            )
            progress = await ChallengeProgress.filter(id=progress_id).using_db(connection).select_for_update().get()
            approved_count = (
                await ChallengeVerification.filter(
                    progress_id=progress.id,
                    status=ChallengeVerificationStatus.APPROVED,
                )
                .using_db(connection)
                .count()
            )
            progress.completed_count = min(approved_count, progress.target_count)
            progress.progress_rate = self._rate(approved_count, progress.target_count)
            progress.is_completed = approved_count >= progress.target_count
            if progress.is_completed and progress.completed_at is None:
                progress.completed_at = datetime.now(config.TIMEZONE)
            await progress.save(using_db=connection)

            progress_rows = await ChallengeProgress.filter(user_challenge_id=participation.id).using_db(connection)
            participation.completed_count = sum(row.completed_count for row in progress_rows)
            participation.progress_rate = self._rate(
                participation.completed_count,
                participation.target_count,
            )
            if (
                participation.status == ChallengeParticipationStatus.ACTIVE
                and progress_rows
                and all(row.is_completed for row in progress_rows)
            ):
                participation.status = ChallengeParticipationStatus.COMPLETED
                participation.completed_at = datetime.now(config.TIMEZONE)
            await participation.save(using_db=connection)

            if participation.status == ChallengeParticipationStatus.COMPLETED:
                challenge = await Challenge.get(id=participation.challenge_id).using_db(connection)
                if challenge.reward_badge_id is not None:
                    await challenge.fetch_related("reward_badge", using_db=connection)
                    badge = challenge.reward_badge
                    if badge.is_active:
                        await UserBadge.get_or_create(
                            user_challenge_id=participation.id,
                            badge_id=badge.id,
                            defaults={
                                "user_id": participation.user_id,
                                "challenge_id": challenge.id,
                                "status": BadgeAwardStatus.AWARDED,
                                "badge_name": badge.name,
                                "badge_image_path": badge.image_path,
                            },
                            using_db=connection,
                        )

    async def _response(self, participation: UserChallenge) -> UserChallengeResponse:
        await participation.fetch_related(*[f"challenge__{relation}" for relation in CATALOG_RELATIONS])
        progress_rows = await ChallengeProgress.filter(user_challenge_id=participation.id).order_by("period_start")
        now = datetime.now(config.TIMEZONE)
        today = now.date()
        status = self._effective_status(participation, now)
        verifications = await ChallengeVerification.filter(user_challenge_id=participation.id).order_by(
            "verification_date"
        )
        today_verification = next((row for row in verifications if row.verification_date == today), None)
        today_progress = next((row for row in progress_rows if row.period_start <= today <= row.period_end), None)
        return UserChallengeResponse(
            id=participation.id,
            user_id=participation.user_id,
            challenge_id=participation.challenge_id,
            challenge_name=participation.challenge.name,
            status=status,
            joined_at=participation.joined_at,
            started_at=participation.started_at,
            end_at=participation.end_at,
            target_count=participation.target_count,
            completed_count=participation.completed_count,
            progress_rate=participation.progress_rate,
            completed_at=participation.completed_at,
            cancelled_at=participation.cancelled_at,
            progress_periods=[ProgressResponse.model_validate(row) for row in progress_rows],
            challenge=ChallengeCatalogService.response(participation.challenge, participation.id, now),
            today=today,
            today_verification=self.verification_response(today_verification) if today_verification else None,
            can_verify=bool(
                status == ChallengeParticipationStatus.ACTIVE
                and now >= participation.started_at
                and participation.challenge.check_type.detail_code == "SELF"
                and today_verification is None
                and today_progress is not None
                and not today_progress.is_completed
            ),
            verified_dates=[
                row.verification_date for row in verifications if row.status == ChallengeVerificationStatus.APPROVED
            ],
        )

    @staticmethod
    def _effective_status(participation: UserChallenge, now: datetime) -> ChallengeParticipationStatus:
        if participation.status == ChallengeParticipationStatus.ACTIVE and now >= participation.end_at:
            return ChallengeParticipationStatus.EXPIRED
        return participation.status

    @staticmethod
    def _rate(completed: int, target: int) -> Decimal:
        if target <= 0:
            return Decimal("0.00")
        return min(
            Decimal("100.00"),
            (Decimal(completed) * Decimal(100) / Decimal(target)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
        )

    @staticmethod
    def verification_response(verification: ChallengeVerification) -> VerificationResponse:
        return VerificationResponse.model_validate(verification)
