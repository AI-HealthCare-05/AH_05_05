import logging
import secrets
import string
from datetime import datetime

from app.core.exceptions import (
    AdminNotFoundError,
    CannotSuspendSelfError,
    EmailAlreadyExistsError,
    LastActiveAdminError,
)
from app.core.utils.security import hash_password
from app.dtos.admins import (
    AdminCreateRequest,
    AdminDetailResponse,
    AdminListItem,
    AdminListQuery,
    AdminStatusUpdateRequest,
    AdminStatusUpdateResponse,
)
from app.dtos.pagination import PageResponse
from app.models.enums import AccountStatus, AdminRole

logger = logging.getLogger(__name__)

TEMPORARY_PASSWORD_LENGTH = 12

# ---------------------------------------------------------------------------
# 목 데이터. 마이그레이션은 PR #18 로 완료됐으므로 admin 테이블 조회로 교체하면 된다.
# 화면(PR #9 관리자 관리)이 응답 형태를 먼저 붙일 수 있도록 임시로 둔 값이다.
# ---------------------------------------------------------------------------
_MOCK_ADMINS: list[dict] = [
    {
        "admin_id": 1,
        "name": "김은미",
        "email": "eunmi@ozcoding.ai",
        "role": AdminRole.ADMIN,
        "status": AccountStatus.ACTIVE,
        "created_by_admin_id": None,
        "approved_at": datetime(2024, 11, 2, 10, 5),
        "created_at": datetime(2024, 11, 2, 10, 0),
    },
    {
        "admin_id": 2,
        "name": "김진형",
        "email": "jinhyeong@ozcoding.ai",
        "role": AdminRole.STAFF,
        "status": AccountStatus.PENDING,
        "created_by_admin_id": 1,
        "approved_at": None,
        "created_at": datetime(2026, 8, 14, 9, 0),
    },
]


class AdminQueryService:
    """REQ-ADMIN-010 관리자 조회."""

    async def get_admins(self, query: AdminListQuery) -> PageResponse[AdminListItem]:
        # TODO(#19): admin 테이블 조회로 교체한다.
        #   WHERE (:keyword IS NULL OR name LIKE %:keyword% OR email LIKE %:keyword%)
        #     AND (:role IS NULL OR role = :role)
        #     AND (:status IS NULL OR status = :status)
        #   ORDER BY created_at DESC
        #   LIMIT :size OFFSET (:page - 1) * :size
        rows = [row for row in _MOCK_ADMINS if self._matches(row, query)]
        offset = (query.page - 1) * query.size
        page_rows = rows[offset : offset + query.size]

        return PageResponse[AdminListItem](
            total_count=len(rows),
            page=query.page,
            size=query.size,
            items=[AdminListItem.model_validate(row) for row in page_rows],
        )

    async def get_admin(self, admin_id: int) -> AdminDetailResponse:
        # TODO(#19): admin 단건 조회로 교체한다.
        row = next((row for row in _MOCK_ADMINS if row["admin_id"] == admin_id), None)
        if row is None:
            raise AdminNotFoundError()
        return AdminDetailResponse.model_validate(row)

    async def create_admin(self, request: AdminCreateRequest, actor_admin_id: int) -> AdminDetailResponse:
        """REQ-ADMIN-008 관리자 등록. 임시 비밀번호는 서버가 만들어 메일로만 전달한다."""
        # TODO(#19): admin 테이블 조회·삽입으로 교체한다.
        #   SELECT 1 FROM admin WHERE email = :email  (중복 검사)
        #   INSERT INTO admin (email, hashed_password, status, name, role, created_by_admin_id)
        if any(row["email"] == request.email for row in _MOCK_ADMINS):
            raise EmailAlreadyExistsError()

        temporary_password = self._generate_temporary_password()
        hashed = hash_password(temporary_password)

        # TODO(#19): 임시 비밀번호를 이메일로 발송한다(REQ-ADMIN-008).
        #   발송 실패 시 계정만 생성되어 아무도 쓸 수 없는 상태가 되므로,
        #   생성과 발송을 한 트랜잭션으로 묶거나 재발송 수단(REQ-ADMIN-003)이 필요하다.
        #   평문 비밀번호는 응답·로그 어디에도 남기지 않는다.
        del temporary_password

        created = {
            "admin_id": max((row["admin_id"] for row in _MOCK_ADMINS), default=0) + 1,
            "name": request.name,
            "email": str(request.email),
            "role": request.role,
            "status": AccountStatus.ACTIVE if request.is_active else AccountStatus.PENDING,
            "created_by_admin_id": actor_admin_id,
            "approved_at": None,
            "created_at": datetime.now(),
            "_hashed_password": hashed,
        }
        _MOCK_ADMINS.append(created)

        logger.info("admin created: id=%s by=%s role=%s", created["admin_id"], actor_admin_id, request.role)
        return AdminDetailResponse.model_validate(created)

    async def update_status(self, request: AdminStatusUpdateRequest, actor_admin_id: int) -> AdminStatusUpdateResponse:
        """REQ-ADMIN-011 관리자 정지·해제. 일괄 처리이며 하나라도 실패하면 전체 롤백한다."""
        # TODO(#19): 아래를 하나의 트랜잭션으로 묶는다.
        #   SELECT ... FROM admin WHERE id IN :admin_ids FOR UPDATE
        #   UPDATE admin SET status = :status WHERE id IN :admin_ids
        # 불변식 검사와 UPDATE 사이에 다른 요청이 끼어들면 활성 ADMIN 이 0명이 될 수 있으므로,
        # 잠금 없이 검사만 해서는 안 된다.
        if actor_admin_id in request.admin_ids:
            raise CannotSuspendSelfError()

        targets = {row["admin_id"]: row for row in _MOCK_ADMINS if row["admin_id"] in request.admin_ids}
        missing = set(request.admin_ids) - targets.keys()
        if missing:
            # 부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다. 전체를 거부한다.
            raise AdminNotFoundError(f"존재하지 않는 관리자가 포함되어 있습니다: {sorted(missing)}")

        self._ensure_active_admin_remains(request, targets)

        for row in targets.values():
            row["status"] = request.status

        logger.info(
            "admin status changed: ids=%s status=%s by=%s",
            sorted(targets),
            request.status,
            actor_admin_id,
        )
        return AdminStatusUpdateResponse(
            updated_count=len(targets),
            status=request.status,
            admin_ids=sorted(targets),
        )

    @staticmethod
    def _ensure_active_admin_remains(request: AdminStatusUpdateRequest, targets: dict[int, dict]) -> None:
        """정지 후에도 활성 ADMIN 이 최소 1명 남는지 확인한다."""
        if request.status != AccountStatus.SUSPENDED:
            return

        remaining = [
            row
            for row in _MOCK_ADMINS
            if row["role"] == AdminRole.ADMIN
            and row["status"] == AccountStatus.ACTIVE
            and row["admin_id"] not in targets
        ]
        if not remaining:
            raise LastActiveAdminError()

    @staticmethod
    def _generate_temporary_password() -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(TEMPORARY_PASSWORD_LENGTH))

    @staticmethod
    def _matches(row: dict, query: AdminListQuery) -> bool:
        if query.role is not None and row["role"] != query.role:
            return False
        if query.status is not None and row["status"] != query.status:
            return False
        if query.keyword:
            keyword = query.keyword.lower()
            if keyword not in row["name"].lower() and keyword not in row["email"].lower():
                return False
        return True
