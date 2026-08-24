import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    ENV: Env = Env.LOCAL
    SECRET_KEY: str = f"default-secret-key{uuid.uuid4().hex}"
    TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))
    TEMPLATE_DIR: str = os.path.join(Path(__file__).resolve().parent.parent, "templates")

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "pw1234"
    DB_NAME: str = "ai_health"
    DB_CONNECT_TIMEOUT: int = 5
    DB_CONNECTION_POOL_MAXSIZE: int = 10
    DB_QUERY_LOG_ENABLED: bool = False

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    CLOVA_TEMPLATE_OCR_INVOKE_URL: str | None = None
    CLOVA_TEMPLATE_OCR_SECRET: SecretStr | None = None
    CLOVA_TEMPLATE_ID: int | None = Field(default=None, gt=0)
    CLOVA_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    CLOVA_READ_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    OCR_REVIEW_CONFIDENCE_THRESHOLD: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
    )

    INTERNAL_API_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:blesseunmi82@gmail.com"

    ALARM_POLL_SECONDS: int = 10
    ALARM_MAX_RETRY_COUNT: int = 3
    ALARM_RETRY_BASE_SECONDS: int = 30
    ALARM_PUSH_TTL_SECONDS: int = 300
    ALARM_CLICK_URL: str = "/"

    COOKIE_DOMAIN: str = "localhost"

    # 메일 발송 방식. console 은 로그로만 출력하고 실제로 보내지 않는다.
    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None

    JWT_ALGORITHM: str = "HS256"
    # NFR-ADMIN-001 은 액세스 30분·리프레시 7일이었으나, 세션 무효화 수단을 두지 않기로
    # 하면서 1일로 줄였다. 비밀번호를 바꿔도 다른 기기의 리프레시 토큰을 끊을 수 없어
    # 이 값이 그대로 노출 창이 된다.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 24 * 60
    JWT_LEEWAY: int = 5

    # 초기 ADMIN 시드용(scripts/seed_admin.py). 운영에서는 시드 후 값을 지운다.
    SUPERADMIN_EMAIL: str | None = None
    SUPERADMIN_PASSWORD: str | None = None

    # REQ-DASH-001 회원 현황 경보 임계치(정지 비율 %).
    # 이하는 NORMAL, 초과~WARNING 이하는 WARNING, 그 위는 DANGER.
    # 기준이 바뀌어도 프론트를 고치지 않도록 서버 설정으로 둔다.
    DASHBOARD_SUSPENDED_WARNING_PERCENT: float = 10.0
    DASHBOARD_SUSPENDED_DANGER_PERCENT: float = 20.0
