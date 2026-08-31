from pathlib import Path

import pytest

from ai_worker.schemas.chat_evaluation import (
    ChatEvaluationCaseResult,
    ChatEvaluationCategory,
    ChatEvaluationFailureCategory,
    ChatEvaluationReport,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    MedicationChatRoute,
    MedicationChatSourceKind,
)
from scripts import evaluate_chat_core as module


def build_report(*, passed: bool) -> ChatEvaluationReport:
    failures = [] if passed else [ChatEvaluationFailureCategory.SOURCE_RETRIEVAL]
    return ChatEvaluationReport(
        dataset_version="chat-test-v1",
        query_count=1,
        passed_count=int(passed),
        route_accuracy=1.0,
        entity_accuracy=1.0,
        section_accuracy=1.0,
        source_contract_rate=1.0 if passed else 0.0,
        safety_contract_rate=1.0,
        langsmith_trace_coverage=1.0,
        timeout_rate=0.0,
        response_p50_ms=100.0,
        response_p95_ms=100.0,
        failure_counts=({} if passed else {ChatEvaluationFailureCategory.SOURCE_RETRIEVAL: 1}),
        passed=passed,
        results=[
            ChatEvaluationCaseResult(
                query_id="calcium-iron",
                question="칼슘과 철분을 같이 먹어도 되나요?",
                category=ChatEvaluationCategory.VECTOR_ONLY,
                expected_route=MedicationChatRoute.INTERACTION,
                observed_route=MedicationChatRoute.INTERACTION,
                expected_entities=["칼슘", "철분"],
                observed_entities=["칼슘", "철분"],
                expected_section_types=[KnowledgeSectionType.INTERACTION],
                observed_section_types=[KnowledgeSectionType.INTERACTION],
                required_source_kinds=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
                observed_source_kinds=([MedicationChatSourceKind.PUBLIC_KNOWLEDGE] if passed else []),
                expected_safety_status=SafetyStatus.SAFE,
                observed_safety_status=SafetyStatus.SAFE,
                response_time_ms=100.0,
                langsmith_trace_id="trace-1",
                error_code=None,
                answer="근거 기반 답변",
                route_match=True,
                entity_match=True,
                section_match=True,
                source_match=passed,
                safety_match=True,
                latency_match=True,
                trace_match=True,
                failure_categories=failures,
                failure_details=([] if passed else ["필수 출처를 찾지 못했습니다."]),
                passed=passed,
            )
        ],
    )


def test_write_report_supports_json_and_markdown(tmp_path: Path) -> None:
    report = build_report(passed=False)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    module.write_report(report, json_path)
    module.write_report(report, markdown_path)

    assert ChatEvaluationReport.model_validate_json(json_path.read_text(encoding="utf-8")) == report
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Chat Core 평가 보고서" in markdown
    assert "SOURCE_RETRIEVAL" in markdown


def test_write_report_rejects_unknown_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="json 또는 md"):
        module.write_report(
            build_report(passed=True),
            tmp_path / "report.txt",
        )


def test_load_evaluation_manifest_reads_chat_yaml(tmp_path: Path) -> None:
    path = tmp_path / "chat.yaml"
    path.write_text(
        """
schema_version: chat-evaluation-v1
dataset_version: chat-test-v1
frontend_preset: false
cases:
  - query_id: calcium-iron
    category: VECTOR_ONLY
    question: 칼슘과 철분을 같이 먹어도 되나요?
    preconditions: [Qdrant 근거가 존재한다.]
    expected:
      route: INTERACTION
      intent_tags: [SUPPLEMENT_SUPPLEMENT_INTERACTION]
      normalized_entities:
        - entity_type: INGREDIENT_NAME
          canonical_name: 칼슘
        - entity_type: INGREDIENT_NAME
          canonical_name: 철분
      section_types: [INTERACTION]
      required_source_kinds: [PUBLIC_KNOWLEDGE]
      safety_status: SAFE
      require_langsmith_trace: true
      answer_requirements: [근거를 설명한다.]
      forbidden_claims: [복용 변경을 지시하지 않는다.]
""".strip(),
        encoding="utf-8",
    )

    manifest = module.load_evaluation_manifest(path)

    assert manifest.cases[0].query_id == "calcium-iron"


def test_exit_code_is_two_when_any_case_fails() -> None:
    assert module.exit_code_for(build_report(passed=True)) == 0
    assert module.exit_code_for(build_report(passed=False)) == 2
