import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.repositories.medication_product_guide_repository import (
    DbMedicationProductGuideRepository,
)
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.interactions import MedicationProductGuide


def _report_repository():
    from ai_worker.core.config import Config
    from ai_worker.services.intake_report_core_service import build_intake_report_core_service

    service = build_intake_report_core_service(
        settings=Config(OPENAI_API_KEY="offline-test-key", KNOWLEDGE_SEARCH_MODE="DENSE", _env_file=None),
        qdrant_client=object(),
    )
    repository = service._use_case._guide_repository
    repository._candidate_selector = _CandidateSelector(None)
    return repository


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


@pytest.mark.parametrize("query", ["타이래늘", "타이래놀"])
async def test_report_typo_finds_candidates_without_guessing_strength(initialized_db, query):
    names = ["타이레놀정500밀리그람", "타이레놀8시간이알서방정"]
    for index, name in enumerate(names):
        await _create_guide(str(index), name)

    result = await _report_repository().find_by_name(query)

    assert result.is_ambiguous
    assert result.guide is None
    assert result.representative_guide is None
    assert set(result.candidate_names) == set(names)
    assert result.original_name == query


@pytest.mark.parametrize("query", ["타이래놀정500밀리그람", "타이 레놀정500밀리그람"])
async def test_report_connects_unique_typo_with_unchanged_product_details(initialized_db, query):
    guide = await _create_guide("100", "타이레놀정500밀리그람")
    await _create_guide("200", "타이레놀정160밀리그람")

    result = await _report_repository().find_by_name(query)

    assert not result.is_ambiguous
    assert result.guide is not None
    assert result.guide.medication_guide_id == guide.id


@pytest.mark.parametrize("query", ["타이래놀정250밀리그람", "타이래놀서방정500밀리그람", "아무제품", "타"])
async def test_report_never_corrects_strength_form_or_unrelated_name(initialized_db, query):
    await _create_guide("100", "타이레놀정500밀리그람")

    result = await _report_repository().find_by_name(query)

    assert result.guide is None


async def test_report_bare_typo_needs_confirmation_even_with_one_catalog_product(initialized_db):
    await _create_guide("100", "타이레놀정500밀리그람")

    result = await _report_repository().find_by_name("타이래놀")

    assert result.is_ambiguous
    assert result.guide is None
    assert result.candidate_names == ["타이레놀정500밀리그람"]


@pytest.mark.parametrize("query", ["타이레놀", "타이레놀정500밀리그", "레놀정500", "타이레놀정50"])
async def test_report_partial_substring_cannot_bypass_product_identity_guard(initialized_db, query):
    await _create_guide("100", "타이레놀정500밀리그람")
    result = await _report_repository().find_by_name(query)

    assert result.guide is None
    assert result.is_ambiguous
    assert result.original_name == query
    assert result.candidate_names == ["타이레놀정500밀리그람"]


async def test_report_does_not_choose_between_equally_close_brand_names(initialized_db):
    await _create_guide("100", "타이레놀정500밀리그람")
    await _create_guide("200", "타이레날정500밀리그람")

    result = await _report_repository().find_by_name("타이레늘정500밀리그람")

    assert result.guide is None
    assert result.is_ambiguous
    assert len(result.candidate_names) == 2


async def test_report_candidates_are_visible_without_changing_registered_name(initialized_db):
    from ai_worker.assemblers.intake_report_assembler import IntakeReportAssembler
    from ai_worker.schemas.medication_chat import ActiveIntakeContext, ActiveMedication

    await _create_guide("100", "타이레놀정500밀리그람")
    lookup = await _report_repository().find_by_name("타이래늘")
    draft = IntakeReportAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(medication_id=1, care_episode_id=1, name="타이래늘"),
            ],
        ),
        guide_lookups=[lookup],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.current_stack[0].product_name == "타이래늘"
    notice = next(item for item in draft.unverified_items if "제품명 후보" in item.message)
    assert "타이래늘" in notice.message
    assert "타이레놀정500밀리그람" in notice.message
    assert "확정되지 않아" in notice.message


async def test_report_binds_only_confirmed_typo_and_preserves_both_registrations(initialized_db):
    from ai_worker.schemas.medication_chat import ActiveIntakeContext, ActiveMedication
    from ai_worker.tests.use_cases.test_generate_intake_report import (
        FakeContextProvider,
        FakeGenerator,
        FakeRetriever,
        FakeRuleRepository,
    )
    from ai_worker.use_cases.generate_intake_report import GenerateIntakeReportUseCase

    guide = await _create_guide("100", "타이레놀정500밀리그람")
    names = ["타이래놀정500밀리그람", "타이래늘"]
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(medication_id=index + 1, care_episode_id=1, name=name) for index, name in enumerate(names)
        ],
    )
    generator = FakeGenerator()

    result = await GenerateIntakeReportUseCase(
        context_provider=FakeContextProvider(context),
        guide_repository=_report_repository(),
        interaction_rule_repository=FakeRuleRepository(),
        knowledge_retriever=FakeRetriever(),
        generator=generator,
    ).execute(user_id=1)

    assert [item.product_name for item in result.current_stack] == names
    assert generator.draft.guide_item_bindings == {1: guide.id}
    assert [item.product_name for item in generator.draft.guide_evidence] == [guide.product_name]


