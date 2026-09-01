from datetime import date

from app.models.care import FollowUpVisit


class FollowUpVisitRepository:
    async def create(self, user_id: int, **values: object) -> FollowUpVisit:
        return await FollowUpVisit.create(user_id=user_id, **values)

    async def get_owned(self, visit_id: int, user_id: int) -> FollowUpVisit | None:
        return await FollowUpVisit.get_or_none(id=visit_id, user_id=user_id)

    async def list_owned(
        self,
        user_id: int,
        *,
        start_date: date | None,
        end_date: date | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FollowUpVisit], int]:
        query = FollowUpVisit.filter(user_id=user_id)
        if start_date is not None:
            query = query.filter(visit_date__gte=start_date)
        if end_date is not None:
            query = query.filter(visit_date__lte=end_date)
        total = await query.count()
        items = await query.order_by("visit_date", "visit_time", "id").offset(offset).limit(limit)
        return list(items), total

    async def delete(self, visit: FollowUpVisit) -> None:
        await visit.delete()
