"""Run with --noconftest; review visibility uses only this in-memory SQLite database."""

from datetime import date

import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import AccountStatus
from app.models.supplement_nutrients import SupplementNutrient, UserSupplementNutrient
from app.models.users import User
from app.services.supplement_reviews import SupplementReviewService


@pytest_asyncio.fixture(autouse=True)
async def isolated_sqlite_database() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _user(email: str, name: str) -> User:
    return await User.create(
        email=email,
        hashed_password="unused",
        name=name,
        status=AccountStatus.ACTIVE,
    )


async def _registration(
    user: User,
    product: SupplementNutrient,
    *,
    score: int,
    review_body: str,
) -> UserSupplementNutrient:
    return await UserSupplementNutrient.create(
        user=user,
        supplement_nutrient=product,
        dose_amount="1.000",
        dose_unit="정",
        start_date=date(2026, 9, 1),
        score=score,
        review_body=review_body,
    )


async def test_reported_review_stays_hidden_only_for_reporter_and_counts_after_refresh() -> None:
    product = await SupplementNutrient.create(
        food_code="REVIEW-SQLITE-001",
        name="신고자별 숨김 제품",
        basis_qty="500mg",
        energy_kcal=0,
        protein_g="0.00",
        carb_g="0.00",
        serving_desc="1정",
        serving_size="500mg",
        daily_freq="1회",
    )
    visible_owner = await _user("visible-owner@example.com", "계속보임")
    reported_owner = await _user("reported-owner@example.com", "신고대상")
    reporter = await _user("reporter@example.com", "신고자")
    other_viewer = await _user("other-viewer@example.com", "다른조회자")
    visible = await _registration(
        visible_owner,
        product,
        score=5,
        review_body="신고하지 않은 후기",
    )
    reported = await _registration(
        reported_owner,
        product,
        score=3,
        review_body="신고 후 숨길 후기",
    )
    service = SupplementReviewService()

    before = await service.list(reporter, product.id, offset=0, limit=1)
    await service.report(reporter, reported.id)
    refreshed = await service.list(reporter, product.id, offset=0, limit=1)
    other_result = await service.list(other_viewer, product.id, offset=0, limit=10)

    assert [item.id for item in before.items] == [reported.id]
    assert (before.total, before.review_count, before.rating_average) == (2, 2, 4)
    assert [item.id for item in refreshed.items] == [visible.id]
    assert (refreshed.total, refreshed.review_count, refreshed.rating_average) == (1, 1, 5)
    assert [item.id for item in other_result.items] == [reported.id, visible.id]
    assert (other_result.total, other_result.review_count, other_result.rating_average) == (2, 2, 4)
