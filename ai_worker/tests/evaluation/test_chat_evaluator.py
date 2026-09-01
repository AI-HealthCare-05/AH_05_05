import pytest
from pydantic import ValidationError

from ai_worker.evaluation.chat_evaluator import (
    ChatEvaluator,
    render_chat_evaluation_markdown,
)
from ai_worker.schemas.chat_evaluation import (
    ChatEvaluationCase,
    ChatEvaluationCategory,
    ChatEvaluationExpected,
    ChatEvaluationFailureCategory,
    ChatEvaluationManifest,
    ChatEvaluationObservation,
    ChatExpectedEntity,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    MedicationChatRoute,
    MedicationChatSourceKind,
)


class SequenceExecutor:
    def __init__(self, observations: list[ChatEvaluationObservation]) -> None:
        self._observations = iter(observations)
        self.executed_query_ids: list[str] = []

    async def execute(
        self,
        case: ChatEvaluationCase,
    ) -> ChatEvaluationObservation:
        self.executed_query_ids.append(case.query_id)
        return next(self._observations)


def build_case(
    query_id: str,
    *,
    route: MedicationChatRoute,
    entities: list[str],
    sources: list[MedicationChatSourceKind],
) -> ChatEvaluationCase:
    category = (
        ChatEvaluationCategory.VECTOR_ONLY
        if sources == [MedicationChatSourceKind.PUBLIC_KNOWLEDGE]
        else ChatEvaluationCategory.RDB_ONLY
    )
    return ChatEvaluationCase(
        query_id=query_id,
        category=category,
        question=f"질문 {query_id}",
        preconditions=["평가 조건"],
        expected=ChatEvaluationExpected(
            route=route,
            intent_tags=["TEST_INTENT"],
            normalized_entities=[
                ChatExpectedEntity(
                    entity_type="INGREDIENT_NAME",
                    canonical_name=entity,
                )
                for entity in entities
            ],
            section_types=[KnowledgeSectionType.INTERACTION],
            required_source_kinds=sources,
            safety_status=SafetyStatus.SAFE,
            require_langsmith_trace=True,
            answer_requirements=["근거를 설명한다."],
            forbidden_claims=["복용 변경을 지시하지 않는다."],
        ),
    )


async def test_evaluate_runs_cases_sequentially_and_computes_contract_metrics() -> None:
    cases = [
        build_case(
            "passing-case",
            route=MedicationChatRoute.INTERACTION,
            entities=["칼슘", "철분"],
            sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
        ),
        build_case(
            "failing-case",
            route=MedicationChatRoute.MEDICATION_GUIDE,
            entities=["타이레놀"],
            sources=[MedicationChatSourceKind.MEDICATION_GUIDE],
        ),
    ]
    executor = SequenceExecutor(
        [
            ChatEvaluationObservation(
                query_id="passing-case",
                route=MedicationChatRoute.INTERACTION,
                normalized_entities=["칼슘", "철분"],
                section_types=[KnowledgeSectionType.INTERACTION],
                source_kinds=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
                safety_status=SafetyStatus.SAFE,
                response_time_ms=100.0,
                langsmith_trace_id="trace-passing",
                answer="근거 기반 답변",
            ),
            ChatEvaluationObservation(
                query_id="failing-case",
                route=MedicationChatRoute.GENERAL_GUIDANCE,
                normalized_entities=["아세트아미노펜"],
                section_types=[KnowledgeSectionType.CAUTION],
                source_kinds=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
                safety_status=SafetyStatus.BLOCKED,
                response_time_ms=31_000.0,
                langsmith_trace_id=None,
                answer="차단된 답변",
                error_code="API_TIMEOUT",
            ),
        ]
    )
    manifest = ChatEvaluationManifest(
        dataset_version="chat-test-v1",
        max_case_latency_ms=30_000.0,
        cases=cases,
    )

    report = await ChatEvaluator(executor=executor).evaluate(manifest)

    assert executor.executed_query_ids == ["passing-case", "failing-case"]
    assert report.query_count == 2
    assert report.passed_count == 1
    assert report.route_accuracy == 0.5
    assert report.entity_accuracy == 0.5
    assert report.section_accuracy == 0.5
    assert report.source_contract_rate == 0.5
    assert report.safety_contract_rate == 0.5
    assert report.langsmith_trace_coverage == 0.5
    assert report.timeout_rate == 0.5
    assert report.response_p50_ms == 15_550.0
    assert report.response_p95_ms == 31_000.0
    assert report.passed is False
    assert report.results[0].passed is True
    assert report.results[1].failure_categories == [
        ChatEvaluationFailureCategory.QUESTION_CLASSIFICATION,
        ChatEvaluationFailureCategory.ENTITY_NORMALIZATION,
        ChatEvaluationFailureCategory.SOURCE_RETRIEVAL,
        ChatEvaluationFailureCategory.SAFETY_VALIDATION,
        ChatEvaluationFailureCategory.PERFORMANCE,
        ChatEvaluationFailureCategory.OBSERVABILITY,
    ]


