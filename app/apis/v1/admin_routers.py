from datetime import date
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
from app.dtos.admin_users import (
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListQuery,
    AdminUserStatusUpdateRequest,
    AdminUserStatusUpdateResponse,
)
from app.dtos.admins import (
    AdminCreateRequest,
    AdminCreateResponse,
    AdminDetailResponse,
    AdminListItem,
    AdminListQuery,
    AdminPasswordResetResponse,
    AdminRoleUpdateRequest,
    AdminRoleUpdateResponse,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)
from app.dtos.background_jobs import (
    AdminBackgroundJobListItem,
    AdminBackgroundJobListQuery,
    AdminBackgroundJobStatsResponse,
)
from app.dtos.pagination import PageResponse
from app.services.admin_auth import AdminAuthService
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_users import AdminUserQueryService
from app.services.admins import AdminQueryService
from app.services.background_jobs import BackgroundJobService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# 조회 4건은 ADMIN·STAFF 모두 허용한다(권한 매트릭스).
AdminOrStaff = Annotated[AuthenticatedAdmin, Depends(require_admin_or_staff)]
# 계정 생성·상태 변경은 ADMIN 전용.
AdminOnly = Annotated[AuthenticatedAdmin, Depends(require_admin)]
# 대시보드는 역할을 가리지 않고 ACTIVE 관리자면 통과한다.
ActiveAdmin = Annotated[AuthenticatedAdmin, Depends(get_current_admin)]


def get_background_job_service() -> BackgroundJobService:
    return BackgroundJobService()


