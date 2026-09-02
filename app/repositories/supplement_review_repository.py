from decimal import Decimal

from tortoise.expressions import Q
from tortoise.functions import Avg, Count

from app.models.enums import AccountStatus
from app.models.supplement_nutrients import (
    SupplementNutrient,
    SupplementReviewReport,
    UserSupplementNutrient,
)


class SupplementReviewRepository:
    async def list_hidden_registration_ids(self) -> list[int]:
        rows = (
            await SupplementReviewReport.all()
            .annotate(report_count=Count("id"))
            .group_by("registration_id")
            .filter(report_count__gte=3)
            .values_list("registration_id", flat=True)
        )
        return list(rows)

    async def list_inactive_owner_registration_ids(self) -> list[int]:
        rows = await UserSupplementNutrient.exclude(user__status=AccountStatus.ACTIVE).values_list("id", flat=True)
        return list(rows)

    async def list_excluded_registration_ids(self) -> list[int]:
        hidden_ids = await self.list_hidden_registration_ids()
        inactive_ids = await self.list_inactive_owner_registration_ids()
        return list(dict.fromkeys(hidden_ids + inactive_ids))

    async def list_public(
        self,
        product_id: int,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[UserSupplementNutrient], int, Decimal | None, int] | None:
        if not await SupplementNutrient.exists(id=product_id):
            return None

        excluded_ids = await self.list_excluded_registration_ids()
        display_filter = Q(score__isnull=False) | Q(review_body__isnull=False)
        query = UserSupplementNutrient.filter(
            display_filter,
            supplement_nutrient_id=product_id,
        )
        if excluded_ids:
            query = query.exclude(id__in=excluded_ids)

        total = await query.count()
        items = await query.select_related("user").order_by("-id").offset(offset).limit(limit)

        rating_filter = Q(user_registrations__score__isnull=False)
        if excluded_ids:
            rating_filter &= ~Q(user_registrations__id__in=excluded_ids)
        summary = (
            await SupplementNutrient.filter(id=product_id)
            .annotate(
                rating_average=Avg("user_registrations__score", _filter=rating_filter),
                review_count=Count("user_registrations", _filter=rating_filter),
            )
            .first()
        )
        return items, total, summary.rating_average, summary.review_count

    async def list_reported_registration_ids(self, user_id: int, registration_ids: list[int]) -> set[int]:
        if not registration_ids:
            return set()
        rows = await SupplementReviewReport.filter(
            user_id=user_id,
            registration_id__in=registration_ids,
        ).values_list("registration_id", flat=True)
        return set(rows)

    async def get_registration(self, registration_id: int) -> UserSupplementNutrient | None:
        return await UserSupplementNutrient.filter(id=registration_id).select_related("user").first()

    async def report_count(self, registration_id: int) -> int:
        return await SupplementReviewReport.filter(registration_id=registration_id).count()

    async def has_reported(self, user_id: int, registration_id: int) -> bool:
        return await SupplementReviewReport.exists(user_id=user_id, registration_id=registration_id)

    async def create_report(self, user_id: int, registration_id: int) -> None:
        await SupplementReviewReport.create(user_id=user_id, registration_id=registration_id)
