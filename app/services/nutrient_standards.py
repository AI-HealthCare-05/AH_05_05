from app.models.supplement_nutrients import NutrientStandard
from app.repositories.nutrient_standard_repository import NutrientStandardRepository

AGE_RANGES = (
    (2, "1-2세"),
    (5, "3-5세"),
    (8, "6-8세"),
    (11, "9-11세"),
    (14, "12-14세"),
    (18, "15-18세"),
    (29, "19-29세"),
    (49, "30-49세"),
    (64, "50-64세"),
    (74, "65-74세"),
)


def resolve_age_range(age: int) -> str:
    for maximum_age, age_range in AGE_RANGES:
        if age <= maximum_age:
            return age_range
    return "75세 이상"


class NutrientStandardService:
    def __init__(self, repository: NutrientStandardRepository | None = None):
        self.repository = repository or NutrientStandardRepository()

    async def list(
        self,
        *,
        grp: str | None,
        age: int | None,
        offset: int,
        limit: int,
    ) -> tuple[list[NutrientStandard], int]:
        return await self.repository.list(
            grp=grp.strip() if grp else None,
            age=resolve_age_range(age) if age is not None else None,
            offset=offset,
            limit=limit,
        )