@admin_router.get(
    "/jobs",
    response_model=PageResponse[AdminBackgroundJobListItem],
    status_code=status.HTTP_200_OK,
    summary="관리자 작업 목록 조회",
)
async def list_background_jobs_for_admin(
    _: AdminOrStaff,
    query: Annotated[AdminBackgroundJobListQuery, Query()],
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> PageResponse[AdminBackgroundJobListItem]:
    """관리자 JWT로 백그라운드 작업을 조회한다.

    브라우저에 내부 API 키를 노출하지 않고 작업 모니터링 화면에서 실제 작업 이력을
    조회하기 위한 관리자용 프록시 엔드포인트다. ADMIN·STAFF 모두 사용할 수 있다.
    """
    return await service.list_for_admin(query)


@admin_router.get(
    "/jobs/stats",
    response_model=AdminBackgroundJobStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 작업 상태별 통계 조회",
)
async def get_background_job_stats_for_admin(
    _: AdminOrStaff,
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    service: Annotated[BackgroundJobService, Depends(get_background_job_service)],
) -> AdminBackgroundJobStatsResponse:
    """내부 API 키를 노출하지 않고 관리자 JWT로 작업 상태별 건수를 조회한다."""
    result = await service.stats(start_date, end_date)
    return AdminBackgroundJobStatsResponse.model_validate(result)


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
    """운영 대시보드의 회원 현황 집계. (REQ-DASH-001)

    역할을 가리지 않고 ACTIVE 관리자면 조회할 수 있다. 집계 숫자만 나가며
    개별 회원의 이메일·전화번호는 포함되지 않는다.

    `period` 는 `newSignups` 와 그 증감률에만 적용된다. `total`·`active`·`pending`·
    `suspended`·`withdrawn` 은 조회 시점의 현재 값이라 기간을 바꿔도 변하지 않는다.

    - `total` = `active` + `suspended` (화면이 활성·정지 합을 100% 로 표시한다).
      `pending`·`withdrawn` 은 별도 필드로만 내려가므로 `newSignups` 가 `total` 보다 클 수 있다.
    - 증감률은 직전 동일 기간과 비교하며, 경과 시간까지 맞춘다(TODAY 면 어제 같은 시각까지).
      직전 기간이 0건이면 계산할 수 없어 `null` 이다.
    - `signupTrend` 는 기간과 무관하게 항상 최근 14일이고, 가입자가 없는 날도 0 으로 포함된다.
    - `status` 는 정지 비율 기준 경보 단계다(NORMAL / WARNING / DANGER).

    OCR·챗봇·알림·시스템 지표는 아직 데이터가 없어 응답에 넣지 않았다.
    0 으로 채우면 화면이 정상값으로 그려 오해를 부른다.

    - **422 VALIDATION_ERROR** — 지원하지 않는 `period`
    """
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
    """관리자 계정 목록을 페이지 단위로 조회한다. (REQ-ADMIN-004)

    ADMIN·STAFF 모두 조회할 수 있다.

    `keyword` 는 이름·이메일 부분 일치이며, `role`·`status` 로 좁힐 수 있다.
    정렬은 등록일 최신순 고정이다.

    관리자 계정에는 `WITHDRAWN` 을 쓰지 않는다(탈퇴는 사용자 전용).
    값을 넣어도 거부되지는 않지만 결과가 항상 비어 있다.
    """
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
    """관리자 계정을 새로 만든다. ADMIN 전용. (REQ-ADMIN-008)

    비밀번호는 받지 않는다. 서버가 임시 비밀번호를 만들어 해시로 저장하고 평문은
    안내 메일로만 전달한다. **응답에는 평문이 포함되지 않는다.**

    `isActive` 가 false 면 PENDING 으로 만들어져 첫 로그인 후 비밀번호를 바꿔야 한다.

    메일 발송이 실패해도 계정 생성은 되돌리지 않고 `emailSent: false` 로 알린다.
    롤백하면 "계정이 안 만들어졌다"와 "메일만 실패했다"를 구분할 수 없기 때문이며,
    실패 시에는 임시 비밀번호 재발송 API 로 복구한다.

    - **409 EMAIL_ALREADY_EXISTS** — 이미 등록된 이메일
    - **403 FORBIDDEN** — STAFF 계정
    """
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
    """로그인한 본인의 비밀번호를 바꾼다. (REQ-ADMIN-009)

    대상은 토큰의 `sub` 로 정한다. 다른 관리자 ID 를 받는 파라미터는 없으며,
    본문에 넣어도 무시된다.

    임시 비밀번호를 바꿀 유일한 경로라 PENDING 계정도 허용한다(다른 관리자 API 는
    ACTIVE 만 통과). PENDING 이었다면 변경과 함께 ACTIVE 로 전환되고 승인 시각이 기록된다.
    이미 ACTIVE 면 상태를 건드리지 않는다.

    새 비밀번호는 사용자 회원가입과 같은 정책을 따른다 —
    8자 이상, 대문자·소문자·숫자·특수문자 각 1개 이상.

    이 브라우저의 리프레시 쿠키는 삭제되지만, **다른 기기에 남은 리프레시 토큰은 끊지 못한다.**
    발급된 JWT 를 개별 폐기할 수단이 없어 수명이 다할 때까지 유효하다.
    액세스 토큰도 만료 전까지 그대로 쓸 수 있다.

    - **400 INVALID_PASSWORD** — 현재 비밀번호 불일치
    - **400 SAME_AS_CURRENT** — 새 비밀번호가 현재와 동일
    - **422 VALIDATION_ERROR** — 비밀번호 정책 위반 (부족한 조건을 메시지로 알려준다)
    """
    result = await service.change_password(actor.admin_id, request)
    # 이 브라우저의 쿠키만 지운다. 다른 기기에 남은 리프레시 토큰은 끊을 수단이 없어
    # 만료될 때까지 유효하다.
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
    """관리자 계정을 일괄 정지하거나 해제한다. ADMIN 전용. (REQ-ADMIN-011)

    화면에서 체크박스로 여러 명을 고르므로 한 번에 최대 100건까지 받는다.
    `status` 는 `SUSPENDED` 또는 `ACTIVE` 만 가능하다. 계정 삭제는 제공하지 않는다.

    **전부 성공하거나 전부 롤백된다.** 없는 ID 가 하나라도 섞이면 아무것도 바꾸지 않고
    404 로 거부한다. 부분 성공을 허용하면 무엇이 실패했는지 알 수 없기 때문이다.

    정지된 계정은 갱신 시점의 상태 확인으로 막힌다. 이미 발급된 액세스 토큰은
    만료(최대 30분) 전까지 통하므로 차단이 즉시 이뤄지지는 않는다.

    - **409 LAST_ACTIVE_ADMIN** — 정지 후 활성 ADMIN 이 0명이 되는 경우.
      아무도 콘솔에 로그인할 수 없게 되므로 막는다
    - **409 CANNOT_SUSPEND_SELF** — 본인 계정 포함
    - **404 ADMIN_NOT_FOUND** — 존재하지 않는 ID 포함
    """
    return await service.update_status(request, actor_admin_id=actor.admin_id)


@admin_router.patch(
    "/accounts/{admin_id}/role",
    response_model=AdminRoleUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 역할 변경",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "UNAUTHORIZED — 토큰 없음·만료"},
        status.HTTP_403_FORBIDDEN: {"description": "FORBIDDEN — ADMIN 이 아님"},
        status.HTTP_404_NOT_FOUND: {"description": "ADMIN_NOT_FOUND"},
        status.HTTP_409_CONFLICT: {
            "description": (
                "CANNOT_CHANGE_OWN_ROLE / SAME_ROLE / LAST_ACTIVE_ADMIN / CANNOT_CHANGE_INACTIVE_ADMIN"
            )
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "VALIDATION_ERROR — role 이 enum 밖"},
    },
)
async def update_admin_role(
    actor: AdminOnly,
    admin_id: Annotated[int, Path(ge=1)],
    request: AdminRoleUpdateRequest,
    service: Annotated[AdminQueryService, Depends(AdminQueryService)],
) -> AdminRoleUpdateResponse:
    """관리자의 역할을 바꾼다. ADMIN 전용. 한 번에 한 명이다. (REQ-ADMIN-011)

    상태 변경(정지·해제)은 `PATCH /accounts/status` 가 일괄로 처리한다. 역할은 그쪽과
    분리해 이 엔드포인트에서만 다룬다.

    **권한 검사는 매 요청 DB 를 보므로 변경이 다음 요청부터 즉시 반영된다.** 강등된
    관리자는 액세스 토큰이 남아 있어도 ADMIN 전용 API 에서 곧바로 403 을 받는다.
    그래서 아래 두 검사를 서버가 반드시 막는다.

    - **409 CANNOT_CHANGE_OWN_ROLE** — 본인 역할. 스스로를 낮추면 되돌릴 API 에도
      접근할 수 없어 복구 수단이 없다
    - **409 LAST_ACTIVE_ADMIN** — 마지막 활성 ADMIN 강등. 아무도 관리자 기능을 쓸 수
      없게 되고 DB 를 직접 고치는 것 외에 복구 수단이 없다
    - **409 SAME_ROLE** — 현재와 같은 역할
    - **409 CANNOT_CHANGE_INACTIVE_ADMIN** — 정지·탈퇴 계정. 해제될 때 의도하지 않은
      권한으로 살아나는 것을 막는다. **PENDING 은 허용한다** — 첫 로그인 전 역할
      오지정을 정정할 유일한 경로다
    - **404 ADMIN_NOT_FOUND** — 존재하지 않는 ID
    """
    return await service.update_role(admin_id, request, actor_admin_id=actor.admin_id)


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
    """대상 관리자의 임시 비밀번호를 새로 발급해 메일로 보낸다. ADMIN 전용. (REQ-ADMIN-003)

    등록 시 메일 발송이 실패하면 비밀번호를 아무도 모르는 계정이 남는데,
    이메일이 UNIQUE 라 재등록도 막힌다. 그 상황을 푸는 유일한 경로다.

    새 비밀번호는 해시로 저장하고 평문은 메일로만 전달한다.
    **응답에는 평문이 포함되지 않는다.**

    발급하면 계정이 PENDING 으로 돌아가고 승인 시각이 비워진다. 비밀번호를 바꿔야
    관리자 기능을 다시 쓸 수 있다.

    **이전 보유자의 리프레시 토큰은 남는다.** 계정을 넘겨받는 상황이라 끊는 게 맞지만
    발급된 JWT 를 개별 폐기할 수단이 없다. 수명이 다할 때까지 기다려야 한다.

    등록과 같은 정책으로, 메일 발송이 실패해도 비밀번호 변경은 되돌리지 않고
    `emailSent: false` 로 알린다.

    - **409 CANNOT_RESET_SUSPENDED** — 정지를 풀지 않고 비밀번호만 주면 정지가 무의미해진다
    - **409 CANNOT_RESET_WITHDRAWN** — 탈퇴한 계정
    - **404 ADMIN_NOT_FOUND**
    """
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
    """관리자 계정 한 건의 상세 정보를 조회한다. (REQ-ADMIN-005)

    ADMIN·STAFF 모두 조회할 수 있다.

    `createdByAdminId` 는 이 계정을 만든 관리자다. 최초 슈퍼 ADMIN 은 생성자가 없어 `null` 이다.
    `approvedAt` 은 임시 비밀번호를 바꿔 ACTIVE 가 된 시각이며, 아직 PENDING 이면 `null` 이다.

    - **404 ADMIN_NOT_FOUND**
    """
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
    """서비스 회원 목록을 페이지 단위로 조회한다. (REQ-ADMIN-010)

    ADMIN·STAFF 모두 조회할 수 있다.

    `keyword` 는 이름·이메일 부분 일치, `status` 는 계정 상태, `startDate`·`endDate` 는
    가입일 범위다. 종료일은 **당일을 포함**한다. 정렬은 가입일 최신순 고정이다.

    - **422 VALIDATION_ERROR** — 가입일 시작이 종료보다 늦은 경우
    """
    return await service.get_users(query)


