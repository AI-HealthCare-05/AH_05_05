import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.domain.medication_question_resolver import RuleBasedMedicationQuestionResolver
from ai_worker.rag import ingredient_name_aliases
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
    def __init__(self, names: list[str] | None = None) -> None:
        self._names = names if names is not None else ["비타민 K"]

    async def list_names(self) -> list[str]:
        return self._names


@pytest.fixture
def matched_ingredient_aliases(monkeypatch):
    monkeypatch.setattr(
        ingredient_name_aliases,
        "_active_collection",
        ingredient_name_aliases.load_ingredient_name_aliases().source_collection,
    )
    ingredient_name_aliases._alias_pairs.cache_clear()
    yield
    ingredient_name_aliases._alias_pairs.cache_clear()


@pytest.mark.parametrize("drug_names", [("와파린",), ("warfarin",), ("와파린", "warfarin")])
async def test_catalog_resolves_english_and_korean_to_the_same_canonical_pair(
    initialized_db, matched_ingredient_aliases, drug_names
):
    for name in drug_names:
        await InteractionEntity.create(
            entity_kind=InteractionEntityKind.DRUG,
            canonical_name=name,
            normalized_name=name,
        )
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=DbMedicationExpressionCatalog(supplement_catalog=StaticSupplementIngredientCatalog())
    )

    for question in ("warfarin과 vitamin K 상호작용 알려줘", "와파린과 비타민 K 상호작용 알려줘"):
        result = await resolver.resolve(question=question)
        assert [(entity.canonical_name, entity.kind, entity.resolution_status) for entity in result.entities] == [
            ("와파린", SearchEntityKind.DRUG, "RESOLVED"),
            ("비타민 K", SearchEntityKind.SUPPLEMENT, "RESOLVED"),
        ]
        assert {"와파린", "warfarin"}.issubset(result.entities[0].search_aliases)
        assert "vitamin K" in result.entities[1].search_aliases


@pytest.mark.parametrize("canonical_name, query", [("비타민 K", "vitamin K"), ("비타민B12", "vitamin B12")])
async def test_catalog_adds_generic_vitamin_equivalence_only_for_existing_names(initialized_db, canonical_name, query):
    catalog = DbMedicationExpressionCatalog(
        supplement_catalog=StaticSupplementIngredientCatalog([canonical_name, "비타민복합체", "비타민 K 추출물"])
    )
    result = await RuleBasedMedicationQuestionResolver(catalog=catalog).resolve(question=f"{query} 효능 알려줘")

    assert [entity.canonical_name for entity in result.entities] == [canonical_name]
    expressions = await catalog.list_expressions()
    assert "vitamin Z99" not in expressions
    assert "vitamin복합체" not in expressions
    assert "vitamin K 추출물" not in expressions


async def test_catalog_does_not_create_vitamin_k_when_absent(initialized_db):
    expressions = await DbMedicationExpressionCatalog().list_expressions()
    assert "vitamin K" not in expressions
    assert "비타민 K" not in expressions


@pytest.mark.parametrize("canonical_name, forbidden", [("와파린", "warfarin"), ("warfarin", "와파린")])
async def test_catalog_disables_reviewed_aliases_for_collection_mismatch(
    initialized_db, matched_ingredient_aliases, canonical_name, forbidden
):
    ingredient_name_aliases.use_collection("unreviewed-collection")
    await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name=canonical_name,
        normalized_name=canonical_name,
    )
    expressions = await DbMedicationExpressionCatalog().list_expressions()
    assert canonical_name in expressions
    assert forbidden not in expressions


async def test_catalog_does_not_resolve_chlorphentermine_as_phentermine(initialized_db, matched_ingredient_aliases):
    await InteractionEntity.create(
        entity_kind=InteractionEntityKind.DRUG,
        canonical_name="펜터민",
        normalized_name="펜터민",
    )
    catalog = DbMedicationExpressionCatalog()
    resolver = RuleBasedMedicationQuestionResolver(catalog=catalog)
    positive = await resolver.resolve(question="phentermine 효능 알려줘")
    assert [entity.canonical_name for entity in positive.entities] == ["펜터민"]
    negative = await resolver.resolve(question="chlorphentermine 효능 알려줘")
    assert negative.entities == []
    assert "chlorphentermine" not in await catalog.list_expressions()


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["밀리그램", "밀리그람"])
async def test_catalog_unit_spelling_resolves_the_exact_strength_and_form(initialized_db, unit):
    for index, name in enumerate(
        [
            "타이레놀정500밀리그람(아세트아미노펜)",
            "타이레놀정160밀리그람(아세트아미노펜)",
            "타이레놀산500밀리그램(아세트아미노펜)",
        ]
    ):
        await MedicationProductGuide.create(
            item_seq=str(index),
            product_name=name,
            manufacturer_name="테스트제약",
            efficacy="효능",
            usage_instructions="용법",
            pre_use_warning="경고",
            precautions="주의",
            drug_food_interactions="상호작용",
            adverse_reactions="이상반응",
            storage_instructions="보관",
        )
    resolver = RuleBasedMedicationQuestionResolver(catalog=DbMedicationExpressionCatalog(product_names_only=True))
    result = await resolver.resolve(question=f"타이레놀정500{unit} 효능 알려줘")
    assert result.status != "CLARIFICATION_REQUIRED"
    assert [entity.canonical_name for entity in result.entities] == ["타이레놀정500밀리그람(아세트아미노펜)"]


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
