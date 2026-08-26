import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS


@pytest_asyncio.fixture(autouse=True)
async def initialize() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