@admin_router.patch(
    "/users/status",
    response_model=AdminUserStatusUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="사용자 정지·해제 (일괄)",
)
async def update_user_status(
    actor: AdminOnly,
    request: AdminUserStatusUpdateRequest,
    service: Annotated[AdminUserQueryService, Depends(AdminUserQueryService)],
) -> AdminUserStatusUpdateResponse:
    """회원 계정을 일괄 정지하거나 해제한다. ADMIN 전용. (REQ-ADMIN-006)

    화면에서 체크박스로 여러 명을 고르므로 한 번에 최대 100건까지 받는다.
    `status` 는 `SUSPENDED` 또는 `ACTIVE` 만 가능하다.

    **강제 탈퇴는 이 API 로 하지 않는다.** 탈퇴는 본인 의사이고, 관리자에 의한
    데이터 삭제는 REQ-ADMIN-007 의 별도 API 다.

    **전부 성공하거나 전부 롤백된다.** 없는 ID 가 하나라도 섞이면 아무것도 바꾸지 않고
    404 로 거부한다. 부분 성공을 허용하면 무엇이 실패했는지 알 수 없기 때문이다.
    같은 ID 를 여러 번 보내도 한 명으로 센다.

    정지해도 **이미 로그인한 회원의 세션은 끊기지 않는다.** 새 로그인은 막히지만,
    사용자 토큰 갱신은 계정 상태를 다시 확인하지 않아 리프레시 토큰이 만료될 때까지
    접근이 이어진다. 관리자 계정과 달리 아직 차단 수단이 없다.

    - **409 CANNOT_REACTIVATE_WITHDRAWN** — 탈퇴한 회원이 포함된 경우.
      되살리면 삭제 대기 중인 계정이 다시 살아난다
    - **404 USER_NOT_FOUND** — 존재하지 않는 ID 포함
    - **403 FORBIDDEN** — STAFF 계정(조회는 되지만 상태 변경은 ADMIN 전용)
    """
    return await service.update_status(request, actor_admin_id=actor.admin_id)


# "/users/{user_id}" 보다 먼저 선언한다. 지금은 메서드가 달라 겹치지 않지만,
# 나중에 PATCH /users/{user_id} 가 생기면 "status" 를 id 로 해석하게 된다.
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
    """회원 한 명의 상세 정보를 조회한다. (REQ-ADMIN-010)

    ADMIN·STAFF 모두 조회할 수 있다.

    `isTermsAgreed` 는 `user_settings` 를 조인해 가져온다. 가입 직후라 설정 행이 아직
    없는 회원은 미동의(false)로 본다.

    `activeAlarmCount` 는 상태가 ACTIVE 인 알람 수다. 복약 알람이 (회원 x 시간대) 단위라
    회원당 최대 4건이며, 화면이 기대하는 "활성 알림 수"와 같은 기준인지는 알림 담당자 확인이 남아 있다.

    - **404 USER_NOT_FOUND**
    """
    return await service.get_user(user_id)
