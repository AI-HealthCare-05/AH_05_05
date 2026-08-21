from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator

from app.dtos.base import CamelModel


class DashboardPeriod(StrEnum):
    """집계 기간. 캘린더 단위가 아니라 오늘을 끝으로 하는 롤링 구간이다.

    DB 컬럼이 아니므로 app/models/enums.py 가 아니라 DTO 쪽에 둔다.
    그 파일은 ERD 의 enum 과 1:1 로 맞춰야 한다.
    """

    TODAY = "TODAY"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"


class MemberAlertStatus(StrEnum):
    """정지 비율로 판정한 회원 현황 경보 단계. 임계치는 config 에 있다."""

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    DANGER = "DANGER"


def validate_period(value: object) -> DashboardPeriod:
    """Pydantic 기본 영문 메시지 대신 한글 메시지를 내보낸다.

    enum 변환 전에 걸러야 해서 BeforeValidator 를 쓴다.
    """
    if isinstance(value, DashboardPeriod):
        return value
    try:
        return DashboardPeriod(str(value))
    except ValueError as err:
        allowed = ", ".join(period.value for period in DashboardPeriod)
        raise ValueError(f"지원하지 않는 집계 기간입니다. {allowed} 중 하나여야 합니다.") from err


class DashboardSummaryQuery(CamelModel):
    period: Annotated[DashboardPeriod, BeforeValidator(validate_period)] = DashboardPeriod.TODAY


class SignupTrendPoint(CamelModel):
    """가입 추이 그래프의 막대 하나. 가입자가 없는 날도 count=0 으로 채워 보낸다."""

    date: date
    count: int


class MemberStats(CamelModel):
    """회원 현황.

    period 는 newSignups 와 그 증감률에만 적용된다.
    total·active·pending·suspended·withdrawn 은 조회 시점의 현재 값이라 기간과 무관하다.
    (기간을 바꿔도 이 값들이 그대로인 것은 정상이다.)
    """

    # total = active + suspended. 화면이 활성 95% + 정지 5% = 100% 로 표시하기 때문이다.
    # PENDING·WITHDRAWN 은 total 에 넣지 않고 아래 별도 필드로만 내려준다.
    total: int
    # 상태를 가리지 않고 기간 내 가입 전체를 센다. total 이 PENDING·WITHDRAWN 을 빼므로
    # newSignups > total 이 나올 수 있는데 버그가 아니다(분모가 서로 다른 값이다).
    new_signups: int
    active: int
    pending: int
    suspended: int
    withdrawn: int
    # 직전 동일 기간 대비 증감률(%). 분모가 0이면 계산할 수 없어 null 이다.
    total_change_rate: float | None = None
    new_signups_change_rate: float | None = None
    # 화면의 "14일간 가입 추이" 차트용. period 와 무관하게 항상 14일치다.
    signup_trend: list[SignupTrendPoint]
    status: MemberAlertStatus


class DashboardSummaryResponse(CamelModel):
    """REQ-DASH-001 대시보드 요약.

    1차는 회원 현황 블록 하나다. OCR·챗봇·알림·시스템·보안은 타 담당 데이터와
    로그 테이블이 생긴 뒤 같은 응답에 블록을 추가하는 방식으로 확장한다.
    """

    period: DashboardPeriod
    generated_at: datetime
    members: MemberStats
