from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status

from app.core import config
from app.dtos.follow_up_visits import (
    FollowUpVisitCreateRequest,
    FollowUpVisitListResponse,
    FollowUpVisitResponse,
    FollowUpVisitUpdateRequest,
)
from app.models.care import FollowUpVisit
from app.models.users import User
from app.repositories.follow_up_visit_repository import FollowUpVisitRepository


class FollowUpVisitService:
    def __init__(self, repository: FollowUpVisitRepository | None = None):
        self.repository = repository or FollowUpVisitRepository()

    async def create(self, user: User, data: FollowUpVisitCreateRequest) -> FollowUpVisitResponse:
        visit = await self.repository.create(user.id, **data.model_dump())
        return self._to_response(visit)

    async def list(
        self,
        user: User,
        *,
        start_date: date | None,
        end_date: date | None,
        offset: int,
        limit: int,
    ) -> FollowUpVisitListResponse:
        if start_date is not None and end_date is not None and end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="end_date must be on or after start_date.",
            )
        visits, total = await self.repository.list_owned(
            user.id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=limit,
        )
        return FollowUpVisitListResponse(
            items=[self._to_response(visit) for visit in visits],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get(self, user: User, visit_id: int) -> FollowUpVisitResponse:
        return self._to_response(await self._get_owned(user.id, visit_id))

    async def update(
        self,
        user: User,
        visit_id: int,
        data: FollowUpVisitUpdateRequest,
    ) -> FollowUpVisitResponse:
        visit = await self._get_owned(user.id, visit_id)
        updates = data.model_dump(exclude_unset=True)
        if "visit_date" in updates and updates["visit_date"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="visit_date cannot be null.",
            )
        if updates:
            for field_name, value in updates.items():
                setattr(visit, field_name, value)
            visit.updated_at = datetime.now(config.TIMEZONE)
            await visit.save(update_fields=[*updates, "updated_at"])
        return self._to_response(visit)

    async def delete(self, user: User, visit_id: int) -> None:
        await self.repository.delete(await self._get_owned(user.id, visit_id))

    async def _get_owned(self, user_id: int, visit_id: int) -> FollowUpVisit:
        visit = await self.repository.get_owned(visit_id, user_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up visit not found.")
        return visit

    @staticmethod
    def _to_response(visit: FollowUpVisit) -> FollowUpVisitResponse:
        visit_time = visit.visit_time
        if isinstance(visit_time, timedelta):
            seconds = int(visit_time.total_seconds()) % (24 * 60 * 60)
            hour, remainder = divmod(seconds, 60 * 60)
            minute, second = divmod(remainder, 60)
            visit_time = time(hour=hour, minute=minute, second=second)
        return FollowUpVisitResponse(
            id=visit.id,
            user_id=visit.user_id,
            visit_date=visit.visit_date,
            visit_time=visit_time,
            hospital=visit.hospital,
            created_at=visit.created_at,
            updated_at=visit.updated_at,
        )
