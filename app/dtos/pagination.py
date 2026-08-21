from typing import Generic, TypeVar

from pydantic import Field

from app.dtos.base import CamelModel

ItemT = TypeVar("ItemT")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PageQuery(CamelModel):
    """목록 조회 공통 쿼리. 회의 확정(A-7)에 따라 offset 방식을 쓴다."""

    page: int = Field(default=1, ge=1, description="1부터 시작")
    size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PageResponse(CamelModel, Generic[ItemT]):
    """목록 조회 공통 응답."""

    total_count: int = Field(description="필터 조건에 맞는 전체 건수")
    page: int
    size: int
    items: list[ItemT]
