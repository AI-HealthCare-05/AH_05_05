import logging
from datetime import timedelta

from tortoise.expressions import Q
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from app.core.exceptions import CannotReactivateWithdrawnError, UserNotFoundError
from app.dtos.admin_users import (
    AdminUserDetailResponse,
    AdminUserListItem,
    AdminUserListQuery,
    AdminUserStatusUpdateRequest,
    AdminUserStatusUpdateResponse,
)
from app.dtos.pagination import PageResponse
from app.models.alarms import Alarm
from app.models.enums import AccountStatus, AlarmStatus
from app.models.users import User, UserSettings

logger = logging.getLogger(__name__)


class AdminUserQueryService:
    """REQ-ADMIN-004 / REQ-ADMIN-005 / REQ-ADMIN-006 관리자용 사용자 조회·상태 변경."""

    async def get_users(self, query: AdminUserListQuery) -> PageResponse[AdminUserListItem]:
        queryset = self._apply_filters(User.all(), query)

        total_count = await queryset.count()
        offset = (query.page - 1) * query.size
        users = await queryset.order_by("-created_at").offset(offset).limit(query.size)

        return PageResponse[AdminUserListItem](
            total_count=total_count,
            page=query.page,
            size=query.size,
            items=[
                AdminUserListItem(
                    user_id=user.id,
                    name=user.name,
                    email=user.email,
                    status=user.status,
                    created_at=user.created_at,
                )
                for user in users
            ],
        )

    async def get_user(self, user_id: int) -> AdminUserDetailResponse:
        user = await User.get_or_none(id=user_id)
        if user is None:
            raise UserNotFoundError()

        # user 와 1:1 이지만 가입 직후에는 설정 행이 아직 없을 수 있다. 그 경우 미동의로 본다.
        settings = await UserSettings.get_or_none(user_id=user_id)
        is_terms_agreed = bool(settings and settings.is_terms_agreed)

        # 집계 기준이 알림 담당자와 미합의 상태다. 복약 알람이 (사용자 x 시간대) 단위라
        # 사용자당 최대 4건이므로, 화면이 기대하는 "활성 알림 수"와 같은지 확인이 필요하다.
        active_alarm_count = await Alarm.filter(user_id=user_id, status=AlarmStatus.ACTIVE).count()

        return AdminUserDetailResponse(
            user_id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            status=user.status,
            is_terms_agreed=is_terms_agreed,
            created_at=user.created_at,
            active_alarm_count=active_alarm_count,
        )

    async def update_status(
        self, request: AdminUserStatusUpdateRequest, actor_admin_id: int
    ) -> AdminUserStatusUpdateResponse:
        """REQ-ADMIN-006 사용자 정지·해제. 일괄 처리이며 하나라도 실패하면 전체 롤백한다."""
        user_ids = sorted(set(request.user_ids))

        async with in_transaction():
            # 검사와 UPDATE 사이에 대상이 탈퇴하면 탈퇴 계정이 되살아난다. 잠근 뒤 검사한다.
            targets = await User.filter(id__in=user_ids).select_for_update()

            missing = set(user_ids) - {user.id for user in targets}
            if missing:
                # 부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다. 전체를 거부한다.
                raise UserNotFoundError(f"존재하지 않는 사용자가 포함되어 있습니다: {sorted(missing)}")

            withdrawn = sorted(user.id for user in targets if user.status == AccountStatus.WITHDRAWN)
            if withdrawn:
                raise CannotReactivateWithdrawnError(f"탈퇴한 사용자가 포함되어 있습니다: {withdrawn}")

            updated_count = await User.filter(id__in=user_ids).update(status=request.status)

        # 정지 이력은 남겨야 나중에 "왜 막혔는지" 를 추적할 수 있다.
        logger.info(
            "user status changed: ids=%s status=%s by=%s",
            user_ids,
            request.status,
            actor_admin_id,
        )
        return AdminUserStatusUpdateResponse(
            updated_count=updated_count,
            status=request.status,
            user_ids=user_ids,
        )

    @staticmethod
    def _apply_filters(queryset: QuerySet[User], query: AdminUserListQuery) -> QuerySet[User]:
        if query.keyword:
            queryset = queryset.filter(Q(name__icontains=query.keyword) | Q(email__icontains=query.keyword))
        if query.status is not None:
            queryset = queryset.filter(status=query.status)
        if query.start_date:
            queryset = queryset.filter(created_at__gte=query.start_date)
        if query.end_date:
            # created_at 은 시각까지 있으므로 종료일 당일을 포함하려면 다음 날 0시 미만으로 본다.
            queryset = queryset.filter(created_at__lt=query.end_date + timedelta(days=1))
        return queryset
