# API Request Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply a three-second default timeout to every `/api/v1/**` request and allow each endpoint to override the limit with `@api_timeout(seconds)`.

**Architecture:** A pure ASGI middleware wraps only `/api/v1/**`, resolves the matched FastAPI endpoint, and reads optional timeout metadata written by a decorator. It runs the downstream application inside `asyncio.timeout()`, returns the agreed HTTP 504 JSON before a response starts, and logs timeout context without sensitive data.

**Tech Stack:** Python 3.13, FastAPI, Starlette ASGI, asyncio, Pydantic Settings, HTTPX ASGITransport, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-28-api-timeout-design.md`

## Global Constraints

- Apply the default timeout only to paths beginning with `/api/v1/`.
- The default is exactly `3.0` seconds through `API_TIMEOUT_SECONDS`.
- `/api/docs`, `/api/redoc`, `/api/openapi.json`, and static paths are excluded.
- Individual endpoints may set a shorter or longer positive finite timeout.
- Timeout responses use HTTP 504 and `{"code":"API_TIMEOUT","message":"요청 처리 시간이 초과되었습니다."}`.
- Async cancellation is cooperative; do not claim already-committed or external side effects are rolled back.
- Do not add third-party dependencies.
- Do not commit changes; the user requested work without commits.

---

## File Map

- Create `app/core/api_timeout.py`: timeout value validation, `api_timeout` decorator, route resolution, and pure ASGI middleware.
- Modify `app/core/config.py`: define and validate the default timeout setting.
- Modify `app/main.py`: register timeout middleware outside the OCR upload-size middleware.
- Modify `.env.example`: document the default environment value.
- Modify `README.md`: document global behavior, response contract, and endpoint override syntax.
- Create `app/tests/test_api_timeout.py`: decorator and standalone middleware behavior tests.
- Create `app/tests/test_api_timeout_integration.py`: production app registration and middleware order tests.

### Task 1: Default setting and endpoint decorator

**Files:**
- Create: `app/core/api_timeout.py`
- Modify: `app/core/config.py`
- Test: `app/tests/test_api_timeout.py`

**Interfaces:**
- Produces: `api_timeout(seconds: int | float) -> Callable[[F], F]`
- Produces: endpoint metadata attribute `__api_timeout_seconds__: float`
- Produces: `Config.API_TIMEOUT_SECONDS: float`, default `3.0`, greater than zero
- Consumes: Pydantic `Field` and Python `math.isfinite`

- [ ] **Step 1: Add a failing test for the configuration default and validation**

Create `app/tests/test_api_timeout.py` with:

```python
import importlib
import math

import pytest
from pydantic import ValidationError

from app.core.config import Config


def test_api_timeout_setting_defaults_to_three_seconds() -> None:
    settings = Config(_env_file=None)

    assert settings.API_TIMEOUT_SECONDS == 3.0


@pytest.mark.parametrize("value", [0, -1, -0.1])
def test_api_timeout_setting_rejects_non_positive_values(value: float) -> None:
    with pytest.raises(ValidationError):
        Config(_env_file=None, API_TIMEOUT_SECONDS=value)
```

- [ ] **Step 2: Run the configuration tests and verify RED**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: `test_api_timeout_setting_defaults_to_three_seconds` fails because `Config` has no declared `API_TIMEOUT_SECONDS` default.

- [ ] **Step 3: Add the validated setting**

In `app/core/config.py`, add near the other server settings:

```python
API_TIMEOUT_SECONDS: float = Field(default=3.0, gt=0)
```

- [ ] **Step 4: Run the configuration tests and verify GREEN**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: the two configuration behaviors pass.

- [ ] **Step 5: Add failing decorator contract tests**

Append to `app/tests/test_api_timeout.py`:

```python
def _load_timeout_module():
    return importlib.import_module("app.core.api_timeout")


