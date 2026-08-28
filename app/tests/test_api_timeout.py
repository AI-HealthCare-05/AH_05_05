import asyncio
import importlib
import logging
import math

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.config import Config


def _load_timeout_module():
    return importlib.import_module("app.core.api_timeout")


def test_api_timeout_setting_defaults_to_three_seconds():
    settings = Config(_env_file=None)

    assert settings.API_TIMEOUT_SECONDS == 3.0


@pytest.mark.parametrize("value", [0, -1, -0.1])
def test_api_timeout_setting_rejects_non_positive_values(value):
    with pytest.raises(ValidationError):
        Config(_env_file=None, API_TIMEOUT_SECONDS=value)


def test_api_timeout_decorator_stores_normalized_seconds():
    api_timeout = _load_timeout_module().api_timeout

    @api_timeout(7)
    async def endpoint():
        return None

    assert endpoint.__api_timeout_seconds__ == 7.0


@pytest.mark.parametrize("value", [0, -1, math.inf, -math.inf, math.nan])
def test_api_timeout_decorator_rejects_non_positive_or_non_finite_values(value):
    api_timeout = _load_timeout_module().api_timeout

    with pytest.raises(ValueError):
        api_timeout(value)


@pytest.mark.parametrize("value", [None, "3", True])
def test_api_timeout_decorator_rejects_non_numeric_values(value):
    api_timeout = _load_timeout_module().api_timeout

    with pytest.raises(TypeError):
        api_timeout(value)


def _create_timeout_test_app(default_timeout_seconds: float) -> FastAPI:
    timeout_module = _load_timeout_module()
    test_app = FastAPI()
    test_app.add_middleware(
        timeout_module.ApiTimeoutMiddleware,
        router=test_app.router,
        default_timeout_seconds=default_timeout_seconds,
        path_prefix="/api/v1/",
    )
    return test_app


@pytest.mark.asyncio
async def test_default_timeout_returns_504_and_cancels_endpoint():
    test_app = _create_timeout_test_app(0.01)
    cancelled = asyncio.Event()

    @test_app.get("/api/v1/slow")
    async def slow_endpoint():
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.set()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/slow")

    assert response.status_code == 504
    assert response.json() == {
        "code": "API_TIMEOUT",
        "message": "요청 처리 시간이 초과되었습니다.",
    }
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_endpoint_override_can_extend_default_timeout():
    timeout_module = _load_timeout_module()
    test_app = _create_timeout_test_app(0.005)

    @test_app.get("/api/v1/extended")
    @timeout_module.api_timeout(0.05)
    async def extended_endpoint():
        await asyncio.sleep(0.02)
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/extended")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_endpoint_override_can_shorten_default_timeout():
    timeout_module = _load_timeout_module()
    test_app = _create_timeout_test_app(0.1)

    @test_app.get("/api/v1/shortened")
    @timeout_module.api_timeout(0.005)
    async def shortened_endpoint():
        await asyncio.sleep(0.02)
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/shortened")

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_non_api_v1_path_is_not_timed_out():
    test_app = _create_timeout_test_app(0.005)

    @test_app.get("/health")
    async def health_endpoint():
        await asyncio.sleep(0.02)
        return {"status": "ok"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_api_v1_path_preserves_404_response():
    test_app = _create_timeout_test_app(0.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_timeout_log_contains_method_path_and_limit(caplog):
    test_app = _create_timeout_test_app(0.005)

    @test_app.post("/api/v1/logged")
    async def logged_endpoint():
        await asyncio.sleep(0.02)

    with caplog.at_level(logging.WARNING, logger="app.core.api_timeout"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/logged")

    assert response.status_code == 504
    assert "method=POST" in caplog.text
    assert "path=/api/v1/logged" in caplog.text
    assert "timeout_seconds=0.005" in caplog.text


@pytest.mark.asyncio
async def test_timeout_after_response_started_does_not_send_second_response(caplog):
    timeout_module = _load_timeout_module()
    messages = []

    async def started_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await asyncio.sleep(0.02)

    middleware = timeout_module.ApiTimeoutMiddleware(
        started_app,
        router=FastAPI().router,
        default_timeout_seconds=0.005,
        path_prefix="/api/v1/",
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/started",
        "raw_path": b"/api/v1/started",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    with caplog.at_level(logging.ERROR, logger="app.core.api_timeout"):
        await middleware(scope, receive, send)

    assert [message["type"] for message in messages].count("http.response.start") == 1
    assert "response_started=true" in caplog.text
