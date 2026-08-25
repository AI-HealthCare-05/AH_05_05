from app.models.supplement_nutrients import NutrientStandard


class NutrientStandardRepository:
    async def list(
        self,
        *,
        grp: str | None,
        age: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[NutrientStandard], int]:
        query = NutrientStandard.all()
        if grp is not None:
            query = query.filter(grp=grp)
        if age is not None:
            query = query.filter(age=age)

        total = await query.count()
        items = await query.order_by("id").offset(offset).limit(limit)
        return items, total
