import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.medication_product_guide_repository import (
    DbMedicationProductGuideRepository,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.interactions import MedicationProductGuide


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _create_guide(item_seq: str, product_name: str) -> MedicationProductGuide:
    return await MedicationProductGuide.create(
        item_seq=item_seq,
        product_name=product_name,
        manufacturer_name="테스트제약",
        efficacy="통증과 발열을 완화합니다.",
        usage_instructions="제품 설명서와 전문가의 안내를 따릅니다.",
        pre_use_warning="성분을 확인합니다.",
        precautions="정해진 용법을 지킵니다.",
        drug_food_interactions="다른 약 복용 시 전문가에게 알립니다.",
        adverse_reactions="이상반응 발생 시 전문가와 상담합니다.",
        storage_instructions="실온에 보관합니다.",
    )


@pytest.mark.asyncio
async def test_product_guide_repository_returns_exact_match(
    initialized_db: None,
) -> None:
    guide = await _create_guide("100", "타이레놀정500밀리그람")

    result = await DbMedicationProductGuideRepository().find_by_name(
        " 타이레놀정500밀리그람 ",
    )

    assert result.is_ambiguous is False
    assert result.guide is not None
    assert result.guide.medication_guide_id == guide.id


@pytest.mark.asyncio
async def test_product_guide_repository_does_not_guess_ambiguous_name(
    initialized_db: None,
) -> None:
    await _create_guide("100", "타이레놀정500밀리그람")
    await _create_guide("200", "타이레놀8시간이알서방정")

    result = await DbMedicationProductGuideRepository().find_by_name("타이레놀")

    assert result.is_ambiguous is True
    assert result.guide is None
    assert result.candidate_names == [
        "타이레놀8시간이알서방정",
        "타이레놀정500밀리그람",
    ]


@pytest.mark.asyncio
async def test_product_guide_repository_selects_family_reference_from_same_ingredient(
    initialized_db: None,
) -> None:
    await _create_guide(
        "100",
        "타이레놀8시간이알서방정(아세트아미노펜)",
    )
    reference = await _create_guide(
        "200",
        "타이레놀정500밀리그람(아세트아미노펜)",
    )
    await _create_guide(
        "300",
        "타이레놀콜드-에스정",
    )

    result = await DbMedicationProductGuideRepository().find_by_name(
        "타이레놀",
    )

    assert result.is_ambiguous is True
    assert result.guide is None
    assert result.representative_guide is not None
    assert result.representative_guide.medication_guide_id == reference.id
