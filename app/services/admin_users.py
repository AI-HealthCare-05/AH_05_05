from datetime import datetime

from app.core.exceptions import UserNotFoundError
from app.dtos.admin_users import (
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListQuery,
    ConsentType,
    UserConsentItem,
)
from app.dtos.pagination import PageResponse
from app.models.accounts import AccountStatus

# ---------------------------------------------------------------------------
# 목 데이터. 마이그레이션(이슈 #10) 완료 후 accounts·user 조인 조회로 교체한다.
# ---------------------------------------------------------------------------
_MOCK_USERS: list[dict] = [
    {
        "user_id": 9201,
        "name": "홍길동",
        "email": "user@mail.com",
        "phone": "010-1234-5678",
        "status": AccountStatus.ACTIVE,
        "is_alarm": True,
        "created_at": datetime(2024, 11, 2, 14, 18),
        "consents": [
            {
                "consent_type": ConsentType.MEDICAL_DATA,
                "agreed": True,
                "agreed_at": datetime(2024, 11, 2, 14, 18),
                "withdrawn_at": None,
            },
            {
                "consent_type": ConsentType.AI_USAGE,
                "agreed": True,
                "agreed_at": datetime(2024, 11, 2, 14, 18),
                "withdrawn_at": None,
            },
            # 선택 항목을 동의 후 철회한 사례 — 최신 행이 agreed=false 라 withdrawn_at 이 채워진다.
            {
                "consent_type": ConsentType.NOTIFICATION,
                "agreed": False,
                "agreed_at": datetime(2024, 11, 2, 14, 18),
                "withdrawn_at": datetime(2026, 3, 5, 9, 12),
            },
        ],
        "active_alarm_count": 3,
    },
    {
        "user_id": 9202,
        "name": "김퇴원",
        "email": "discharged@mail.com",
        "phone": None,
        "status": AccountStatus.PENDING,
        "is_alarm": False,
        "created_at": datetime(2026, 8, 13, 11, 30),
        "consents": [],
        "active_alarm_count": 0,
    },
]


class AdminUserQueryService:
    """REQ-ADMIN-004 / REQ-ADMIN-005 관리자용 사용자 조회."""

    async def get_users(self, query: AdminUserListQuery) -> PageResponse[AdminUserListItem]:
        # TODO(#10): accounts JOIN user 조회로 교체한다.
        #   WHERE accounts.account_type = 'USER'
        #     AND (:keyword IS NULL OR user.name LIKE %:keyword% OR accounts.email LIKE %:keyword%)
        #     AND (:status IS NULL OR accounts.status = :status)
        #     AND (:start_date IS NULL OR accounts.created_at >= :start_date)
        #     AND (:end_date IS NULL OR accounts.created_at < :end_date + 1day)
        #   ORDER BY accounts.created_at DESC
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
        # TODO(#10): accounts JOIN user 단건 조회 후 아래 두 가지를 덧붙인다.
        #
        # (1) 항목별 동의 — (user_id, consent_type) 별 agreed_at 최신 행이 현재 상태다.
        #     SELECT c.* FROM user_consents c
        #       JOIN (SELECT consent_type, MAX(agreed_at) AS latest
        #               FROM user_consents WHERE user_id = :user_id
        #              GROUP BY consent_type) m
        #         ON c.consent_type = m.consent_type AND c.agreed_at = m.latest
        #      WHERE c.user_id = :user_id
        #     withdrawn_at 컬럼은 없다. 최신 행이 agreed=false 면 그 행의 agreed_at 을
        #     withdrawn_at 으로 내려보내고, agreed=true 면 null 로 둔다.
        #
        # (2) 활성 알림 수
        #     SELECT COUNT(*) FROM alarms WHERE user_id = :user_id AND status = 'ACTIVE'
        #     (user_id, status) 인덱스가 있어 그대로 탄다.
        row = next((row for row in _MOCK_USERS if row["user_id"] == user_id), None)
        if row is None:
            raise UserNotFoundError()

        return AdminUserDetailResponse(
            **{key: value for key, value in row.items() if key != "consents"},
            consents=[UserConsentItem.model_validate(consent) for consent in row["consents"]],
        )

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