async def test_report_catalog_queries_only_products_and_reuses_snapshot(initialized_db, monkeypatch):
    from ai_worker.repositories.medication_expression_catalog_repository import DbMedicationExpressionCatalog
    from app.models.interactions import InteractionEntity
    from app.models.supplement_nutrients import SupplementNutrient

    await _create_guide("100", "타이레놀정500밀리그람")

    def unexpected_query():
        raise AssertionError("보고서 약명 후보 검색은 다른 카탈로그를 조회하지 않아야 합니다.")

    monkeypatch.setattr(InteractionEntity, "all", unexpected_query)
    monkeypatch.setattr(SupplementNutrient, "all", unexpected_query)
    catalog = DbMedicationExpressionCatalog(product_names_only=True)
    entries = await catalog.list_entries()
    monkeypatch.setattr(MedicationProductGuide, "all", unexpected_query)

    assert [entry.canonical_name for entry in entries] == ["타이레놀정500밀리그람"]
    assert await catalog.list_entries() == entries


@pytest.mark.parametrize("typo", ["아스피힌", "아스피흰"])
@pytest.mark.parametrize("unit", ["밀리그램", "밀리그람", "mg"])
async def test_report_selects_dominant_typo_among_multiple_products(initialized_db, typo, unit):
    guide = await _create_guide("100", f"아스피린프로텍트정100{unit}(아스피린)")
    await _create_guide("200", "아스피린장용정100밀리그램(아스피린)")
    await _create_guide("300", "우르콜정100밀리그램")

    query = f"{typo}프로텍트정100밀리그램"
    result = await _report_repository().find_by_name(query)

    assert result.guide is not None
    assert result.guide.medication_guide_id == guide.id
    assert result.original_name == query
    assert result.is_inferred is True
    assert result.is_ambiguous is False


@pytest.mark.parametrize(
    "candidate",
    [
        "아스피린프로텍트정100그램",
        "아스피린프로텍트정100마이크로그램",
        "아스피린프로텍트정200밀리그람",
        "아스피린프로텍트서방정100밀리그람",
    ],
)
async def test_report_unit_spelling_correction_keeps_strength_and_form_guards(initialized_db, candidate):
    await _create_guide("100", candidate)
    result = await _report_repository().find_by_name("아스피흰프로텍트정100밀리그램")
    assert result.guide is None


class _CandidateSelector:
    def __init__(self, selected_id):
        self.selected_id = selected_id
        self.calls = []

    async def select(self, *, query, candidates):
        self.calls.append((query, candidates))
        return self.selected_id


