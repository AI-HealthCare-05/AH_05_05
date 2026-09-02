from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dtos.supplement_rank_displays import SupplementRankDisplayResponse
from app.services.supplement_rank_displays import SupplementRankDisplayService

display_router = APIRouter(prefix="/display", tags=["display"])


def get_supplement_rank_display_service() -> SupplementRankDisplayService:
    return SupplementRankDisplayService()


@display_router.get(
    "/med/nutr/rank",
    response_model=SupplementRankDisplayResponse,
    status_code=status.HTTP_200_OK,
    summary="현재 영양제 랭킹 전시 조회",
)
async def get_current_supplement_rank_display(
    service: Annotated[SupplementRankDisplayService, Depends(get_supplement_rank_display_service)],
) -> SupplementRankDisplayResponse:
    """현재 전시기간에 포함되고 활성화된 영양제 랭킹 한 건을 순위와 함께 조회한다."""
    return await service.current()
