import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core import config


def require_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
) -> None:
    expected = config.INTERNAL_API_KEY
    if not expected or not x_internal_api_key or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key.")
