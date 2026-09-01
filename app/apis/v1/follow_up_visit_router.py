from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.dependencies.security import get_request_user
from app.dtos.follow_up_visits import (
    FollowUpVisitCreateRequest,
    FollowUpVisitListResponse,
    FollowUpVisitResponse,
    FollowUpVisitUpdateRequest,
)
from app.models.users import User
from app.services.follow_up_visits import FollowUpVisitService

follow_up_visit_router = APIRouter(prefix="/user/follow-up-visits", tags=["follow-up-visits"])


def get_follow_up_visit_service() -> FollowUpVisitService:
    return FollowUpVisitService()


@follow_up_visit_router.post(
    "",
    response_model=FollowUpVisitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="추후 진료 일정 등록",
)
async def create_follow_up_visit(
    request: FollowUpVisitCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[FollowUpVisitService, Depends(get_follow_up_visit_service)],
) -> FollowUpVisitResponse:
    """현재 사용자의 병원 재방문·추후 진료 일정을 등록한다."""
    return await service.create(user, request)


@follow_up_visit_router.get(
    "",
    response_model=FollowUpVisitListResponse,
    summary="추후 진료 일정 목록 조회",
)
async def list_follow_up_visits(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[FollowUpVisitService, Depends(get_follow_up_visit_service)],
    start_date: Annotated[date | None, Query(description="조회 시작일")] = None,
    end_date: Annotated[date | None, Query(description="조회 종료일")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FollowUpVisitListResponse:
    """현재 사용자의 추후 진료 일정을 날짜 범위와 페이지 단위로 조회한다."""
    return await service.list(
        user,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )


@follow_up_visit_router.get(
    "/{visit_id}",
    response_model=FollowUpVisitResponse,
    summary="추후 진료 일정 상세 조회",
)
async def get_follow_up_visit(
    visit_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[FollowUpVisitService, Depends(get_follow_up_visit_service)],
) -> FollowUpVisitResponse:
    """현재 사용자가 소유한 추후 진료 일정 한 건을 조회한다."""
    return await service.get(user, visit_id)


@follow_up_visit_router.patch(
    "/{visit_id}",
    response_model=FollowUpVisitResponse,
    summary="추후 진료 일정 수정",
)
async def update_follow_up_visit(
    request: FollowUpVisitUpdateRequest,
    visit_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[FollowUpVisitService, Depends(get_follow_up_visit_service)],
) -> FollowUpVisitResponse:
    """현재 사용자가 소유한 추후 진료 일정의 입력 필드만 수정한다."""
    return await service.update(user, visit_id, request)


@follow_up_visit_router.delete(
    "/{visit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="추후 진료 일정 삭제",
)
async def delete_follow_up_visit(
    visit_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[FollowUpVisitService, Depends(get_follow_up_visit_service)],
) -> Response:
    """현재 사용자가 소유한 추후 진료 일정과 연결된 알람을 삭제한다."""
    await service.delete(user, visit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
