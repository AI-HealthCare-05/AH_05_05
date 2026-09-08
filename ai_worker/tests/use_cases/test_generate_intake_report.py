from datetime import date

from ai_worker.assemblers.intake_report_assembler import IntakeReportAssembler
from ai_worker.schemas.intake_report import (
    IntakeReportGenerationOutcome,
    IntakeReportStatus,
)
from ai_worker.schemas.knowledge import (
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveSupplement,
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

    async def generate(self, *, draft) -> IntakeReportGenerationOutcome:
        self.calls += 1
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
