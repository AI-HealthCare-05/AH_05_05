from __future__ import annotations

from datetime import datetime

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.functions import Count

from app.models.supplement_nutrients import (
    DisplaySupplementNutrientRank,
    SupplementNutrient,
    SupplementNutrientRankItem,
)


class SupplementRankDisplayRepository:
    async def list(
        self,
        *,
        is_enabled: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DisplaySupplementNutrientRank], int]:
        query = DisplaySupplementNutrientRank.all()
        if is_enabled is not None:
            query = query.filter(is_enabled=is_enabled)
        total = await query.count()
        items = await (
            query.annotate(item_count=Count("items")).order_by("-created_at", "-id").offset(offset).limit(limit)
        )
        return items, total

    async def get(self, display_id: int) -> DisplaySupplementNutrientRank | None:
        return await (
            DisplaySupplementNutrientRank.filter(id=display_id).prefetch_related("items__supplement_nutrient").first()
        )

    async def get_for_update(
        self,
        display_id: int,
        connection: BaseDBAsyncClient,
    ) -> DisplaySupplementNutrientRank | None:
        return await (
            DisplaySupplementNutrientRank.filter(id=display_id).using_db(connection).select_for_update().first()
        )

    async def get_current(self, now: datetime) -> DisplaySupplementNutrientRank | None:
        return await (
            DisplaySupplementNutrientRank.filter(
                is_enabled=True,
                start_at__lte=now,
                end_at__gte=now,
            )
            .order_by("-start_at", "-id")
            .prefetch_related("items__supplement_nutrient")
            .first()
        )

    async def has_enabled_overlap(
        self,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_display_id: int | None = None,
        connection: BaseDBAsyncClient | None = None,
    ) -> bool:
        query = DisplaySupplementNutrientRank.filter(
            is_enabled=True,
            start_at__lte=end_at,
            end_at__gte=start_at,
        )
        if exclude_display_id is not None:
            query = query.exclude(id=exclude_display_id)
        if connection is not None:
            query = query.using_db(connection)
        return await query.exists()

    async def get_products(self, product_ids: list[int]) -> list[SupplementNutrient]:
        return await SupplementNutrient.filter(id__in=product_ids)

    async def replace_items(
        self,
        display_id: int,
        items: list[tuple[int, int]],
        connection: BaseDBAsyncClient,
    ) -> None:
        await SupplementNutrientRankItem.filter(display_id=display_id).using_db(connection).delete()
        await SupplementNutrientRankItem.bulk_create(
            [
                SupplementNutrientRankItem(
                    display_id=display_id,
                    supplement_nutrient_id=product_id,
                    rank_no=rank_no,
                )
                for product_id, rank_no in items
            ],
            using_db=connection,
        )
