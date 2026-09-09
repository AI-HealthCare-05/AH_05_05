import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from statistics import median
from typing import Protocol

from ai_worker.schemas.chat_evaluation import (
    ChatEvaluationCase,
    ChatEvaluationCaseResult,
    ChatEvaluationFailureCategory,
    ChatEvaluationManifest,
    ChatEvaluationObservation,
    ChatEvaluationReport,
)


class ChatEvaluationExecutor(Protocol):
    async def execute(
        self,
        case: ChatEvaluationCase,
    ) -> ChatEvaluationObservation: ...


class ChatEvaluator:
    def __init__(self, *, executor: ChatEvaluationExecutor) -> None:
        self._executor = executor

    async def evaluate(
        self,
        manifest: ChatEvaluationManifest,
    ) -> ChatEvaluationReport:
        results: list[ChatEvaluationCaseResult] = []
        for case in manifest.cases:
            observation = await self._executor.execute(case)
            results.append(
                self._compare(
                    case=case,
                    observation=observation,
                    max_case_latency_ms=manifest.max_case_latency_ms,
                )
            )

        query_count = len(results)
        failure_counts = Counter(category for result in results for category in result.failure_categories)
        latencies = [result.response_time_ms for result in results]
        passed_count = sum(result.passed for result in results)
        return ChatEvaluationReport(
            dataset_version=manifest.dataset_version,
            query_count=query_count,
            passed_count=passed_count,
            route_accuracy=self._rate(result.route_match for result in results),
            question_intent_accuracy=self._rate(result.intent_match for result in results),
            entity_accuracy=self._rate(result.entity_match for result in results),
            section_accuracy=self._rate(result.section_match for result in results),
            source_contract_rate=self._rate(result.source_match for result in results),
            safety_contract_rate=self._rate(result.safety_match for result in results),
            answer_policy_contract_rate=self._rate(result.answer_policy_match for result in results),
            langsmith_trace_coverage=self._rate(result.trace_match for result in results),
            timeout_rate=(sum(result.error_code == "API_TIMEOUT" for result in results) / query_count),
            response_p50_ms=self._percentile(latencies, 0.50),
            response_p95_ms=self._percentile(latencies, 0.95),
            failure_counts=dict(failure_counts),
            passed=passed_count == query_count,
            results=results,
        )

    @classmethod
    def _compare(
        cls,
        *,
        case: ChatEvaluationCase,
        observation: ChatEvaluationObservation,
        max_case_latency_ms: float,
    ) -> ChatEvaluationCaseResult:
        expected = case.expected
        expected_entities = [entity.canonical_name for entity in expected.normalized_entities]
        route_match = observation.route == expected.route
        intent_match = expected.question_intent is None or observation.question_intent == expected.question_intent
        entity_match = cls._contains_all(
            observation.normalized_entities,
            expected_entities,
        )
        section_match = set(expected.section_types).issubset(
            observation.section_types,
        )
        source_match = set(expected.required_source_kinds).issubset(
            observation.source_kinds,
        )
        safety_match = observation.safety_status == expected.safety_status
        answer_policy_match, answer_policy_details = cls._answer_policy_match(
            answer=observation.answer,
            required_markers=expected.required_answer_markers,
            forbidden_markers=expected.forbidden_answer_markers,
        )
        latency_match = observation.response_time_ms <= max_case_latency_ms and observation.error_code != "API_TIMEOUT"
        trace_match = not expected.require_langsmith_trace or bool(observation.langsmith_trace_id)

        categories, details = cls._contract_failures(
            route_match=route_match,
            intent_match=intent_match,
            section_match=section_match,
            entity_match=entity_match,
            source_match=source_match,
            safety_match=safety_match,
            answer_policy_match=answer_policy_match,
            answer_policy_details=answer_policy_details,
        )
        if not latency_match:
            categories.append(ChatEvaluationFailureCategory.PERFORMANCE)
            details.append("응답 시간이 기준을 초과했거나 타임아웃되었습니다.")
        if not trace_match:
            categories.append(ChatEvaluationFailureCategory.OBSERVABILITY)
            details.append("LangSmith Trace ID가 생성되지 않았습니다.")
        execution_details = cls._execution_failure_details(case=case, observation=observation)
        if execution_details:
            categories.append(ChatEvaluationFailureCategory.EXECUTION_ERROR)
            details.extend(execution_details)

        return ChatEvaluationCaseResult(
            query_id=case.query_id,
            question=case.question,
            category=case.category,
            expected_route=expected.route,
            observed_route=observation.route,
            expected_question_intent=expected.question_intent,
            observed_question_intent=observation.question_intent,
            question_confidence=observation.question_confidence,
            interpretation_version=observation.interpretation_version,
            interpretation_reason_codes=(observation.interpretation_reason_codes),
            expected_entities=expected_entities,
            observed_entities=observation.normalized_entities,
            expected_section_types=expected.section_types,
            observed_section_types=observation.section_types,
            required_source_kinds=expected.required_source_kinds,
            observed_source_kinds=observation.source_kinds,
            expected_safety_status=expected.safety_status,
            observed_safety_status=observation.safety_status,
            response_time_ms=observation.response_time_ms,
            langsmith_trace_id=observation.langsmith_trace_id,
            query_plan_hash=observation.query_plan_hash,
            execution_plan_hash=observation.execution_plan_hash,
            error_code=observation.error_code,
            answer=observation.answer,
            route_match=route_match,
            intent_match=intent_match,
            entity_match=entity_match,
            section_match=section_match,
            source_match=source_match,
            safety_match=safety_match,
            answer_policy_match=answer_policy_match,
            latency_match=latency_match,
            trace_match=trace_match,
            failure_categories=categories,
            failure_details=details,
            passed=not categories,
        )

    @staticmethod
    def _contract_failures(
        *,
        route_match: bool,
        intent_match: bool,
        section_match: bool,
        entity_match: bool,
        source_match: bool,
        safety_match: bool,
        answer_policy_match: bool,
        answer_policy_details: list[str],
    ) -> tuple[list[ChatEvaluationFailureCategory], list[str]]:
        checks = (
            (
                route_match and intent_match and section_match,
                ChatEvaluationFailureCategory.QUESTION_CLASSIFICATION,
                ["질문 의도·경로 또는 검색 섹션 분류가 예상과 다릅니다."],
            ),
            (
                entity_match,
                ChatEvaluationFailureCategory.ENTITY_NORMALIZATION,
                ["필수 제품명·성분명이 정규화 결과에 없습니다."],
            ),
            (
                source_match,
                ChatEvaluationFailureCategory.SOURCE_RETRIEVAL,
                ["필수 RDBMS·Qdrant 출처 계약을 충족하지 못했습니다."],
            ),
            (
                safety_match,
                ChatEvaluationFailureCategory.SAFETY_VALIDATION,
                ["안전성 상태가 예상과 다릅니다."],
            ),
            (
                answer_policy_match,
                ChatEvaluationFailureCategory.ANSWER_POLICY,
                answer_policy_details,
            ),
        )
        categories = [category for matched, category, _ in checks if not matched]
        details = [detail for matched, _, check_details in checks if not matched for detail in check_details]
        return categories, details

    @staticmethod
    def _execution_failure_details(
        *,
        case: ChatEvaluationCase,
        observation: ChatEvaluationObservation,
    ) -> list[str]:
        details = (
            []
            if observation.query_id == case.query_id
            else [f"실행 결과의 질문 ID가 일치하지 않습니다: expected={case.query_id}, observed={observation.query_id}"]
        )
        if observation.error_code and observation.error_code != "API_TIMEOUT":
            details.append(f"실행 오류가 발생했습니다: {observation.error_code}")
        return details

    @classmethod
    def _answer_policy_match(
        cls,
        *,
        answer: str,
        required_markers: list[str],
        forbidden_markers: list[str],
    ) -> tuple[bool, list[str]]:
        normalized_answer = cls._answer_key(answer)
        missing_markers = [marker for marker in required_markers if cls._answer_key(marker) not in normalized_answer]
        found_forbidden_markers = [
            marker for marker in forbidden_markers if cls._answer_key(marker) in normalized_answer
        ]
        details: list[str] = []
        if missing_markers:
            details.append(f"필수 답변 표현이 없습니다: {', '.join(missing_markers)}")
        if found_forbidden_markers:
            details.append(f"금지된 답변 표현이 포함되었습니다: {', '.join(found_forbidden_markers)}")
        return not details, details

    @staticmethod
    def _contains_all(
        observed: list[str],
        expected: list[str],
    ) -> bool:
        observed_keys = {ChatEvaluator._entity_key(value) for value in observed}
        return all(ChatEvaluator._entity_key(value) in observed_keys for value in expected)

    @staticmethod
    def _entity_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"\s+", "", normalized)

    @staticmethod
    def _answer_key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"\s+", "", normalized)

    @staticmethod
    def _rate(
        values: Iterable[bool],
    ) -> float:
        resolved_values = list(values)
        return sum(resolved_values) / len(resolved_values)

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float:
        if quantile == 0.50:
            return round(median(values), 3)
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * quantile) - 1)
        return round(ordered[index], 3)


