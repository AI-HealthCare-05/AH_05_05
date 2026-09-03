import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
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
        is_preferred=True,
    )

    result = await DbMedicationExpressionCatalog().list_expressions()

    assert result == [
        "아세트아미노펜",
        "타이레놀",
        "타이레놀정500밀리그람",
        "해열진통제",
    ]


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
async def test_catalog_includes_dynamic_qdrant_ingredient_names(
    initialized_db: None,
) -> None:
    catalog = DbMedicationExpressionCatalog(
        supplement_catalog=StaticSupplementIngredientCatalog(),
    )

    result = await catalog.list_expressions()

    assert "비타민 K" in result
