import logging

from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from app.core.exceptions import (
    AdminNotFoundError,
    CannotChangeInactiveAdminError,
    CannotChangeOwnRoleError,
    CannotResetSuspendedError,
    CannotResetWithdrawnError,
    CannotSuspendSelfError,
    EmailAlreadyExistsError,
    ForbiddenError,
    LastActiveAdminError,
    SameRoleError,
)
from app.dependencies.admin import AuthenticatedAdmin
from app.dtos.admins import (
    AdminCreateRequest,
    AdminCreateResponse,
    AdminDetailResponse,
    AdminListItem,
    AdminListQuery,
    AdminNameUpdateRequest,
    AdminNameUpdateResponse,
    AdminPasswordResetResponse,
    AdminRoleUpdateRequest,
    AdminRoleUpdateResponse,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)
from app.dtos.pagination import PageResponse
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.services.admin_credentials import issue_temporary_password
from app.services.email_jobs import EmailJobService

logger = logging.getLogger(__name__)


class AdminQueryService:
    """REQ-ADMIN-008/010/011 관리자 계정 관리."""

    def __init__(self) -> None:
        self.email_job_service = EmailJobService()

    async def get_admins(self, query: AdminListQuery) -> PageResponse[AdminListItem]:
        queryset = self._apply_filters(Admin.all(), query)

        total_count = await queryset.count()
        offset = (query.page - 1) * query.size
        admins = await queryset.order_by("-created_at").offset(offset).limit(query.size)

        return PageResponse[AdminListItem](
            total_count=total_count,
            page=query.page,
            size=query.size,
            items=[
                AdminListItem(
                    admin_id=admin.id,
                    name=admin.name,
                    email=admin.email,
                    role=admin.role,
                    status=admin.status,
                )
                for admin in admins
            ],
        )

    async def get_admin(self, admin_id: int) -> AdminDetailResponse:
        admin = await Admin.get_or_none(id=admin_id)
        if admin is None:
            raise AdminNotFoundError()
        return self._to_detail(admin)

    async def create_admin(self, request: AdminCreateRequest, actor_admin_id: int) -> AdminCreateResponse:
        """REQ-ADMIN-008 관리자 등록. 임시 비밀번호는 서버가 만들어 메일로만 전달한다."""
        email = str(request.email)

        try:
            async with in_transaction():
                if await Admin.filter(email=email).exists():
                    raise EmailAlreadyExistsError()

                credential = issue_temporary_password()
                admin = await Admin.create(
                    email=email,
                    hashed_password=credential.hashed_password,
                    name=request.name,
                    role=request.role,
                    status=AccountStatus.ACTIVE if request.is_active else AccountStatus.PENDING,
                    created_by_admin_id=actor_admin_id,
                )
        except IntegrityError:
            # 사전 exists 검사와 INSERT 사이에 같은 이메일 요청이 들어올 수 있다.
            # UNIQUE 위반만 도메인 오류로 변환하고 다른 제약 오류는 원인 그대로 올린다.
            if await Admin.filter(email=email).exists():
                raise EmailAlreadyExistsError() from None
            raise

        # 이메일 작업은 트랜잭션 밖에서 만든다. 큐 등록에 실패해도 FAILED 작업을 남겨
        # 계정 생성 성공과 이메일 전달 실패를 분리해 추적할 수 있다.
        email_job = await self.email_job_service.enqueue_admin_temporary_password(
            admin_id=admin.id,
            recipient_email=email,
            recipient_name=request.name,
            temporary_password=credential.plaintext_for_delivery,
        )

        logger.info(
            "admin created: id=%s by=%s role=%s email_job_id=%s email_job_status=%s",
            admin.id,
            actor_admin_id,
            request.role,
            email_job.id,
            email_job.status,
        )
        return AdminCreateResponse(
            admin_id=admin.id,
            name=admin.name,
            email=admin.email,
            role=admin.role,
            status=admin.status,
            created_by_admin_id=admin.created_by_admin_id,  # type: ignore[attr-defined]
            approved_at=admin.approved_at,
            created_at=admin.created_at,
            email_job_id=email_job.id,
            email_job_status=email_job.status,
        )

    async def reset_password(self, admin_id: int, actor_admin_id: int) -> AdminPasswordResetResponse:
        """REQ-ADMIN-003 임시 비밀번호 재발송.

        등록 시 메일 발송이 실패하면 비밀번호를 아무도 모르는 계정이 남는데,
        이메일이 UNIQUE 라 재등록도 막힌다. 그 상황을 푸는 유일한 경로다.
        """
        admin = await Admin.get_or_none(id=admin_id)
        if admin is None:
            raise AdminNotFoundError()

        # 정지를 풀지 않고 비밀번호만 새로 주면 정지가 무의미해진다.
        if admin.status == AccountStatus.SUSPENDED:
            raise CannotResetSuspendedError()
        if admin.status == AccountStatus.WITHDRAWN:
            raise CannotResetWithdrawnError()

        credential = issue_temporary_password()
        admin.hashed_password = credential.hashed_password
        # 임시 비밀번호 발급은 인증 정보만 교체한다. 계정 상태와 승인 시각은 관리자가
        # 별도의 상태 변경 API로 관리하므로 여기서 함께 바꾸지 않는다.
        # 이전 보유자의 리프레시 토큰은 남는다. 계정을 넘겨받는 상황이라 끊는 게 맞지만
        # 발급된 JWT 를 개별 폐기할 수단이 없다. 리프레시 수명이 지나야 정리된다.
        await admin.save(update_fields=["hashed_password"])

        # 등록과 같은 정책. 작업 등록이 실패해도 비밀번호 변경은 되돌리지 않는다.
        email_job = await self.email_job_service.enqueue_admin_temporary_password(
            admin_id=admin.id,
            recipient_email=admin.email,
            recipient_name=admin.name,
            temporary_password=credential.plaintext_for_delivery,
        )

        logger.info(
            "admin password reset: id=%s by=%s email_job_id=%s email_job_status=%s",
            admin.id,
            actor_admin_id,
            email_job.id,
            email_job.status,
        )
        return AdminPasswordResetResponse(
            admin_id=admin.id,
            email=admin.email,
            status=admin.status,
            email_job_id=email_job.id,
            email_job_status=email_job.status,
        )

    async def update_status(self, request: AdminStatusUpdateRequest, actor_admin_id: int) -> AdminStatusUpdateResponse:
        """REQ-ADMIN-011 관리자 정지·해제. 일괄 처리이며 하나라도 실패하면 전체 롤백한다."""
        if actor_admin_id in request.admin_ids:
            raise CannotSuspendSelfError()

        admin_ids = sorted(set(request.admin_ids))

        async with in_transaction():
            # 불변식 검사와 UPDATE 사이에 다른 요청이 끼어들면 활성 ADMIN 이 0명이 될 수 있다.
            # 대상 행을 잠근 뒤 검사해야 한다.
            targets = await Admin.filter(id__in=admin_ids).select_for_update()

            missing = set(admin_ids) - {admin.id for admin in targets}
            if missing:
                # 부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다. 전체를 거부한다.
                raise AdminNotFoundError(f"존재하지 않는 관리자가 포함되어 있습니다: {sorted(missing)}")

            await self._ensure_active_admin_remains(request.status, admin_ids)

            # 정지해도 이미 발급된 토큰을 즉시 폐기하지는 못한다. 갱신 시점에 상태를 다시
            # 확인해 막으므로, 액세스 토큰이 만료되는 30분 안에는 기존 토큰이 통한다.
            for admin in targets:
                admin.status = request.status
                await admin.save()
            updated_count = len(targets)

        logger.info(
            "admin status changed: ids=%s status=%s by=%s",
            admin_ids,
            request.status,
            actor_admin_id,
        )
        return AdminStatusUpdateResponse(
            updated_count=updated_count,
            status=request.status,
            admin_ids=admin_ids,
        )

    async def update_role(
        self, admin_id: int, request: AdminRoleUpdateRequest, actor_admin_id: int
    ) -> AdminRoleUpdateResponse:
        """REQ-ADMIN-011 관리자 역할 변경. ADMIN 전용이며 한 명씩 바꾼다.

        권한 검사가 매 요청 DB 를 보므로(dependencies/admin.py 의 _authenticate) 변경은
        다음 요청부터 즉시 반영된다. 그래서 본인·마지막 ADMIN 검사가 필수다.
        """
        if admin_id == actor_admin_id:
            raise CannotChangeOwnRoleError()

        async with in_transaction():
            # 검사와 UPDATE 사이에 다른 요청이 끼어들면 활성 ADMIN 이 0명이 될 수 있다.
            # 두 ADMIN 이 동시에 서로를 강등하는 경우가 그렇다. 대상 행을 잠근 뒤 검사한다.
            target = await Admin.filter(id=admin_id).select_for_update().first()
            if target is None:
                raise AdminNotFoundError()

            # 역할은 로그인해서 쓸 수 있는 권한이다. 쓸 수 없는 계정의 권한을 손대면
            # 나중에 해제될 때 의도하지 않은 권한으로 살아난다.
            # PENDING 은 허용한다 — 첫 로그인 전 역할 오지정을 정정할 유일한 경로다.
            if target.status in {AccountStatus.SUSPENDED, AccountStatus.WITHDRAWN}:
                raise CannotChangeInactiveAdminError()

            if target.role == request.role:
                raise SameRoleError()

            await self._ensure_active_admin_remains_after_role_change(target, request.role)

            target.role = request.role
            await target.save()

        logger.info(
            "admin role changed: id=%s role=%s by=%s",
            admin_id,
            request.role,
            actor_admin_id,
        )
        return AdminRoleUpdateResponse(admin_id=target.id, role=target.role)

    async def update_name(
        self, admin_id: int, request: AdminNameUpdateRequest, actor: AuthenticatedAdmin
    ) -> AdminNameUpdateResponse:
        """관리자 이름을 바꾼다. 한 명씩 처리한다.

        ADMIN 은 모든 관리자를, STAFF 는 본인만 바꿀 수 있다. 역할별 분기가 라우터의
        의존성만으로 갈리지 않아(STAFF 도 통과해야 하고 대상은 본인이어야 한다) 여기서
        본다. update_role 이 CannotChangeOwnRoleError 를 서비스에서 보는 것과 같은 이유다.

        이메일은 바꾸지 않는다. 로그인 식별자이고, 바꾸면 기존 계정과 충돌하는지·메일을
        다시 보내야 하는지까지 따라와서 이름 변경과 성격이 다르다.
        """
        if actor.role != AdminRole.ADMIN and admin_id != actor.admin_id:
            raise ForbiddenError("본인 계정만 수정할 수 있습니다.")

        async with in_transaction():
            # 이름만 바꾸므로 불변식은 없지만, 같은 행을 동시에 고치면 나중 쓰기가 이긴다.
            # update_role 과 같은 방식으로 대상 행을 잠근다.
            target = await Admin.filter(id=admin_id).select_for_update().first()
            if target is None:
                raise AdminNotFoundError()

            # 쓸 수 없는 계정은 손대지 않는다. update_role 과 같은 기준이며,
            # PENDING 은 허용한다(첫 로그인 전 오타를 고칠 수 있어야 한다).
            if target.status in {AccountStatus.SUSPENDED, AccountStatus.WITHDRAWN}:
                raise CannotChangeInactiveAdminError()

            target.name = request.name
            await target.save(update_fields=["name"])

        logger.info("admin name changed: id=%s by=%s", admin_id, actor.admin_id)
        return AdminNameUpdateResponse(admin_id=target.id, name=target.name)

    @staticmethod
    async def _ensure_active_admin_remains_after_role_change(target: Admin, new_role: AdminRole) -> None:
        """강등 후에도 활성 ADMIN 이 최소 1명 남는지 확인한다.

        _ensure_active_admin_remains 와 같은 목적이지만 조건이 다르다. 그쪽은 상태 변경을
        보고 이쪽은 역할 변경을 본다. 정지 API 는 화면에 이미 연동돼 있어 건드리지 않았다.

        **이 검사를 지우지 말 것.** HTTP 경로만 보면 도달하지 않는 것처럼 보인다 —
        주체가 ACTIVE ADMIN 이어야 API 를 부를 수 있고(require_admin) 본인은
        CANNOT_CHANGE_OWN_ROLE 로 먼저 막히므로, 남을 강등해도 주체가 활성 ADMIN 으로
        남는다. 하지만 아래 두 경우에 실제로 필요하다.

        1. ACTIVE ADMIN 이 정확히 2명일 때 두 사람이 동시에 서로를 강등하면 각자의 검사가
           모두 통과해 0명이 될 수 있다. select_for_update 는 대상 행만 잠그고 여기의
           카운트 쿼리는 MVCC 로 읽으므로, 상대의 커밋 전 스냅샷을 보고 판단한다.
           (관리자 정지 API 도 같은 구조다 — 근본 해결은 두 API 를 함께 다뤄야 한다)
        2. 나중에 본인 강등을 허용하거나 사람이 아닌 주체(배치·스크립트)가 이 서비스를
           직접 부르게 되면 곧바로 유일한 방어선이 된다.
        """
        demoting = target.role == AdminRole.ADMIN and new_role != AdminRole.ADMIN
        if not demoting:
            return

        remaining = Admin.filter(role=AdminRole.ADMIN, status=AccountStatus.ACTIVE).exclude(id=target.id)
        if not await remaining.exists():
            raise LastActiveAdminError("마지막 활성 관리자는 역할을 변경할 수 없습니다.")

    @staticmethod
    async def _ensure_active_admin_remains(new_status: AccountStatus, admin_ids: list[int]) -> None:
        """정지 후에도 활성 ADMIN 이 최소 1명 남는지 확인한다.

        0명이 되면 아무도 관리자 콘솔에 로그인할 수 없고 DB 를 직접 고치는 것 외에
        복구 수단이 없다.
        """
        if new_status != AccountStatus.SUSPENDED:
            return

        remaining = Admin.filter(role=AdminRole.ADMIN, status=AccountStatus.ACTIVE).exclude(id__in=admin_ids)
        if not await remaining.exists():
            raise LastActiveAdminError()

    @staticmethod
    def _to_detail(admin: Admin) -> AdminDetailResponse:
        return AdminDetailResponse(
            admin_id=admin.id,
            name=admin.name,
            email=admin.email,
            role=admin.role,
            status=admin.status,
            # Tortoise 가 FK 필드(created_by_admin)의 <name>_id 접근자를 런타임에 만든다.
            # 조회 없이 id 만 읽을 수 있으나 정적 분석에는 보이지 않는다.
            created_by_admin_id=admin.created_by_admin_id,  # type: ignore[attr-defined]
            approved_at=admin.approved_at,
            created_at=admin.created_at,
        )

    @staticmethod
    def _apply_filters(queryset: QuerySet[Admin], query: AdminListQuery) -> QuerySet[Admin]:
        if query.keyword:
            queryset = queryset.filter(Q(name__icontains=query.keyword) | Q(email__icontains=query.keyword))
        if query.name:
            queryset = queryset.filter(name__icontains=query.name)
        if query.email:
            queryset = queryset.filter(email__icontains=query.email)
        if query.role is not None:
            queryset = queryset.filter(role=query.role)
        if query.status is not None:
            queryset = queryset.filter(status=query.status)
        return queryset
