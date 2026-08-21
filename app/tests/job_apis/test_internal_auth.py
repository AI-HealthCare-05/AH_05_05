import pytest
from fastapi import HTTPException, status

from app.dependencies.internal_auth import require_internal_api_key


def test_internal_key_accepts_matching_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.dependencies.internal_auth.config.INTERNAL_API_KEY", "test-key")

    assert require_internal_api_key("test-key") is None


def test_internal_key_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.dependencies.internal_auth.config.INTERNAL_API_KEY", "test-key")

    with pytest.raises(HTTPException) as error:
        require_internal_api_key("wrong-key")

    assert error.value.status_code == status.HTTP_403_FORBIDDEN
