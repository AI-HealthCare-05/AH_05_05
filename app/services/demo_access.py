from app.core import config
from app.core.exceptions import AppError


class DemoFeatureUnavailableError(AppError):
    status_code = 403
    code = "DEMO_FEATURE_UNAVAILABLE"
    message = "데모버전에서는 기능을 지원하지 않습니다."


def is_demo_account(email: str | None) -> bool:
    return bool(email and email.strip().casefold() == config.DEMO_LOGIN_EMAIL.strip().casefold())


def reject_demo_account(email: str | None) -> None:
    if is_demo_account(email):
        raise DemoFeatureUnavailableError()
