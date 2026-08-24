from app.models.supplement_nutrients import SupplementNutrient


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
