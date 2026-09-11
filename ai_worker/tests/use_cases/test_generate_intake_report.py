from datetime import date
from types import SimpleNamespace

from ai_worker.assemblers.intake_report_assembler import IntakeReportAssembler
from ai_worker.schemas.intake_report import (
    IntakeReportFallbackReason,
    IntakeReportGenerationOutcome,
    IntakeReportNutrientTotal,
    IntakeReportStatus,
)
from ai_worker.schemas.knowledge import (
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    MedicationGuideFact,
    MedicationGuideLookup,
)
from ai_worker.use_cases.generate_intake_report import GenerateIntakeReportUseCase


class FakeContextProvider:
    def __init__(self, context: ActiveIntakeContext) -> None:
        self.context = context

    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext:
        assert care_episode_id is None
        assert user_id == self.context.user_id
        return self.context


class FakeGuideRepository:
    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        raise AssertionError(f"의약품이 없으면 호출하면 안 됩니다: {product_name}")


class FakeRuleRepository:
    async def find_approved_rules(self, **_: object) -> list:
        return []


class FakeRetriever:
    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    async def search_with_diagnostics(self, **_: object) -> KnowledgeRetrievalResult:
        self.calls += 1
        if self.unavailable:
            raise RuntimeError("qdrant unavailable")
        return KnowledgeRetrievalResult(
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=0,
                entity_filtered_count=0,
                broad_candidate_count=0,
                fallback_used=False,
                eligible_candidate_count=0,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=0,
            )
        )


class FakeGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.draft = None

    async def generate(self, *, draft) -> IntakeReportGenerationOutcome:
        self.calls += 1
        self.draft = draft
        return IntakeReportGenerationOutcome(
            report_markdown=draft.deterministic_markdown,
            fallback_used=False,
        )


def _supplement_context() -> ActiveIntakeContext:
    return ActiveIntakeContext(
        user_id=1,
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=10,
                name="마그네슘",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 9, 1),
            )
        ],
    )


def _use_case(
    *,
    context: ActiveIntakeContext,
    retriever: FakeRetriever,
    generator: FakeGenerator,
) -> GenerateIntakeReportUseCase:
    return GenerateIntakeReportUseCase(
        context_provider=FakeContextProvider(context),
        guide_repository=FakeGuideRepository(),
        interaction_rule_repository=FakeRuleRepository(),
        knowledge_retriever=retriever,
        generator=generator,
        assembler=IntakeReportAssembler(),
    )


async def test_use_case_returns_empty_without_openai_or_qdrant_call() -> None:
    retriever = FakeRetriever()
    generator = FakeGenerator()
    use_case = _use_case(
        context=ActiveIntakeContext(user_id=1),
        retriever=retriever,
        generator=generator,
    )

    result = await use_case.execute(user_id=1)

    assert result.status == IntakeReportStatus.EMPTY
    assert generator.calls == 0
    assert retriever.calls == 0


async def test_evidence_locked_generator_does_not_depend_on_unused_rag() -> None:
    class EvidenceLockedGenerator(FakeGenerator):
        uses_knowledge_evidence = False

    retriever = FakeRetriever(unavailable=True)
    generator = EvidenceLockedGenerator()
    result = await _use_case(context=_supplement_context(), retriever=retriever, generator=generator).execute(user_id=1)

    assert retriever.calls == 0
    assert generator.calls == 1
    assert generator.draft.knowledge_evidence == []
    assert result.data_availability.rag_evidence_available is False
    assert result.status == IntakeReportStatus.COMPLETED
    assert all(item.title != "추가 검색 근거 확인 필요" for item in result.unverified_items)


