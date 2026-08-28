import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest
from _pytest.fixtures import FixtureRequest
from pydantic import SecretStr
from tortoise import generate_config
from tortoise.contrib.test import SimpleTestCase, finalizer, initializer

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS

TEST_BASE_URL = "http://test"
TEST_DB_LABEL = "models"
TEST_DB_TZ = "Asia/Seoul"
_TEST_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
TEST_PHONE_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

# 테스트 DB에 저장된 전화번호도 운영과 같은 Fernet 경로를 사용한다.
config.PHONE_ENCRYPTION_KEY = SecretStr(TEST_PHONE_ENCRYPTION_KEY)


def _setup_tortoise_test_runner(test_case: SimpleTestCase) -> None:
    """Reuse the loop that owns the MySQL pool on Python 3.13/pytest 9."""

    if _TEST_EVENT_LOOP is None:
        raise RuntimeError("Tortoise test event loop is not initialized")
    test_case._asyncioRunner = asyncio.Runner(  # type: ignore[attr-defined]  # noqa: SLF001
        debug=True,
        loop_factory=lambda: _TEST_EVENT_LOOP,
    )


SimpleTestCase._setupAsyncioRunner = _setup_tortoise_test_runner  # type: ignore[method-assign]  # noqa: SLF001


def get_test_db_config() -> dict[str, Any]:
    tortoise_config = generate_config(
        db_url=f"mysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/test",
        app_modules={TEST_DB_LABEL: TORTOISE_APP_MODELS},
        connection_label=TEST_DB_LABEL,
        testing=True,
    )
    tortoise_config["timezone"] = TEST_DB_TZ

    return tortoise_config


@pytest.fixture(scope="session", autouse=True)
def initialize(request: FixtureRequest) -> Generator[None, None]:
    global _TEST_EVENT_LOOP

    loop = asyncio.new_event_loop()
    _TEST_EVENT_LOOP = loop
    asyncio.set_event_loop(loop)
    with patch("tortoise.contrib.test.getDBConfig", Mock(return_value=get_test_db_config())):
        initializer(modules=TORTOISE_APP_MODELS, loop=loop)
    yield
    finalizer()
    loop.close()
    _TEST_EVENT_LOOP = None
