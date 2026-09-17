"""Bounded, source-locked RAG guidance for the intake report.

The model can plan searches and extract candidate claims, but the server owns
target identity, provenance, quote matching, and the final public card shape.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from ai_worker.llm.prompts.prompt_assets import load_prompt_asset
from ai_worker.reports.text_guidance_rules import mentions_food_or_drink
from ai_worker.schemas.intake_report_cards import CardSource, LifestyleCard, ReportGuidanceSectionStatus
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeStudyPopulation,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    InteractionRuleLookupStatus,
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntityType,
    MedicationSearchExecutionPlan,
)

_SECTION_IDS = ("food_drink", "lifestyle", "additional_precautions")
_SECTION_CATEGORY = {
    "food_drink": "음식·음료 참고",
    "lifestyle": "생활관리 참고",
    "additional_precautions": "추가 주의사항",
}
_INJECTION = re.compile(
    r"(?i)(ignore\s+(all\s+)?previous|system\s+prompt|instructions?\s*:|이전\s*지시|시스템\s*프롬프트)"
)
_DOSE_CHANGE = re.compile(r"(?i)(?:\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|iu|ml)\b|용량|복용량|증량|감량|늘리|줄이)")
_INGREDIENT_DOSING = re.compile(
    r"\d+(?:\.\d+)?\s*(?:번|회|정|알|차례|캡슐|포|방울|스푼|시간|일|밀리그램|마이크로그램|그램)|"
    r"(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|일|이|삼|사)\s*"
    r"(?:번|회|정|알|차례|캡슐|포|방울|스푼|시간)|용법|복용법|투여량"
)
# Keep identifiers such as B12 intact: their trailing Korean particle is not
# a quantity unit. Compare the identifier too, so B12 -> B13 is still rejected.
_NUMBER = re.compile(
    r"(?<![0-9.A-Za-z])(?:[A-Za-z]+\d+[A-Za-z0-9]*|\d+(?:\.\d+)?(?:\s*(?:[A-Za-z%]+|[가-힣]+))?)",
    re.IGNORECASE,
)
_FOOD_CONTEXT = re.compile(
    r"음료|우유|유제품|카페인|커피|녹차|홍차|식이섬유|"
    r"\b(?:foods?|meals?|drinks?|beverages?|juice|grapefruit|alcohol|milk|dairy|caffeine|coffee|tea|fasting)\b",
    re.IGNORECASE,
)
_CLINICAL_PRECAUTION = re.compile(
    r"질환|혈증|과량|이상\s*(?:사례|반응)|부작용|금기|"
    r"\b(?:disease|hypercalcemia|overdose|adverse|contraindicat\w*)\b",
    re.IGNORECASE,
)
_MAX_BATCH_EVIDENCE_BYTES = 20_000
_BATCH_EVIDENCE_OVERLAP_CHARACTERS = 512


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _PlanSection(_Strict):
    section_id: Literal["food_drink", "lifestyle", "additional_precautions"]
    target_ids: list[str] = Field(min_length=1)
    queries: list[str] = Field(min_length=1, max_length=3)


class _PlanPayload(_Strict):
    sections: list[_PlanSection] = Field(min_length=1, max_length=3)


class _Evidence(_Strict):
    chunk_id: str = Field(min_length=1)
    exact_quote: str = Field(min_length=1)


class _Claim(_Strict):
    model_config = ConfigDict(str_strip_whitespace=True)

    section_id: Literal["food_drink", "lifestyle", "additional_precautions"]
    target_ids: list[str] = Field(min_length=1)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=600)
    action: str = Field(min_length=1, max_length=200)
    evidence: list[_Evidence] = Field(min_length=1)
    grounded: bool


class _ClaimsPayload(_Strict):
    claims: list[_Claim] = Field(default_factory=list)


def _count_rejection(metrics: dict[str, int] | None, reason: str) -> None:
    # Aggregate codes only: never log product names, excerpts, or patient input.
    if metrics is not None:
        key = f"claim_rejected_{reason}"
        metrics[key] = metrics.get(key, 0) + 1


def _parse_claims(value: object, *, metrics: dict[str, int] | None = None, stage: str = "final") -> _ClaimsPayload:
    """Keep every valid sibling while rejecting malformed envelopes."""
    if isinstance(value, _ClaimsPayload):
        return value
    if not isinstance(value, dict) or set(value) != {"claims"} or not isinstance(value["claims"], list):
        _count_rejection(metrics, f"{stage}_envelope")
        return _ClaimsPayload()
    claims = []
    for candidate in value["claims"]:
        try:
            claims.append(_Claim.model_validate(candidate))
        except ValidationError:
            _count_rejection(metrics, f"{stage}_schema")
    return _ClaimsPayload(claims=claims)


@dataclass(frozen=True)
class ReportRagTarget:
    id: str
    item_id: int
    item_type: Literal["MEDICATION", "SUPPLEMENT"]
    name: str
    aliases: tuple[str, ...] = ()
    ingredient_only: bool = False


@dataclass(frozen=True)
class ReportRagSectionPlan:
    section_id: str
    target_ids: tuple[str, ...]
    queries: tuple[str, ...]


@dataclass(frozen=True)
class ReportRagResult:
    cards: list[LifestyleCard]
    sources: list[CardSource]
    section_statuses: list[ReportGuidanceSectionStatus]
    rag_evidence_available: bool
    metrics: dict[str, int]


class _Retriever(Protocol):
    async def search_with_diagnostics(self, *, execution_plan: MedicationSearchExecutionPlan) -> Any: ...


def load_report_rag_source_registry() -> dict[str, tuple[str, str]]:
    """Return verified Qdrant sources, including user-approved demo material."""
    root = Path(__file__).resolve().parents[2]
    manifest_root = root / "data" / "knowledge" / "manifests"
    try:
        sources = yaml.safe_load((manifest_root / "sources.yaml").read_text(encoding="utf-8"))["sources"]
        allowed_sources = {
            entry["source_id"]: entry["provider"]
            for entry in sources
            if entry.get("target") == "QDRANT" and entry.get("access_scope") in {"PUBLIC", "DEMO_RESTRICTED"}
        }
        registry: dict[str, tuple[str, str]] = {}
        for line in (manifest_root / "documents.jsonl").read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            source_id = entry.get("source_id")
            if (
                entry.get("access_scope") in {"PUBLIC", "DEMO_RESTRICTED"}
                and source_id in allowed_sources
                and entry.get("provider") == allowed_sources[source_id]
            ):
                registry[entry["document_id"]] = (source_id, allowed_sources[source_id])
        return registry
    except (OSError, KeyError, TypeError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise RuntimeError("report RAG source registry could not be verified") from error


class ReportRagPlanner:
    """Keep planner output within server-owned section and target bounds."""

    def validate_or_fallback(self, value: object, *, targets: list[ReportRagTarget]) -> list[ReportRagSectionPlan]:
        try:
            payload = value if isinstance(value, _PlanPayload) else _PlanPayload.model_validate(value)
            known = {target.id for target in targets}
            sections: list[ReportRagSectionPlan] = []
            seen: set[str] = set()
            for section in payload.sections:
                if section.section_id in seen or any(item not in known for item in section.target_ids):
                    raise ValueError("unknown or repeated section target")
                queries = tuple(dict.fromkeys(query.strip() for query in section.queries if query.strip()))
                if not queries:
                    raise ValueError("invalid query count")
                # Coverage is server-owned. A model must not silently drop
                # products, including supplements whose evidence is searchable
                # by a known ingredient rather than the commercial name.
                searched_names = " ".join(queries).casefold().replace(" ", "")
                missing_query_target = any(
                    not any(
                        name.casefold().replace(" ", "") in searched_names
                        for name in (target.name, *target.aliases)
                        if name.strip()
                    )
                    for target in targets
                )
                if set(section.target_ids) != known or missing_query_target:
                    queries = self._fallback_queries(section.section_id, targets)
                seen.add(section.section_id)
                sections.append(
                    ReportRagSectionPlan(section.section_id, tuple(target.id for target in targets), queries)
                )
            if not sections:
                raise ValueError("empty plan")
            return sections
        except Exception:
            return self.fallback(targets=targets)

    @classmethod
    def fallback(cls, *, targets: list[ReportRagTarget]) -> list[ReportRagSectionPlan]:
        target_ids = tuple(target.id for target in targets)
        return [
            ReportRagSectionPlan(section_id, target_ids, cls._fallback_queries(section_id, targets))
            for section_id in _SECTION_IDS
        ]

    @staticmethod
    def _fallback_queries(section_id: str, targets: list[ReportRagTarget]) -> tuple[str, ...]:
        topic = {
            "food_drink": "음식·음료 주의사항",
            "lifestyle": "생활관리 참고사항",
            "additional_precautions": "주의사항",
        }[section_id]
        # Bound search cost without dropping registered target names.
        group_count = min(3, len(targets)) or 1
        groups = [targets[position::group_count] for position in range(group_count)]
        return tuple(
            " ".join(dict.fromkeys(name for target in group for name in (target.name, *target.aliases))) + f" {topic}"
            for group in groups
        )


def _invoke(runnable: Runnable | Callable[[Any], Any], value: Any) -> Awaitable[Any]:
    # Raw target/evidence payloads must not be sent to LangSmith's automatic
    # runnable tracer. The report tracer records aggregate metrics separately.
    try:
        from langsmith import tracing_context

        trace_context = tracing_context(enabled=False)
    except ImportError:
        trace_context = nullcontext()
    if hasattr(runnable, "ainvoke"):

        async def invoke_runnable() -> Any:
            with trace_context:
                return await runnable.ainvoke(value)  # type: ignore[union-attr]

        return invoke_runnable()
    with trace_context:
        output = runnable(value)  # type: ignore[operator]
    if asyncio.iscoroutine(output):
        return output

    async def resolved() -> Any:
        return output

    return resolved()


def _json_data(value: Any) -> str:
    def default(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        return str(item)

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=default)


class ReportRagPipeline:
    """Three model stages around concurrent, bounded retrieval.

    Calls are intentionally independent of the legacy report generator so the
    new mode cannot serially spend its 90-second budget before RAG begins.
    """

    def __init__(
        self,
        *,
        retriever: _Retriever,
        dataset_version: str,
        planner: Runnable | Callable[[Any], Any],
        claim_writer: Runnable | Callable[[Any], Any],
        verifier: Runnable | Callable[[Any], Any],
        timeout_seconds: float = 100.0,
        source_registry: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self._retriever = retriever
        self._dataset_version = dataset_version.strip()
        self._planner = planner
        self._claim_writer = claim_writer
        self._verifier = verifier
        self._timeout_seconds = timeout_seconds
        self._source_registry = source_registry if source_registry is not None else load_report_rag_source_registry()
        self._plan_validator = ReportRagPlanner()

    async def run(  # noqa: C901 - deadline, retained sections, and source boundary are one control flow
        self,
        *,
        targets: list[ReportRagTarget],
        remaining_seconds: float | None = None,
        approved_warnings: list[dict[str, str]] | None = None,
    ) -> ReportRagResult:
        statuses = self._statuses(targets=targets, reasons={})
        if not targets or not self._dataset_version:
            return ReportRagResult([], [], statuses, False, {"query_count": 0, "verified_claim_count": 0})
        budget = (
            min(self._timeout_seconds, remaining_seconds) if remaining_seconds is not None else self._timeout_seconds
        )
        if budget <= 0:
            return ReportRagResult(
                [],
                [],
                self._statuses(targets=targets, reasons={s: "검증 시간 초과" for s in _SECTION_IDS}),
                False,
                {"query_count": 0, "verified_claim_count": 0},
            )
        deadline = asyncio.get_running_loop().time() + budget
        query_cache: dict[tuple[str, tuple[str, ...]], asyncio.Task[Any]] = {}
        section_tasks: dict[asyncio.Task[Any], str] = {}
        rejection_metrics: dict[str, int] = {}
        try:
            try:
                async with asyncio.timeout(max(0.1, deadline - asyncio.get_running_loop().time())):
                    plan_raw = await _invoke(self._planner, self._planner_input(targets))
                plan = self._plan_validator.validate_or_fallback(plan_raw, targets=targets)
            except Exception:
                plan = self._plan_validator.fallback(targets=targets)
            query_semaphore = asyncio.Semaphore(3)
            batch_semaphore = asyncio.Semaphore(3)
            stage_metrics = {
                key: value
                for section_id in _SECTION_IDS
                for key, value in self._empty_section_metrics(section_id).items()
            }
            section_tasks = {
                asyncio.create_task(
                    self._run_section(
                        section,
                        targets,
                        query_cache,
                        query_semaphore,
                        batch_semaphore,
                        approved_warnings or [],
                        rejection_metrics,
                        deadline,
                    )
                ): section.section_id
                for section in plan
            }
            done, pending = await asyncio.wait(
                section_tasks, timeout=max(0, deadline - asyncio.get_running_loop().time())
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            cards: list[LifestyleCard] = []
            sources: dict[str, CardSource] = {}
            coverage: dict[str, set[str]] = {}
            reasons: dict[str, str] = {section.section_id: "검증 시간 초과" for section in plan}
            for task in sorted(done, key=lambda item: _SECTION_IDS.index(section_tasks[item])):
                section_id = section_tasks[task]
                try:
                    section_cards, section_sources, section_coverage, reason, section_metrics = task.result()
                except Exception:
                    reasons[section_id] = "검색 또는 검증 실패"
                    continue
                cards.extend(section_cards)
                sources.update({source.id: source for source in section_sources})
                coverage[section_id] = section_coverage
                reasons[section_id] = reason
                stage_metrics.update(section_metrics)
            all_target_ids = {target.id for target in targets}
            # A searched target is not necessarily supported by verified evidence.
            incomplete = {
                section.section_id
                for section in plan
                if stage_metrics[self._section_metric_key(section.section_id, "batch_incomplete_count")] > 0
                or stage_metrics[self._section_metric_key(section.section_id, "batch_failed_count")] > 0
            }
            verified = {
                section.section_id
                for section in plan
                if coverage.get(section.section_id) == all_target_ids and section.section_id not in incomplete
            }
            partial = {
                section.section_id
                for section in plan
                if coverage.get(section.section_id) and section.section_id not in verified
            }
            for section_id in verified:
                reasons[section_id] = "검증됨"
            for section_id in partial:
                if reasons.get(section_id) == "검증된 근거 없음":
                    reasons[section_id] = "일부 등록 항목의 근거만 확인됨"
            cards = self._deduplicate_cards(cards)
            return ReportRagResult(
                cards,
                list(sources.values()),
                self._statuses(targets=targets, reasons=reasons, verified=verified, partial=partial),
                bool(cards),
                {
                    "query_count": len(query_cache),
                    "focused_query_count": sum(key[1][0] == "focused" for key in query_cache),
                    "verified_claim_count": len(cards),
                    **stage_metrics,
                    **rejection_metrics,
                },
            )
        except Exception:
            return ReportRagResult(
                [],
                [],
                self._statuses(targets=targets, reasons={s: "검색 또는 검증 실패" for s in _SECTION_IDS}),
                False,
                {"query_count": 0, "verified_claim_count": 0},
            )
        finally:
            outstanding = [*section_tasks, *query_cache.values()]
            for task in outstanding:
                if not task.done():
                    task.cancel()
            if outstanding:
                await asyncio.gather(*outstanding, return_exceptions=True)

    def _deduplicate_cards(self, cards: list[LifestyleCard]) -> list[LifestyleCard]:
        retained: list[LifestyleCard] = []
        seen: set[tuple[object, ...]] = set()
        for card in cards:
            # Identical instructions backed by identical quotes are one card.
            # Distinct warnings from the same source must remain separate.
            key = (
                tuple(card.id.split(":")[2:4]),
                tuple(sorted(card.related_item_ids)),
                tuple(sorted(card.source_ids)),
                self._normal(card.summary),
                self._normal(card.action),
            )
            if key not in seen:
                retained.append(card)
                seen.add(key)
        return retained

    async def _run_section(  # noqa: C901 - metric capture stays beside the stage transitions it measures
        self,
        section: ReportRagSectionPlan,
        targets: list[ReportRagTarget],
        query_cache: dict[tuple[str, tuple[str, ...]], asyncio.Task[Any]],
        query_semaphore: asyncio.Semaphore,
        batch_semaphore: asyncio.Semaphore,
        approved_warnings: list[dict[str, str]],
        rejection_metrics: dict[str, int],
        deadline: float,
    ) -> tuple[list[LifestyleCard], list[CardSource], set[str], str, dict[str, int]]:
        index = {target.id: target for target in targets}
        section_targets = [index[target_id] for target_id in section.target_ids]
        stage_metrics = self._empty_section_metrics(section.section_id)

        results = await asyncio.gather(
            *(
                self._retrieve_grouped(query, section_targets, query_cache, query_semaphore)
                for query in section.queries[:3]
            ),
            return_exceptions=True,
        )
        if all(isinstance(result, Exception) for result in results):
            return [], [], set(), "자료 검색 실패", stage_metrics
        retrieved = [chunk for result in results if not isinstance(result, Exception) for chunk in result.chunks]
        stage_metrics[self._section_metric_key(section.section_id, "retrieved_chunk_count")] = len(retrieved)
        for result in results:
            if isinstance(result, Exception):
                continue
            diagnostics = getattr(result, "diagnostics", None)
            if diagnostics is None:
                continue
            for name, attribute in (
                ("retriever_raw_candidate_count", "raw_candidate_count"),
                ("retriever_eligible_candidate_count", "eligible_candidate_count"),
                ("retriever_selected_child_count", "parent_context_child_count"),
            ):
                stage_metrics[self._section_metric_key(section.section_id, name)] += int(
                    getattr(diagnostics, attribute, 0) or 0
                )
        chunks = self._filter_chunks(
            retrieved,
            targets=section_targets,
        )
        missing_targets = [
            target
            for target in section_targets
            if not any(self._chunk_matches_target(chunk, target) for chunk in chunks)
        ]
        if missing_targets:
            retrieved.extend(await self._retrieve_focused_aliases(missing_targets, query_cache, query_semaphore))
            chunks = self._filter_chunks(retrieved, targets=section_targets)
            stage_metrics[self._section_metric_key(section.section_id, "retrieved_chunk_count")] = len(retrieved)
        stage_metrics[self._section_metric_key(section.section_id, "filtered_chunk_count")] = len(chunks)
        if not chunks:
            return (
                [],
                [],
                set(),
                "검색 근거를 검증하지 못함" if retrieved else "관련 검색 자료 없음",
                stage_metrics,
            )
        batches, split_chunk_count = self._evidence_batches(chunks)
        stage_metrics[self._section_metric_key(section.section_id, "batch_count")] = len(batches)
        stage_metrics[self._section_metric_key(section.section_id, "batch_forwarded_chunk_count")] = sum(
            len(batch) for batch in batches
        )
        stage_metrics[self._section_metric_key(section.section_id, "split_chunk_count")] = split_chunk_count
        if not batches:
            return [], [], set(), "관련 검색 자료 없음", stage_metrics
        batch_tasks = {
            asyncio.create_task(
                self._process_evidence_batch(
                    section=section,
                    chunks=batch,
                    targets=section_targets,
                    approved_warnings=approved_warnings,
                    rejection_metrics=rejection_metrics,
                    batch_semaphore=batch_semaphore,
                    deadline=deadline,
                )
            ): index
            for index, batch in enumerate(batches)
        }
        try:
            done, pending = await asyncio.wait(
                batch_tasks,
                timeout=max(0, deadline - asyncio.get_running_loop().time() - 0.1),
            )
        except BaseException:
            for task in batch_tasks:
                task.cancel()
            await asyncio.gather(*batch_tasks, return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        stage_metrics[self._section_metric_key(section.section_id, "batch_completed_count")] = len(done)
        stage_metrics[self._section_metric_key(section.section_id, "batch_incomplete_count")] = len(pending)
        cards: list[LifestyleCard] = []
        sources: dict[str, CardSource] = {}
        coverage: set[str] = set()
        failed = 0
        for task in sorted(done, key=batch_tasks.__getitem__):
            try:
                batch_cards, batch_sources, batch_coverage, drafted_count, omitted_count = task.result()
            except Exception:
                failed += 1
                continue
            stage_metrics[self._section_metric_key(section.section_id, "drafted_claim_count")] += drafted_count
            stage_metrics[self._section_metric_key(section.section_id, "verifier_omitted_claim_count")] += omitted_count
            for card in batch_cards:
                prefix = card.id.rsplit(":", 1)[0]
                cards.append(card.model_copy(update={"id": f"{prefix}:{len(cards) + 1}"}))
            sources.update({source.id: source for source in batch_sources})
            coverage.update(batch_coverage)
        stage_metrics[self._section_metric_key(section.section_id, "batch_failed_count")] = failed
        stage_metrics[self._section_metric_key(section.section_id, "verified_card_count")] = len(cards)
        reason = "검증된 근거 없음"
        if pending:
            reason = "일부 근거 배치 검증 시간 초과"
        elif failed:
            reason = "일부 근거 배치 검증 실패"
        return cards, list(sources.values()), coverage, reason, stage_metrics

    async def _process_evidence_batch(
        self,
        *,
        section: ReportRagSectionPlan,
        chunks: list[RetrievedKnowledgeChunk],
        targets: list[ReportRagTarget],
        approved_warnings: list[dict[str, str]],
        rejection_metrics: dict[str, int],
        batch_semaphore: asyncio.Semaphore,
        deadline: float,
    ) -> tuple[list[LifestyleCard], list[CardSource], set[str], int, int]:
        # The byte budget bounds retrieved evidence. Targets and approved
        # warnings are server-owned small metadata today; budget them too if
        # their contract grows rather than silently dropping either payload.
        trusted = self._claims_input([section], chunks, targets, approved_warnings)
        async with batch_semaphore:
            drafted = _parse_claims(
                await _invoke(self._claim_writer, trusted), metrics=rejection_metrics, stage="draft"
            )
            if not drafted.claims:
                return [], [], set(), 0, 0
            edited = _parse_claims(
                await _invoke(self._verifier, self._verifier_input(drafted, trusted, chunks)),
                metrics=rejection_metrics,
                stage="verify",
            )
            omitted_count = max(0, len(drafted.claims) - len(edited.claims))
            if self._claim_text_changed(drafted, edited):
                originals = {claim.model_dump_json(exclude={"grounded"}) for claim in drafted.claims}
                unchanged = [
                    claim for claim in edited.claims if claim.model_dump_json(exclude={"grounded"}) in originals
                ]
                changed = _ClaimsPayload(claims=[claim for claim in edited.claims if claim not in unchanged])
                repaired = _ClaimsPayload()
                try:
                    # The section keeps a 0.1s publish reserve, so a slow
                    # repair cannot erase already verified siblings.
                    repair_seconds = deadline - asyncio.get_running_loop().time() - 0.11
                    if repair_seconds <= 0:
                        raise TimeoutError("no repair budget remaining")
                    async with asyncio.timeout(repair_seconds):
                        reverified = _parse_claims(
                            await _invoke(self._verifier, self._verifier_input(changed, trusted, chunks)),
                            metrics=rejection_metrics,
                            stage="repair",
                        )
                    repaired = self._retain_unchanged_reverified_claims(changed, reverified)
                except Exception:
                    _count_rejection(rejection_metrics, "repair_failed")
                edited = _ClaimsPayload(claims=[*unchanged, *repaired.claims])
        cards, sources, coverage = self._validated_cards(
            value=edited,
            chunks=chunks,
            targets=targets,
            planned_targets={section.section_id: set(section.target_ids)},
            rejection_metrics=rejection_metrics,
        )
        return cards, sources, coverage.get(section.section_id, set()), len(drafted.claims), omitted_count

    @staticmethod
    def _verifier_input(claims: _ClaimsPayload, trusted: dict, chunks: list[RetrievedKnowledgeChunk]) -> dict:
        # Give the existing verifier precise structural failures before final
        # rejection. These checks do not establish medical support or approval.
        content_by_id = {chunk.point_id: chunk.content for chunk in chunks}
        checks = []
        for claim_index, claim in enumerate(claims.claims):
            for evidence_index, evidence in enumerate(claim.evidence):
                content = content_by_id.get(evidence.chunk_id)
                if content is None or evidence.exact_quote.strip() not in content:
                    checks.append(
                        {
                            "claim_index": claim_index,
                            "evidence_index": evidence_index,
                            "code": "unknown_chunk" if content is None else "quote_not_in_chunk",
                        }
                    )
        return {"candidate_claims": claims.model_dump(), "trusted_evidence": trusted, "server_checks": checks}

    @classmethod
    def _evidence_batches(
        cls,
        chunks: list[RetrievedKnowledgeChunk],
    ) -> tuple[list[list[RetrievedKnowledgeChunk]], int]:
        batches: list[list[RetrievedKnowledgeChunk]] = []
        current: list[RetrievedKnowledgeChunk] = []
        current_bytes = 0
        split_chunk_count = 0
        for chunk in chunks:
            parts = cls._split_evidence_chunk(chunk)
            if len(parts) > 1:
                split_chunk_count += 1
                if current:
                    batches.append(current)
                    current, current_bytes = [], 0
                # The original point ID is retained for exact-quote/source
                # binding. Isolate its overlapping parts so a batch-local ID
                # index never overwrites a sibling part.
                batches.extend([[part] for part in parts])
                continue
            part = parts[0]
            size = len(part.content.encode("utf-8"))
            if current and current_bytes + size > _MAX_BATCH_EVIDENCE_BYTES:
                batches.append(current)
                current, current_bytes = [], 0
            current.append(part)
            current_bytes += size
        if current:
            batches.append(current)
        return batches, split_chunk_count

    @staticmethod
    def _split_evidence_chunk(chunk: RetrievedKnowledgeChunk) -> list[RetrievedKnowledgeChunk]:
        text = chunk.content
        if len(text.encode("utf-8")) <= _MAX_BATCH_EVIDENCE_BYTES:
            return [chunk]
        parts: list[RetrievedKnowledgeChunk] = []
        start = 0
        while start < len(text):
            end = ReportRagPipeline._utf8_batch_end(text, start)
            if end < len(text):
                end = ReportRagPipeline._preferred_batch_end(text, start, end)
            part = text[start:end]
            parts.append(chunk.model_copy(update={"content": part, "embedding_text": part}))
            if end >= len(text):
                break
            start = max(start + 1, end - _BATCH_EVIDENCE_OVERLAP_CHARACTERS)
        return parts

    @staticmethod
    def _utf8_batch_end(text: str, start: int) -> int:
        low, high = start + 1, len(text)
        while low <= high:
            middle = (low + high) // 2
            if len(text[start:middle].encode("utf-8")) <= _MAX_BATCH_EVIDENCE_BYTES:
                low = middle + 1
            else:
                high = middle - 1
        return max(start + 1, high)

    @staticmethod
    def _preferred_batch_end(text: str, start: int, end: int) -> int:
        minimum = start + (end - start) // 2
        candidates = (
            text.rfind("\n\n", minimum, end),
            text.rfind("\n", minimum, end),
            text.rfind(". ", minimum, end),
            text.rfind(" ", minimum, end),
        )
        boundary = max(candidates)
        return boundary + 1 if boundary > start else end

    @staticmethod
    def _section_metric_key(section_id: str, name: str) -> str:
        return f"section_{section_id}_{name}"

    @classmethod
    def _empty_section_metrics(cls, section_id: str) -> dict[str, int]:
        return {
            cls._section_metric_key(section_id, name): 0
            for name in (
                "retrieved_chunk_count",
                "filtered_chunk_count",
                "drafted_claim_count",
                "verifier_omitted_claim_count",
                "verified_card_count",
                "retriever_raw_candidate_count",
                "retriever_eligible_candidate_count",
                "retriever_selected_child_count",
                "batch_count",
                "batch_forwarded_chunk_count",
                "split_chunk_count",
                "batch_completed_count",
                "batch_incomplete_count",
                "batch_failed_count",
            )
        }

    async def _retrieve_grouped(
        self,
        query: str,
        targets: list[ReportRagTarget],
        cache: dict[tuple[str, tuple[str, ...]], asyncio.Task[Any]],
        semaphore: asyncio.Semaphore,
    ) -> Any:
        key = (query, tuple(target.id for target in targets))
        if key not in cache:
            # The retriever appends entity_names to the embedding input: scope
            # them to this query rather than embedding the whole stack again.
            scoped = [
                target
                for target in targets
                if any(
                    self._normal(name) in self._normal(query)
                    for name in (target.name, *target.aliases)
                    if self._normal(name)
                )
            ] or targets

            async def call() -> Any:
                async with semaphore:
                    return await self._retriever.search_with_diagnostics(
                        execution_plan=self._execution_plan(query=query, targets=scoped)
                    )

            cache[key] = asyncio.create_task(call())
        return await cache[key]

    async def _retrieve_focused_aliases(
        self,
        targets: list[ReportRagTarget],
        query_cache: dict[tuple[str, tuple[str, ...]], asyncio.Task[Any]],
        semaphore: asyncio.Semaphore,
    ) -> list[RetrievedKnowledgeChunk]:
        # Compound queries may dilute known ingredients below the threshold.
        # Rescue only supplied aliases; round-robin avoids starving siblings.
        focused: dict[tuple[str, str], ReportRagTarget] = {}
        for position in range(max((len(target.aliases) for target in targets), default=0)):
            for target in targets:
                if position < len(target.aliases):
                    alias = target.aliases[position].strip()
                    if alias and self._normal(alias) != self._normal(target.name):
                        focused.setdefault((target.item_type, alias), target)
            if len(focused) >= 24:
                break

        async def retrieve(kind: str, alias: str, target: ReportRagTarget) -> Any:
            query = f"{alias} 주의사항"
            key = (query, ("focused", kind))
            if key not in query_cache:
                # One report-wide budget, even when sections miss different
                # targets. Reserve synchronously before yielding to another task.
                if sum(cache_key[1][0] == "focused" for cache_key in query_cache) >= 24:
                    return None
                # Original section targets still govern evidence/claim binding.
                plan = self._execution_plan(
                    query=query, targets=[ReportRagTarget(target.id, target.item_id, kind, alias)]
                )
                entity = plan.query_plan.entities[0].model_copy(
                    update={"entity_type": MedicationQueryEntityType.INGREDIENT_NAME}
                )
                plan = plan.model_copy(update={"query_plan": plan.query_plan.model_copy(update={"entities": [entity]})})

                async def call() -> Any:
                    async with semaphore:
                        return await self._retriever.search_with_diagnostics(execution_plan=plan)

                query_cache[key] = asyncio.create_task(call())
            return await query_cache[key]

        results = await asyncio.gather(
            *(retrieve(kind, alias, target) for (kind, alias), target in list(focused.items())[:24]),
            return_exceptions=True,
        )
        return [
            chunk
            for result in results
            if result is not None and not isinstance(result, BaseException)
            for chunk in result.chunks
        ]

    @staticmethod
    def _claim_text_changed(before: object, after: object) -> bool:
        originals = {claim.model_dump_json(exclude={"grounded"}) for claim in _parse_claims(before).claims}
        return any(
            claim.model_dump_json(exclude={"grounded"}) not in originals for claim in _parse_claims(after).claims
        )

    @staticmethod
    def _retain_unchanged_reverified_claims(before: object, after: object) -> _ClaimsPayload:
        """A repair may omit bad claims, but may not silently rewrite good ones."""
        original = _parse_claims(before)
        reverified = _parse_claims(after)

        originals = {claim.model_dump_json(exclude={"grounded"}) for claim in original.claims}
        retained = [claim for claim in reverified.claims if claim.model_dump_json(exclude={"grounded"}) in originals]
        return _ClaimsPayload(claims=retained)

    def _execution_plan(self, *, query: str, targets: list[ReportRagTarget]) -> MedicationSearchExecutionPlan:
        entities = [
            MedicationQueryEntity(
                surface=alias,
                canonical_name=alias,
                entity_type=(
                    MedicationQueryEntityType.PRODUCT_NAME
                    if alias == target.name and not target.ingredient_only
                    else MedicationQueryEntityType.INGREDIENT_NAME
                ),
                kind=(
                    InteractionEntityKind.DRUG if target.item_type == "MEDICATION" else InteractionEntityKind.SUPPLEMENT
                ),
            )
            for target in targets
            for alias in (target.aliases if target.ingredient_only else (target.name, *target.aliases))
        ]
        names = list(dict.fromkeys(entity.canonical_name for entity in entities))
        return MedicationSearchExecutionPlan(
            query_plan=MedicationKnowledgeQueryPlan(
                original_query=query,
                expanded_query=query,
                entity_names=names,
                entities=entities,
                document_types=[
                    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    KnowledgeDocumentType.SUPPLEMENT_CODE,
                    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
                    KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                    KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH,
                    KnowledgeDocumentType.RESEARCH_ARTICLE,
                    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    KnowledgeDocumentType.PHARM_REVIEW,
                ],
            ),
            patient_medication_names=[
                target.name for target in targets if target.item_type == "MEDICATION" and not target.ingredient_only
            ],
            patient_supplement_names=[target.name for target in targets if target.item_type == "SUPPLEMENT"],
            approved_rule_status=InteractionRuleLookupStatus.NO_APPROVED_RULE,
            include_patient_context=False,
            context_hash="0" * 64,
            approved_rules_hash="0" * 64,
            limit=6,
        )

    def _filter_chunks(
        self, chunks: list[RetrievedKnowledgeChunk], *, targets: list[ReportRagTarget]
    ) -> list[RetrievedKnowledgeChunk]:
        eligible: list[RetrievedKnowledgeChunk] = []
        seen: set[str] = set()
        for chunk in sorted(chunks, key=lambda item: (-item.similarity_score, item.point_id)):
            metadata = chunk.metadata
            registry_source = self._source_registry.get(metadata.document_id)
            valid_provenance = bool(
                metadata.source_id.strip()
                and metadata.title.strip()
                and metadata.provider.strip()
                and registry_source == (metadata.source_id, metadata.provider)
                and (metadata.source_url is None or self._safe_source_url(metadata.source_url))
            )
            if (
                chunk.point_id in seen
                or chunk.chunk_id in seen
                or metadata.dataset_version != self._dataset_version
                or not metadata.index_eligible
                or metadata.access_scope not in (KnowledgeAccessScope.PUBLIC, KnowledgeAccessScope.DEMO_RESTRICTED)
                or not (
                    metadata.study_population
                    in (KnowledgeStudyPopulation.HUMAN, KnowledgeStudyPopulation.NOT_APPLICABLE)
                    or (
                        metadata.study_population is KnowledgeStudyPopulation.UNKNOWN
                        and metadata.document_type is KnowledgeDocumentType.DRUG_ENCYCLOPEDIA
                    )
                )
                or not valid_provenance
                or _INJECTION.search(chunk.content) is not None
                or not any(self._chunk_matches_target(chunk, target) for target in targets)
            ):
                continue
            eligible.append(chunk)
            seen.update((chunk.point_id, chunk.chunk_id))
        return eligible

    def _validated_cards(  # noqa: C901 - validation keeps evidence boundary in one auditable pass
        self,
        *,
        value: object,
        chunks: list[RetrievedKnowledgeChunk],
        targets: list[ReportRagTarget],
        planned_targets: dict[str, set[str]],
        rejection_metrics: dict[str, int] | None = None,
    ) -> tuple[list[LifestyleCard], list[CardSource], dict[str, set[str]]]:
        payload = _parse_claims(value, metrics=rejection_metrics)
        chunk_by_id = {chunk.point_id: chunk for chunk in chunks}
        known_targets = {target.id: target for target in targets}
        cards: list[LifestyleCard] = []
        sources: dict[str, CardSource] = {}
        coverage: dict[str, set[str]] = {}
        for claim in payload.claims:
            if not claim.grounded:
                _count_rejection(rejection_metrics, "ungrounded")
                continue
            if any(target_id not in known_targets for target_id in claim.target_ids) or not set(
                claim.target_ids
            ).issubset(planned_targets.get(claim.section_id, set())):
                _count_rejection(rejection_metrics, "target")
                continue
            rendered_text = " ".join((claim.title, claim.summary, claim.action))
            if _DOSE_CHANGE.search(rendered_text):
                _count_rejection(rejection_metrics, "dose")
                continue
            pairs = [(chunk_by_id.get(item.chunk_id), item.exact_quote) for item in claim.evidence]
            if any(chunk is None for chunk, _ in pairs):
                _count_rejection(rejection_metrics, "source")
                continue
            if not all(quote.strip() and quote.strip() in chunk.content for chunk, quote in pairs):
                _count_rejection(rejection_metrics, "quote")
                continue
            if claim.section_id == "food_drink" and not any(
                mentions_food_or_drink(quote) or _FOOD_CONTEXT.search(quote) for _, quote in pairs
            ):
                _count_rejection(rejection_metrics, "section")
                continue
            if claim.section_id == "lifestyle" and _CLINICAL_PRECAUTION.search(
                " ".join([rendered_text, *(quote for _, quote in pairs)])
            ):
                _count_rejection(rejection_metrics, "section")
                continue
            claim_targets = [known_targets[target_id] for target_id in claim.target_ids]
            if not self._safe_ingredient_claim(claim_targets, pairs, rendered_text) or not all(
                any(self._chunk_matches_target(chunk, target) for chunk, _ in pairs) for target in claim_targets
            ):
                _count_rejection(rejection_metrics, "target_evidence")
                continue
            quote_numbers = {self._normal(token) for _, quote in pairs for token in _NUMBER.findall(quote)}
            if not {self._normal(token) for token in _NUMBER.findall(rendered_text)}.issubset(quote_numbers):
                _count_rejection(rejection_metrics, "number")
                continue
            source_ids: list[str] = []
            for chunk, quote in pairs:
                base_source_id = f"rag:source-{chunk.metadata.document_id}:{chunk.point_id}"
                source_id = base_source_id + ":" + hashlib.sha256(quote.strip().encode()).hexdigest()[:8]
                source_ids.append(source_id)
                sources[source_id] = CardSource(
                    id=source_id,
                    title=chunk.metadata.title,
                    organization=chunk.metadata.provider,
                    url=chunk.metadata.source_url,
                    evidence_level=chunk.metadata.evidence_level.value,
                    quote=quote.strip(),
                    chunk_id=chunk.point_id,
                    dataset_version=chunk.metadata.dataset_version,
                )
            target_item_ids = list(dict.fromkeys(known_targets[target_id].item_id for target_id in claim.target_ids))
            cards.append(
                LifestyleCard(
                    id=f"rag:{claim.section_id}:{claim.target_ids[0]}:{len(cards) + 1}",
                    category=_SECTION_CATEGORY[claim.section_id],
                    title=claim.title.strip(),
                    summary=self._scoped_summary(claim.summary.strip(), claim_targets),
                    action=claim.action.strip(),
                    related_item_ids=target_item_ids,
                    source_ids=source_ids,
                )
            )
            coverage.setdefault(claim.section_id, set()).update(claim.target_ids)
        return cards, list(sources.values()), coverage

    @staticmethod
    def _normal(value: str) -> str:
        return "".join(value.casefold().split())

    @staticmethod
    def _safe_source_url(value: str) -> bool:
        try:
            parsed = urlparse(value)
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and parsed.username is None
        except ValueError:
            return False

    def _chunk_matches_target(self, chunk: RetrievedKnowledgeChunk, target: ReportRagTarget) -> bool:
        if target.ingredient_only:
            # A manufacturer's label does not establish a generic product's
            # identity or formulation. Only explicitly tagged common evidence.
            known = {self._normal(alias) for alias in target.aliases}
            tagged = {self._normal(name) for name in chunk.metadata.ingredient_names}
            drug_names = {self._normal(name) for name in chunk.metadata.drug_names}
            # Legacy encyclopedias store their ingredient in the bilingual
            # document title/drug tags rather than ingredient_names. Accept
            # only an exact title anchor, never a brand-prefixed substring.
            if not tagged and chunk.metadata.document_type is KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
                title = self._normal(chunk.metadata.title)
                match = re.fullmatch(r"([^()]+)(?:\(([a-z][a-z0-9 -]*)\))?", title)
                if match and match[1] in known and match[1] in drug_names:
                    allowed_tags = {match[1], title, match[2] or ""}
                    if drug_names.issubset(allowed_tags):
                        tagged = {match[1]}
                        drug_names = {match[1]}
            return (
                chunk.metadata.document_type
                in {
                    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
                    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    KnowledgeDocumentType.PHARM_REVIEW,
                    KnowledgeDocumentType.RESEARCH_ARTICLE,
                }
                and bool(known & tagged)
                and drug_names.issubset(known)
            )
        searchable = self._normal(
            " ".join(
                [
                    chunk.content,
                    *chunk.metadata.drug_names,
                    *chunk.metadata.ingredient_names,
                    *chunk.metadata.food_names,
                ]
            )
        )
        return any(self._normal(name) in searchable for name in (target.name, *target.aliases) if self._normal(name))

    def _safe_ingredient_claim(self, targets, pairs, text: str) -> bool:
        scoped = [target for target in targets if target.ingredient_only]
        if not scoped:
            return True
        return not (_DOSE_CHANGE.search(text) or _INGREDIENT_DOSING.search(text)) and all(
            self._chunk_matches_target(chunk, target)
            and not (_DOSE_CHANGE.search(quote) or _INGREDIENT_DOSING.search(quote))
            for target in scoped
            for chunk, quote in pairs
        )

    @staticmethod
    def _scoped_summary(summary: str, targets: list[ReportRagTarget]) -> str:
        if any(target.ingredient_only for target in targets):
            return "정확한 제품은 미확정이며, 확인된 성분 공통 안내입니다. " + summary
        return summary

    @staticmethod
    def _planner_input(targets: list[ReportRagTarget]) -> dict[str, object]:
        return {
            "targets": [
                {"id": target.id, "name": target.name, "aliases": list(target.aliases), "type": target.item_type}
                for target in targets
            ],
            "allowed_sections": list(_SECTION_IDS),
        }

    def _claims_input(
        self,
        plan: list[ReportRagSectionPlan],
        chunks: list[RetrievedKnowledgeChunk],
        targets: list[ReportRagTarget],
        approved_warnings: list[dict[str, str]],
    ) -> dict[str, object]:
        return {
            "plan": [{"section_id": section.section_id, "target_ids": section.target_ids} for section in plan],
            "targets": [
                {
                    "id": target.id,
                    "name": target.name,
                    "aliases": list(target.aliases),
                    "ingredient_only": target.ingredient_only,
                }
                for target in targets
            ],
            "approved_warnings": approved_warnings,
            "chunks": [
                {
                    "chunk_id": chunk.point_id,
                    "content": chunk.content,
                    "source": chunk.metadata.title,
                    "source_section": chunk.metadata.section_type.value,
                    "matched_target_ids": [
                        target.id
                        for target in targets
                        if any(target.id in section.target_ids for section in plan)
                        and self._chunk_matches_target(chunk, target)
                    ],
                }
                for chunk in chunks
            ],
        }

    @staticmethod
    def _statuses(
        *,
        targets: list[ReportRagTarget],
        reasons: dict[str, str],
        verified: set[str] | None = None,
        partial: set[str] | None = None,
        section_target_ids: dict[str, set[str]] | None = None,
    ) -> list[ReportGuidanceSectionStatus]:
        verified = verified or set()
        partial = partial or set()
        target_by_id = {target.id: target for target in targets}
        section_target_ids = section_target_ids or {section_id: set(target_by_id) for section_id in _SECTION_IDS}
        return [
            ReportGuidanceSectionStatus(
                section_id=section_id,
                status=("partial" if section_id in partial else "verified" if section_id in verified else "unverified"),
                reason=reasons.get(section_id, "검증된 근거 없음"),
                target_item_ids=list(
                    dict.fromkeys(
                        target.item_id for target in targets if target.id in section_target_ids.get(section_id, set())
                    )
                ),
            )
            for section_id in _SECTION_IDS
        ]


def build_openai_report_rag_pipeline(
    *, retriever: _Retriever, dataset_version: str, model: str, api_key: SecretStr | None
) -> ReportRagPipeline:
    """Build three actual LCEL structured stages; all source text is data, never instructions."""
    client = ChatOpenAI(model=model, temperature=0, api_key=api_key, timeout=25.0, max_retries=0)
    planner_chain = (
        RunnableLambda(
            lambda value: [
                SystemMessage(content=load_prompt_asset("intake_report_planner.md")),
                HumanMessage(content=_json_data(value)),
            ]
        )
        | client.with_structured_output(_PlanPayload, method="json_schema", strict=True)
    ).with_config(run_name="intake_report_rag.planner")
    claims_chain = (
        RunnableLambda(
            lambda value: [
                SystemMessage(content=load_prompt_asset("intake_report_claims.md")),
                HumanMessage(content=_json_data(value)),
            ]
        )
        # Keep the remote schema strict, but parse locally per claim so one
        # malformed candidate cannot discard its valid neighbors.
        | client.with_structured_output(_ClaimsPayload.model_json_schema(), method="json_schema", strict=True)
    ).with_config(run_name="intake_report_rag.claims")
    verifier_chain = (
        RunnableLambda(
            lambda value: [
                SystemMessage(content=load_prompt_asset("intake_report_verifier.md")),
                HumanMessage(content=_json_data(value)),
            ]
        )
        | client.with_structured_output(_ClaimsPayload.model_json_schema(), method="json_schema", strict=True)
    ).with_config(run_name="intake_report_rag.verifier")
    return ReportRagPipeline(
        retriever=retriever,
        dataset_version=dataset_version,
        planner=planner_chain,
        claim_writer=claims_chain,
        verifier=verifier_chain,
    )


class RagIntakeReportCardsGenerator:
    """Server-rendered report cards plus source-locked RAG lifestyle cards."""

    # The pipeline owns its retrieval. Avoid a second, serial legacy retrieval.
    uses_knowledge_evidence = False

    def __init__(self, *, pipeline: ReportRagPipeline, base_generator: Any) -> None:
        self._pipeline = pipeline
        self._base_generator = base_generator

    async def generate(self, *, draft: Any, remaining_seconds: float | None = None) -> Any:
        from ai_worker.reports.v11_cards import render_cards_markdown
        from ai_worker.schemas.intake_report import IntakeReportGenerationOutcome

        targets = [
            ReportRagTarget(
                id=f"{item.item_type.value.lower()}:{item.item_id}",
                item_id=item.item_id,
                item_type=item.item_type.value,
                name=item.product_name,
                ingredient_only=(
                    item.item_type.value == "MEDICATION" and item.item_id not in draft.guide_item_bindings
                ),
                aliases=tuple(
                    dict.fromkeys(
                        alias
                        for alias in (
                            item.ingredient_name,
                            *getattr(item, "ingredient_aliases", []),
                            *(
                                total.nutrient_name
                                for total in draft.nutrient_totals
                                if item.product_name in total.included_product_names
                            ),
                        )
                        if alias and alias.strip() and alias.strip() != item.product_name
                    )
                ),
            )
            for item in draft.current_stack
        ]
        # The established whitespace-only generator and new RAG chain share
        # one use-case deadline but run concurrently, never 90s + RAG serially.
        base_task = asyncio.create_task(self._base_generator.generate(draft=draft))
        approved_warnings = [
            {"title": card.title, "summary": card.summary, "action": card.check_item}
            for card in draft.review_cards
            if card.evidence_level.value == "APPROVED_RULE"
        ]
        rag_task = asyncio.create_task(
            self._pipeline.run(
                targets=targets,
                # Keep a short outer-budget reserve for cancellation, merge,
                # Markdown rendering, and a graceful partial outcome.
                remaining_seconds=(max(0.1, remaining_seconds - 1.0) if remaining_seconds is not None else None),
                approved_warnings=approved_warnings,
            )
        )
        try:
            base = await base_task
            rag = await rag_task
        except BaseException:
            for task in (base_task, rag_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(base_task, rag_task, return_exceptions=True)
            raise
        cards = base.cards
        if cards is None:  # The established generator always returns cards; fail closed if its contract changes.
            raise RuntimeError("evidence card generator returned no cards")
        sources = {source.id: source for source in cards.sources}
        sources.update({source.id: source for source in rag.sources})
        merged = cards.model_copy(
            update={
                "lifestyle": [*cards.lifestyle, *rag.cards],
                "sources": sorted(sources.values(), key=lambda source: source.id),
                "section_statuses": rag.section_statuses,
            }
        )
        return IntakeReportGenerationOutcome(
            report_markdown=render_cards_markdown(merged, draft),
            cards=merged,
            fallback_used=False,
            rag_evidence_available=rag.rag_evidence_available,
            rag_metrics=rag.metrics,
            rag_partial=any(status.status != "verified" for status in rag.section_statuses),
        )

    async def generate_with_budget(self, *, draft: Any, remaining_seconds: float) -> Any:
        return await self.generate(draft=draft, remaining_seconds=remaining_seconds)
