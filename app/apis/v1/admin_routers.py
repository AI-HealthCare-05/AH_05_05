from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.dependencies.admin import AuthenticatedAdmin, require_admin, require_admin_or_staff
from app.dtos.admin_users import AdminUserDetailResponse, AdminUserListItem, AdminUserListQuery
from app.dtos.admins import (
    AdminCreateRequest,
    AdminDetailResponse,
    AdminListItem,
    AdminListQuery,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)
from app.dtos.pagination import PageResponse
from app.services.admin_users import AdminUserQueryService
from app.services.admins import AdminQueryService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# 조회 4건은 ADMIN·STAFF 모두 허용한다(권한 매트릭스).
AdminOrStaff = Annotated[AuthenticatedAdmin, Depends(require_admin_or_staff)]
# 계정 생성·상태 변경은 ADMIN 전용.
AdminOnly = Annotated[AuthenticatedAdmin, Depends(require_admin)]


@admin_router.get(
    "/accounts",
    response_model=PageResponse[AdminListItem],
    status_code=status.HTTP_200_OK,
    summary="관리자 목록 조회",
)
async def list_admins(
    _: AdminOrStaff,
    query: Annotated[AdminListQuery, Query()],
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> PageResponse[AdminListItem]:
    return await service.get_admins(query)


@admin_router.post(
    "/accounts",
    response_model=AdminDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="관리자 등록",
)
async def create_admin(
    actor: AdminOnly,
    request: AdminCreateRequest,
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminDetailResponse:
    return await service.create_admin(request, actor_admin_id=actor.admin_id)


@admin_router.patch(
    "/accounts/status",
    response_model=AdminStatusUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 정지·해제 (일괄)",
)
async def update_admin_status(
    actor: AdminOnly,
    request: AdminStatusUpdateRequest,
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminStatusUpdateResponse:
    return await service.update_status(request, actor_admin_id=actor.admin_id)


@admin_router.get(
    "/accounts/{admin_id}",
    response_model=AdminDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 상세 조회",
)
async def get_admin(
    _: AdminOrStaff,
    admin_id: Annotated[int, Path(ge=1)],
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminDetailResponse:
    return await service.get_admin(admin_id)


@admin_router.get(
    "/users",
    response_model=PageResponse[AdminUserListItem],
    status_code=status.HTTP_200_OK,
    summary="사용자 목록 조회",
)
async def list_users(
    _: AdminOrStaff,
    query: Annotated[AdminUserListQuery, Query()],
    service: Annotated[AdminUserQueryService, Depends(AdminUserQueryService)],
) -> PageResponse[AdminUserListItem]:
    return await service.get_users(query)


@admin_router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="사용자 상세 조회",
)
async def get_user(
    _: AdminOrStaff,
    user_id: Annotated[int, Path(ge=1)],
    service: Annotated[AdminUserQueryService, Depends(AdminUserQueryService)],
) -> AdminUserDetailResponse:
    return await service.get_user(user_id)
