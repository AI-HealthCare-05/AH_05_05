import logging

from tortoise.expressions import Q
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from app.core.exceptions import (
    AdminNotFoundError,
    CannotResetSuspendedError,
    CannotResetWithdrawnError,
    CannotSuspendSelfError,
    EmailAlreadyExistsError,
    LastActiveAdminError,
)
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
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.services.admin_credentials import issue_temporary_password

logger = logging.getLogger(__name__)


class AdminQueryService:
    """REQ-ADMIN-008/010/011 관리자 계정 관리."""

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

        # 발송은 트랜잭션 밖에서 한다. 실패해도 계정 생성을 되돌리지 않는다.
        # 되돌리면 관리자는 "계정이 안 만들어졌다"고만 알게 되는데, 실제로는 메일만
        # 실패한 것이라 상황을 구분할 수 없다. emailSent 로 알려주는 편이 낫다.
        # 발송에 실패해도 재발송(REQ-ADMIN-003)으로 복구할 수 있다.
        email_sent = credential.send_to(name=request.name, email=email)

        logger.info(
            "admin created: id=%s by=%s role=%s email_sent=%s",
            admin.id,
            actor_admin_id,
            request.role,
            email_sent,
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
            email_sent=email_sent,
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
        # 임시 비밀번호를 다시 받은 상태이므로 활성 계정도 PENDING 으로 돌린다.
        # 비밀번호를 바꿔야 관리자 기능을 다시 쓸 수 있다.
        admin.status = AccountStatus.PENDING
        # approved_at 은 "현재 활성 상태가 된 시각"이다(change_password 가 전이할 때마다
        # 덮어쓴다). PENDING 으로 돌아갔는데 값이 남아 있으면 목록에서 모순으로 보이므로 비운다.
        admin.approved_at = None
        # 이전 보유자의 리프레시 토큰은 남는다. 계정을 넘겨받는 상황이라 끊는 게 맞지만
        # 발급된 JWT 를 개별 폐기할 수단이 없다. 리프레시 수명이 지나야 정리된다.
        await admin.save()

        # 등록과 같은 정책. 발송이 실패해도 되돌리지 않고 결과만 알린다.
        email_sent = credential.send_to(name=admin.name, email=admin.email)

        logger.info(
            "admin password reset: id=%s by=%s email_sent=%s",
            admin.id,
            actor_admin_id,
            email_sent,
        )
        return AdminPasswordResetResponse(
            admin_id=admin.id,
            email=admin.email,
            status=admin.status,
            email_sent=email_sent,
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

            for admin in targets:
            # 정지된 계정은 갱신할 때 상태를 다시 확인해 막는다. 액세스 토큰이 만료되는
            # 30분 안에는 기존 토큰으로 접근할 수 있다.
            updated_count = await Admin.filter(id__in=admin_ids).update(status=request.status)

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
        if query.role is not None:
            queryset = queryset.filter(role=query.role)
        if query.status is not None:
            queryset = queryset.filter(status=query.status)
        return queryset
