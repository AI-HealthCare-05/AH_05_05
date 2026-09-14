import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
)
from ai_worker.schemas.interaction import InteractionEntityKind as SearchEntityKind
from ai_worker.schemas.medication_search import (
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.enums import InteractionAliasType, InteractionEntityKind
from app.models.interactions import (
    InteractionEntity,
    InteractionEntityAlias,
    MedicationProductGuide,
)


class StaticSupplementIngredientCatalog:
    async def list_names(self) -> list[str]:
        return ["비타민 K"]


class FailingSupplementIngredientCatalog:
    async def list_names(self) -> list[str]:
        raise RuntimeError("Qdrant unavailable")

    async def list_entries(self) -> list[object]:
        raise RuntimeError("Qdrant unavailable")


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_catalog_combines_product_entity_and_alias_names(
    initialized_db: None,
) -> None:
    await MedicationProductGuide.create(
        item_seq="100",
        product_name="타이레놀정500밀리그람",
        manufacturer_name="테스트제약",
        efficacy="통증과 발열을 완화합니다.",
        usage_instructions="정해진 용법을 따릅니다.",
        pre_use_warning="성분을 확인합니다.",
        precautions="주의사항을 확인합니다.",
        drug_food_interactions="상호작용을 확인합니다.",
        adverse_reactions="이상반응을 확인합니다.",
        storage_instructions="실온 보관합니다.",
    )
    entity = await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="아세트아미노펜",
        normalized_name="아세트아미노펜",
    )
    await InteractionEntityAlias.create(
        interaction_entity=entity,
        alias_type=InteractionAliasType.PRODUCT_NAME,
        alias="해열진통제",
        normalized_alias="해열진통제",
    )

    result = await DbMedicationExpressionCatalog().list_expressions()

    assert {
        "아세트아미노펜",
        "타이레놀",
        "타이레놀정500밀리그람",
        "해열진통제",
    }.issubset(result)

    entries = await DbMedicationExpressionCatalog().list_entries()
    alias_entry = next(entry for entry in entries if entry.aliases == ["해열진통제"])
    assert alias_entry.canonical_name == "아세트아미노펜"
    assert alias_entry.entity_type == MedicationQueryEntityType.BRAND_ALIAS
    assert alias_entry.kind == SearchEntityKind.DRUG
    assert alias_entry.source == MedicationQueryEntitySource.RDBMS


@pytest.mark.asyncio
async def test_catalog_includes_product_name_without_parenthetical_ingredient(
    initialized_db: None,
) -> None:
    await MedicationProductGuide.create(
        item_seq="200",
        product_name="마그오캡슐500mg(산화마그네슘)",
        manufacturer_name="테스트제약",
        efficacy="제산 작용에 사용합니다.",
        usage_instructions="정해진 용법을 따릅니다.",
        pre_use_warning="성분을 확인합니다.",
        precautions="주의사항을 확인합니다.",
        drug_food_interactions="상호작용을 확인합니다.",
        adverse_reactions="이상반응을 확인합니다.",
        storage_instructions="실온 보관합니다.",
    )

    result = await DbMedicationExpressionCatalog().list_expressions()

    assert "마그오캡슐500mg(산화마그네슘)" in result
    assert "마그오캡슐500mg" in result
    assert "마그오" in result


@pytest.mark.asyncio
async def test_catalog_does_not_turn_a_product_name_ending_in_san_into_another_brand_alias(
    initialized_db: None,
) -> None:
    """`타이레놀`과 `타이레놀산`은 서로 다른 제품명으로 해석한다."""

    for item_seq, product_name in (
        ("301", "타이레놀정500밀리그람(아세트아미노펜)"),
        ("302", "타이레놀산500밀리그램(아세트아미노펜)"),
    ):
        await MedicationProductGuide.create(
            item_seq=item_seq,
            product_name=product_name,
            manufacturer_name="테스트제약",
            efficacy="통증 완화",
            usage_instructions="정해진 용법을 따릅니다.",
            pre_use_warning="주의사항을 확인합니다.",
            precautions="",
            drug_food_interactions="",
            adverse_reactions="",
            storage_instructions="",
        )

    entries = await DbMedicationExpressionCatalog().list_entries()
    aliases_by_product = {entry.canonical_name: entry.aliases for entry in entries}

    assert "타이레놀" in aliases_by_product["타이레놀정500밀리그람(아세트아미노펜)"]
    assert "타이레놀" not in aliases_by_product["타이레놀산500밀리그램(아세트아미노펜)"]


@pytest.mark.asyncio
async def test_catalog_includes_dynamic_qdrant_ingredient_names(
    initialized_db: None,
) -> None:
    catalog = DbMedicationExpressionCatalog(
        supplement_catalog=StaticSupplementIngredientCatalog(),
    )

    result = await catalog.list_expressions()

    assert "비타민 K" in result


@pytest.mark.asyncio
async def test_catalog_includes_shared_general_supplement_vocabulary(
    initialized_db: None,
) -> None:
    entries = await DbMedicationExpressionCatalog().list_entries()

    omega3 = next(entry for entry in entries if entry.canonical_name == "오메가3")
    assert omega3.entity_type == MedicationQueryEntityType.INGREDIENT_NAME
    assert omega3.kind == SearchEntityKind.SUPPLEMENT
    assert omega3.source == MedicationQueryEntitySource.CATALOG


@pytest.mark.asyncio
async def test_catalog_keeps_rdbms_entries_when_qdrant_catalog_fails(
    initialized_db: None,
) -> None:
    await MedicationProductGuide.create(
        item_seq="300",
        product_name="검증약정",
        manufacturer_name="테스트제약",
        efficacy="효능",
        usage_instructions="용법",
        pre_use_warning="사전 주의",
        precautions="주의",
        drug_food_interactions="상호작용",
        adverse_reactions="이상반응",
        storage_instructions="보관",
    )
    catalog = DbMedicationExpressionCatalog(
        supplement_catalog=FailingSupplementIngredientCatalog(),
    )

    entries = await catalog.list_entries()

    assert any(entry.canonical_name == "검증약정" for entry in entries)