async def test_render_markdown_includes_summary_and_failure_classification() -> None:
    case = build_case(
        "trace-missing",
        route=MedicationChatRoute.INTERACTION,
        entities=["비타민 K", "와파린"],
        sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
    )
    executor = SequenceExecutor(
        [
            ChatEvaluationObservation(
                query_id="trace-missing",
                route=MedicationChatRoute.INTERACTION,
                normalized_entities=["비타민 K", "와파린"],
                section_types=[KnowledgeSectionType.INTERACTION],
                source_kinds=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
                safety_status=SafetyStatus.SAFE,
                response_time_ms=120.0,
                langsmith_trace_id=None,
                answer="근거 기반 답변",
            )
        ]
    )
    report = await ChatEvaluator(executor=executor).evaluate(
        ChatEvaluationManifest(
            dataset_version="chat-test-v1",
            cases=[case],
        )
    )

    markdown = render_chat_evaluation_markdown(report)

    assert "# Chat Core 평가 보고서" in markdown
    assert "trace-missing" in markdown
    assert "OBSERVABILITY" in markdown
    assert "LangSmith Trace ID" in markdown
    assert "비타민 K, 와파린" in markdown
    assert "PUBLIC_KNOWLEDGE" in markdown
    assert "SAFE" in markdown
    assert "INTERACTION" in markdown


async def test_evaluate_classifies_mismatched_observation_id_as_execution_error() -> None:
    case = build_case(
        "expected-id",
        route=MedicationChatRoute.INTERACTION,
        entities=["칼슘", "철분"],
        sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
    )
    executor = SequenceExecutor(
        [
            ChatEvaluationObservation(
                query_id="another-id",
                route=MedicationChatRoute.INTERACTION,
                normalized_entities=["칼슘", "철분"],
                section_types=[KnowledgeSectionType.INTERACTION],
                source_kinds=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
                safety_status=SafetyStatus.SAFE,
                response_time_ms=100.0,
                langsmith_trace_id="trace-id",
            )
        ]
    )

    report = await ChatEvaluator(executor=executor).evaluate(
        ChatEvaluationManifest(dataset_version="chat-test-v1", cases=[case])
    )

    assert report.results[0].failure_categories == [ChatEvaluationFailureCategory.EXECUTION_ERROR]
    assert "another-id" in report.results[0].failure_details[0]


def test_manifest_rejects_category_that_conflicts_with_required_sources() -> None:
    case = build_case(
        "invalid-source-category",
        route=MedicationChatRoute.INTERACTION,
        entities=["칼슘", "철분"],
        sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
    ).model_copy(update={"category": ChatEvaluationCategory.RDB_ONLY})

    with pytest.raises(ValidationError, match="category와 required_source_kinds"):
        ChatEvaluationManifest(dataset_version="chat-test-v1", cases=[case])
