from datetime import datetime

from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import (
    SupplementNutrientNotFoundError,
    SupplementRankDisplayNotFoundError,
    SupplementRankPeriodConflictError,
)
from app.dtos.supplement_rank_displays import (
    SupplementRankDisplayListItem,
    SupplementRankDisplayListQuery,
    SupplementRankDisplayListResponse,
    SupplementRankDisplayResponse,
    SupplementRankDisplayWriteRequest,
    SupplementRankItemResponse,
)
from app.models.supplement_nutrients import DisplaySupplementNutrientRank
from app.repositories.supplement_rank_display_repository import SupplementRankDisplayRepository


class SupplementRankDisplayService:
    def __init__(self, repository: SupplementRankDisplayRepository | None = None):
        self.repository = repository or SupplementRankDisplayRepository()

    async def list(
        self,
        query: SupplementRankDisplayListQuery,
    ) -> SupplementRankDisplayListResponse:
        offset = (query.page - 1) * query.size
        displays, total = await self.repository.list(
            is_enabled=query.is_enabled,
            offset=offset,
            limit=query.size,
        )
        return SupplementRankDisplayListResponse(
            total_count=total,
            page=query.page,
            size=query.size,
            items=[
                SupplementRankDisplayListItem(
                    display_id=display.id,
                    title=display.title,
                    start_at=display.start_at,
                    end_at=display.end_at,
                    is_enabled=display.is_enabled,
                    item_count=display.item_count,
                    created_at=display.created_at,
                )
                for display in displays
            ],
        )

    async def get(self, display_id: int) -> SupplementRankDisplayResponse:
        display = await self.repository.get(display_id)
        if display is None:
            raise SupplementRankDisplayNotFoundError()
        return self._to_response(display)

    async def current(self) -> SupplementRankDisplayResponse:
        display = await self.repository.get_current(datetime.now(config.TIMEZONE))
        if display is None:
            raise SupplementRankDisplayNotFoundError()
        return self._to_response(display)

    async def create(
        self,
        data: SupplementRankDisplayWriteRequest,
        *,
        actor_admin_id: int,
    ) -> SupplementRankDisplayResponse:
        await self._validate_products(data)
        async with in_transaction() as connection:
            if data.is_enabled and await self.repository.has_enabled_overlap(
                data.start_at,
                data.end_at,
                connection=connection,
            ):
                raise SupplementRankPeriodConflictError()
            display = await DisplaySupplementNutrientRank.create(
                title=data.title,
                start_at=data.start_at,
                end_at=data.end_at,
                is_enabled=data.is_enabled,
                created_by_admin_id=actor_admin_id,
                using_db=connection,
            )
            await self.repository.replace_items(
                display.id,
                [(item.supplement_nutrient_id, item.rank_no) for item in data.items],
                connection,
            )
        return await self.get(display.id)

    async def update(
        self,
        display_id: int,
        data: SupplementRankDisplayWriteRequest,
    ) -> SupplementRankDisplayResponse:
        await self._validate_products(data)
        async with in_transaction() as connection:
            display = await self.repository.get_for_update(display_id, connection)
            if display is None:
                raise SupplementRankDisplayNotFoundError()
            if data.is_enabled and await self.repository.has_enabled_overlap(
                data.start_at,
                data.end_at,
                exclude_display_id=display_id,
                connection=connection,
            ):
                raise SupplementRankPeriodConflictError()
            display.title = data.title
            display.start_at = data.start_at
            display.end_at = data.end_at
            display.is_enabled = data.is_enabled
            display.updated_at = datetime.now(config.TIMEZONE)
            await display.save(
                using_db=connection,
                update_fields=["title", "start_at", "end_at", "is_enabled", "updated_at"],
            )
            await self.repository.replace_items(
                display.id,
                [(item.supplement_nutrient_id, item.rank_no) for item in data.items],
                connection,
            )
        return await self.get(display_id)

    async def delete(self, display_id: int) -> None:
        deleted_count = await DisplaySupplementNutrientRank.filter(id=display_id).delete()
        if deleted_count == 0:
            raise SupplementRankDisplayNotFoundError()

    async def _validate_products(self, data: SupplementRankDisplayWriteRequest) -> None:
        requested_ids = [item.supplement_nutrient_id for item in data.items]
        products = await self.repository.get_products(requested_ids)
        if {product.id for product in products} != set(requested_ids):
            raise SupplementNutrientNotFoundError()

    @staticmethod
    def _to_response(display: DisplaySupplementNutrientRank) -> SupplementRankDisplayResponse:
        ordered_items = sorted(display.items, key=lambda item: item.rank_no)
        return SupplementRankDisplayResponse(
            display_id=display.id,
            title=display.title,
            start_at=display.start_at,
            end_at=display.end_at,
            is_enabled=display.is_enabled,
            created_by_admin_id=display.created_by_admin_id,
            created_at=display.created_at,
            updated_at=display.updated_at,
            items=[
                SupplementRankItemResponse(
                    supplement_nutrient_id=item.supplement_nutrient_id,
                    name=item.supplement_nutrient.name,
                    rank_no=item.rank_no,
                )
                for item in ordered_items
            ],
        )