async def test_real_report_keeps_retrieval_and_generation_with_calculated_nutrients() -> None:
    context = _supplement_context()
    retriever, generator = FakeRetriever(), FakeGenerator()

    async def load_nutrients(actual_context):
        assert actual_context.user_id == 1
        return SimpleNamespace(
            totals=[
                IntakeReportNutrientTotal(
                    nutrient_name="철",
                    daily_total="7 mg",
                    calculation_status="LABEL_SCHEDULE",
                    amount="7",
                    unit="mg",
                    reference_value="10",
                    reference_kind="RNI",
                    reference_percent="70",
                    included_product_names=["마그네슘"],
                )
            ],
            profile_label="남자 · 30-49세",
            basis_note="제품 안내량 기준 · 실제 복용량 아님",
            product_labels={10: "제품 안내량 · 하루 1정"},
        )

    use_case = GenerateIntakeReportUseCase(
        context_provider=FakeContextProvider(context),
        guide_repository=FakeGuideRepository(),
        interaction_rule_repository=FakeRuleRepository(),
        knowledge_retriever=retriever,
        generator=generator,
        nutrient_loader=load_nutrients,
    )
    result = await use_case.execute(user_id=1)
    assert retriever.calls == generator.calls == 1
    assert generator.draft.profile_label == result.profile_label == "남자 · 30-49세"
    assert generator.draft.nutrient_totals[0].reference_percent == "70"
    assert result.presentation_version == "ai-report-v2"
    assert result.fallback_used is False
    assert result.nutrient_totals[0].amount == "7"
    assert "7 mg" in generator.draft.deterministic_markdown


async def test_model_fallback_is_partial_and_visible_to_caller() -> None:
    class FailingGenerator(FakeGenerator):
        async def generate(self, *, draft):
            return IntakeReportGenerationOutcome(
                report_markdown=draft.deterministic_markdown,
                fallback_used=True,
                fallback_reason=IntakeReportFallbackReason.CLIENT_ERROR,
            )

    result = await _use_case(
        context=_supplement_context(),
        retriever=FakeRetriever(),
        generator=FailingGenerator(),
    ).execute(user_id=1)
    assert result.status == IntakeReportStatus.PARTIAL
    assert result.fallback_used is True
    assert result.fallback_reason == IntakeReportFallbackReason.CLIENT_ERROR


async def test_arbitrary_registered_products_supply_raw_evidence_to_the_model() -> None:
    class GuideRepository:
        async def find_by_name(self, product_name):
            return MedicationGuideLookup(
                guide=MedicationGuideFact(
                    medication_guide_id=93821,
                    item_seq="dynamic-product",
                    product_name=product_name,
                    manufacturer_name="테스트 제조사",
                    efficacy="실제 DB 효능 원문",
                    usage_instructions="실제 DB 복용법 원문",
                    pre_use_warning="실제 DB 경고 원문",
                    precautions="조건을 보존해야 하는 주의·금기 원문",
                    drug_food_interactions="실제 DB 음식 상호작용 원문",
                    adverse_reactions="실제 DB 이상반응 원문",
                    storage_instructions="실제 DB 보관법 원문",
                )
            )

    class GeneratedText(FakeGenerator):
        async def generate(self, *, draft):
            self.draft = draft
            return IntakeReportGenerationOutcome(report_markdown="## 모델 생성 본문", fallback_used=False)

    generator = GeneratedText()
    for name in ["처음 등록한 제품", "바꿔 등록한 다른 제품"]:
        context = ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=901,
                    care_episode_id=27,
                    name=name,
                )
            ],
        )
        result = await GenerateIntakeReportUseCase(
            context_provider=FakeContextProvider(context),
            guide_repository=GuideRepository(),
            interaction_rule_repository=FakeRuleRepository(),
            knowledge_retriever=FakeRetriever(),
            generator=generator,
        ).execute(user_id=1)
        assert result.report_markdown == "## 모델 생성 본문"
        assert [item.product_name for item in generator.draft.guide_evidence] == [name]
        assert generator.draft.guide_evidence[0].pre_use_warning == "실제 DB 경고 원문"
        assert generator.draft.guide_evidence[0].drug_food_interactions == "실제 DB 음식 상호작용 원문"
        assert generator.draft.guide_item_bindings == {901: 93821}
        assert len(result.current_stack) == 1


