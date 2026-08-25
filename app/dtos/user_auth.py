from enum import StrEnum

from pydantic import EmailStr, Field

from app.dtos.base import CamelModel


class RecordStatus(StrEnum):
    """진료기록 보유 여부. **계정 상태(AccountStatus)가 아니다.**

    프론트 명세가 소문자를 요구해 팀의 "enum 대문자" 관례와 다르다.
    화면 분기에 그대로 쓰이는 값이라 명세를 따른다.
    """

    PENDING = "pending"
    ACTIVE = "active"


class UserLoginRequest(CamelModel):
    email: EmailStr
    # 빈 문자열도 막는다. 누락·공백 모두 Pydantic 이 422 로 처리한다.
    password: str = Field(min_length=1)


class UserLoginResponse(CamelModel):
    """사용자 로그인 성공 응답.

    리프레시 토큰은 본문에 담지 않고 http_only 쿠키로 내려간다.
    """

    access_token: str
    # 진료기록이 있으면 ACTIVE, 없으면 PENDING. 계정 정지 여부와 무관하다.
    status_code: RecordStatus
    # 가장 최근 진료기록(care_episodes) ID. 기록이 없으면 null 이다.
    # status_code 와 항상 짝이 맞는다 — ACTIVE 인데 null 일 수 없다.
    latest_record_id: int | None = None
