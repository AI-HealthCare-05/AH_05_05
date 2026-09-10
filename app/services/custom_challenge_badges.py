from datetime import datetime

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.custom_challenges import (
    CustomChallengeBadgeAwardListResponse,
    CustomChallengeBadgeAwardResponse,
)
from app.models.challenges import Badge
from app.models.custom_challenges import CustomChallengeBadgeAward, CustomChallengeParticipation
from app.models.enums import ChallengeParticipationStatus
from app.models.users import User


class CustomChallengeBadgeService:
    async def award_for_completed_participation(
        self,
        participation: CustomChallengeParticipation,
        *,
        using_db: BaseDBAsyncClient,
    ) -> CustomChallengeBadgeAward | None:
        award, _ = await self.award_for_completed_participation_with_status(
            participation,
            using_db=using_db,
        )
        return award

    async def award_for_completed_participation_with_status(
        self,
        participation: CustomChallengeParticipation,
        *,
        using_db: BaseDBAsyncClient,
    ) -> tuple[CustomChallengeBadgeAward | None, bool]:
        locked_participation = await (
            CustomChallengeParticipation.filter(id=participation.id)
            .using_db(using_db)
            .select_for_update()
            .first()
        )
        if locked_participation is None:
            return None, False
        participation = locked_participation
        if (
            participation.status is not ChallengeParticipationStatus.COMPLETED
            or participation.reward_badge_id is None
        ):
            return None, False

        existing = await (
            CustomChallengeBadgeAward.filter(
                participation_id=participation.id,
                badge_id=participation.reward_badge_id,
            )
            .using_db(using_db)
            .first()
        )
        if existing is not None:
            return existing, False

        badge = await Badge.filter(id=participation.reward_badge_id, is_active=True).using_db(using_db).first()
        if badge is None:
            return None, False
        try:
            award, created = await CustomChallengeBadgeAward.get_or_create(
                participation_id=participation.id,
                badge_id=badge.id,
                defaults={
                    "user_id": participation.user_id,
                    "badge_name": badge.name,
                    "badge_image_path": badge.image_path,
                },
                using_db=using_db,
            )
            return award, created
        except IntegrityError:
            award = await (
                CustomChallengeBadgeAward.filter(
                    participation_id=participation.id,
                    badge_id=badge.id,
                )
                .using_db(using_db)
                .get()
            )
            return award, False

    async def list_for_user(self, user_id: int) -> CustomChallengeBadgeAwardListResponse:
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user_id).using_db(connection).select_for_update().first()
            if locked_user is not None:
                from app.services.custom_challenge_lifecycle import CustomChallengeLifecycleService

                await CustomChallengeLifecycleService().finalize_due_for_user(
                    user_id=user_id,
                    now=datetime.now(config.TIMEZONE),
                    connection=connection,
                )
        awards = await CustomChallengeBadgeAward.filter(user_id=user_id).order_by("-awarded_at", "-id")
        return CustomChallengeBadgeAwardListResponse(
            items=[self.response(award) for award in awards],
            total_count=len(awards),
        )

    async def get_for_participation(
        self,
        user_id: int,
        participation_id: int,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> CustomChallengeBadgeAward | None:
        query = CustomChallengeBadgeAward.filter(
            user_id=user_id,
            participation_id=participation_id,
        )
        if using_db is not None:
            query = query.using_db(using_db)
        return await query.first()

    @staticmethod
    def response(award: CustomChallengeBadgeAward) -> CustomChallengeBadgeAwardResponse:
        return CustomChallengeBadgeAwardResponse(
            id=award.id,
            participation_id=award.participation_id,
            badge_id=award.badge_id,
            badge_name=award.badge_name,
            badge_image_path=award.badge_image_path,
            awarded_at=award.awarded_at,
        )
