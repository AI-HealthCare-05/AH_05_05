import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable

from ai_worker.assemblers.intake_report_assembler import IntakeReportAssembler
from ai_worker.domain.errors import AIWorkerError
from ai_worker.domain.interfaces import (
    ActiveIntakeContextProvider,
    IntakeReportGenerator,
    InteractionRuleRepository,
    MedicationGuideRepository,
    MedicationKnowledgeRetriever,
)
from ai_worker.observability.chat_tracer import ChatTracer, NoOpChatTracer
from ai_worker.reports.nutrients import ReportNutrientData
from ai_worker.schemas.intake_report import (
    IntakeReportDraft,
    IntakeReportItemType,
    IntakeReportResult,
    IntakeReportStatus,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import ActiveIntakeContext, InteractionRuleFact
from ai_worker.schemas.medication_search import (
    InteractionRuleLookupStatus,
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntityType,
    MedicationSearchExecutionPlan,
)

logger = logging.getLogger(__name__)


_SAFE_RAG_METRIC_NAMES = frozenset({"query_count", "focused_query_count", "verified_claim_count"})
_SAFE_RAG_SECTION_METRIC_SUFFIXES = frozenset(
    {
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
    }
)


def _safe_rag_metrics(metrics: dict[str, int]) -> dict[str, int]:
    """Keep report runtime logs to known integer counters only."""
    safe: dict[str, int] = {}
    for name, value in metrics.items():
        if not isinstance(value, int) or isinstance(value, bool):
            continue
        if name in _SAFE_RAG_METRIC_NAMES or name.startswith("claim_rejected_"):
            safe[name] = value
            continue
        if name.startswith("section_") and any(
            name.endswith(f"_{suffix}") for suffix in _SAFE_RAG_SECTION_METRIC_SUFFIXES
        ):
            safe[name] = value
    return safe


class GenerateIntakeReportUseCase:
    """Build a report from active intakes without creating a chat session."""

    _MAX_RAG_SUPPLEMENTS = 5
    _RAG_CHUNKS_PER_SUPPLEMENT = 2

    def __init__(
        self,
        *,
        context_provider: ActiveIntakeContextProvider,
        guide_repository: MedicationGuideRepository,
        interaction_rule_repository: InteractionRuleRepository,
        knowledge_retriever: MedicationKnowledgeRetriever,
        generator: IntakeReportGenerator,
        assembler: IntakeReportAssembler | None = None,
        tracer: ChatTracer | None = None,
        nutrient_loader: Callable[[ActiveIntakeContext], Awaitable[ReportNutrientData]] | None = None,
    ) -> None:
        self._context_provider = context_provider
        self._guide_repository = guide_repository
        self._interaction_rule_repository = interaction_rule_repository
        self._knowledge_retriever = knowledge_retriever
        self._generator = generator
        self._assembler = assembler or IntakeReportAssembler()
        self._tracer = tracer or NoOpChatTracer()
        self._nutrient_loader = nutrient_loader

    async def execute(
        self,
        *,
        user_id: int,
    ) -> IntakeReportResult:
        deadline = asyncio.get_running_loop().time() + 110.0
        context = await self._load_context(user_id=user_id)
        if not context.medications and not context.supplements:
            return IntakeReportResult.empty(user_id=user_id)

        guide_lookups, approved_rules = await self._collect_rdbms_evidence(
            context=context,
        )
        # Evidence-locked cards do not consume free-form retrieval passages.
        # Do not label an unused dependency's outage as a partial card report.
        # Legacy generators retain their existing retrieval path by default.
        if getattr(self._generator, "uses_knowledge_evidence", True):
            knowledge_chunks, rag_available = await self._retrieve_knowledge(
                context=context,
                approved_rules=approved_rules,
            )
        else:
            knowledge_chunks, rag_available = [], True
        draft = self._assembler.assemble(
            context=context,
            guide_lookups=guide_lookups,
            approved_rules=approved_rules,
            knowledge_chunks=knowledge_chunks,
            rag_available=rag_available,
        )
        # Preserve registration identity even when names are repeated or a guide
        # has a canonical display name different from the user's registration.
        medication_names = list(dict.fromkeys(item.name.strip() for item in context.medications if item.name.strip()))
        lookups_by_name = dict(zip(medication_names, guide_lookups, strict=True))
        guides_by_name = {
            name: lookup.guide.medication_guide_id
            for name, lookup in lookups_by_name.items()
            if lookup.guide is not None and not lookup.is_ambiguous
        }
        inferred_guide_items = {
            item.medication_id: self._inferred_guide_notice(
                input_name=(lookup.original_name or item.name).strip(),
                product_name=lookup.guide.product_name,
            )
            for item in context.medications
            if (lookup := lookups_by_name.get(item.name.strip())) is not None
            and lookup.guide is not None
            and not lookup.is_ambiguous
            and lookup.is_inferred
        }
        draft = draft.model_copy(
            update={
                "guide_item_bindings": {
                    item.medication_id: guides_by_name[item.name.strip()]
                    for item in context.medications
                    if item.name.strip() in guides_by_name
                },
                "guide_evidence": list(
                    {
                        lookup.guide.medication_guide_id: lookup.guide
                        for lookup in guide_lookups
                        if lookup.guide is not None and not lookup.is_ambiguous
                    }.values()
                ),
                "inferred_guide_items": inferred_guide_items,
                "deterministic_markdown": self._with_inferred_guide_notices(
                    draft.deterministic_markdown,
                    inferred_guide_items,
                ),
                "knowledge_evidence": knowledge_chunks,
            }
        )
        if self._nutrient_loader is not None:
            nutrient_data = await self._nutrient_loader(context)
            draft = self._with_nutrients(draft, context, nutrient_data)
        async with self._tracer.span("intake_report.generate_markdown") as span:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise AIWorkerError("보고서 생성 제한 시간을 초과했습니다.")
            try:
                async with asyncio.timeout(remaining):
                    budgeted_generate = getattr(self._generator, "generate_with_budget", None)
                    outcome = (
                        await budgeted_generate(draft=draft, remaining_seconds=remaining)
                        if callable(budgeted_generate)
                        else await self._generator.generate(draft=draft)
                    )
            except TimeoutError as error:
                raise AIWorkerError("보고서 생성 제한 시간을 초과했습니다.") from error
            span.end(
                {
                    "fallback_used": outcome.fallback_used,
                    "fallback_reason": (outcome.fallback_reason.value if outcome.fallback_reason is not None else None),
                    "rag_evidence_available": outcome.rag_evidence_available,
                    "rag_query_count": outcome.rag_metrics.get("query_count", 0),
                    "rag_verified_claim_count": outcome.rag_metrics.get("verified_claim_count", 0),
                }
            )
            logger.info(
                "intake_report.rag_metrics=%s",
                json.dumps(_safe_rag_metrics(outcome.rag_metrics), sort_keys=True, separators=(",", ":")),
            )
        outcome_rag_available = (
            outcome.rag_evidence_available if outcome.rag_evidence_available is not None else rag_available
        )
        if outcome.rag_evidence_available is not None:
            draft = draft.model_copy(
                update={
                    "data_availability": draft.data_availability.model_copy(
                        update={"rag_evidence_available": outcome_rag_available}
                    )
                }
            )
        status = (
            IntakeReportStatus.COMPLETED
            if outcome_rag_available and not outcome.fallback_used and not outcome.rag_partial
            else IntakeReportStatus.PARTIAL
        )
        return draft.to_result(
            status=status,
            report_markdown=outcome.report_markdown,
            cards=outcome.cards,
            fallback_used=outcome.fallback_used,
            fallback_reason=outcome.fallback_reason,
        )

    @staticmethod
    def _inferred_guide_notice(*, input_name: str, product_name: str) -> str:
        return f"‘{input_name}’을 ‘{product_name}’으로 추정한 제품 안내입니다. 등록한 이름은 바꾸지 않았어요."

    @staticmethod
    def _with_inferred_guide_notices(markdown: str, notices: dict[int, str]) -> str:
        if not notices:
            return markdown
        return markdown + "\n\n## 제품 안내 이름 확인\n\n" + "\n".join(f"- {notice}" for notice in notices.values())

    @staticmethod
    def _with_nutrients(
        draft: IntakeReportDraft,
        context: ActiveIntakeContext,
        data: ReportNutrientData,
    ) -> IntakeReportDraft:
        labels = data.product_labels
        summaries = getattr(data, "product_ingredient_summaries", {})
        stack = [
            item.model_copy(
                update={
                    **(
                        {"registered_intake_info": item.registered_intake_info + " · " + labels[item.item_id]}
                        if labels.get(item.item_id)
                        else {}
                    ),
                    **({"ingredient_summary": summaries[item.item_id]} if summaries.get(item.item_id) else {}),
                }
            )
            if item.item_type == IntakeReportItemType.SUPPLEMENT
            and (labels.get(item.item_id) or summaries.get(item.item_id))
            else item
            for item in draft.current_stack
        ]
        lines = ["## 영양소 비교 기준", data.profile_label, data.basis_note]
        for total in data.totals:
            reference = (
                f"{total.reference_kind} {total.reference_value} {total.unit} · {total.reference_percent}%"
                if total.reference_percent is not None
                else "비교 기준 확인 필요"
            )
            lines.append(f"- {total.nutrient_name}: {total.daily_total} · {reference}")
        return draft.model_copy(
            update={
                "current_stack": stack,
                "nutrient_totals": data.totals,
                "profile_label": data.profile_label,
                "basis_note": data.basis_note,
                "deterministic_markdown": draft.deterministic_markdown + "\n\n" + "\n\n".join(lines),
            }
        )

    async def _load_context(self, *, user_id: int) -> ActiveIntakeContext:
        try:
            async with self._tracer.span("intake_report.active_context") as span:
                context = await self._context_provider.get_active_context(
                    user_id=user_id,
                    care_episode_id=None,
                )
                span.end(
                    {
                        "medication_count": len(context.medications),
                        "supplement_count": len(context.supplements),
                    }
                )
                return context
        except AIWorkerError:
            raise
        except Exception as error:
            raise AIWorkerError("활성 복용정보를 조회하지 못했습니다.") from error

    async def _collect_rdbms_evidence(
        self,
        *,
        context: ActiveIntakeContext,
    ) -> tuple[list, list[InteractionRuleFact]]:
        medication_names = list(
            dict.fromkeys(medication.name.strip() for medication in context.medications if medication.name.strip())
        )
        try:
            async with self._tracer.span("intake_report.rdbms_evidence") as span:
                guide_task = asyncio.gather(*(self._guide_repository.find_by_name(name) for name in medication_names))
                rule_task = self._interaction_rule_repository.find_approved_rules(
                    context=context,
                )
                guide_lookups, approved_rules = await asyncio.gather(
                    guide_task,
                    rule_task,
                )
                span.end(
                    {
                        "guide_lookup_count": len(guide_lookups),
                        "approved_rule_count": len(approved_rules),
                    }
                )
                return list(guide_lookups), approved_rules
        except AIWorkerError:
            raise
        except Exception as error:
            raise AIWorkerError("보고서용 제품 안내 또는 승인 규칙을 조회하지 못했습니다.") from error

    async def _retrieve_knowledge(
        self,
        *,
        context: ActiveIntakeContext,
        approved_rules: list[InteractionRuleFact],
    ) -> tuple[list[RetrievedKnowledgeChunk], bool]:
        supplement_names = list(
            dict.fromkeys(supplement.name.strip() for supplement in context.supplements if supplement.name.strip())
        )[: self._MAX_RAG_SUPPLEMENTS]
        if not supplement_names:
            return [], True

        plans = [
            self._build_execution_plan(
                supplement_name=name,
                context=context,
                approved_rules=approved_rules,
            )
            for name in supplement_names
        ]
        async with self._tracer.span("intake_report.rag_retrieve") as span:
            results = await asyncio.gather(
                *(
                    self._knowledge_retriever.search_with_diagnostics(
                        execution_plan=plan,
                    )
                    for plan in plans
                ),
                return_exceptions=True,
            )
            failures = [result for result in results if isinstance(result, Exception)]
            chunks = [
                chunk
                for result in results
                if not isinstance(result, Exception)
                for chunk in result.chunks[: self._RAG_CHUNKS_PER_SUPPLEMENT]
            ]
            span.end(
                {
                    "query_count": len(plans),
                    "retrieved_chunk_count": len(chunks),
                    "rag_available": not failures,
                }
            )
        return chunks, not failures

    @classmethod
    def _build_execution_plan(
        cls,
        *,
        supplement_name: str,
        context: ActiveIntakeContext,
        approved_rules: list[InteractionRuleFact],
    ) -> MedicationSearchExecutionPlan:
        query = f"{supplement_name} 기능 주의사항"
        query_plan = MedicationKnowledgeQueryPlan(
            original_query=query,
            expanded_query=query,
            entity_names=[supplement_name],
            entities=[
                MedicationQueryEntity(
                    surface=supplement_name,
                    canonical_name=supplement_name,
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.SUPPLEMENT,
                )
            ],
            document_types=[
                KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                KnowledgeDocumentType.SUPPLEMENT_CODE,
                KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH,
                KnowledgeDocumentType.RESEARCH_ARTICLE,
            ],
        )
        return MedicationSearchExecutionPlan(
            query_plan=query_plan,
            patient_medication_names=[item.name for item in context.medications],
            patient_supplement_names=[item.name for item in context.supplements],
            approved_rule_pair_keys=[rule.pair_key for rule in approved_rules],
            approved_rule_status=(
                InteractionRuleLookupStatus.MATCHED if approved_rules else InteractionRuleLookupStatus.NO_APPROVED_RULE
            ),
            include_patient_context=True,
            context_hash=cls._payload_hash(context.model_dump(mode="json")),
            approved_rules_hash=cls._payload_hash(
                [rule.model_dump(mode="json") for rule in approved_rules],
            ),
            limit=cls._RAG_CHUNKS_PER_SUPPLEMENT,
        )

    @staticmethod
    def _payload_hash(value: object) -> str:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
