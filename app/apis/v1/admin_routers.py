from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from app.dependencies.admin import (
    AuthenticatedAdmin,
    get_current_admin,
    get_current_admin_allow_pending,
    require_admin,
    require_admin_or_staff,
)
from app.dtos.admin_auth import AdminPasswordChangeRequest, AdminPasswordChangeResponse
from app.dtos.admin_dashboard import DashboardSummaryQuery, DashboardSummaryResponse
from app.dtos.admin_users import AdminUserDetailResponse, AdminUserListItem, AdminUserListQuery
from app.dtos.admins import (
    AdminCreateRequest,
    AdminCreateResponse,
    AdminDetailResponse,
    AdminListItem,
    AdminListQuery,
    AdminPasswordResetResponse,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)
from app.dtos.pagination import PageResponse
from app.services.admin_auth import AdminAuthService
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_users import AdminUserQueryService
from app.services.admins import AdminQueryService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# 조회 4건은 ADMIN·STAFF 모두 허용한다(권한 매트릭스).
AdminOrStaff = Annotated[AuthenticatedAdmin, Depends(require_admin_or_staff)]
# 계정 생성·상태 변경은 ADMIN 전용.
AdminOnly = Annotated[AuthenticatedAdmin, Depends(require_admin)]
# 대시보드는 역할을 가리지 않고 ACTIVE 관리자면 통과한다.
ActiveAdmin = Annotated[AuthenticatedAdmin, Depends(get_current_admin)]


@admin_router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="대시보드 요약 (회원 현황)",
)
async def get_dashboard_summary(
    _: ActiveAdmin,
    query: Annotated[DashboardSummaryQuery, Query()],
    service: Annotated[AdminDashboardService, Depends(AdminDashboardService)],
) -> DashboardSummaryResponse:
    return await service.get_summary(query)


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
    response_model=AdminCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="관리자 등록",
)
async def create_admin(
    actor: AdminOnly,
    request: AdminCreateRequest,
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminCreateResponse:
    return await service.create_admin(request, actor_admin_id=actor.admin_id)


@admin_router.patch(
    "/accounts/password",
    response_model=AdminPasswordChangeResponse,
    status_code=status.HTTP_200_OK,
    summary="본인 비밀번호 변경",
)
async def change_password(
    # 임시 비밀번호를 바꿀 유일한 경로라 PENDING 계정도 허용한다.
    # 다른 관리자 API 는 get_current_admin(ACTIVE 전용)을 쓴다.
    actor: Annotated[AuthenticatedAdmin, Depends(get_current_admin_allow_pending)],
    request: AdminPasswordChangeRequest,
    response: Response,
    service: Annotated[AdminAuthService, Depends(AdminAuthService)],
) -> AdminPasswordChangeResponse:
    result = await service.change_password(actor.admin_id, request)
    # 이전 리프레시 토큰은 지문 검증에서 이미 무효가 된다.
    # 브라우저에 남은 쿠키까지 지워 다음 갱신에서 불필요한 401 을 만들지 않는다.
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, httponly=True)
    return result


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


@admin_router.post(
    "/accounts/{admin_id}/password/reset",
    response_model=AdminPasswordResetResponse,
    status_code=status.HTTP_200_OK,
    summary="임시 비밀번호 재발송",
)
async def reset_admin_password(
    actor: AdminOnly,
    admin_id: Annotated[int, Path(ge=1)],
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminPasswordResetResponse:
    return await service.reset_password(admin_id, actor_admin_id=actor.admin_id)


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
