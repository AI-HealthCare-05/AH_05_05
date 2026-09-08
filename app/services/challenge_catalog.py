from datetime import datetime

from app.core import config
from app.core.exceptions import ChallengeNotFoundError
from app.dtos.challenges import CatalogBadgeResponse, ChallengeCatalogResponse
from app.models.challenges import Challenge, UserChallenge
from app.services.challenge_periods import build_progress_periods

CATALOG_RELATIONS = ("challenge_type", "challenge_period", "check_type", "check_frequency", "reward_badge")


class ChallengeCatalogService:
    async def list(self, user_id: int, offset: int, limit: int) -> tuple[list[ChallengeCatalogResponse], int]:
        query = Challenge.filter(is_displayed=True, is_deleted=False)
        total = await query.count()
        rows = await query.order_by("-id").offset(offset).limit(limit).prefetch_related(*CATALOG_RELATIONS)
        owned = await UserChallenge.filter(user_id=user_id, challenge_id__in=[row.id for row in rows])
        participation_ids = {item.challenge_id: item.id for item in owned}
        now = datetime.now(config.TIMEZONE)
        return [self.response(row, participation_ids.get(row.id), now) for row in rows], total

    async def get(self, user_id: int, challenge_id: int) -> ChallengeCatalogResponse:
        row = await Challenge.get_or_none(id=challenge_id, is_displayed=True, is_deleted=False).prefetch_related(
            *CATALOG_RELATIONS
        )
        if row is None:
            raise ChallengeNotFoundError()
        owned = await UserChallenge.get_or_none(user_id=user_id, challenge_id=challenge_id)
        return self.response(row, owned.id if owned else None, datetime.now(config.TIMEZONE))

    @staticmethod
    def response(challenge: Challenge, participation_id: int | None, now: datetime) -> ChallengeCatalogResponse:
        period_code = challenge.challenge_period.detail_code
        duration = {"D7": 7, "D14": 14, "D30": 30}.get(period_code, 0)
        frequency = challenge.check_frequency.detail_code
        try:
            periods = build_progress_periods(now, period_code, frequency)
            supported = all(
                period.target_count <= (period.period_end - period.period_start).days + 1 for period in periods
            )
        except ValueError:
            supported = False
        badge = challenge.reward_badge
        return ChallengeCatalogResponse(
            id=challenge.id,
            name=challenge.name,
            phrase=challenge.phrase,
            description=challenge.description,
            challenge_type_code=challenge.challenge_type.detail_code,
            period_code=period_code,
            duration_days=duration,
            frequency_code=frequency,
            check_type_code=challenge.check_type.detail_code,
            recruit_start_at=challenge.recruit_start_at,
            recruit_end_at=challenge.recruit_end_at,
            reward_badge=CatalogBadgeResponse.model_validate(badge) if badge and badge.is_active else None,
            participation_id=participation_id,
            can_join=bool(
                supported
                and participation_id is None
                and challenge.is_displayed
                and not challenge.is_deleted
                and challenge.recruit_start_at <= now <= challenge.recruit_end_at
            ),
        )
