from datetime import datetime

from app.core.exceptions import AdminNotFoundError
from app.dtos.admins import AdminDetailResponse, AdminListItem, AdminListQuery
from app.dtos.pagination import PageResponse
from app.models.accounts import AccountStatus
from app.models.admin import AdminRole

# ---------------------------------------------------------------------------
# 목 데이터. 마이그레이션(이슈 #10) 완료 후 AdminRepository 조회로 교체한다.
# 화면(PR #9 관리자 관리)이 응답 형태를 먼저 붙일 수 있도록 임시로 둔 값이다.
# ---------------------------------------------------------------------------
_MOCK_ADMINS: list[dict] = [
    {
        "admin_id": 1,
        "name": "김은미",
        "email": "eunmi@ozcoding.ai",
        "role": AdminRole.ADMIN,
        "status": AccountStatus.ACTIVE,
        "created_by_account_id": None,
        "approved_at": datetime(2024, 11, 2, 10, 5),
        "created_at": datetime(2024, 11, 2, 10, 0),
    },
    {
        "admin_id": 2,
        "name": "김진형",
        "email": "jinhyeong@ozcoding.ai",
        "role": AdminRole.STAFF,
        "status": AccountStatus.PENDING,
        "created_by_account_id": 1,
        "approved_at": None,
        "created_at": datetime(2026, 8, 14, 9, 0),
    },
]


class AdminQueryService:
    """REQ-ADMIN-010 관리자 조회."""

    async def get_admins(self, query: AdminListQuery) -> PageResponse[AdminListItem]:
        # TODO(#10): accounts JOIN admin 조회로 교체한다.
        #   WHERE accounts.account_type = 'ADMIN'
        #     AND (:keyword IS NULL OR user.name LIKE %:keyword% OR accounts.email LIKE %:keyword%)
        #     AND (:role IS NULL OR admin.role = :role)
        #     AND (:status IS NULL OR accounts.status = :status)
        #   ORDER BY admin.created_at DESC
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
        # TODO(#10): accounts JOIN admin 단건 조회로 교체한다.
        row = next((row for row in _MOCK_ADMINS if row["admin_id"] == admin_id), None)
        if row is None:
            raise AdminNotFoundError()
        return AdminDetailResponse.model_validate(row)

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
