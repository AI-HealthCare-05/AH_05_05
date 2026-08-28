from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from typing import TypeVar

from fastapi.responses import ORJSONResponse
from starlette.routing import Match, Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TIMEOUT_ATTRIBUTE = "__api_timeout_seconds__"
_TIMEOUT_RESPONSE = {
    "code": "API_TIMEOUT",
    "message": "요청 처리 시간이 초과되었습니다.",
}

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., object])


def _normalize_timeout(seconds: object) -> float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("timeout seconds must be a number")

    normalized = float(seconds)
    if normalized <= 0 or not math.isfinite(normalized):
        raise ValueError("timeout seconds must be positive and finite")
    return normalized


def api_timeout(seconds: float) -> Callable[[F], F]:
    """특정 API 엔드포인트의 처리 제한 시간을 초 단위로 재정의한다."""
    normalized = _normalize_timeout(seconds)

    def decorator(endpoint: F) -> F:
        setattr(endpoint, _TIMEOUT_ATTRIBUTE, normalized)
        return endpoint

    return decorator


class ApiTimeoutMiddleware:
    """지정한 API 경로에 공통 및 엔드포인트별 처리 제한 시간을 적용한다."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        router: Router,
        default_timeout_seconds: float,
        path_prefix: str = "/api/v1/",
    ) -> None:
        self.app = app
        self._router = router
        self._default_timeout_seconds = _normalize_timeout(default_timeout_seconds)
        self._path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self._path_prefix):
            await self.app(scope, receive, send)
            return

        timeout_seconds = self._resolve_timeout(scope)
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            async with asyncio.timeout(timeout_seconds):
                await self.app(scope, receive, tracked_send)
        except TimeoutError:
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "")
            if response_started:
                logger.error(
                    "API request timed out after response start: "
                    "method=%s path=%s timeout_seconds=%s response_started=true",
                    method,
                    path,
                    timeout_seconds,
                )
                return

            logger.warning(
                "API request timed out: method=%s path=%s timeout_seconds=%s",
                method,
                path,
                timeout_seconds,
            )
            response = ORJSONResponse(status_code=504, content=_TIMEOUT_RESPONSE)
            await response(scope, receive, send)

    def _resolve_timeout(self, scope: Scope) -> float:
        for route in self._router.routes:
            match, _ = route.matches(scope)
            if match is Match.FULL:
                endpoint = getattr(route, "endpoint", None)
                return getattr(
                    endpoint,
                    _TIMEOUT_ATTRIBUTE,
                    self._default_timeout_seconds,
                )
        return self._default_timeout_seconds