def test_api_timeout_decorator_stores_a_normalized_timeout() -> None:
    api_timeout = getattr(_load_timeout_module(), "api_timeout")

    @api_timeout(7)
    async def endpoint() -> None:
        pass

    assert endpoint.__api_timeout_seconds__ == 7.0


@pytest.mark.parametrize("value", [0, -1, math.inf, -math.inf, math.nan])
def test_api_timeout_decorator_rejects_non_positive_or_non_finite_values(value: float) -> None:
    api_timeout = getattr(_load_timeout_module(), "api_timeout")

    with pytest.raises(ValueError):
        api_timeout(value)


@pytest.mark.parametrize("value", [None, "3", True])
def test_api_timeout_decorator_rejects_non_numeric_values(value: object) -> None:
    api_timeout = getattr(_load_timeout_module(), "api_timeout")

    with pytest.raises(TypeError):
        api_timeout(value)
```

- [ ] **Step 6: Run decorator tests and verify RED**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: tests fail inside the test body with `ModuleNotFoundError: app.core.api_timeout`.

- [ ] **Step 7: Implement timeout normalization and the decorator**

Create `app/core/api_timeout.py` with the focused decorator implementation:

```python
from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypeVar

_TIMEOUT_ATTRIBUTE = "__api_timeout_seconds__"

F = TypeVar("F", bound=Callable[..., object])


def _normalize_timeout(seconds: int | float) -> float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TypeError("timeout seconds must be a number")
    normalized = float(seconds)
    if normalized <= 0 or not math.isfinite(normalized):
        raise ValueError("timeout seconds must be positive and finite")
    return normalized


def api_timeout(seconds: int | float) -> Callable[[F], F]:
    normalized = _normalize_timeout(seconds)

    def decorator(endpoint: F) -> F:
        setattr(endpoint, _TIMEOUT_ATTRIBUTE, normalized)
        return endpoint

    return decorator
```

- [ ] **Step 8: Run Task 1 tests and verify GREEN**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: all configuration and decorator tests pass.

- [ ] **Step 9: Review the Task 1 diff without committing**

Run:

```bash
git diff -- app/core/config.py app/core/api_timeout.py app/tests/test_api_timeout.py
```

Confirm only the setting, decorator contract, and tests changed.

### Task 2: Pure ASGI timeout middleware

**Files:**
- Modify: `app/core/api_timeout.py`
- Modify: `app/tests/test_api_timeout.py`

**Interfaces:**
- Consumes: `api_timeout(seconds)` and `__api_timeout_seconds__` from Task 1
- Produces: `ApiTimeoutMiddleware(app: ASGIApp, *, router: Router, default_timeout_seconds: int | float, path_prefix: str = "/api/v1/")`
- Produces: HTTP 504 JSON contract before `http.response.start`
- Produces: WARNING log `API request timed out method=%s path=%s timeout_seconds=%s`

- [ ] **Step 1: Add a standalone test-app helper**

Append imports and helper code to `app/tests/test_api_timeout.py`:

```python
import asyncio
import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def create_timeout_test_app(default_timeout: float) -> FastAPI:
    module = _load_timeout_module()
    middleware_class = getattr(module, "ApiTimeoutMiddleware")
    test_app = FastAPI()
    test_app.add_middleware(
        middleware_class,
        router=test_app.router,
        default_timeout_seconds=default_timeout,
    )
    return test_app
```

- [ ] **Step 2: Add the failing default-timeout and cancellation test**

Append:

```python
@pytest.mark.asyncio
async def test_default_timeout_returns_504_and_cancels_the_endpoint() -> None:
    test_app = create_timeout_test_app(0.01)
    cancelled = asyncio.Event()

    @test_app.get("/api/v1/slow")
    async def slow_endpoint() -> dict[str, bool]:
        try:
            await asyncio.sleep(1)
            return {"completed": True}
        finally:
            cancelled.set()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/slow")

    assert response.status_code == 504
    assert response.json() == {
        "code": "API_TIMEOUT",
        "message": "요청 처리 시간이 초과되었습니다.",
    }
    assert cancelled.is_set()
