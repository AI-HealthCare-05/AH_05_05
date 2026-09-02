from datetime import datetime

from fastapi import HTTPException, status

from app.core import config
from app.models.supplement_nutrients import SupplementNutrient
from app.repositories.supplement_nutrient_repository import (
    SupplementNutrientRepository,
    SupplementSort,
)


class SupplementNutrientService:
    def __init__(self, repository: SupplementNutrientRepository | None = None):
        self.repository = repository or SupplementNutrientRepository()

    async def search(
        self,
        name: str,
        *,
        sort: SupplementSort = "name",
        offset: int,
        limit: int,
    ) -> tuple[list[SupplementNutrient], int]:
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="name must not be blank.",
            )
        return await self.repository.search(normalized_name, sort=sort, offset=offset, limit=limit)

    async def get(self, supplement_nutrient_id: int) -> SupplementNutrient:
        product = await self.repository.get(supplement_nutrient_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplement nutrient not found.",
            )
        return product

    async def list_popular(self, *, limit: int = 5) -> list[SupplementNutrient]:
        return await self.repository.list_popular(datetime.now(config.TIMEZONE).date(), limit=limit)
