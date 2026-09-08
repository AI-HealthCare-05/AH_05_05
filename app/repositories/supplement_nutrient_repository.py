from datetime import date
from typing import Any, Literal

from tortoise.expressions import Q
from tortoise.functions import Avg, Count

from app.models.enums import SupplementStatus
from app.models.supplement_nutrients import SupplementNutrient, UserSupplementNutrient
from app.repositories.supplement_review_repository import SupplementReviewRepository

SupplementSort = Literal["name", "registered", "rating", "reviews"]
SupplementSortDirection = Literal["asc", "desc"]

_DEFAULT_DIRECTIONS: dict[SupplementSort, SupplementSortDirection] = {
    "name": "asc",
    "registered": "desc",
    "rating": "desc",
    "reviews": "desc",
}
_SORT_FIELDS: dict[SupplementSort, tuple[str, ...]] = {
    "name": ("name",),
    "registered": ("registration_count",),
    "rating": ("rating_average", "review_count"),
    "reviews": ("review_count", "rating_average"),
}


class SupplementNutrientRepository:
    def __init__(self, review_repository: SupplementReviewRepository | None = None) -> None:
        self.review_repository = review_repository or SupplementReviewRepository()

    async def search(
        self,
        name: str,
        *,
        sort: SupplementSort,
        direction: SupplementSortDirection | None = None,
        offset: int,
        limit: int,
    ) -> tuple[list[SupplementNutrient], int]:
        query = SupplementNutrient.filter(name__icontains=name)
        total = await query.count()
        excluded_ids = await self.review_repository.list_excluded_registration_ids()
        review_filter = Q(user_registrations__score__isnull=False)
        if excluded_ids:
            review_filter &= ~Q(user_registrations__id__in=excluded_ids)
        active_registration_filter = Q(user_registrations__status=SupplementStatus.ACTIVE)
        annotated = query.annotate(
            rating_average=Avg("user_registrations__score", _filter=review_filter),
            review_count=Count("user_registrations", _filter=review_filter),
            registration_count=Count(
                "user_registrations",
                _filter=active_registration_filter,
            ),
        )
        resolved_direction = direction or _DEFAULT_DIRECTIONS[sort]
        prefix = "-" if resolved_direction == "desc" else ""
        orderings = tuple(f"{prefix}{field}" for field in _SORT_FIELDS[sort]) + ("id",)
        items = await annotated.order_by(*orderings).offset(offset).limit(limit)
        return items, total

    async def get(self, supplement_nutrient_id: int) -> SupplementNutrient | None:
        return await SupplementNutrient.get_or_none(id=supplement_nutrient_id)

    async def list_popular(self, as_of: date, *, limit: int = 5) -> list[SupplementNutrient]:
        rows: list[dict[str, Any]] = (
            await UserSupplementNutrient.filter(
                status=SupplementStatus.ACTIVE,
                supplement_nutrient_id__isnull=False,
                start_date__lte=as_of,
            )
            .filter(Q(end_date=None) | Q(end_date__gte=as_of))
            .annotate(usage_count=Count("id"))
            .group_by("supplement_nutrient_id")
            .order_by("-usage_count", "supplement_nutrient_id")
            .limit(limit)
            .values("supplement_nutrient_id", "usage_count")
        )
        product_ids = [row["supplement_nutrient_id"] for row in rows]
        if not product_ids:
            return []

        products = await SupplementNutrient.filter(id__in=product_ids)
        products_by_id = {product.id: product for product in products}
        return [products_by_id[product_id] for product_id in product_ids if product_id in products_by_id]