def render_chat_evaluation_markdown(
    report: ChatEvaluationReport,
) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        "# Chat Core 평가 보고서",
        "",
        f"- 데이터셋: `{report.dataset_version}`",
        f"- 전체 상태: **{status}**",
        f"- 통과: {report.passed_count}/{report.query_count}",
        f"- 경로 정확도: {report.route_accuracy:.1%}",
        f"- 질문 의도 정확도: {report.question_intent_accuracy:.1%}",
        f"- 엔터티 정규화 정확도: {report.entity_accuracy:.1%}",
        f"- 검색 섹션 정확도: {report.section_accuracy:.1%}",
        f"- 출처 계약 충족률: {report.source_contract_rate:.1%}",
        f"- 안전성 계약 충족률: {report.safety_contract_rate:.1%}",
        f"- 답변 정책 계약 충족률: {report.answer_policy_contract_rate:.1%}",
        f"- LangSmith Trace ID 생성률: {report.langsmith_trace_coverage:.1%}",
        f"- 타임아웃 비율: {report.timeout_rate:.1%}",
        f"- 응답 시간 P50/P95: {report.response_p50_ms:.1f}ms / {report.response_p95_ms:.1f}ms",
        "",
        "## 질문별 결과",
        "",
        (
            "| 질문 ID | 상태 | 해석 버전 | 의도/신뢰도 | 경로 | "
            "정규화 엔터티 | 검색 섹션 | 사용 출처 | 안전성 | 응답 시간 | "
            "LangSmith Trace ID | 실패 분류 |"
        ),
        ("| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |"),
    ]
    for result in report.results:
        result_status = "PASS" if result.passed else "FAIL"
        interpretation_version = result.interpretation_version or "-"
        intent = result.observed_question_intent.value if result.observed_question_intent is not None else "-"
        confidence = result.question_confidence.value if result.question_confidence is not None else "-"
        route = result.observed_route.value if result.observed_route else "-"
        entities = ", ".join(result.observed_entities) or "-"
        sections = ", ".join(section.value for section in result.observed_section_types) or "-"
        sources = ", ".join(source.value for source in result.observed_source_kinds) or "-"
        safety = result.observed_safety_status.value if result.observed_safety_status else "-"
        trace_id = result.langsmith_trace_id or "-"
        failures = ", ".join(category.value for category in result.failure_categories) or "-"
        lines.append(
            f"| {result.query_id} | {result_status} | "
            f"{interpretation_version} | {intent}/{confidence} | {route} | "
            f"{entities} | {sections} | {sources} | {safety} | "
            f"{result.response_time_ms:.1f}ms | {trace_id} | {failures} |"
        )

    failed_results = [result for result in report.results if not result.passed]
    if failed_results:
        lines.extend(["", "## 실패 상세", ""])
        for result in failed_results:
            lines.append(f"### {result.query_id}")
            lines.append("")
            lines.extend(f"- {detail}" for detail in result.failure_details)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
