from datetime import date
from typing import Any

from tortoise.expressions import Q
from tortoise.functions import Count

from app.models.enums import SupplementStatus
from app.models.supplement_nutrients import SupplementNutrient, UserSupplementNutrient


class SupplementNutrientRepository:
    async def search(
        self,
        name: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[SupplementNutrient], int]:
        query = SupplementNutrient.filter(name__icontains=name)
        total = await query.count()
        items = await query.order_by("name", "id").offset(offset).limit(limit)
        return items, total

    async def get(self, supplement_nutrient_id: int) -> SupplementNutrient | None:
        return await SupplementNutrient.get_or_none(id=supplement_nutrient_id)

    async def list_popular(self, as_of: date, *, limit: int = 5) -> list[SupplementNutrient]:
        rows: list[dict[str, Any]] = (
            await UserSupplementNutrient.filter(
                status=SupplementStatus.ACTIVE,
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