async def test_report_unknown_form_typo_requires_selector_confirmation(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    guide = await _create_guide("100", "아스피린프로텍트정100밀리그람")
    query = "아스피흰프로텍트청100밀리그람"
    selector = _CandidateSelector(guide.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name(query)
    assert result.guide is not None
    assert result.guide.medication_guide_id == guide.id
    assert result.original_name == query
    assert result.is_inferred is True
    assert selector.calls[0][0] == query

    without_confirmation = await ReportMedicationGuideRepository().find_by_name(query)
    assert without_confirmation.guide is None
    assert without_confirmation.is_ambiguous is True


@pytest.mark.parametrize(
    "query",
    [
        "아스피흰프로텍트액100밀리그람",
        "아스피흰프로텍트서방정100밀리그람",
        "아스피흰프로텍트100밀리그람",
        "아스피흰프로텍트청200밀리그람",
        "아스피흰프로텍트청100그램",
        "아스피흰프로텍트캡슐100밀리그람",
    ],
)
async def test_report_form_correction_does_not_infer_known_or_missing_forms(initialized_db, query):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    guide = await _create_guide("100", "아스피린프로텍트정100밀리그람")
    selector = _CandidateSelector(guide.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name(query)
    assert result.guide is None
    assert selector.calls == []


async def test_report_uses_llm_only_for_guarded_dominant_borderline_typo(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    guide = await _create_guide("100", "타이레놀정500밀리그람")
    await _create_guide("200", "아세트정500밀리그람")
    selector = _CandidateSelector(guide.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name("타이래늘정500밀리그람")

    assert result.guide is not None
    assert result.guide.medication_guide_id == guide.id
    assert result.is_inferred is True
    assert len(selector.calls) == 1
    assert selector.calls[0][0] == "타이래늘정500밀리그람"
    assert len(selector.calls[0][1]) == 2


async def test_report_llm_disagreement_cannot_select_the_runner_up(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    await _create_guide("100", "타이레놀정500밀리그람")
    runner_up = await _create_guide("200", "아세트정500밀리그람")
    selector = _CandidateSelector(runner_up.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name("타이래늘정500밀리그람")

    assert result.guide is None
    assert result.is_ambiguous
    assert len(selector.calls) == 1


async def test_report_high_confidence_or_exact_match_does_not_call_llm(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    await _create_guide("100", "타이레놀정500밀리그람")
    selector = _CandidateSelector(None)
    repository = ReportMedicationGuideRepository(candidate_selector=selector)
    for query in ["타이레놀정500밀리그람", "타이래놀정500밀리그람"]:
        result = await repository.find_by_name(query)
        assert result.guide is not None
    assert selector.calls == []


async def test_report_optional_selector_failure_abstains_without_failing_report(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    class FailingSelector:
        async def select(self, **kwargs):
            raise RuntimeError("offline failure")

    await _create_guide("100", "타이레놀정500밀리그람")
    result = await ReportMedicationGuideRepository(candidate_selector=FailingSelector()).find_by_name(
        "타이래늘정500밀리그람"
    )
    assert result.guide is None
    assert result.is_ambiguous


@pytest.mark.parametrize("selected_id", [None, 999999, True, "1"])
async def test_report_llm_cannot_invent_or_coerce_a_selected_product(initialized_db, selected_id):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    await _create_guide("100", "타이레놀정500밀리그람")
    selector = _CandidateSelector(selected_id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name("타이래늘정500밀리그람")

    assert result.guide is None
    assert result.is_ambiguous
    assert len(selector.calls) == 1


@pytest.mark.parametrize(
    "query",
    ["타이래늘", "타이래늘정", "타이래늘정250밀리그람", "타이래늘서방정500밀리그람", "아무제품정500밀리그람"],
)
async def test_report_never_asks_llm_to_override_identity_or_weak_similarity(initialized_db, query):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    guide = await _create_guide("100", "타이레놀정500밀리그람")
    selector = _CandidateSelector(guide.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name(query)

    assert result.guide is None
    assert selector.calls == []


async def test_report_does_not_let_llm_break_a_near_tie(initialized_db):
    from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository

    guide = await _create_guide("100", "타이레놀정500밀리그람")
    await _create_guide("200", "타이레날정500밀리그람")
    selector = _CandidateSelector(guide.id)
    result = await ReportMedicationGuideRepository(candidate_selector=selector).find_by_name("타이레늘정500밀리그람")

    assert result.guide is None
    assert selector.calls == []


async def test_report_known_ingredient_conflict_blocks_typo_connection(initialized_db):
    await _create_guide("100", "타이레놀정500밀리그람(아세트아미노펜)")
    result = await _report_repository().find_by_name("타이래놀정500밀리그람(다른성분)")
    assert result.guide is None


async def test_report_rechecks_dominance_after_catalog_changes(initialized_db):
    repository = _report_repository()
    await _create_guide("100", "타이레놀정500밀리그람")
    assert (await repository.find_by_name("타이레늘정500밀리그람")).guide is not None
    await _create_guide("200", "타이레날정500밀리그람")

    result = await repository.find_by_name("타이레늘정500밀리그람")
    assert result.guide is None
    assert result.is_ambiguous


@pytest.mark.parametrize(
    "query,product",
    [
        ("타이레놀정500밀리그람", "타이레놀큐정500밀리그람"),
        ("타이레놀큐정500밀리그람", "타이레놀정500밀리그람"),
    ],
)
async def test_report_cannot_add_or_remove_a_brand_variant_suffix(initialized_db, query, product):
    await _create_guide("100", product)
    assert (await _report_repository().find_by_name(query)).guide is None


@pytest.mark.parametrize("annotation", ["(글루타티온(환원형))", "(카르보시스테인)(수출명:HyundiolCapsule375Mg)"])
async def test_report_handles_balanced_product_annotations_without_changing_identity(initialized_db, annotation):
    guide = await _create_guide("100", "리나치올캡슐375밀리그램" + annotation)
    direct = await _report_repository().find_by_name("리나치올캡슐375밀리그램")
    assert direct.guide is not None
    assert direct.guide.medication_guide_id == guide.id
    assert not direct.is_inferred
    corrected = await _report_repository().find_by_name("리나치울캡슐375밀리그램")
    assert corrected.guide is not None
    assert corrected.guide.medication_guide_id == guide.id
    assert corrected.is_inferred
