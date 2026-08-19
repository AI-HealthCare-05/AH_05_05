from datetime import timedelta

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from app.core.exceptions import UserNotFoundError
from app.dtos.admin_users import AdminUserDetailResponse, AdminUserListItem, AdminUserListQuery
from app.dtos.pagination import PageResponse
from app.models.alarms import Alarm
from app.models.enums import AlarmStatus
from app.models.users import User, UserSettings


class AdminUserQueryService:
    """REQ-ADMIN-004 / REQ-ADMIN-005 관리자용 사용자 조회."""

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
