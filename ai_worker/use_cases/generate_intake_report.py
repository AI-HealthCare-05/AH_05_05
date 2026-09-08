import asyncio
import hashlib
import json

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
from ai_worker.schemas.intake_report import IntakeReportResult, IntakeReportStatus
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
    ) -> None:
        self._context_provider = context_provider
        self._guide_repository = guide_repository
        self._interaction_rule_repository = interaction_rule_repository
        self._knowledge_retriever = knowledge_retriever
        self._generator = generator
        self._assembler = assembler or IntakeReportAssembler()
        self._tracer = tracer or NoOpChatTracer()

    async def execute(
        self,
        *,
        user_id: int,
    ) -> IntakeReportResult:
        context = await self._load_context(user_id=user_id)
        if not context.medications and not context.supplements:
            return IntakeReportResult.empty(user_id=user_id)

        guide_lookups, approved_rules = await self._collect_rdbms_evidence(
            context=context,
        )
        knowledge_chunks, rag_available = await self._retrieve_knowledge(
            context=context,
            approved_rules=approved_rules,
        )
        draft = self._assembler.assemble(
            context=context,
            guide_lookups=guide_lookups,
            approved_rules=approved_rules,
            knowledge_chunks=knowledge_chunks,
            rag_available=rag_available,
        )
        async with self._tracer.span("intake_report.generate_markdown") as span:
            outcome = await self._generator.generate(draft=draft)
            span.end(
                {
                    "fallback_used": outcome.fallback_used,
                    "fallback_reason": (
                        outcome.fallback_reason.value
                        if outcome.fallback_reason is not None
                        else None
                    ),
                }
            )
        status = (
            IntakeReportStatus.COMPLETED
            if rag_available
            else IntakeReportStatus.PARTIAL
        )
        return draft.to_result(
            status=status,
            report_markdown=outcome.report_markdown,
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
            dict.fromkeys(
                medication.name.strip()
                for medication in context.medications
                if medication.name.strip()
            )
        )
        try:
            async with self._tracer.span("intake_report.rdbms_evidence") as span:
                guide_task = asyncio.gather(
                    *(
                        self._guide_repository.find_by_name(name)
                        for name in medication_names
                    )
                )
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
            dict.fromkeys(
                supplement.name.strip()
                for supplement in context.supplements
                if supplement.name.strip()
            )
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
                InteractionRuleLookupStatus.MATCHED
                if approved_rules
                else InteractionRuleLookupStatus.NO_APPROVED_RULE
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
