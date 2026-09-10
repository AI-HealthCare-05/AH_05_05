from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import AccountStatus, OcrJobStatus
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.admin_dashboard import AdminDashboardService


@pytest.fixture
async def isolated_sqlite_database() -> None:
    """Exercise dashboard aggregation without the repository MySQL test fixture."""
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


async def create_ocr_job(
    user: User,
    status_value: OcrJobStatus,
    created_at: datetime,
) -> None:
    job = await OcrJob.create(
        user=user,
        status=status_value,
        idempotency_key=f"dashboard-count-{status_value.value}-{created_at.timestamp()}",
        input_manifest={},
        avg_field_confidence=Decimal("0.8") if status_value is OcrJobStatus.COMPLETE else None,
        ocr_model="clova-template",
        structuring_model="rule-based",
        prompt_version="v1",
        schema_version="v1",
    )
    await OcrJob.filter(id=job.id).update(created_at=created_at)


async def test_ocr_documents_counts_cancelled_separately_within_selected_period(
    isolated_sqlite_database: None,
) -> None:
    now = datetime.now(config.TIMEZONE).replace(microsecond=0)
    start = now - timedelta(days=7)
    empty = await AdminDashboardService._ocr_documents(start, now)
    assert empty.model_dump(by_alias=True) == {
        "total": 0,
        "queued": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "avgFieldConfidence": None,
    }
    user = await User.create(
        email="dashboard-counts@example.com",
        hashed_password="test-only",
        status=AccountStatus.ACTIVE,
        name="대시보드 집계 사용자",
    )
    for status_value in (
        OcrJobStatus.QUEUED,
        OcrJobStatus.PROCESSING,
        OcrJobStatus.READY_FOR_REVIEW,
        OcrJobStatus.COMPLETE,
        OcrJobStatus.FAILED,
        OcrJobStatus.CANCELLED,
    ):
        await create_ocr_job(user, status_value, start + timedelta(days=1))
    await create_ocr_job(user, OcrJobStatus.CANCELLED, start - timedelta(seconds=1))

    stats = await AdminDashboardService._ocr_documents(start, now)

    assert stats.total == 6
    assert stats.queued == 3
    assert stats.completed == 1
    assert stats.failed == 1
    assert stats.cancelled == 1
    assert stats.total == stats.queued + stats.completed + stats.failed + stats.cancelled
    assert stats.avg_field_confidence == 0.8
