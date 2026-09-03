from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dtos.common_codes import CommonCodeLookupItem, CommonCodeLookupResponse
from app.services.common_codes import CommonCodeService

common_code_router = APIRouter(prefix="/common-codes", tags=["common-codes"])


def get_common_code_service() -> CommonCodeService:
    return CommonCodeService()


@common_code_router.get(
    "/{category}/{group_code}",
    response_model=CommonCodeLookupResponse,
    status_code=status.HTTP_200_OK,
    summary="활성 공통코드 조회",
)
async def list_active_common_codes(
    category: str,
    group_code: str,
    service: Annotated[CommonCodeService, Depends(get_common_code_service)],
) -> CommonCodeLookupResponse:
    """대분류와 코드그룹에 속한 활성 상세코드를 정렬순서대로 반환한다."""
    group, codes = await service.list_active_codes(category, group_code)
    return CommonCodeLookupResponse(
        category=group.category,
        group_code=group.group_code,
        group_name=group.group_name,
        items=[CommonCodeLookupItem.model_validate(code) for code in codes],
    )
