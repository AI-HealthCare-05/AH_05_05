from datetime import date, datetime
from enum import StrEnum

from app.dtos.base import CamelModel


class DashboardPeriod(StrEnum):
    """대시보드 조회 기간. 화면의 오늘/7일/30일 토글과 1:1 로 대응한다.

    DB 컬럼이 아니므로 app/models/enums.py 가 아니라 DTO 쪽에 둔다.
    models/enums.py 는 ERD 의 enum 과 1:1 로 맞춰야 한다.
    """

    TODAY = "TODAY"
    LAST_7_DAYS = "7D"
    LAST_30_DAYS = "30D"


class DashboardQuery(CamelModel):
    # 화면 진입 시 기본 선택이 7일이다.
    period: DashboardPeriod = DashboardPeriod.LAST_7_DAYS


class TrendPoint(CamelModel):
    """추이 그래프의 막대 하나. 값이 없는 날도 0 으로 채워 보낸다."""

    date: date
    count: int


class MemberStats(CamelModel):
    """회원 현황 및 가입. total/active/suspended 는 기간과 무관한 현재 스냅샷이다."""

    total_count: int
    active_count: int
    suspended_count: int
    # 화면 라벨이 "오늘 가입"이라 선택 기간과 무관하게 오늘 0시 기준으로 센다.
    today_signup_count: int
    period_signup_count: int
    # 직전 동일 기간 대비 증감률(%). 직전 기간이 0건이면 정의할 수 없어 null 이다.
    signup_change_rate: float | None = None
    signup_trend: list[TrendPoint]


class ChatStats(CamelModel):
    """AI 챗봇 응답 현황.

    한 건은 ASSISTANT 메시지 하나다. 사용자 질문이 아니라 답변 시도를 세야
    성공·실패의 합이 전체와 맞는다.
    """

    total_count: int
    success_count: int
    failure_count: int
    # 자동 해결률. 전체가 0이면 null 이다(0% 로 내리면 "전부 실패"로 오독된다).
    success_rate: float | None = None
    change_rate: float | None = None


class OcrStats(CamelModel):
    """OCR 문서 처리.

    pending 은 서버가 처리 중인 QUEUED·PROCESSING 만 센다.
    READY_FOR_REVIEW 는 사용자 확인을 기다리는 상태라 운영 대기열이 아니다.
    """

    total_count: int
    pending_count: int
    success_count: int
    failure_count: int
    success_rate: float | None = None
    change_rate: float | None = None


class NotificationStats(CamelModel):
    """알림 발송 허브. alarm_events 의 이벤트 종류별 집계다."""

    scheduled_count: int
    sent_count: int
    failure_count: int
    success_rate: float | None = None
    daily_sent_trend: list[TrendPoint]


class SystemStats(CamelModel):
    """시스템 코어.

    화면 시안의 OCR 추출 정확도와 SMTP 발송 건수는 저장하는 곳이 없어 빠졌다.
    정확도를 기록하는 컬럼이 없고, 메일 발송 로그 테이블도 아직 없다.
    """

    # 지금 밀려 있는 작업 수. 기간과 무관한 현재 스냅샷이다.
    queued_job_count: int
    # 기간 내 완료된 LLM 작업의 평균 처리 시간. 완료 건이 없으면 null 이다.
    llm_average_latency_ms: int | None = None


class DashboardResponse(CamelModel):
    """REQ-DASH-001 운영 대시보드. 화면 카드 5개를 한 번에 채운다."""

    period: DashboardPeriod
    # 집계 구간을 함께 내려 화면이 "언제부터 언제까지"를 표시할 수 있게 한다.
    start_at: datetime
    end_at: datetime
    members: MemberStats
    chat: ChatStats
    ocr: OcrStats
    notifications: NotificationStats
    system: SystemStats