```

- [ ] **Step 3: Run the default-timeout test and verify RED**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py::test_default_timeout_returns_504_and_cancels_the_endpoint -q
```

Expected: FAIL because `ApiTimeoutMiddleware` is not defined.

- [ ] **Step 4: Implement the common timeout and normal 504 response**

Extend `app/core/api_timeout.py` with:

```python
import asyncio
import logging

from fastapi.responses import ORJSONResponse
from starlette.routing import Match, Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_TIMEOUT_CONTENT = {
    "code": "API_TIMEOUT",
    "message": "요청 처리 시간이 초과되었습니다.",
}


class ApiTimeoutMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        router: Router,
        default_timeout_seconds: int | float,
        path_prefix: str = "/api/v1/",
    ) -> None:
        self._app = app
        self._router = router
        self._default_timeout_seconds = _normalize_timeout(default_timeout_seconds)
        self._path_prefix = path_prefix

    def _resolve_timeout(self, scope: Scope) -> float:
        return self._default_timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._path_prefix):
            await self._app(scope, receive, send)
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
                await self._app(scope, receive, tracked_send)
        except TimeoutError:
            logger.warning(
                "API request timed out method=%s path=%s timeout_seconds=%s",
                scope["method"],
                scope["path"],
                timeout_seconds,
            )
            if response_started:
                logger.error(
                    "API timeout occurred after response started method=%s path=%s",
                    scope["method"],
                    scope["path"],
                )
                return
            response = ORJSONResponse(status_code=504, content=_TIMEOUT_CONTENT)
            await response(scope, receive, send)
```

