from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core import config
from app.models.enums import AccountStatus
from app.services import email_background_tasks as tasks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email,recipient,verified,active,owner,expected",
    [
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", True, True, 7, True),
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", False, True, 7, True),
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", False, False, 7, False),
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", False, True, 8, False),
        ("normal@example.com", "visitor@example.com", True, True, 7, False),
        ("normal@example.com", "normal@example.com", True, True, 7, True),
        ("normal@example.com", "normal@example.com", False, True, 7, False),
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", True, False, 7, False),
        ("demo_tester@rxvita.p-e.kr", "visitor@example.com", True, True, 8, False),
    ],
)
async def test_report_target_validation(monkeypatch, email, recipient, verified, active, owner, expected):
    monkeypatch.setattr(config, "DEMO_LOGIN_EMAIL", "demo_tester@rxvita.p-e.kr")

    async def get_user(**filters):
        assert filters["id"] == 7
        assert filters["status"] == AccountStatus.ACTIVE
        if not active or filters.get("email", email) != email:
            return None
        return SimpleNamespace(id=7, email=email)

    monkeypatch.setattr(tasks.User, "get_or_none", get_user)
    monkeypatch.setattr(
        tasks.EmailVerification, "filter", Mock(return_value=SimpleNamespace(exists=AsyncMock(return_value=verified)))
    )
    job = SimpleNamespace(reference_table="intake_reports", reference_id=7, user_id=owner)
    assert await tasks.EmailBackgroundTaskExecutor._is_intake_report_sendable(job, recipient) is expected
