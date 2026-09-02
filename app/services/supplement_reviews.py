from decimal import Decimal

from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError

from app.core.validators.user_validators import mask_name
from app.dtos.supplement_reviews import SupplementReviewListResponse, SupplementReviewResponse
from app.models.enums import AccountStatus
from app.models.users import User
from app.repositories.supplement_review_repository import SupplementReviewRepository


class SupplementReviewService:
    def __init__(self, repository: SupplementReviewRepository | None = None) -> None:
        self.repository = repository or SupplementReviewRepository()

    async def list(
        self,
        user: User,
        product_id: int,
        *,
        offset: int,
        limit: int,
    ) -> SupplementReviewListResponse:
        result = await self.repository.list_public(product_id, offset=offset, limit=limit)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplement nutrient not found.")

        registrations, total, rating_average, review_count = result
        registration_ids = [registration.id for registration in registrations]
        reported_ids = await self.repository.list_reported_registration_ids(user.id, registration_ids)
        rounded_average = Decimal(str(rating_average)).quantize(Decimal("0.1")) if rating_average is not None else None
        return SupplementReviewListResponse(
            items=[
                SupplementReviewResponse(
                    id=registration.id,
                    author_label=mask_name(registration.user.name),
                    score=registration.score,
                    review_body=registration.review_body,
                    updated_at=registration.updated_at,
                    is_mine=registration.user_id == user.id,
                    reported_by_me=registration.id in reported_ids,
                )
                for registration in registrations
            ],
            total=total,
            offset=offset,
            limit=limit,
            rating_average=rounded_average,
            review_count=review_count,
        )

    async def report(self, user: User, registration_id: int) -> None:
        registration = await self.repository.get_registration(registration_id)
        if registration is None:
            self._raise_not_found()

        if await self.repository.has_reported(user.id, registration_id):
            return

        is_public = (
            registration.supplement_nutrient_id is not None
            and (registration.score is not None or registration.review_body is not None)
            and registration.user.status == AccountStatus.ACTIVE
            and await self.repository.report_count(registration_id) < 3
        )
        if not is_public:
            self._raise_not_found()
        if registration.user_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 후기는 신고할 수 없습니다",
            )

        try:
            await self.repository.create_report(user.id, registration_id)
        except IntegrityError:
            if not await self.repository.has_reported(user.id, registration_id):
                raise

    @staticmethod
    def _raise_not_found() -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplement review not found.")
