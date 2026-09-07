from datetime import date, datetime, time, timedelta

from app.core import config
from app.models.challenges import Challenge


class ChallengeRepository:
    async def get(self, challenge_id: int, *, include_deleted: bool = False) -> Challenge | None:
        query = Challenge.filter(id=challenge_id)
        if not include_deleted:
            query = query.filter(is_deleted=False)
        return await query.first()

    async def list(
        self,
        *,
        name: str | None = None,
        challenge_type_id: int | None = None,
        is_displayed: bool | None = None,
        recruit_start_date: date | None = None,
        recruit_end_date: date | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[Challenge], int]:
        query = Challenge.filter(is_deleted=False)
        if name:
            query = query.filter(name__icontains=name.strip())
        if challenge_type_id is not None:
            query = query.filter(challenge_type_id=challenge_type_id)
        if is_displayed is not None:
            query = query.filter(is_displayed=is_displayed)
        if recruit_start_date is not None:
            range_start = datetime.combine(recruit_start_date, time.min, tzinfo=config.TIMEZONE)
            query = query.filter(recruit_end_at__gte=range_start)
        if recruit_end_date is not None:
            range_end = datetime.combine(
                recruit_end_date + timedelta(days=1),
                time.min,
                tzinfo=config.TIMEZONE,
            )
            query = query.filter(recruit_start_at__lt=range_end)
        return list(await query.order_by("-created_at").offset(offset).limit(limit)), await query.count()
