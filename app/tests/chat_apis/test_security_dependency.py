from types import SimpleNamespace

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import UnauthorizedError
from app.dependencies.security import get_request_user
from app.models.enums import AccountStatus
from app.models.users import User


@pytest.mark.parametrize(
    "account_status",
    [
        AccountStatus.PENDING,
        AccountStatus.SUSPENDED,
        AccountStatus.WITHDRAWN,
    ],
)
async def test_get_request_user_rejects_inactive_account(
    account_status: AccountStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await User.create(
        email=f"inactive-{account_status.value.lower()}@example.com",
        hashed_password="hashed-password",
        name="비활성 사용자",
        status=account_status,
    )
    monkeypatch.setattr(
        "app.dependencies.security.JwtService.verify_jwt",
        lambda self, *, token, token_type: SimpleNamespace(payload={"user_id": user.id}),
    )

    with pytest.raises(UnauthorizedError):
        await get_request_user(
            HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="valid-token",
            )
        )
