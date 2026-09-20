from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import config
from app.core.exceptions import AppError
from app.core.utils.security import hash_password
from app.dtos.users import PasswordChangeRequest, WithdrawRequest
from app.services.users import UserManageService


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["password", "withdraw"])
async def test_demo_account_cannot_change_password_or_withdraw(monkeypatch, operation):
    monkeypatch.setattr(config, "DEMO_LOGIN_EMAIL", "demo_tester@rxvita.p-e.kr", raising=False)
    user = SimpleNamespace(
        email="demo_tester@rxvita.p-e.kr", hashed_password=hash_password("Old1234!"), save=AsyncMock()
    )
    service = UserManageService()
    with pytest.raises(AppError, match="데모버전에서는 기능을 지원하지 않습니다."):
        if operation == "password":
            await service.change_password(
                user, PasswordChangeRequest(current_password="Old1234!", new_password="Next1234!")
            )
        else:
            await service.withdraw(user, WithdrawRequest(password="Old1234!"))


@pytest.mark.asyncio
async def test_demo_login_is_disabled_by_default(monkeypatch):
    from app.apis.v1 import auth_routers

    monkeypatch.setattr(config, "DEMO_LOGIN_ENABLED", False)
    response = await auth_routers.demo_login(AsyncMock(), AsyncMock())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_demo_login_uses_server_credentials(monkeypatch):
    import json

    from pydantic import SecretStr

    from app.apis.v1 import auth_routers

    monkeypatch.setattr(config, "DEMO_LOGIN_ENABLED", True)
    monkeypatch.setattr(config, "DEMO_LOGIN_PASSWORD", SecretStr("Server1234!"))
    monkeypatch.setattr(config, "DEMO_LOGIN_EMAIL", "demo_tester@rxvita.p-e.kr")
    monkeypatch.setattr(config, "USER_REFRESH_ENABLED", False)
    service = AsyncMock()
    service.login.return_value = {"access_token": "issued-token"}
    response = await auth_routers.demo_login(service, AsyncMock())
    assert json.loads(response.body)["email"] == "demo_tester@rxvita.p-e.kr"
    credentials = service.authenticate.call_args.args[0]
    assert str(credentials.email) == "demo_tester@rxvita.p-e.kr"
    assert credentials.password == "Server1234!"
    assert b"Server1234!" not in response.body


def test_report_email_accepts_valid_recipient_and_rejects_invalid():
    from pydantic import ValidationError

    from app.dtos.intake_reports import SendIntakeReportEmailRequest

    request = SendIntakeReportEmailRequest(email_token="snapshot", recipient_email="visitor@example.com")
    assert request.recipient_email == "visitor@example.com"
    with pytest.raises(ValidationError):
        SendIntakeReportEmailRequest(email_token="snapshot", recipient_email="invalid")


@pytest.mark.asyncio
async def test_normal_user_cannot_override_report_recipient(monkeypatch):
    from app.apis.v1.intake_report_router import send_intake_report_email
    from app.dtos.intake_reports import SendIntakeReportEmailRequest

    monkeypatch.setattr(config, "DEMO_LOGIN_ENABLED", True)
    with pytest.raises(AppError) as error:
        await send_intake_report_email(
            SendIntakeReportEmailRequest(email_token="snapshot", recipient_email="visitor@example.com"),
            SimpleNamespace(id=1, email="normal@example.com"),
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_demo_report_uses_validated_snapshot_and_requested_recipient(monkeypatch):
    from datetime import date
    from importlib import import_module
    from unittest.mock import Mock

    from app.dtos.intake_reports import SendIntakeReportEmailRequest
    from app.models.enums import BackgroundJobStatus

    monkeypatch.setattr(config, "DEMO_LOGIN_ENABLED", True)
    router = import_module("app.apis.v1.intake_report_router")
    from app.services import demo_access

    monkeypatch.setattr(
        demo_access, "Redis", Mock(side_effect=AssertionError("Email must not require Redis")), raising=False
    )
    email = Mock()
    email.consume_snapshot_token.return_value = SimpleNamespace(
        report_id="r1", report_markdown="# safe", report_html=None
    )
    jobs = AsyncMock()
    jobs.enqueue_intake_report.return_value = SimpleNamespace(id=7, status=BackgroundJobStatus.QUEUED)
    user = SimpleNamespace(id=1, email=config.DEMO_LOGIN_EMAIL, birth_date=date(1990, 1, 1), name="데모")
    result = await router.send_intake_report_email(
        SendIntakeReportEmailRequest(email_token="signed-snapshot", recipient_email="visitor@example.com"),
        user,
        email,
        jobs,
        AsyncMock(),
    )
    assert result.job_id == 7
    assert jobs.enqueue_intake_report.call_args.kwargs["recipient_email"] == "visitor@example.com"
    assert jobs.enqueue_intake_report.call_args.kwargs["report_markdown"] == "# safe"
    email.consume_snapshot_token.assert_called_once_with(token="signed-snapshot", user=user)
