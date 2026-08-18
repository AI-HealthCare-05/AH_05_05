from datetime import datetime

from app.core.exceptions import UserNotFoundError
from app.dtos.admin_users import AdminUserDetailResponse, AdminUserListItem, AdminUserListQuery
from app.dtos.pagination import PageResponse
from app.models.enums import AccountStatus

# ---------------------------------------------------------------------------
# 목 데이터. 마이그레이션(이슈 #19) 완료 후 user 테이블 조회로 교체한다.
# ERD v3 에서 accounts 가 사라져 user 단일 테이블 조회로 끝난다.
# ---------------------------------------------------------------------------
_MOCK_USERS: list[dict] = [
    {
        "user_id": 9201,
        "name": "홍길동",
        "email": "user@mail.com",
        "phone": "010-1234-5678",
        "status": AccountStatus.ACTIVE,
        "is_terms_agreed": True,
        "created_at": datetime(2024, 11, 2, 14, 18),
        "active_alarm_count": 3,
    },
    {
        "user_id": 9202,
        "name": "김퇴원",
        "email": "discharged@mail.com",
        "phone": None,
        "status": AccountStatus.PENDING,
        "is_terms_agreed": False,
        "created_at": datetime(2026, 8, 13, 11, 30),
        "active_alarm_count": 0,
    },
]


class AdminUserQueryService:
    """REQ-ADMIN-004 / REQ-ADMIN-005 관리자용 사용자 조회."""

    async def get_users(self, query: AdminUserListQuery) -> PageResponse[AdminUserListItem]:
        # TODO(#19): user 테이블 조회로 교체한다.
        #   WHERE (:keyword IS NULL OR name LIKE %:keyword% OR email LIKE %:keyword%)
        #     AND (:status IS NULL OR status = :status)
        #     AND (:start_date IS NULL OR created_at >= :start_date)
        #     AND (:end_date IS NULL OR created_at < :end_date + 1day)
        #   ORDER BY created_at DESC
        #   LIMIT :size OFFSET (:page - 1) * :size
        # NFR-ADMIN-002(3초 이내)를 위해 keyword·status·created_at 인덱스가 필요하다.
        rows = [row for row in _MOCK_USERS if self._matches(row, query)]
        offset = (query.page - 1) * query.size
        page_rows = rows[offset : offset + query.size]

        return PageResponse[AdminUserListItem](
            total_count=len(rows),
            page=query.page,
            size=query.size,
            items=[AdminUserListItem.model_validate(row) for row in page_rows],
        )

    async def get_user(self, user_id: int) -> AdminUserDetailResponse:
        # TODO(#19): user 단건 조회 + 활성 알림 수 집계로 교체한다.
        #   SELECT COUNT(*) FROM alarms WHERE user_id = :user_id AND status = 'ACTIVE'
        #   (user_id, status) 인덱스가 있어 그대로 탄다.
        row = next((row for row in _MOCK_USERS if row["user_id"] == user_id), None)
        if row is None:
            raise UserNotFoundError()
        return AdminUserDetailResponse.model_validate(row)

    @staticmethod
    def _matches(row: dict, query: AdminUserListQuery) -> bool:
        if query.status is not None and row["status"] != query.status:
            return False
        if query.start_date and row["created_at"].date() < query.start_date:
            return False
        if query.end_date and row["created_at"].date() > query.end_date:
            return False
        if query.keyword:
            keyword = query.keyword.lower()
            if keyword not in row["name"].lower() and keyword not in row["email"].lower():
                return False
        return True
