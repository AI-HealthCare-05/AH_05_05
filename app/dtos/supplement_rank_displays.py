from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from app.dtos.base import BaseSerializerModel, CamelModel
from app.dtos.pagination import PageQuery


class SupplementRankItemRequest(CamelModel):
    supplement_nutrient_id: int = Field(gt=0)
    rank_no: int = Field(ge=1, le=5)


class SupplementRankDisplayWriteRequest(CamelModel):
    title: str = Field(min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime
    is_enabled: bool = False
    items: list[SupplementRankItemRequest] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_period_and_items(self) -> Self:
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("전시 제목을 입력해 주세요.")
        if self.end_at < self.start_at:
            raise ValueError("전시 종료 일시는 시작 일시 이후여야 합니다.")

        product_ids = [item.supplement_nutrient_id for item in self.items]
        rank_numbers = [item.rank_no for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("같은 영양제를 중복 등록할 수 없습니다.")
        if len(set(rank_numbers)) != len(rank_numbers):
            raise ValueError("같은 순위를 중복 등록할 수 없습니다.")
        if sorted(rank_numbers) != list(range(1, len(rank_numbers) + 1)):
            raise ValueError("순위는 1부터 빠짐없이 입력해 주세요.")
        return self


class SupplementRankItemResponse(BaseSerializerModel):
    supplement_nutrient_id: int
    name: str
    rank_no: int


class SupplementRankDisplayResponse(BaseSerializerModel):
    display_id: int
    title: str
    start_at: datetime
    end_at: datetime
    is_enabled: bool
    created_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None
    items: list[SupplementRankItemResponse]


class SupplementRankDisplayListItem(BaseSerializerModel):
    display_id: int
    title: str
    start_at: datetime
    end_at: datetime
    is_enabled: bool
    item_count: int
    created_at: datetime


class SupplementRankDisplayListResponse(BaseSerializerModel):
    total_count: int
    page: int
    size: int
    items: list[SupplementRankDisplayListItem]


class SupplementRankDisplayListQuery(PageQuery):
    is_enabled: bool | None = None