- [ ] **Step 5: Run the default-timeout test and verify GREEN**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py::test_default_timeout_returns_504_and_cancels_the_endpoint -q
```

Expected: PASS.

- [ ] **Step 6: Add failing individual override tests**

Append:

```python
@pytest.mark.asyncio
async def test_endpoint_can_extend_the_default_timeout() -> None:
    module = _load_timeout_module()
    api_timeout = getattr(module, "api_timeout")
    test_app = create_timeout_test_app(0.005)

    @test_app.get("/api/v1/extended")
    @api_timeout(0.05)
    async def extended_endpoint() -> dict[str, bool]:
        await asyncio.sleep(0.02)
        return {"completed": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/extended")

    assert response.status_code == 200
    assert response.json() == {"completed": True}


@pytest.mark.asyncio
async def test_endpoint_can_shorten_the_default_timeout() -> None:
    module = _load_timeout_module()
    api_timeout = getattr(module, "api_timeout")
    test_app = create_timeout_test_app(0.1)

    @test_app.get("/api/v1/shortened")
    @api_timeout(0.005)
    async def shortened_endpoint() -> dict[str, bool]:
        await asyncio.sleep(0.02)
        return {"completed": True}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/shortened")

    assert response.status_code == 504
```

- [ ] **Step 7: Run override tests and verify behavior**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: both override tests fail because endpoint metadata is not read yet: the extended endpoint receives 504 and the shortened endpoint incorrectly receives 200. These are the regressions the next step fixes.

- [ ] **Step 8: Implement endpoint metadata resolution and verify GREEN**

Replace `_resolve_timeout` with:

```python
def _resolve_timeout(self, scope: Scope) -> float:
    for route in self._router.routes:
        match, _ = route.matches(scope)
        if match is not Match.FULL:
            continue
        endpoint = getattr(route, "endpoint", None)
        return getattr(endpoint, _TIMEOUT_ATTRIBUTE, self._default_timeout_seconds)
    return self._default_timeout_seconds
```

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: both extension and shortening tests pass.

- [ ] **Step 9: Add API-exclusion, 404-preservation, and logging tests**

Append:

```python
@pytest.mark.asyncio
async def test_non_api_path_is_not_timed_out() -> None:
    test_app = create_timeout_test_app(0.005)

    @test_app.get("/health")
    async def health() -> dict[str, str]:
        await asyncio.sleep(0.02)
        return {"status": "ok"}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_missing_api_path_keeps_the_framework_404() -> None:
    test_app = create_timeout_test_app(0.05)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_timeout_log_contains_method_path_and_limit(caplog: pytest.LogCaptureFixture) -> None:
    test_app = create_timeout_test_app(0.005)

    @test_app.post("/api/v1/logged-timeout")
    async def logged_timeout() -> None:
        await asyncio.sleep(0.02)

    with caplog.at_level(logging.WARNING, logger="app.core.api_timeout"):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.post("/api/v1/logged-timeout")

    assert response.status_code == 504
    assert "method=POST" in caplog.text
    assert "path=/api/v1/logged-timeout" in caplog.text
    assert "timeout_seconds=0.005" in caplog.text
```

- [ ] **Step 10: Add the response-started edge-case test**

Use a minimal ASGI downstream app so the test checks emitted protocol messages rather than a framework mock:

```python
@pytest.mark.asyncio
async def test_timeout_after_response_start_does_not_send_a_second_response(caplog: pytest.LogCaptureFixture) -> None:
    module = _load_timeout_module()
    middleware_class = getattr(module, "ApiTimeoutMiddleware")
    router = FastAPI().router
    messages: list[dict] = []

    async def started_app(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await asyncio.sleep(0.02)

    middleware = middleware_class(started_app, router=router, default_timeout_seconds=0.005)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/stream",
        "raw_path": b"/api/v1/stream",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    with caplog.at_level(logging.ERROR, logger="app.core.api_timeout"):
        await middleware(scope, receive, send)

    assert [message["type"] for message in messages] == ["http.response.start"]
    assert "after response started" in caplog.text
```

- [ ] **Step 11: Run all middleware tests**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py -q
```

Expected: all Task 1 and Task 2 tests pass with no unhandled task warnings.

- [ ] **Step 12: Review the Task 2 diff without committing**

Run:

```bash
git diff -- app/core/api_timeout.py app/tests/test_api_timeout.py
```

Confirm the middleware does not alter non-API responses and never logs request bodies or headers.

### Task 3: Production application integration and usage documentation

**Files:**
- Modify: `app/main.py`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `app/tests/test_api_timeout_integration.py`

**Interfaces:**
- Consumes: `ApiTimeoutMiddleware` from Task 2
- Consumes: `config.API_TIMEOUT_SECONDS` from Task 1
- Produces: production middleware registration with `router=app.router`
- Produces: documented `@api_timeout(seconds)` usage and decorator order

- [ ] **Step 1: Add a failing integration test for registration and order**

Create `app/tests/test_api_timeout_integration.py`:

```python
from app.core import config
from app.core.api_timeout import ApiTimeoutMiddleware
from app.core.ocr_upload_middleware import OcrUploadSizeLimitMiddleware
from app.main import app


def test_production_app_registers_timeout_outside_ocr_upload_limit() -> None:
    middleware_classes = [entry.cls for entry in app.user_middleware]

    assert ApiTimeoutMiddleware in middleware_classes
    assert middleware_classes.index(ApiTimeoutMiddleware) < middleware_classes.index(OcrUploadSizeLimitMiddleware)


def test_production_timeout_uses_configured_default_and_router() -> None:
    entry = next(item for item in app.user_middleware if item.cls is ApiTimeoutMiddleware)

    assert entry.kwargs["default_timeout_seconds"] == config.API_TIMEOUT_SECONDS
    assert entry.kwargs["router"] is app.router
    assert entry.kwargs.get("path_prefix", "/api/v1/") == "/api/v1/"
```

- [ ] **Step 2: Run the integration test and verify RED**

Run:

```bash
uv run pytest app/tests/test_api_timeout_integration.py -q
```

Expected: FAIL because `app.main` has not registered `ApiTimeoutMiddleware`.

- [ ] **Step 3: Register the middleware in production**

In `app/main.py`, import the middleware:

```python
from app.core.api_timeout import ApiTimeoutMiddleware
```

Register it after the existing OCR middleware call so Starlette places it outside that middleware:

```python
app.add_middleware(OcrUploadSizeLimitMiddleware)
app.add_middleware(
    ApiTimeoutMiddleware,
    router=app.router,
    default_timeout_seconds=config.API_TIMEOUT_SECONDS,
    path_prefix="/api/v1/",
)
```

- [ ] **Step 4: Run integration and middleware tests**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py app/tests/test_api_timeout_integration.py -q
```

Expected: PASS.

- [ ] **Step 5: Document the environment setting**

Add to the server section of `.env.example`:

```dotenv
# /api/v1/** 공통 요청 처리 제한 시간(초)
API_TIMEOUT_SECONDS=3.0
```

- [ ] **Step 6: Document endpoint override usage**

Add an “API 처리시간 제한” subsection near the API development guidance in `README.md`:

````markdown
### API 처리시간 제한

`/api/v1/**` 요청은 `API_TIMEOUT_SECONDS`(기본 3초) 안에 응답해야 합니다.
개별 API가 다른 제한 시간을 필요로 하면 FastAPI 라우트 데코레이터 아래에
`@api_timeout(seconds)`를 둡니다.

```python
from app.core.api_timeout import api_timeout

@router.post("/slow-operation")
@api_timeout(10)
async def slow_operation():
    ...
```

제한을 넘으면 HTTP 504와 `API_TIMEOUT` 오류가 반환됩니다. 오래 걸리는 작업은
HTTP 요청 안에서 기다리지 말고 `background_jobs`와 ARQ worker로 넘깁니다.
````

- [ ] **Step 7: Review the Task 3 diff without committing**

Run:

```bash
git diff -- app/main.py .env.example README.md app/tests/test_api_timeout_integration.py
```

Confirm the middleware is outside the OCR upload middleware and the documented decorator order matches the implemented metadata lookup.

### Task 4: Regression and quality verification

**Files:**
- Verify: `app/core/config.py`
- Verify: `app/core/api_timeout.py`
- Verify: `app/main.py`
- Verify: `.env.example`
- Verify: `README.md`
- Verify: `app/tests/test_api_timeout.py`
- Verify: `app/tests/test_api_timeout_integration.py`

**Interfaces:**
- Consumes: all deliverables from Tasks 1–3
- Produces: evidence that timeout behavior and existing application behavior pass together

- [ ] **Step 1: Run focused timeout tests**

Run:

```bash
uv run pytest app/tests/test_api_timeout.py app/tests/test_api_timeout_integration.py -q
```

Expected: all timeout tests pass.

- [ ] **Step 2: Run existing middleware and API integration tests**

Run:

```bash
uv run pytest app/tests/test_static_mount.py app/tests/med_apis app/tests/admin_apis -q
```

Expected: all tests pass. If the known local MySQL session timezone regression reports `SYSTEM` instead of `+09:00`, report it separately and rerun excluding only `test_session_timezone_offset_is_kst`; do not alter timeout code to hide that environment issue.

- [ ] **Step 3: Run the full Python test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass, subject only to explicitly reported pre-existing environment failures.

- [ ] **Step 4: Run Ruff checks**

Run:

```bash
uv run ruff check app/core/config.py app/core/api_timeout.py app/main.py app/tests/test_api_timeout.py app/tests/test_api_timeout_integration.py
uv run ruff format --check app/core/config.py app/core/api_timeout.py app/main.py app/tests/test_api_timeout.py app/tests/test_api_timeout_integration.py
```

Expected: no lint findings and all files already formatted.

- [ ] **Step 5: Check the final scope without committing**

Run:

```bash
git status --short
git diff --stat
git diff -- app/core/config.py app/core/api_timeout.py app/main.py .env.example README.md app/tests/test_api_timeout.py app/tests/test_api_timeout_integration.py
```

Confirm no database migration, router rewrite, dependency addition, or unrelated user change is included. Leave all changes uncommitted.