async def test_use_case_returns_completed_report_after_knowledge_lookup() -> None:
    retriever = FakeRetriever()
    generator = FakeGenerator()
    use_case = _use_case(
        context=_supplement_context(),
        retriever=retriever,
        generator=generator,
    )

    result = await use_case.execute(user_id=1)

    assert result.status == IntakeReportStatus.COMPLETED
    assert retriever.calls == 1
    assert generator.calls == 1


async def test_duplicate_registrations_keep_ids_and_ambiguous_guides_are_not_bound() -> None:
    class GuideRepository:
        async def find_by_name(self, name):
            guide = MedicationGuideFact(
                medication_guide_id=17,
                item_seq="guide-17",
                product_name="정식 제품명",
                manufacturer_name="제조사",
                efficacy="효능",
                usage_instructions="",
                pre_use_warning="",
                precautions="",
                drug_food_interactions="",
                adverse_reactions="",
                storage_instructions="",
            )
            return MedicationGuideLookup(guide=guide, is_ambiguous=name == "모호한 제품")

    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(medication_id=101, care_episode_id=1, name=" 등록 제품 "),
            ActiveMedication(medication_id=102, care_episode_id=2, name="등록 제품"),
            ActiveMedication(medication_id=103, care_episode_id=2, name="모호한 제품"),
            ActiveMedication(medication_id=104, care_episode_id=3, name="정식 제품명"),
        ],
    )
    generator = FakeGenerator()
    result = await GenerateIntakeReportUseCase(
        context_provider=FakeContextProvider(context),
        guide_repository=GuideRepository(),
        interaction_rule_repository=FakeRuleRepository(),
        knowledge_retriever=FakeRetriever(),
        generator=generator,
    ).execute(user_id=1)
    assert generator.draft.guide_item_bindings == {101: 17, 102: 17, 104: 17}
    assert [item.medication_guide_id for item in generator.draft.guide_evidence] == [17]
    assert [item.item_id for item in result.current_stack] == [101, 102, 103, 104]


async def test_use_case_returns_partial_when_rag_is_unavailable() -> None:
    retriever = FakeRetriever(unavailable=True)
    generator = FakeGenerator()
    use_case = _use_case(
        context=_supplement_context(),
        retriever=retriever,
        generator=generator,
    )

    result = await use_case.execute(user_id=1)

    assert result.status == IntakeReportStatus.PARTIAL
    assert result.data_availability.rag_evidence_available is False
    assert "확인하지 못했습니다" in result.report_markdown


async def test_real_chain_and_validator_deliver_model_text_without_a_live_model_call() -> None:
    import json

    from ai_worker.llm.generators.intake_report_generator import OpenAIIntakeReportGenerator
    from app.dtos.intake_reports import IntakeReportResponse

    class OfflineModelClient:
        async def ainvoke(self, messages):
            content = messages[1].content
            payload = json.loads(content[content.index("{") :])
            assert payload["current_stack"][0]["product_name"] == "마그네슘"
            assert "guide_evidence" in payload and "knowledge_evidence" in payload
            return {
                "report_markdown": "# 약·영양제 생활관리 보고서\n\n## 등록한 영양제\n\n마그네슘: 제공된 자료에서 확인 필요"
            }

    use_case = GenerateIntakeReportUseCase(
        context_provider=FakeContextProvider(_supplement_context()),
        guide_repository=FakeGuideRepository(),
        interaction_rule_repository=FakeRuleRepository(),
        knowledge_retriever=FakeRetriever(),
        generator=OpenAIIntakeReportGenerator(model="offline-test", client=OfflineModelClient()),
    )
    result = await use_case.execute(user_id=1)
    response = IntakeReportResponse.from_result(result)
    assert response.presentation_version == "ai-report-v2"
    assert response.fallback_used is False
    assert response.report_markdown.endswith("마그네슘: 제공된 자료에서 확인 필요")
