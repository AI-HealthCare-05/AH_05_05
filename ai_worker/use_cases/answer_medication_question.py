import hashlib
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass

from ai_worker.chains.conditional_question_interpretation_chain import (
    ConditionalInterpretationReasonCode,
    ConditionalQuestionInterpretationChain,
    ConditionalQuestionInterpretationInput,
    ConditionalQuestionInterpretationOutput,
)
from ai_worker.chains.conversation_gate_chain import (
    ConversationGateChain,
    ConversationGateInput,
)
from ai_worker.chains.medication_query_plan_chain import (
    MedicationQueryPlanChain,
    MedicationQueryPlanChainInput,
    MedicationQuestionPlanResult,
    build_medication_query_plan_chain,
)
from ai_worker.chains.semantic_question_router import (
    QuestionRoutingDecision,
    QuestionRoutingReasonCode,
    QuestionRoutingStage,
    SemanticQuestionRouter,
    SemanticRouterInput,
)
from ai_worker.domain.chat_content_compactor import (
    ANSWER_COMPACTION_MARKER,
    compact_chat_content,
)
from ai_worker.domain.chat_risk_policy import MedicationChatRiskPolicy
from ai_worker.domain.chat_session_reference_memory import (
    ChatSessionReferenceMemory,
)
from ai_worker.domain.conversation_safety_policy import ConversationSafetyPolicy
from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.domain.evidence_gap_guidance import (
    EvidenceGapGuidanceBuilder,
    EvidenceGapSubject,
)
from ai_worker.domain.fatigue_conversation_policy import (
    FatigueConversationDisposition,
    FatigueConversationPolicy,
)
from ai_worker.domain.follow_up_schedule_answer import FollowUpScheduleAnswerAssembler
from ai_worker.domain.interaction_question_detector import (
    is_interaction_question,
)
from ai_worker.domain.interfaces import (
    ActiveIntakeContextProvider,
    FollowUpScheduleProvider,
    GroundedClaimValidator,
    InteractionRuleRepository,
    MedicationAnswerGenerator,
    MedicationGuideRepository,
    MedicationKnowledgeRetriever,
    MedicationQuestionResolver,
    SupplementIngredientCatalog,
    TherapeuticClassRepository,
)
from ai_worker.domain.medication_dose_question_policy import (
    MedicationDoseQuestionDecision,
    MedicationDoseQuestionKind,
    MedicationDoseQuestionPolicy,
)
from ai_worker.domain.medication_evidence_coverage import (
    MedicationEvidenceCoverageEvaluator,
)
from ai_worker.domain.medication_question_retrieval_policy import (
    should_execute_source_backed_retrieval,
)
from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy
from ai_worker.llm.assemblers.medication_answer_assembler import (
    MedicationAnswerAssembler,
)
from ai_worker.llm.generators.conversation_response_generator import (
    ConversationResponseGenerator,
    ConversationResponseInput,
)
from ai_worker.observability.chat_tracer import ChatTracer, NoOpChatTracer
from ai_worker.rag.errors import GuidelineRetrievalError
from ai_worker.rag.metadata.supplement_interaction_registry import (
    find_supplement_interaction_pair,
    known_supplement_names_in,
    supplement_pair_matches_text,
)
from ai_worker.rag.query_builders.coverage_gap_query_expander import (
    CoverageGapQueryExpander,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.conversation_gate import (
    ConversationClassification,
    ConversationDisposition,
    ConversationIntent,
    ConversationSafetySignal,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
    interaction_pair_type_for_kinds,
)
from ai_worker.schemas.knowledge import (
    KnowledgeCoverageRetryObservation,
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    InteractionRuleFact,
    MedicationChatAnswerDomain,
    MedicationChatProgress,
    MedicationChatProgressCallback,
    MedicationChatProgressStage,
    MedicationChatReasonCode,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRiskDecision,
    MedicationChatRiskScope,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
    MedicationEvidenceCoverage,
    MedicationGuideFact,
    MedicationGuideLookup,
    TherapeuticClassSelection,
    TherapeuticClassSelectionStatus,
)
from ai_worker.schemas.medication_search import (
    InteractionRuleLookupStatus,
    MedicationCatalogEntry,
    MedicationExpressionResolutionStatus,
    MedicationInteractionQueryPair,
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQuestionConfidence,
    MedicationQuestionIntent,
    MedicationQuestionInterpretation,
    MedicationQuestionReasonCode,
    MedicationQuestionResolution,
    MedicationQuestionScope,
    MedicationSearchExecutionObservation,
    MedicationSearchExecutionPlan,
)
from ai_worker.use_cases.medication_chat_pipeline import (
    MedicationChatDraft,
    MedicationEvidenceBundle,
    PreparedMedicationQuestion,
)
from ai_worker.use_cases.medication_note_summary import MedicationNoteSummaryUseCase

MEDICATION_CHAT_PROMPT_VERSION = "medication-chat-prompt-v3"
MEDICATION_CHAT_SCHEMA_VERSION = "medication-chat-result-v1"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _KnowledgeRetrievalAttempt:
    result: KnowledgeRetrievalResult
    error: Exception | None = None

    @property
    def unavailable(self) -> bool:
        return self.error is not None

    def trace_outputs(self) -> dict[str, str]:
        if self.error is None:
            return {}
        stage = self.error.stage.value if isinstance(self.error, GuidelineRetrievalError) else "UNCLASSIFIED"
        cause = self.error.__cause__
        return {
            "rag_error_stage": stage,
            "rag_error_type": type(self.error).__name__,
            "rag_error_cause_type": type(cause).__name__ if cause is not None else type(self.error).__name__,
        }


@dataclass(frozen=True)
class _CoverageRetryOutcome:
    retrieval: KnowledgeRetrievalResult
    chunks: list[RetrievedKnowledgeChunk]
    answer_chunks: list[RetrievedKnowledgeChunk]
    rag_unavailable: bool
    evidence_coverage: MedicationEvidenceCoverage


@dataclass(frozen=True)
class _QuestionRoutingOutcome:
    planning: MedicationQuestionPlanResult
    decision: QuestionRoutingDecision | None


class AnswerMedicationQuestionUseCase:
    _MAX_PRODUCT_NAME_CANDIDATES = 12
    _PARENTHETICAL_DESCRIPTION_PATTERN = re.compile(r"\s*[\(（][^()（）]*[\)）]")
    _EXACT_PRODUCT_REQUIRED_PATTERN = re.compile(
        r"복용법|사용법|어떻게\s*(?:먹|복용)|"
        r"몇\s*(?:정|캡슐|포)|용량|횟수|간격|"
        r"하루|1일|임신|수유|소아|어린이|"
        r"상호작용|같이\s*먹|함께\s*먹"
    )
    _PATIENT_CONTEXT_CUE_PATTERN = re.compile(
        r"등록한|등록된|복용\s*중|먹고\s*있는|내\s*(?:약|영양제)|"
        r"현재\s*(?:복용|먹)|지금\s*(?:복용|먹)|복약\s*정보|"
        r"(?:약|영양제|복용)\s*목록|전체\s*상호작용",
    )
    _ACTIVE_INTAKE_INTERACTION_CUE_PATTERN = re.compile(
        r"상호작용|병용|같이|함께|조심|주의|영향|피해야|중복",
    )
    _PERSONALIZED_GUIDANCE_CUE_PATTERN = re.compile(
        r"(?:나|저|내)\s*(?:게|는|의)?\s*(?:추천|권장)|"
        r"평소보다\s*(?:더|적게|두\s*배)|"
        r"(?:복용|용량|섭취량)\s*(?:을|를)?\s*(?:늘리|줄이|바꾸|변경)|"
        r"(?:시작|중단|증량|감량)\s*(?:해도|해야|해|할)",
    )

    def __init__(
        self,
        *,
        context_provider: ActiveIntakeContextProvider,
        guide_repository: MedicationGuideRepository,
        interaction_rule_repository: InteractionRuleRepository,
        knowledge_retriever: MedicationKnowledgeRetriever,
        answer_generator: MedicationAnswerGenerator,
        grounded_claim_validator: GroundedClaimValidator,
        tracer: ChatTracer | None = None,
        question_resolver: MedicationQuestionResolver | None = None,
        supplement_ingredient_catalog: SupplementIngredientCatalog | None = None,
        query_plan_chain: MedicationQueryPlanChain | None = None,
        conditional_interpretation_chain: ConditionalQuestionInterpretationChain | None = None,
        conversation_gate_chain: ConversationGateChain | None = None,
        conversation_response_generator: ConversationResponseGenerator | None = None,
        conversation_safety_policy: ConversationSafetyPolicy | None = None,
        urgent_health_signal_policy: UrgentHealthSignalPolicy | None = None,
        semantic_question_router: SemanticQuestionRouter | None = None,
        risk_policy: MedicationChatRiskPolicy | None = None,
        dose_question_policy: MedicationDoseQuestionPolicy | None = None,
        therapeutic_class_repository: TherapeuticClassRepository | None = None,
        follow_up_schedule_provider: FollowUpScheduleProvider | None = None,
        medication_note_summary_use_case: MedicationNoteSummaryUseCase | None = None,
    ) -> None:
        self._context_provider = context_provider
        self._guide_repository = guide_repository
        self._interaction_rule_repository = interaction_rule_repository
        self._knowledge_retriever = knowledge_retriever
        self._answer_generator = answer_generator
        self._grounded_claim_validator = grounded_claim_validator
        self._tracer = tracer or NoOpChatTracer()
        self._question_resolver = question_resolver
        self._supplement_ingredient_catalog = supplement_ingredient_catalog
        self._query_plan_chain = query_plan_chain or build_medication_query_plan_chain()
        self._conditional_interpretation_chain = conditional_interpretation_chain
        self._conversation_gate_chain = conversation_gate_chain
        self._conversation_response_generator = conversation_response_generator
        self._conversation_safety_policy = conversation_safety_policy or ConversationSafetyPolicy()
        self._urgent_health_signal_policy = urgent_health_signal_policy or UrgentHealthSignalPolicy()
        self._semantic_question_router = semantic_question_router
        self._risk_policy = risk_policy or MedicationChatRiskPolicy()
        self._dose_question_policy = dose_question_policy or MedicationDoseQuestionPolicy()
        self._therapeutic_class_repository = therapeutic_class_repository
        self._follow_up_schedule_provider = follow_up_schedule_provider
        self._medication_note_summary_use_case = medication_note_summary_use_case
        self._assembler = MedicationAnswerAssembler()

    async def execute(
        self,
        request: MedicationChatRequest,
        *,
        limit: int = 5,
        progress_callback: MedicationChatProgressCallback | None = None,
    ) -> MedicationChatResult:
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.QUESTION_CHECKING,
        )
        async with self._tracer.span(
            "patient_context.load",
            run_type="tool",
        ) as context_span:
            context = await self._context_provider.get_active_context(
                user_id=request.user_id,
                care_episode_id=request.care_episode_id,
            )
            context_span.end(
                {
                    "medication_count": len(context.medications),
                    "supplement_count": len(context.supplements),
                    "context_hash": self._context_hash(context),
                }
            )
        request, referenced_product_name = self._apply_session_reference(request)
        prepared_question = await self._prepare_question(
            request=request,
            context=context,
        )
        request = prepared_question.request
        resolution = prepared_question.resolution
        early_result = prepared_question.early_result
        supplement_names = [] if early_result is not None else await self._supplement_ingredient_names()
        planning = await self._plan_question(
            request=request,
            resolution=resolution,
            supplement_names=supplement_names,
            allow_legacy_entity_inference=self._question_resolver is None,
        )
        if planning is None:
            return self._query_plan_failure_result(
                request=request,
                context=context,
            )
        routing_outcome = await self._semantically_route_question(
            request=request,
            planning=planning,
        )
        planning = routing_outcome.planning
        planning = await self._conditionally_interpret_question(
            request=request,
            planning=planning,
            routing_decision=routing_outcome.decision,
        )
        therapeutic_class_selection = await self._select_therapeutic_class(
            request=request,
            context=context,
        )
        context = self._context_for_therapeutic_class_selection(
            context=context,
            selection=therapeutic_class_selection,
        )
        planning = self._with_active_intake_query_plan(
            request=request,
            context=context,
            planning=planning,
        )
        query_plan = planning.query_plan
        interpretation = planning.interpretation
        if terminal_result := await self._pre_retrieval_terminal_result(
            request=request,
            context=context,
            resolution=resolution,
            early_result=early_result,
            interpretation=interpretation,
        ):
            return terminal_result
        risk_decision = await self._evaluate_risk_policy(
            request=request,
            query_plan=query_plan,
        )
        interaction_question = (
            bool(query_plan.interaction_pairs)
            or query_plan.interaction_pair is not None
            or self._is_interaction_question(request.question)
        )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.EVIDENCE_SEARCHING,
        )
        async with self._tracer.span(
            "interaction_rules.search",
            run_type="tool",
        ) as rules_span:
            try:
                rules = await self._interaction_rule_repository.find_approved_rules(
                    context=context,
                    query_entity_names=query_plan.entity_names,
                )
            except Exception:
                rules = []
                rule_status = InteractionRuleLookupStatus.RULE_REPOSITORY_UNAVAILABLE
            else:
                rule_status = (
                    InteractionRuleLookupStatus.MATCHED if rules else InteractionRuleLookupStatus.NO_APPROVED_RULE
                )
            execution_plan = self._build_execution_plan(
                query_plan=query_plan,
                context=context,
                rules=rules,
                rule_status=rule_status,
                limit=limit,
            )
            rules_span.end(
                {
                    "approved_rule_count": len(rules),
                    "rule_lookup_status": rule_status.value,
                    "query_plan_hash": execution_plan.query_plan_hash,
                    "execution_plan_hash": (execution_plan.execution_plan_hash),
                }
            )
        if self._ingredient_family_detail_required(query_plan):
            await self._report_progress(
                progress_callback,
                MedicationChatProgressStage.SAFETY_CHECKING,
            )
            return self._ingredient_family_clarification_result(
                request=request,
                context=context,
                execution_plan=execution_plan,
                interpretation=interpretation,
            )
        async with self._tracer.span(
            "rag.retrieve",
            run_type="retriever",
        ) as rag_span:
            retrieval_attempt = await self._retrieve_knowledge(
                execution_plan=execution_plan,
            )
            retrieval = retrieval_attempt.result
            rag_unavailable = retrieval_attempt.unavailable
            chunks = retrieval.chunks
            retrieval_outputs = retrieval.diagnostics.model_dump(
                exclude={"candidate_diagnostics"},
            )
            if self._tracer.capture_content:
                retrieval_outputs["candidate_diagnostics"] = [
                    diagnostic.model_dump() for diagnostic in retrieval.diagnostics.candidate_diagnostics
                ]
            rag_span.end(
                {
                    **retrieval_outputs,
                    "query_plan_hash": execution_plan.query_plan_hash,
                    "execution_plan_hash": execution_plan.execution_plan_hash,
                    "rag_unavailable": rag_unavailable,
                    **retrieval_attempt.trace_outputs(),
                    "document_types": sorted({chunk.metadata.document_type.value for chunk in chunks}),
                    "drug_encyclopedia_evidence_count": sum(
                        chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA for chunk in chunks
                    ),
                }
            )
        has_supplement_evidence = self._has_supplement_evidence(
            request.question,
            chunks=chunks,
        )
        async with self._tracer.span(
            "medication_guide.lookup",
            run_type="tool",
        ) as guide_span:
            guide_lookup = (
                MedicationGuideLookup()
                if (
                    request.symptom_interaction_follow_up
                    or query_plan.interaction_pair is not None
                    or (has_supplement_evidence and not query_plan.has_medication_product_cue)
                )
                else await self._find_guide(
                    request=request,
                    context=context,
                    query_plan=query_plan,
                    interaction_question=interaction_question,
                )
            )
            guide_lookup, family_reference = self._resolve_family_reference(
                request=request,
                guide_lookup=guide_lookup,
            )
            guide_span.end(
                {
                    "guide_found": guide_lookup.guide is not None,
                    "ambiguous": guide_lookup.is_ambiguous,
                    "candidate_count": len(guide_lookup.candidate_names),
                    "family_reference": family_reference,
                }
            )
        has_drug_encyclopedia_evidence = self._has_drug_encyclopedia_evidence(chunks)
        can_use_ingredient_family_fallback = (
            has_drug_encyclopedia_evidence and not query_plan.has_medication_product_cue
        )
        if (
            guide_lookup.is_ambiguous
            and not self._has_supplement_evidence(
                request.question,
                chunks=chunks,
            )
            and not can_use_ingredient_family_fallback
        ):
            await self._report_progress(
                progress_callback,
                MedicationChatProgressStage.SAFETY_CHECKING,
            )
            return self._clarification_result(
                request=request,
                context=context,
                guide_lookup=guide_lookup,
                execution_plan=execution_plan,
                interpretation=interpretation,
            )
        answer_chunks = self._authoritative_chunks(
            guide_lookup=guide_lookup,
            chunks=chunks,
            prefer_supplement=(
                has_supplement_evidence and not query_plan.has_medication_product_cue and not interaction_question
            ),
        )
        coverage_retry = await self._retry_for_missing_coverage(
            retrieval=retrieval,
            query_plan=query_plan,
            execution_plan=execution_plan,
            guide_lookup=guide_lookup,
            rules=rules,
            chunks=chunks,
            answer_chunks=answer_chunks,
            prefer_supplement=(
                has_supplement_evidence and not query_plan.has_medication_product_cue and not interaction_question
            ),
            rag_unavailable=rag_unavailable,
        )
        retrieval = coverage_retry.retrieval
        chunks = coverage_retry.chunks
        answer_chunks = coverage_retry.answer_chunks
        rag_unavailable = coverage_retry.rag_unavailable
        evidence_coverage = coverage_retry.evidence_coverage
        evidence = MedicationEvidenceBundle(
            query_plan=query_plan,
            execution_plan=execution_plan,
            rules=tuple(rules),
            retrieval=retrieval,
            rag_unavailable=rag_unavailable,
            guide_lookup=guide_lookup,
            answer_chunks=tuple(answer_chunks),
            interaction_question=interaction_question,
        )
        query_plan = evidence.query_plan
        execution_plan = evidence.execution_plan
        rules = list(evidence.rules)
        rag_unavailable = evidence.rag_unavailable
        guide_lookup = evidence.guide_lookup
        answer_chunks = list(evidence.answer_chunks)
        interaction_question = evidence.interaction_question
        ingredient_family_reference = guide_lookup.guide is None and self._has_drug_encyclopedia_evidence(answer_chunks)
        if terminal_result := await self._evidence_gap_terminal_result(
            request=request,
            context=context,
            execution_plan=execution_plan,
            resolution=resolution,
            rag_unavailable=rag_unavailable,
            risk_decision=risk_decision,
            interpretation=interpretation,
            guide_lookup=guide_lookup,
            rules=rules,
            answer_chunks=answer_chunks,
            evidence_coverage=evidence_coverage,
            progress_callback=progress_callback,
        ):
            return terminal_result
        unsupported_pairs = self._unsupported_interaction_pairs(
            query_plan=query_plan,
            rules=rules,
            chunks=answer_chunks,
        )
        route = self._resolve_route(
            request=request,
            context=context,
            guide_lookup=guide_lookup,
            interaction_question=interaction_question,
            chunks=answer_chunks,
        )
        safety_reason_codes = self._safety_reason_codes(
            rag_unavailable=rag_unavailable,
            rule_status=execution_plan.approved_rule_status,
        )
        safety_status = SafetyStatus.RESTRICTED if safety_reason_codes else SafetyStatus.SAFE
        async with self._tracer.span(
            "answer.evidence_coverage",
        ) as coverage_span:
            coverage_span.end(
                {
                    "requested_section_types": [section.value for section in evidence_coverage.requested_section_types],
                    "covered_section_types": [section.value for section in evidence_coverage.covered_section_types],
                    "missing_section_types": [section.value for section in evidence_coverage.missing_section_types],
                    "verified_interaction_pair_count": len(
                        evidence_coverage.verified_interaction_pair_keys,
                    ),
                }
            )
        async with self._tracer.span("answer.draft") as draft_span:
            referenced_product_heading = self._reference_product_heading(
                product_name=referenced_product_name,
                evidence_coverage=evidence_coverage,
            )
            answer_context = self._answer_context_for_route(
                context=context,
                request=request,
                route=route,
            )
            draft = MedicationChatResult(
                request_id=request.request_id,
                answer=self._assembler.assemble(
                    context=answer_context,
                    guide=guide_lookup.guide,
                    rules=rules,
                    chunks=answer_chunks,
                    interaction_question=interaction_question,
                    referenced_product_heading=referenced_product_heading,
                    family_reference=family_reference,
                    ingredient_family_reference=(ingredient_family_reference),
                    ingredient_family=query_plan.ingredient_family,
                    unsupported_pairs=unsupported_pairs,
                    evidence_coverage=evidence_coverage,
                ),
                route=route,
                safety_status=safety_status,
                safety_reason_codes=safety_reason_codes,
                sources=self._build_sources(
                    context=answer_context,
                    guide_lookup=guide_lookup,
                    rules=rules,
                    chunks=answer_chunks,
                ),
                prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
                schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
                context_hash=self._context_hash(context),
                question_interpretation=interpretation,
                search_observation=(
                    MedicationSearchExecutionObservation.from_execution_plan(
                        execution_plan,
                    )
                ),
                evidence_coverage=evidence_coverage,
                official_warning_texts=self._official_warning_texts(
                    guide_lookup.guide,
                ),
            )
            draft = self._apply_risk_policy(
                draft,
                decision=risk_decision,
            )
            draft_span.end(
                {
                    "route": draft.route.value,
                    "source_count": len(draft.sources),
                    "safety_status": draft.safety_status.value,
                }
            )
        draft_stage = MedicationChatDraft(
            result=draft,
            resolution=resolution,
        )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.ANSWER_GENERATING,
        )
        async with self._tracer.span("llm.generate", run_type="llm") as llm_span:
            try:
                outcome = await self._answer_generator.generate(
                    request=request,
                    context=answer_context,
                    result=draft_stage.result,
                )
            except ChatAnswerGenerationError as error:
                llm_span.end(
                    {
                        "rewrite_status": "FAILED",
                        "fallback_used": False,
                        "fallback_reason": error.reason_code,
                        "route": draft_stage.result.route.value,
                        "source_count": len(draft_stage.result.sources),
                    }
                )
                raise
            generated = self._apply_correction_notice(
                outcome.result,
                resolution=resolution,
            )
            generated = generated.model_copy(
                update={
                    "answer": compact_chat_content(
                        generated.answer,
                        marker=ANSWER_COMPACTION_MARKER,
                    )
                }
            )
            generated = self._apply_risk_policy(
                generated,
                decision=risk_decision,
            )
            generated = self._preserve_reference_product_heading(
                result=generated,
                heading=referenced_product_heading,
            )
            llm_span.end(
                {
                    "rewrite_status": outcome.observation.status.value,
                    "fallback_used": outcome.observation.fallback_used,
                    "fallback_reason": (
                        outcome.observation.fallback_reason.value
                        if outcome.observation.fallback_reason is not None
                        else None
                    ),
                    "draft_answer_hash": outcome.observation.draft_answer_hash,
                    "generated_answer_hash": outcome.observation.generated_answer_hash,
                    "route": generated.route.value,
                    "source_count": len(generated.sources),
                    "declared_section_types": [section.value for section in outcome.observation.declared_section_types],
                    "covered_section_types": (
                        [section.value for section in generated.evidence_coverage.covered_section_types]
                        if generated.evidence_coverage is not None
                        else []
                    ),
                }
            )
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.SAFETY_CHECKING,
        )
        return await self._validate_generated_answer(
            context=context,
            generated=generated,
            execution_plan=execution_plan,
        )

    async def current_medication_names(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> list[str]:
        """챗 상단에 표시할 활성 복약정보의 제품명만 반환한다."""

        context = await self._context_provider.get_active_context(
            user_id=user_id,
            care_episode_id=care_episode_id,
        )
        names: list[str] = []
        seen: set[str] = set()
        for medication in context.medications:
            name = self._PARENTHETICAL_DESCRIPTION_PATTERN.sub("", medication.name)
            name = " ".join(name.split())
            key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            names.append(name)
        return names

    async def _validate_generated_answer(
        self,
        *,
        context: ActiveIntakeContext,
        generated: MedicationChatResult,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> MedicationChatResult:
        async with self._tracer.span("safety.validate") as safety_span:
            diagnostic = self._grounded_claim_validator.diagnose(
                context=context,
                result=generated,
            )
            validated = await self._grounded_claim_validator.validate(
                context=context,
                result=generated,
            )
            safety_outputs: dict[str, object] = {
                "status": validated.safety_status.value,
                "reason_codes": validated.safety_reason_codes,
                "query_plan_hash": execution_plan.query_plan_hash,
                "execution_plan_hash": (execution_plan.execution_plan_hash),
            }
            if diagnostic is not None:
                safety_outputs.update(diagnostic.trace_outputs())
            safety_span.end(safety_outputs)
        return validated

    @staticmethod
    def _official_warning_texts(
        guide: MedicationGuideFact | None,
    ) -> list[str]:
        if guide is None:
            return []
        return [
            warning
            for warning in (
                guide.pre_use_warning,
                guide.precautions,
                guide.adverse_reactions,
            )
            if MedicationAnswerAssembler._has_guide_value(warning)
        ]

    async def _evaluate_risk_policy(
        self,
        *,
        request: MedicationChatRequest,
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> MedicationChatRiskDecision:
        domain = self._answer_domain(query_plan)
        asks_for_personalized_guidance = bool(
            self._PERSONALIZED_GUIDANCE_CUE_PATTERN.search(request.question),
        )
        async with self._tracer.span("risk.policy") as risk_span:
            decision = self._risk_policy.evaluate(
                profile=request.risk_profile,
                domain=domain,
                asks_for_personalized_guidance=asks_for_personalized_guidance,
            )
            risk_span.end(
                {
                    "domain": decision.domain.value,
                    "scope": decision.scope.value,
                    "reason_codes": decision.reason_codes,
                    "personalized_guidance_requested": asks_for_personalized_guidance,
                }
            )
        return decision

    @staticmethod
    def _answer_domain(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> MedicationChatAnswerDomain:
        entity_kinds = {entity.kind for entity in query_plan.entities}
        if InteractionEntityKind.DRUG in entity_kinds:
            return MedicationChatAnswerDomain.MEDICATION
        if InteractionEntityKind.SUPPLEMENT in entity_kinds:
            return MedicationChatAnswerDomain.SUPPLEMENT
        return MedicationChatAnswerDomain.LIFESTYLE

    @staticmethod
    def _apply_risk_policy(
        result: MedicationChatResult,
        *,
        decision: MedicationChatRiskDecision,
    ) -> MedicationChatResult:
        if not decision.warning_required:
            return result.model_copy(update={"risk_decision": decision})
        warning = (
            "개인 위험정보(임신·수유·연령·신장/간질환·수술 예정·항응고제 복용)를 "
            "모두 확인하지 못했습니다. 일반 정보로만 참고하고, 복용 전 의료진 또는 "
            "약사와 확인하세요."
        )
        answer = result.answer if warning in result.answer else f"{result.answer.rstrip()}\n\n{warning}"
        reason_codes = list(dict.fromkeys([*result.safety_reason_codes, *decision.reason_codes]))
        return result.model_copy(
            update={
                "answer": answer,
                "safety_status": SafetyStatus.RESTRICTED,
                "safety_reason_codes": reason_codes,
                "risk_decision": decision,
            }
        )

    async def _plan_question(
        self,
        *,
        request: MedicationChatRequest,
        resolution: MedicationQuestionResolution | None,
        supplement_names: list[str],
        allow_legacy_entity_inference: bool,
    ) -> MedicationQuestionPlanResult | None:
        async with self._tracer.span("query.plan") as query_span:
            try:
                planning = MedicationQuestionPlanResult.model_validate(
                    await self._query_plan_chain.ainvoke(
                        MedicationQueryPlanChainInput(
                            question=request.question,
                            supplement_names=supplement_names,
                            resolution=resolution,
                            allow_legacy_entity_inference=(allow_legacy_entity_inference),
                        ),
                        config={
                            "metadata": {
                                "scope": (
                                    resolution.scope.value
                                    if resolution is not None
                                    else MedicationQuestionScope.IN_SCOPE.value
                                ),
                                "resolution_status": (
                                    resolution.status.value
                                    if resolution is not None
                                    else MedicationExpressionResolutionStatus.UNRESOLVED.value
                                ),
                                "correction_count": (len(resolution.corrections) if resolution is not None else 0),
                                "supplement_vocabulary_count": len(
                                    supplement_names,
                                ),
                                "legacy_entity_inference_used": (allow_legacy_entity_inference and resolution is None),
                            }
                        },
                    )
                )
            except Exception:
                query_span.end(
                    {
                        "status": "FAILED",
                        "error_code": (MedicationChatReasonCode.QUERY_PLAN_FAILED.value),
                    }
                )
                return None

            query_plan = planning.query_plan
            interpretation = planning.interpretation
            query_outputs = {
                "status": "COMPLETED",
                "interpretation_version": (interpretation.interpretation_version),
                "intent": interpretation.intent.value,
                "scope": interpretation.scope.value,
                "resolution_status": interpretation.resolution_status.value,
                "confidence": interpretation.confidence.value,
                "needs_clarification": interpretation.needs_clarification,
                "reason_codes": [reason.value for reason in interpretation.reason_codes],
                "entity_resolution_available": bool(resolution is not None and resolution.entity_resolution_available),
                "legacy_entity_inference_used": (allow_legacy_entity_inference and resolution is None),
                "normalized_entity_count": len(
                    interpretation.normalized_entity_names,
                ),
                "entity_sources": sorted(
                    {entity.source.value for entity in query_plan.entities},
                ),
                "entity_source_counts": dict(
                    sorted(Counter(entity.source.value for entity in query_plan.entities).items())
                ),
                "entity_type_counts": dict(
                    sorted(Counter(entity.entity_type.value for entity in query_plan.entities).items())
                ),
                "requested_section_types": [section.value for section in interpretation.requested_section_types],
                "entity_count": len(query_plan.entity_names),
                "section_count": len(query_plan.section_types),
                "interaction_pair_present": (query_plan.interaction_pair is not None),
                "interaction_pair_count": len(query_plan.interaction_pairs),
                "interaction_pair_types": sorted({pair.pair_type.value for pair in query_plan.interaction_pairs}),
                "medication_product_cue": (query_plan.has_medication_product_cue),
                "supplement_vocabulary_count": len(supplement_names),
                "query_plan_hash": query_plan.query_plan_hash,
            }
            if self._tracer.capture_content:
                query_outputs["entity_names"] = query_plan.entity_names
                query_outputs["entity_roles"] = [entity.entity_type.value for entity in query_plan.entities]
                query_outputs["entity_sources_by_entity"] = [entity.source.value for entity in query_plan.entities]
                query_outputs["entity_role_candidates"] = [
                    [candidate.value for candidate in entity.candidate_types] for entity in query_plan.entities
                ]
            query_span.end(query_outputs)
            return planning

    async def _fatigue_triage_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult | None:
        decision = FatigueConversationPolicy().evaluate(request.question)
        if decision is None:
            return None
        async with self._tracer.span("fatigue.triage") as triage_span:
            urgent = decision.disposition == FatigueConversationDisposition.URGENT
            triage_span.end(
                {
                    "disposition": decision.disposition.value,
                    "urgent": urgent,
                }
            )
        return MedicationChatResult(
            request_id=request.request_id,
            answer=decision.answer,
            route=(MedicationChatRoute.RESTRICTED if urgent else MedicationChatRoute.GENERAL_GUIDANCE),
            safety_status=(SafetyStatus.RESTRICTED if urgent else SafetyStatus.SAFE),
            safety_reason_codes=[
                (
                    MedicationChatReasonCode.FATIGUE_URGENT_ASSISTANCE.value
                    if urgent
                    else MedicationChatReasonCode.FATIGUE_FOLLOW_UP_REQUIRED.value
                )
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=self._context_hash(context),
        )

    async def _conditionally_interpret_question(
        self,
        *,
        request: MedicationChatRequest,
        planning: MedicationQuestionPlanResult,
        routing_decision: QuestionRoutingDecision | None = None,
    ) -> MedicationQuestionPlanResult:
        chain = self._conditional_interpretation_chain
        trigger_reasons = self._conditional_interpretation_reasons(
            request=request,
            planning=planning,
        )
        if (
            chain is None
            or not trigger_reasons
            or not planning.query_plan.entities
            or (routing_decision is not None and routing_decision.stage == QuestionRoutingStage.SEMANTIC)
        ):
            return planning

        candidate_entities = {f"candidate_{index}": entity for index, entity in enumerate(planning.query_plan.entities)}

        async with self._tracer.span("query.plan.conditional") as conditional_span:
            try:
                output = ConditionalQuestionInterpretationOutput.model_validate(
                    await chain.ainvoke(
                        ConditionalQuestionInterpretationInput(
                            question=request.question,
                            candidate_entities=candidate_entities,
                            requested_section_types=planning.query_plan.section_types,
                            trigger_reasons=trigger_reasons,
                        ),
                        config={
                            "metadata": {
                                "trigger_reasons": [reason.value for reason in trigger_reasons],
                                "candidate_entity_count": len(
                                    planning.query_plan.entities,
                                ),
                            }
                        },
                    )
                )
            except Exception:
                conditional_span.end(
                    {
                        "status": "FAILED",
                        "trigger_reasons": [reason.value for reason in trigger_reasons],
                    }
                )
                return planning

            validated = self._validated_conditional_plan(
                planning=planning,
                output=output,
                candidate_entities=candidate_entities,
            )
            accepted_entity_count = len([key for key in output.candidate_entity_keys if key in candidate_entities])
            trace_outputs = {
                "status": "APPLIED",
                "interpretation_version": output.interpretation_version,
                "trigger_reasons": [reason.value for reason in trigger_reasons],
                "model_confidence": output.confidence.value,
                "model_reason_codes": [reason.value for reason in output.reason_codes],
                "proposed_entity_count": len(output.candidate_entity_keys),
                "accepted_entity_count": accepted_entity_count,
                "discarded_entity_count": (len(output.candidate_entity_keys) - accepted_entity_count),
                "added_section_count": (
                    len(validated.query_plan.section_types) - len(planning.query_plan.section_types)
                ),
            }
            if self._tracer.capture_content:
                trace_outputs["validated_entity_names"] = validated.interpretation.normalized_entity_names
            conditional_span.end(trace_outputs)
            return validated

    @staticmethod
    def _conditional_interpretation_reasons(
        *,
        request: MedicationChatRequest,
        planning: MedicationQuestionPlanResult,
    ) -> list[ConditionalInterpretationReasonCode]:
        reasons: list[ConditionalInterpretationReasonCode] = []
        if planning.interpretation.confidence != MedicationQuestionConfidence.HIGH:
            reasons.append(ConditionalInterpretationReasonCode.LOW_CONFIDENCE)
        if len(planning.query_plan.entities) > 1:
            reasons.append(ConditionalInterpretationReasonCode.MULTI_ENTITY)
        if request.session_reference.entities:
            reasons.append(ConditionalInterpretationReasonCode.SESSION_REFERENCE)
        return reasons

    @staticmethod
    def _validated_conditional_plan(
        *,
        planning: MedicationQuestionPlanResult,
        output: ConditionalQuestionInterpretationOutput,
        candidate_entities: dict[str, MedicationQueryEntity],
    ) -> MedicationQuestionPlanResult:
        query_plan = planning.query_plan
        validated_entities = [
            candidate_entities[key] for key in output.candidate_entity_keys if key in candidate_entities
        ]
        supported_sections = {
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.DAILY_INTAKE,
            KnowledgeSectionType.CAUTION,
            KnowledgeSectionType.INTERACTION,
        }
        section_types = list(
            dict.fromkeys(
                [
                    *query_plan.section_types,
                    *(section for section in output.requested_section_types if section in supported_sections),
                ]
            )
        )
        validated_query_plan = query_plan.model_copy(
            update={"section_types": section_types},
        )
        normalized_names = list(
            dict.fromkeys(
                [
                    *planning.interpretation.normalized_entity_names,
                    *(entity.canonical_name for entity in validated_entities),
                ]
            )
        )
        interpretation = planning.interpretation.model_copy(
            update={
                "normalized_entity_names": normalized_names,
                "requested_section_types": section_types,
                "query_plan_hash": validated_query_plan.query_plan_hash,
            }
        )
        validated = MedicationQuestionPlanResult(
            query_plan=validated_query_plan,
            interpretation=interpretation,
        )
        if output.route is None:
            return validated
        return AnswerMedicationQuestionUseCase._validated_routing_plan(
            planning=validated,
            decision=QuestionRoutingDecision(
                stage=QuestionRoutingStage.LLM,
                route=output.route,
                confidence=output.confidence,
                reason_codes=[],
            ),
        )

    async def _semantically_route_question(
        self,
        *,
        request: MedicationChatRequest,
        planning: MedicationQuestionPlanResult,
    ) -> _QuestionRoutingOutcome:
        """불확실한 카탈로그 기반 계획만 로컬 Router로 보조한다."""
        router = self._semantic_question_router
        if router is None or not self._semantic_routing_required(planning):
            return _QuestionRoutingOutcome(planning=planning, decision=None)
        started_at = time.perf_counter()
        async with self._tracer.span("query.plan.semantic_router") as router_span:
            try:
                decision = QuestionRoutingDecision.model_validate(
                    await router.ainvoke(
                        SemanticRouterInput(
                            question=request.question,
                            candidate_count=len(planning.query_plan.entities),
                            has_session_reference=bool(request.session_reference.entities),
                        )
                    )
                )
            except Exception as exc:
                router_span.end(
                    {
                        "status": QuestionRoutingStage.FALLBACK.value,
                        "error_type": type(exc).__name__,
                        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
                    }
                )
                return _QuestionRoutingOutcome(
                    planning=planning,
                    decision=QuestionRoutingDecision.fallback(
                        top_score=None,
                        second_score=None,
                        reason_codes=[QuestionRoutingReasonCode.ROUTER_UNAVAILABLE],
                    ),
                )
            validated = self._validated_routing_plan(
                planning=planning,
                decision=decision,
            )
            router_span.end(
                {
                    "status": decision.stage.value,
                    "proposed_route": (decision.route.value if decision.route is not None else None),
                    "applied": validated != planning,
                    "confidence": decision.confidence.value,
                    "top_score": decision.top_score,
                    "second_score": decision.second_score,
                    "reason_codes": [reason.value for reason in decision.reason_codes],
                    "candidate_count": len(planning.query_plan.entities),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
                }
            )
            return _QuestionRoutingOutcome(
                planning=validated,
                decision=decision,
            )

    @staticmethod
    def _semantic_routing_required(
        planning: MedicationQuestionPlanResult,
    ) -> bool:
        interpretation = planning.interpretation
        return bool(
            planning.query_plan.entities
            and interpretation.confidence != MedicationQuestionConfidence.HIGH
            and not interpretation.needs_clarification
            and interpretation.intent
            not in {
                MedicationQuestionIntent.GREETING,
                MedicationQuestionIntent.OUT_OF_SCOPE,
                MedicationQuestionIntent.CLARIFICATION,
            }
        )

    @classmethod
    def _validated_routing_plan(
        cls,
        *,
        planning: MedicationQuestionPlanResult,
        decision: QuestionRoutingDecision,
    ) -> MedicationQuestionPlanResult:
        """Semantic Router는 검증된 두 대상의 상호작용 의도만 보완할 수 있다."""
        query_plan = planning.query_plan
        if (
            decision.stage
            not in {
                QuestionRoutingStage.SEMANTIC,
                QuestionRoutingStage.LLM,
            }
            or decision.route != MedicationChatRoute.INTERACTION
            or query_plan.interaction_pairs
        ):
            return planning
        pairs = cls._interaction_pairs_for_entities(query_plan.entities)
        if not pairs:
            return planning
        section_types = list(dict.fromkeys([*query_plan.section_types, KnowledgeSectionType.INTERACTION]))
        query_plan = query_plan.model_copy(
            update={
                "section_types": section_types,
                "interaction_pairs": pairs,
                "interaction_types": list(
                    dict.fromkeys(pair.pair_type for pair in pairs),
                ),
                "interaction_pair_keys": list(
                    dict.fromkeys(pair.pair_key for pair in pairs),
                ),
            }
        )
        reason_codes = list(planning.interpretation.reason_codes)
        if MedicationQuestionReasonCode.INTERACTION_PAIR_IDENTIFIED not in reason_codes:
            reason_codes.append(MedicationQuestionReasonCode.INTERACTION_PAIR_IDENTIFIED)
        interpretation = planning.interpretation.model_copy(
            update={
                "intent": MedicationQuestionIntent.INTERACTION,
                "requested_section_types": section_types,
                "interaction_types": query_plan.interaction_types,
                "reason_codes": reason_codes,
                "query_plan_hash": query_plan.query_plan_hash,
            }
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
        )

    async def _prepare_question(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> PreparedMedicationQuestion:
        if fatigue_result := await self._fatigue_triage_result(
            request=request,
            context=context,
        ):
            return PreparedMedicationQuestion(
                request=request,
                resolution=None,
                early_result=fatigue_result,
            )
        if self._urgent_health_signal_policy.evaluate(request.question):
            return PreparedMedicationQuestion(
                request=request,
                resolution=None,
                early_result=self._urgent_health_result(
                    request=request,
                    context=context,
                ),
            )
        resolution = await self._resolve_question(
            request=request,
            context=context,
        )
        if resolution is None:
            return PreparedMedicationQuestion(
                request=request,
                resolution=None,
                early_result=None,
            )
        request = await self._with_symptom_interaction_follow_up(
            request=request,
            resolution=resolution,
        )
        if self._is_entity_free_unresolved_question(resolution):
            schedule_result = await self._conversation_terminal_result(
                request=request,
                context=context,
                allowed_intents=frozenset(
                    {
                        ConversationIntent.FOLLOW_UP_SCHEDULE,
                        ConversationIntent.MEDICATION_NOTE_SUMMARY,
                    }
                ),
            )
            if schedule_result is not None:
                return PreparedMedicationQuestion(
                    request=request,
                    resolution=resolution,
                    early_result=schedule_result,
                )
        if resolution.scope in {
            MedicationQuestionScope.GREETING,
            MedicationQuestionScope.OUT_OF_SCOPE,
        }:
            conversation_result = await self._conversation_terminal_result(
                request=request,
                context=context,
            )
            return PreparedMedicationQuestion(
                request=request,
                resolution=resolution,
                early_result=(
                    conversation_result
                    or self._out_of_scope_result(
                        request=request,
                        context=context,
                        resolution=resolution,
                    )
                ),
            )
        if resolution.status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED:
            return PreparedMedicationQuestion(
                request=request,
                resolution=resolution,
                early_result=self._expression_clarification_result(
                    request=request,
                    context=context,
                    resolution=resolution,
                ),
            )
        return PreparedMedicationQuestion(
            request=request.model_copy(
                update={"question": resolution.resolved_question},
            ),
            resolution=resolution,
            early_result=None,
        )

    async def _with_symptom_interaction_follow_up(
        self,
        *,
        request: MedicationChatRequest,
        resolution: MedicationQuestionResolution,
    ) -> MedicationChatRequest:
        """최근 증상 대화 뒤의 제품명만 상호작용 확인으로 제한 전환한다."""

        if (
            self._conversation_gate_chain is None
            or not request.history
            or resolution.scope is not MedicationQuestionScope.IN_SCOPE
            or not resolution.entities
        ):
            return request

        started_at = time.perf_counter()
        async with self._tracer.span("conversation.follow_up.classify") as follow_up_span:
            try:
                classification = ConversationClassification.model_validate(
                    await self._conversation_gate_chain.ainvoke(
                        ConversationGateInput(
                            question=request.question,
                            recent_history=request.history,
                        )
                    )
                )
            except Exception:
                follow_up_span.end(
                    {
                        "history_count": len(request.history[-4:]),
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                        "status": "FAILED",
                    }
                )
                return request

            follow_up = (
                classification.intent is ConversationIntent.SYMPTOM_INTERACTION_FOLLOW_UP
                and classification.safety_signal is ConversationSafetySignal.NONE
            )
            follow_up_span.end(
                {
                    "intent": classification.intent.value,
                    "follow_up": follow_up,
                    "history_count": len(request.history[-4:]),
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "status": "COMPLETED",
                }
            )
        if not follow_up:
            return request
        return request.model_copy(update={"symptom_interaction_follow_up": True})

    async def _conversation_terminal_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        allowed_intents: frozenset[ConversationIntent] | None = None,
    ) -> MedicationChatResult | None:
        """카탈로그 대상이 없는 대화를 구조화 Gate로 안전하게 처리한다."""

        if self._conversation_gate_chain is None:
            return None
        history_count = len(request.history[-4:])
        started_at = time.perf_counter()
        async with self._tracer.span("conversation.classify") as classify_span:
            try:
                classification = ConversationClassification.model_validate(
                    await self._conversation_gate_chain.ainvoke(
                        ConversationGateInput(
                            question=request.question,
                            recent_history=request.history,
                        )
                    )
                )
            except Exception:
                classify_span.end(
                    {
                        "history_count": history_count,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                        "status": "FAILED",
                    }
                )
                return None
            classify_span.end(
                {
                    "intent": classification.intent.value,
                    "safety_signal": classification.safety_signal.value,
                    "confidence": classification.confidence.value,
                    "note_summary_scope": (
                        classification.note_summary_scope.value
                        if classification.note_summary_scope is not None
                        else None
                    ),
                    "history_count": history_count,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "status": "COMPLETED",
                }
            )

        if allowed_intents is not None and classification.intent not in allowed_intents:
            return None

        return await self._conversation_classification_result(
            request=request,
            context=context,
            classification=classification,
        )

    @staticmethod
    def _is_entity_free_unresolved_question(
        resolution: MedicationQuestionResolution,
    ) -> bool:
        return (
            resolution.status is MedicationExpressionResolutionStatus.UNRESOLVED
            and resolution.entity_resolution_available
            and not resolution.entities
        )

    async def _conversation_classification_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        classification: ConversationClassification,
    ) -> MedicationChatResult | None:
        decision = self._conversation_safety_policy.decide(classification)
        if decision.disposition is ConversationDisposition.URGENT:
            return self._urgent_health_result(request=request, context=context)
        if decision.disposition is ConversationDisposition.BLOCK:
            return self._sensitive_request_result(request=request, context=context)
        if decision.disposition is ConversationDisposition.REDIRECT:
            return self._conversation_result(
                request=request,
                context=context,
                answer=(
                    "이 챗봇은 약·영양제·복약 정보와 건강관리 관련 질문을 안내합니다. 관련된 내용으로 질문해 주세요."
                ),
                route=MedicationChatRoute.OUT_OF_SCOPE,
                safety_status=SafetyStatus.SAFE,
                reason_code=MedicationChatReasonCode.OUT_OF_SCOPE_REDIRECTED,
            )
        if classification.intent is ConversationIntent.FOLLOW_UP_SCHEDULE:
            return await self._follow_up_schedule_result(
                request=request,
                context=context,
            )
        if classification.intent is ConversationIntent.MEDICATION_NOTE_SUMMARY:
            return await self._medication_note_summary_result(
                request=request,
                context=context,
                classification=classification,
            )
        return await self._conversation_allow_result(
            request=request,
            context=context,
            classification=classification,
        )

    async def _follow_up_schedule_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult | None:
        if self._follow_up_schedule_provider is None:
            return None

        started_at = time.perf_counter()
        async with self._tracer.span(
            "follow_up_schedule.load",
            run_type="tool",
        ) as schedule_span:
            try:
                schedules = await self._follow_up_schedule_provider.list_upcoming_schedules(
                    user_id=request.user_id,
                    limit=5,
                )
            except Exception:
                schedule_span.end(
                    {
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                        "status": "FAILED",
                    }
                )
                return self._conversation_result(
                    request=request,
                    context=context,
                    answer="진료일정을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
                    route=MedicationChatRoute.FOLLOW_UP_SCHEDULE,
                    safety_status=SafetyStatus.SAFE,
                    reason_code=MedicationChatReasonCode.FOLLOW_UP_SCHEDULE_UNAVAILABLE,
                )
            schedule_span.end(
                {
                    "schedule_count": len(schedules),
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "status": "COMPLETED",
                }
            )

        return self._conversation_result(
            request=request,
            context=context,
            answer=FollowUpScheduleAnswerAssembler.assemble(schedules),
            route=MedicationChatRoute.FOLLOW_UP_SCHEDULE,
            safety_status=SafetyStatus.SAFE,
            reason_code=MedicationChatReasonCode.FOLLOW_UP_SCHEDULE_REQUESTED,
        )

    async def _medication_note_summary_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        classification: ConversationClassification,
    ) -> MedicationChatResult | None:
        if (
            self._medication_note_summary_use_case is None
            or classification.note_summary_scope is None
        ):
            return None
        return await self._medication_note_summary_use_case.execute(
            request=request,
            scope=classification.note_summary_scope,
            context_hash=self._context_hash(context),
        )

    async def _conversation_allow_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        classification: ConversationClassification,
    ) -> MedicationChatResult | None:
        if self._conversation_response_generator is None:
            return None

        route_and_reason = {
            ConversationIntent.VAGUE_SYMPTOM: (
                MedicationChatRoute.CLARIFICATION,
                MedicationChatReasonCode.SYMPTOM_FOLLOW_UP_REQUIRED,
            ),
            ConversationIntent.SPECIFIC_SYMPTOM: (
                MedicationChatRoute.CLARIFICATION,
                MedicationChatReasonCode.SYMPTOM_FOLLOW_UP_REQUIRED,
            ),
            ConversationIntent.CASUAL: (
                MedicationChatRoute.OUT_OF_SCOPE,
                MedicationChatReasonCode.CONVERSATION_CASUAL,
            ),
            ConversationIntent.GREETING: (
                MedicationChatRoute.OUT_OF_SCOPE,
                MedicationChatReasonCode.CONVERSATION_GREETING,
            ),
        }.get(classification.intent)
        if route_and_reason is None:
            return None
        route, reason_code = route_and_reason

        response_input = ConversationResponseInput(
            question=request.question,
            intent=classification.intent,
            follow_up_fields=classification.follow_up_fields,
        )
        started_at = time.perf_counter()
        async with self._tracer.span("conversation.respond") as response_span:
            fallback_used = False
            try:
                answer = await self._conversation_response_generator.generate(response_input)
            except Exception:
                fallback_used = True
                try:
                    answer = self._conversation_response_generator.fallback(response_input)
                except Exception:
                    response_span.end(
                        {
                            "intent": classification.intent.value,
                            "disposition": ConversationDisposition.ALLOW.value,
                            "fallback_used": fallback_used,
                            "duration_ms": round((time.perf_counter() - started_at) * 1000),
                            "status": "FAILED",
                        }
                    )
                    return None
            response_span.end(
                {
                    "intent": classification.intent.value,
                    "disposition": ConversationDisposition.ALLOW.value,
                    "fallback_used": fallback_used,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "status": "COMPLETED",
                }
            )
        return self._conversation_result(
            request=request,
            context=context,
            answer=answer,
            route=route,
            safety_status=SafetyStatus.SAFE,
            reason_code=reason_code,
        )

    @classmethod
    def _conversation_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        answer: str,
        route: MedicationChatRoute,
        safety_status: SafetyStatus,
        reason_code: MedicationChatReasonCode,
    ) -> MedicationChatResult:
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=route,
            safety_status=safety_status,
            safety_reason_codes=[reason_code.value],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
        )

    @classmethod
    def _urgent_health_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult:
        return cls._conversation_result(
            request=request,
            context=context,
            answer=(
                "호흡이 어렵거나 심한 흉통·의식 저하 같은 증상이 있으면 즉시 119 또는 "
                "가까운 응급의료기관에 도움을 요청하세요."
            ),
            route=MedicationChatRoute.RESTRICTED,
            safety_status=SafetyStatus.RESTRICTED,
            reason_code=MedicationChatReasonCode.HEALTH_URGENCY,
        )

    @classmethod
    def _sensitive_request_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult:
        return cls._conversation_result(
            request=request,
            context=context,
            answer="요청하신 내용을 돕거나 구체적인 방법을 안내할 수 없습니다.",
            route=MedicationChatRoute.RESTRICTED,
            safety_status=SafetyStatus.BLOCKED,
            reason_code=MedicationChatReasonCode.SENSITIVE_REQUEST_BLOCKED,
        )

    @classmethod
    def _resolve_family_reference(
        cls,
        *,
        request: MedicationChatRequest,
        guide_lookup: MedicationGuideLookup,
    ) -> tuple[MedicationGuideLookup, bool]:
        use_family_reference = bool(
            guide_lookup.is_ambiguous
            and guide_lookup.representative_guide is not None
            and not cls._EXACT_PRODUCT_REQUIRED_PATTERN.search(
                request.question,
            )
        )
        if not use_family_reference:
            return guide_lookup, False
        return (
            guide_lookup.model_copy(
                update={
                    "guide": guide_lookup.representative_guide,
                    "is_ambiguous": False,
                }
            ),
            True,
        )

    @staticmethod
    def _safety_reason_codes(
        *,
        rag_unavailable: bool,
        rule_status: InteractionRuleLookupStatus,
    ) -> list[str]:
        reasons = [MedicationChatReasonCode.RAG_UNAVAILABLE.value] if rag_unavailable else []
        if rule_status == InteractionRuleLookupStatus.RULE_REPOSITORY_UNAVAILABLE:
            reasons.append(
                MedicationChatReasonCode.INTERACTION_RULE_REPOSITORY_UNAVAILABLE.value,
            )
        return reasons

    @classmethod
    def _dose_question_terminal_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        interpretation: MedicationQuestionInterpretation,
        decision: MedicationDoseQuestionDecision,
    ) -> MedicationChatResult:
        if decision.kind == MedicationDoseQuestionKind.PERSONAL_CHANGE:
            return MedicationChatResult(
                request_id=request.request_id,
                answer=(
                    "평소보다 복용량을 늘려도 되는지는 안내할 수 없습니다.\n\n"
                    "확인을 위해 필요한 정보\n"
                    f"{cls._registered_dose_summary(context=context, interpretation=interpretation)}\n"
                    "- 다른 함께 복용한 제품: 확인 필요\n\n"
                    "제품 포장 또는 의약품안전나라의 허가사항에서 1회 용량과 "
                    "1일 최대량을 확인하고, 해당 정보를 약사 또는 의료진에게 "
                    "확인해 주세요."
                ),
                route=MedicationChatRoute.CLARIFICATION,
                safety_status=SafetyStatus.RESTRICTED,
                safety_reason_codes=[
                    MedicationChatReasonCode.PERSONAL_DOSE_CHANGE_CONFIRMATION_REQUIRED.value,
                ],
                prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
                schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
                context_hash=cls._context_hash(context),
                question_interpretation=interpretation,
            )
        if decision.kind == MedicationDoseQuestionKind.POSSIBLE_OVERDOSE:
            return MedicationChatResult(
                request_id=request.request_id,
                answer=(
                    "실수로 평소보다 많은 양을 복용했을 가능성이 있으면 추가 복용은 "
                    "보류하고, 복용한 제품명·양·시각과 함께 복용한 약을 확인해 "
                    "즉시 약사 또는 의료기관과 상담하세요."
                ),
                route=MedicationChatRoute.RESTRICTED,
                safety_status=SafetyStatus.RESTRICTED,
                safety_reason_codes=[
                    MedicationChatReasonCode.POSSIBLE_OVERDOSE.value,
                ],
                prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
                schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
                context_hash=cls._context_hash(context),
                question_interpretation=interpretation,
            )
        raise ValueError("종료 응답이 필요한 용량 질문 유형이 아닙니다.")

    @classmethod
    def _registered_dose_summary(
        cls,
        *,
        context: ActiveIntakeContext,
        interpretation: MedicationQuestionInterpretation,
    ) -> str:
        medication = cls._matching_registered_medication(
            context=context,
            interpretation=interpretation,
        )
        dose = medication.dose.strip() if medication is not None and medication.dose else None
        frequency = medication.times_per_day if medication is not None else None
        return "\n".join(
            [
                f"- 현재 등록된 1회 용량: {dose or '등록 정보가 없어 확인할 수 없음'}",
                (
                    f"- 현재 등록된 복용 횟수: 하루 {frequency}회"
                    if frequency is not None
                    else "- 현재 등록된 복용 횟수: 등록 정보가 없어 확인할 수 없음"
                ),
                "- 오늘 실제 누적 복용량: 확인할 수 없음",
                "- 마지막 실제 복용 시각: 확인할 수 없음",
            ]
        )

    @classmethod
    def _matching_registered_medication(
        cls,
        *,
        context: ActiveIntakeContext,
        interpretation: MedicationQuestionInterpretation,
    ) -> ActiveMedication | None:
        resolved_names = {
            cls._normalize_entity_name(entity.canonical_name)
            for entity in interpretation.normalized_entities
            if entity.kind == InteractionEntityKind.DRUG
        }
        matches = [
            medication
            for medication in context.medications
            if cls._normalize_entity_name(medication.name) in resolved_names
        ]
        return matches[0] if len(matches) == 1 else None

    @classmethod
    def _apply_correction_notice(
        cls,
        result: MedicationChatResult,
        *,
        resolution: MedicationQuestionResolution | None,
    ) -> MedicationChatResult:
        if resolution is None or resolution.status != MedicationExpressionResolutionStatus.AUTO_CORRECTED:
            return result
        return result.model_copy(update={"answer": (cls._correction_notice(resolution) + "\n\n" + result.answer)})

    async def _resolve_question(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationQuestionResolution | None:
        if self._question_resolver is None:
            return None
        async with self._tracer.span("question.resolve") as resolution_span:
            try:
                resolution = await self._question_resolver.resolve(
                    question=request.question,
                    additional_entities=[
                        *(
                            MedicationCatalogEntry(
                                canonical_name=entity.name,
                                entity_type=entity.entity_type,
                                kind=entity.kind,
                                source=MedicationQueryEntitySource.SESSION_MEMORY,
                            )
                            for entity in request.session_reference.entities
                            if entity.kind is not None
                        ),
                        *(
                            MedicationCatalogEntry(
                                canonical_name=item.name,
                                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                                kind=InteractionEntityKind.DRUG,
                                source=MedicationQueryEntitySource.PATIENT_CONTEXT,
                            )
                            for item in context.medications
                        ),
                        *(
                            MedicationCatalogEntry(
                                canonical_name=item.name,
                                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                                kind=InteractionEntityKind.SUPPLEMENT,
                                source=MedicationQueryEntitySource.PATIENT_CONTEXT,
                            )
                            for item in context.supplements
                        ),
                    ],
                )
            except Exception:
                resolution_span.end({"status": "UNAVAILABLE"})
                return None
            outputs = {
                "scope": resolution.scope.value,
                "status": resolution.status.value,
                "correction_count": len(resolution.corrections),
                "candidate_count": len(resolution.candidate_names),
                "normalization_strategy": resolution.normalization_strategy.value,
                "confidence_tier": resolution.confidence_tier.value,
                "shortlisted_candidate_count": resolution.shortlisted_candidate_count,
                "tie_count": resolution.tie_count,
                "relation_resolution_status": (resolution.relation_resolution_status.value),
                "catalog_source_counts": resolution.catalog_source_counts,
                "catalog_type_counts": resolution.catalog_type_counts,
                "entity_resolution_available": resolution.entity_resolution_available,
                "resolved_entity_count": len(resolution.entities),
                "resolved_entity_sources": sorted(
                    {entity.source.value for entity in resolution.entities},
                ),
            }
            if self._tracer.capture_content:
                outputs["corrections"] = [correction.model_dump() for correction in resolution.corrections]
                outputs["candidate_names"] = resolution.candidate_names
            resolution_span.end(outputs)
            return resolution

    @staticmethod
    def _apply_session_reference(
        request: MedicationChatRequest,
    ) -> tuple[MedicationChatRequest, str | None]:
        resolution = ChatSessionReferenceMemory().resolve(
            question=request.question,
            reference=request.session_reference,
        )
        if resolution.question == request.question:
            return request, resolution.referenced_product_name
        return (
            request.model_copy(update={"question": resolution.question}),
            resolution.referenced_product_name,
        )

    @staticmethod
    def _reference_product_heading(
        *,
        product_name: str | None,
        evidence_coverage: MedicationEvidenceCoverage,
    ) -> str | None:
        if product_name is None:
            return None
        if KnowledgeSectionType.DAILY_INTAKE in evidence_coverage.requested_section_types:
            return f"{product_name}의 복용법"
        return f"{product_name} 안내"

    @staticmethod
    def _preserve_reference_product_heading(
        *,
        result: MedicationChatResult,
        heading: str | None,
    ) -> MedicationChatResult:
        if heading is None or result.route is not MedicationChatRoute.MEDICATION_GUIDE:
            return result
        if result.answer.startswith(heading):
            return result
        return result.model_copy(update={"answer": f"{heading}\n{result.answer}"})

    async def _supplement_ingredient_names(self) -> list[str]:
        if self._supplement_ingredient_catalog is None:
            return []
        try:
            return await self._supplement_ingredient_catalog.list_names()
        except Exception:
            return []

    @classmethod
    def _query_plan_failure_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult:
        return MedicationChatResult(
            request_id=request.request_id,
            answer=("질문을 안전하게 해석하지 못했습니다. 제품명이나 성분명을 확인해 잠시 후 다시 질문해 주세요."),
            route=MedicationChatRoute.RESTRICTED,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.QUERY_PLAN_FAILED.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
        )

    async def _pre_retrieval_terminal_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution | None,
        early_result: MedicationChatResult | None,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult | None:
        if early_result is not None:
            return self._with_interpretation(
                early_result,
                interpretation=interpretation,
            )
        if self._can_answer_from_active_context(
            question=request.question,
            context=context,
        ):
            return None
        if not should_execute_source_backed_retrieval(resolution):
            return self._unrecognized_entity_result(
                request=request,
                context=context,
                interpretation=interpretation,
            )
        dose_decision = self._dose_question_policy.classify(request.question)
        if not dose_decision.requires_terminal_response:
            return None
        async with self._tracer.span("dose.question") as dose_span:
            dose_span.end({"kind": dose_decision.kind.value})
        return self._dose_question_terminal_result(
            request=request,
            context=context,
            interpretation=interpretation,
            decision=dose_decision,
        )

    @classmethod
    def _can_answer_from_active_context(
        cls,
        *,
        question: str,
        context: ActiveIntakeContext,
    ) -> bool:
        return bool((context.medications or context.supplements) and cls._PATIENT_CONTEXT_CUE_PATTERN.search(question))

    async def _select_therapeutic_class(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> TherapeuticClassSelection:
        if self._therapeutic_class_repository is None or not self._is_active_intake_interaction_question(
            question=request.question,
            context=context,
        ):
            return TherapeuticClassSelection(
                status=TherapeuticClassSelectionStatus.NOT_REQUESTED,
            )
        async with self._tracer.span(
            "therapeutic_class.resolve",
            run_type="tool",
        ) as therapeutic_class_span:
            selection = await self._therapeutic_class_repository.select_active_medications(
                context=context,
                question=request.question,
            )
            therapeutic_class_span.end(
                {
                    "status": selection.status.value,
                    "matched_class_count": len(selection.class_codes),
                    "matched_medication_count": len(selection.medication_ids),
                }
            )
        return selection

    @staticmethod
    def _context_for_therapeutic_class_selection(
        *,
        context: ActiveIntakeContext,
        selection: TherapeuticClassSelection,
    ) -> ActiveIntakeContext:
        if not selection.requested:
            return context
        selected_ids = set(selection.medication_ids)
        return context.model_copy(
            update={
                "medications": [
                    medication for medication in context.medications if medication.medication_id in selected_ids
                ]
            }
        )

    @classmethod
    def _with_active_intake_query_plan(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        planning: MedicationQuestionPlanResult,
    ) -> MedicationQuestionPlanResult:
        """등록 복약정보를 명시했지만 질문 본문에 대상이 없을 때만 검색 대상을 보완한다."""
        if request.symptom_interaction_follow_up:
            return cls._with_symptom_interaction_follow_up_query_plan(
                request=request,
                context=context,
                planning=planning,
            )
        if not cls._can_answer_from_active_context(
            question=request.question,
            context=context,
        ) or cls._query_plan_matches_active_context(
            query_plan=planning.query_plan,
            context=context,
        ):
            return planning

        entities = cls._active_intake_query_entities(context)
        if not entities:
            return planning

        is_interaction = cls._is_active_intake_interaction_question(
            question=request.question,
            context=context,
        )
        planning_question = f"{request.question} 상호작용" if is_interaction else request.question
        query_plan = MedicationKnowledgeQueryBuilder(
            catalog_entities=entities,
        ).build(planning_question)
        if is_interaction:
            interaction_pairs = cls._interaction_pairs_for_entities(entities)
            query_plan = query_plan.model_copy(
                update={
                    "interaction_pairs": interaction_pairs,
                    "interaction_types": list(dict.fromkeys(pair.pair_type for pair in interaction_pairs)),
                    "interaction_pair_keys": list(dict.fromkeys(pair.pair_key for pair in interaction_pairs)),
                }
            )
        query_plan = query_plan.model_copy(
            update={"original_query": request.question},
        )
        reason_codes = [
            reason_code
            for reason_code in planning.interpretation.reason_codes
            if reason_code != MedicationQuestionReasonCode.NO_ENTITY_IDENTIFIED
        ]
        reason_codes.append(MedicationQuestionReasonCode.ENTITY_IDENTIFIED)
        if query_plan.interaction_pairs:
            reason_codes.append(
                MedicationQuestionReasonCode.INTERACTION_PAIR_IDENTIFIED,
            )
        interpretation = planning.interpretation.model_copy(
            update={
                "resolved_question": request.question,
                "intent": cls._query_plan_intent(query_plan),
                "confidence": MedicationQuestionConfidence.HIGH,
                "normalized_entity_names": query_plan.entity_names,
                "normalized_entities": query_plan.entities,
                "requested_section_types": query_plan.section_types,
                "interaction_types": query_plan.interaction_types,
                "needs_clarification": False,
                "candidate_count": len(query_plan.entities),
                "reason_codes": list(dict.fromkeys(reason_codes)),
                "query_plan_hash": query_plan.query_plan_hash,
            }
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
        )

    @classmethod
    def _with_symptom_interaction_follow_up_query_plan(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        planning: MedicationQuestionPlanResult,
    ) -> MedicationQuestionPlanResult:
        candidate_entities = [entity for entity in planning.query_plan.entities if entity.kind is not None]
        active_entities = cls._active_intake_query_entities(
            context.model_copy(update={"supplements": []}),
        )
        if not candidate_entities or not active_entities:
            return planning

        candidate_keys = {
            (entity.kind, cls._normalize_entity_name(entity.canonical_name)) for entity in candidate_entities
        }
        active_entities = [
            entity
            for entity in active_entities
            if (entity.kind, cls._normalize_entity_name(entity.canonical_name)) not in candidate_keys
        ]
        interaction_pairs = cls._interaction_pairs_between(
            left_entities=candidate_entities,
            right_entities=active_entities,
        )
        if not interaction_pairs:
            return planning

        entities = [*candidate_entities, *active_entities]
        query_plan = (
            MedicationKnowledgeQueryBuilder(catalog_entities=entities)
            .build(f"{request.question} 상호작용")
            .model_copy(
                update={
                    "original_query": request.question,
                    "entity_names": [entity.canonical_name for entity in entities],
                    "entities": entities,
                    "section_types": [KnowledgeSectionType.INTERACTION],
                    "interaction_pairs": interaction_pairs,
                    "interaction_types": list(dict.fromkeys(pair.pair_type for pair in interaction_pairs)),
                    "interaction_pair_keys": list(dict.fromkeys(pair.pair_key for pair in interaction_pairs)),
                }
            )
        )
        reason_codes = [
            reason_code
            for reason_code in planning.interpretation.reason_codes
            if reason_code != MedicationQuestionReasonCode.NO_ENTITY_IDENTIFIED
        ]
        reason_codes.extend(
            [
                MedicationQuestionReasonCode.ENTITY_IDENTIFIED,
                MedicationQuestionReasonCode.INTERACTION_PAIR_IDENTIFIED,
            ]
        )
        interpretation = planning.interpretation.model_copy(
            update={
                "resolved_question": request.question,
                "intent": MedicationQuestionIntent.INTERACTION,
                "confidence": MedicationQuestionConfidence.HIGH,
                "normalized_entity_names": query_plan.entity_names,
                "normalized_entities": query_plan.entities,
                "requested_section_types": query_plan.section_types,
                "interaction_types": query_plan.interaction_types,
                "needs_clarification": False,
                "candidate_count": len(query_plan.entities),
                "reason_codes": list(dict.fromkeys(reason_codes)),
                "query_plan_hash": query_plan.query_plan_hash,
            }
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
        )

    @classmethod
    def _query_plan_matches_active_context(
        cls,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        context: ActiveIntakeContext,
    ) -> bool:
        active_names = {cls._normalize_entity_name(item.name) for item in [*context.medications, *context.supplements]}
        return bool(active_names.intersection(cls._normalize_entity_name(name) for name in query_plan.entity_names))

    @staticmethod
    def _active_intake_query_entities(
        context: ActiveIntakeContext,
    ) -> list[MedicationQueryEntity]:
        entities: list[MedicationQueryEntity] = []
        seen: set[tuple[InteractionEntityKind, str]] = set()
        for item, kind, entity_type in [
            *(
                (
                    medication,
                    InteractionEntityKind.DRUG,
                    MedicationQueryEntityType.PRODUCT_NAME,
                )
                for medication in context.medications
            ),
            *(
                (
                    supplement,
                    InteractionEntityKind.SUPPLEMENT,
                    MedicationQueryEntityType.INGREDIENT_NAME,
                )
                for supplement in context.supplements
            ),
        ]:
            canonical_name = item.name.strip()
            normalized_name = "".join(canonical_name.casefold().split())
            key = (kind, normalized_name)
            if not canonical_name or key in seen:
                continue
            seen.add(key)
            entities.append(
                MedicationQueryEntity(
                    surface=canonical_name,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    candidate_types=[entity_type],
                    kind=kind,
                    source=MedicationQueryEntitySource.PATIENT_CONTEXT,
                )
            )
        return entities

    @classmethod
    def _interaction_pairs_for_entities(
        cls,
        entities: list[MedicationQueryEntity],
    ) -> list[MedicationInteractionQueryPair]:
        pairs: list[MedicationInteractionQueryPair] = []
        for left_index, left_entity in enumerate(entities):
            for right_entity in entities[left_index + 1 :]:
                if left_entity.kind is None or right_entity.kind is None:
                    continue
                pair_type = interaction_pair_type_for_kinds(
                    left_entity.kind,
                    right_entity.kind,
                )
                if pair_type is None:
                    continue
                pairs.append(
                    MedicationInteractionQueryPair(
                        left_name=left_entity.canonical_name,
                        right_name=right_entity.canonical_name,
                        pair_type=pair_type,
                        pair_key=build_interaction_pair_key(
                            InteractionEntity(
                                kind=left_entity.kind,
                                display_name=left_entity.canonical_name,
                            ),
                            InteractionEntity(
                                kind=right_entity.kind,
                                display_name=right_entity.canonical_name,
                            ),
                        ),
                    )
                )
        return pairs

    @classmethod
    def _interaction_pairs_between(
        cls,
        *,
        left_entities: list[MedicationQueryEntity],
        right_entities: list[MedicationQueryEntity],
    ) -> list[MedicationInteractionQueryPair]:
        pairs: list[MedicationInteractionQueryPair] = []
        for left_entity in left_entities:
            for right_entity in right_entities:
                if left_entity.kind is None or right_entity.kind is None:
                    continue
                pair_type = interaction_pair_type_for_kinds(
                    left_entity.kind,
                    right_entity.kind,
                )
                if pair_type is None:
                    continue
                pairs.append(
                    MedicationInteractionQueryPair(
                        left_name=left_entity.canonical_name,
                        right_name=right_entity.canonical_name,
                        pair_type=pair_type,
                        pair_key=build_interaction_pair_key(
                            InteractionEntity(
                                kind=left_entity.kind,
                                display_name=left_entity.canonical_name,
                            ),
                            InteractionEntity(
                                kind=right_entity.kind,
                                display_name=right_entity.canonical_name,
                            ),
                        ),
                    )
                )
        return pairs

    @staticmethod
    def _query_plan_intent(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> MedicationQuestionIntent:
        if KnowledgeSectionType.INTERACTION in query_plan.section_types:
            return MedicationQuestionIntent.INTERACTION
        if any(entity.kind == InteractionEntityKind.DRUG for entity in query_plan.entities):
            return MedicationQuestionIntent.MEDICATION_GUIDE
        if any(entity.kind == InteractionEntityKind.SUPPLEMENT for entity in query_plan.entities):
            return MedicationQuestionIntent.SUPPLEMENT_GUIDE
        return MedicationQuestionIntent.GENERAL_GUIDANCE

    @classmethod
    def _is_active_intake_interaction_question(
        cls,
        *,
        question: str,
        context: ActiveIntakeContext,
    ) -> bool:
        return bool(
            cls._can_answer_from_active_context(
                question=question,
                context=context,
            )
            and (is_interaction_question(question) or cls._ACTIVE_INTAKE_INTERACTION_CUE_PATTERN.search(question))
        )

    @classmethod
    def _answer_context_for_route(
        cls,
        *,
        context: ActiveIntakeContext,
        request: MedicationChatRequest,
        route: MedicationChatRoute,
    ) -> ActiveIntakeContext:
        """질문 경로에 필요한 등록 정보만 답변 초안과 LLM에 전달한다."""

        requested_personal_context = cls._PATIENT_CONTEXT_CUE_PATTERN.search(request.question) is not None
        include_medications = requested_personal_context or route in {
            MedicationChatRoute.ACTIVE_INTAKE,
            MedicationChatRoute.MEDICATION_GUIDE,
            MedicationChatRoute.INTERACTION,
        }
        return ActiveIntakeContext(
            user_id=context.user_id,
            preferred_care_episode_id=context.preferred_care_episode_id,
            medications=context.medications if include_medications else [],
            supplements=context.supplements if requested_personal_context else [],
        )

    @staticmethod
    def _with_interpretation(
        result: MedicationChatResult,
        *,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        return result.model_copy(
            update={"question_interpretation": interpretation},
        )

    @classmethod
    def _out_of_scope_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution,
    ) -> MedicationChatResult:
        if resolution.scope == MedicationQuestionScope.GREETING:
            answer = "안녕하세요. 의약품의 효능·사용법·주의사항과 약·영양제·음식 간 상호작용을 질문해 주세요."
        else:
            answer = "이 챗봇은 의약품·복약·영양제 정보와 상호작용을 안내합니다. 관련 내용으로 질문해 주세요."
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=MedicationChatRoute.OUT_OF_SCOPE,
            safety_status=SafetyStatus.SAFE,
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
        )

    @classmethod
    def _expression_clarification_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution,
    ) -> MedicationChatResult:
        names = ", ".join(resolution.candidate_names)
        return MedicationChatResult(
            request_id=request.request_id,
            answer=(
                "입력하신 이름만으로는 제품이나 성분을 정확히 "
                "확인하기 어렵습니다. 제품명 또는 복용 목적(의약품/영양제)을 "
                f"알려주세요: {names}"
            ),
            route=MedicationChatRoute.CLARIFICATION,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.AMBIGUOUS_QUERY_EXPRESSION.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
        )

    @classmethod
    def _unrecognized_entity_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        answer = EvidenceGapGuidanceBuilder().build(
            subject=EvidenceGapSubject.UNKNOWN,
            entity_names=interpretation.normalized_entity_names,
        )
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=MedicationChatRoute.RESTRICTED,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
            question_interpretation=interpretation,
        )

    @classmethod
    def _no_evidence_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        resolution: MedicationQuestionResolution,
        rag_unavailable: bool,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        answer = EvidenceGapGuidanceBuilder().build(
            subject=cls._evidence_gap_subject(execution_plan.query_plan),
            entity_names=execution_plan.query_plan.entity_names,
        )
        if resolution.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED:
            answer = cls._correction_notice(resolution) + "\n\n" + answer
        reason_codes = [
            MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value,
        ]
        if rag_unavailable:
            reason_codes.append(
                MedicationChatReasonCode.RAG_UNAVAILABLE.value,
            )
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=MedicationChatRoute.RESTRICTED,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=reason_codes,
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
            question_interpretation=interpretation,
            search_observation=(
                MedicationSearchExecutionObservation.from_execution_plan(
                    execution_plan,
                )
            ),
        )

    @classmethod
    def _active_intake_no_evidence_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        rag_unavailable: bool,
        interpretation: MedicationQuestionInterpretation,
        evidence_coverage: MedicationEvidenceCoverage,
    ) -> MedicationChatResult:
        answer = EvidenceGapGuidanceBuilder().build_active_intake(
            medication_names=[item.name for item in context.medications],
            supplement_names=[item.name for item in context.supplements],
        )
        reason_codes = [
            MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value,
        ]
        if rag_unavailable:
            reason_codes.append(
                MedicationChatReasonCode.RAG_UNAVAILABLE.value,
            )
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=MedicationChatRoute.ACTIVE_INTAKE,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=reason_codes,
            sources=cls._build_sources(
                context=context,
                guide_lookup=MedicationGuideLookup(),
                rules=[],
                chunks=[],
            ),
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
            question_interpretation=interpretation,
            search_observation=(
                MedicationSearchExecutionObservation.from_execution_plan(
                    execution_plan,
                )
            ),
            evidence_coverage=evidence_coverage,
        )

    async def _evidence_gap_terminal_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        resolution: MedicationQuestionResolution | None,
        rag_unavailable: bool,
        risk_decision: MedicationChatRiskDecision,
        interpretation: MedicationQuestionInterpretation,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        answer_chunks: list[RetrievedKnowledgeChunk],
        evidence_coverage: MedicationEvidenceCoverage,
        progress_callback: MedicationChatProgressCallback | None,
    ) -> MedicationChatResult | None:
        if self._is_active_intake_interaction_question(
            question=request.question,
            context=context,
        ) and not self._has_active_intake_interaction_evidence(
            query_plan=execution_plan.query_plan,
            rules=rules,
            evidence_coverage=evidence_coverage,
        ):
            await self._report_progress(
                progress_callback,
                MedicationChatProgressStage.SAFETY_CHECKING,
            )
            return await self._rewrite_evidence_gap_result(
                request=request,
                context=context,
                execution_plan=execution_plan,
                draft=self._active_intake_no_evidence_result(
                    request=request,
                    context=context,
                    execution_plan=execution_plan,
                    rag_unavailable=rag_unavailable,
                    interpretation=interpretation,
                    evidence_coverage=evidence_coverage,
                ),
            )
        if resolution is None or self._has_grounded_evidence(
            request=request,
            context=context,
            query_plan=execution_plan.query_plan,
            guide_lookup=guide_lookup,
            rules=rules,
            chunks=answer_chunks,
        ):
            return None
        await self._report_progress(
            progress_callback,
            MedicationChatProgressStage.SAFETY_CHECKING,
        )
        draft = self._no_evidence_result(
            request=request,
            context=context,
            execution_plan=execution_plan,
            resolution=resolution,
            rag_unavailable=rag_unavailable,
            interpretation=interpretation,
        )
        if self._allows_general_supplement_guidance_without_direct_evidence(
            question=request.question,
            query_plan=execution_plan.query_plan,
            rag_unavailable=rag_unavailable,
            risk_decision=risk_decision,
        ):
            draft = draft.model_copy(
                update={
                    "route": MedicationChatRoute.SUPPLEMENT_GUIDE,
                    "safety_status": SafetyStatus.SAFE,
                    "safety_reason_codes": ["GENERAL_SUPPLEMENT_GUIDANCE"],
                    "risk_decision": risk_decision,
                }
            )
        return await self._rewrite_evidence_gap_result(
            request=request,
            context=context,
            execution_plan=execution_plan,
            draft=draft,
        )

    @staticmethod
    def _allows_general_supplement_guidance_without_direct_evidence(
        *,
        question: str,
        query_plan: MedicationKnowledgeQueryPlan,
        rag_unavailable: bool,
        risk_decision: MedicationChatRiskDecision,
    ) -> bool:
        """직접 근거가 없어도 저위험 영양제 조합에는 일반 정보만 안내한다."""

        return (
            not rag_unavailable
            and risk_decision.domain == MedicationChatAnswerDomain.SUPPLEMENT
            and risk_decision.scope == MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE
            and is_interaction_question(question)
            and bool(query_plan.entities)
            and all(entity.kind == InteractionEntityKind.SUPPLEMENT for entity in query_plan.entities)
        )

    async def _rewrite_evidence_gap_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        draft: MedicationChatResult,
    ) -> MedicationChatResult:
        """근거 부재라는 확인 사실은 유지한 채 LLM이 출력 경로만 짧게 정리한다."""

        answer_context = self._answer_context_for_route(
            context=context,
            request=request,
            route=draft.route,
        )
        async with self._tracer.span("llm.generate", run_type="llm") as llm_span:
            try:
                outcome = await self._answer_generator.generate(
                    request=request,
                    context=answer_context,
                    result=draft,
                )
            except ChatAnswerGenerationError as error:
                llm_span.end(
                    {
                        "rewrite_status": "FAILED",
                        "fallback_used": False,
                        "fallback_reason": error.reason_code,
                        "route": draft.route.value,
                        "source_count": len(draft.sources),
                    }
                )
                raise
            generated = outcome.result.model_copy(
                update={
                    "answer": compact_chat_content(
                        outcome.result.answer,
                        marker=ANSWER_COMPACTION_MARKER,
                    )
                }
            )
            llm_span.end(
                {
                    "rewrite_status": outcome.observation.status.value,
                    "fallback_used": outcome.observation.fallback_used,
                    "fallback_reason": (
                        outcome.observation.fallback_reason.value
                        if outcome.observation.fallback_reason is not None
                        else None
                    ),
                    "route": generated.route.value,
                    "source_count": len(generated.sources),
                }
            )
        return await self._validate_generated_answer(
            context=answer_context,
            generated=generated,
            execution_plan=execution_plan,
        )

    @staticmethod
    def _has_active_intake_interaction_evidence(
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        evidence_coverage: MedicationEvidenceCoverage,
    ) -> bool:
        requested_pair_keys = set(query_plan.interaction_pair_keys)
        return bool(
            requested_pair_keys.intersection(rule.pair_key for rule in rules)
            or evidence_coverage.verified_interaction_pair_keys
        )

    @staticmethod
    def _evidence_gap_subject(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> EvidenceGapSubject:
        if query_plan.interaction_pair is not None or query_plan.interaction_pairs or query_plan.interaction_types:
            return EvidenceGapSubject.INTERACTION
        entity_kinds = {entity.kind for entity in query_plan.entities}
        if InteractionEntityKind.DRUG in entity_kinds:
            return EvidenceGapSubject.MEDICATION
        if InteractionEntityKind.SUPPLEMENT in entity_kinds:
            return EvidenceGapSubject.SUPPLEMENT
        return EvidenceGapSubject.UNKNOWN

    @classmethod
    def _has_grounded_evidence(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        query_plan: MedicationKnowledgeQueryPlan,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list,
    ) -> bool:
        if guide_lookup.guide is not None or rules or chunks:
            return True
        if not context.medications and not context.supplements:
            return False
        if cls._PATIENT_CONTEXT_CUE_PATTERN.search(request.question):
            return True
        query_names = {cls._normalize_entity_name(name) for name in query_plan.entity_names}
        context_names = {cls._normalize_entity_name(item.name) for item in [*context.medications, *context.supplements]}
        return bool(query_names.intersection(context_names))

    @staticmethod
    def _correction_notice(
        resolution: MedicationQuestionResolution,
    ) -> str:
        descriptions = [
            f"‘{correction.original}’을 ‘{correction.replacement}’로" for correction in resolution.corrections
        ]
        return "입력하신 " + ", ".join(descriptions) + " 이해하고 검색했습니다."

    @staticmethod
    async def _report_progress(
        callback: MedicationChatProgressCallback | None,
        stage: MedicationChatProgressStage,
    ) -> None:
        if callback is None:
            return
        await callback(MedicationChatProgress.for_stage(stage))

    async def _find_guide(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        query_plan: MedicationKnowledgeQueryPlan,
        interaction_question: bool,
    ) -> MedicationGuideLookup:
        if interaction_question and not self._should_lookup_official_guide_for_interaction(
            query_plan=query_plan,
        ):
            return MedicationGuideLookup()
        candidates = [
            *query_plan.medication_product_lookup_names,
            *self._product_name_candidates(
                request.question,
                context=context,
                query_plan=query_plan,
            ),
        ]
        for candidate in self._stable_casefold_unique(candidates):
            lookup = await self._guide_repository.find_by_name(candidate)
            if lookup.guide is not None or lookup.is_ambiguous:
                return lookup
        return MedicationGuideLookup()

    @staticmethod
    def _should_lookup_official_guide_for_interaction(
        *,
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        return (
            bool(query_plan.medication_product_lookup_names)
            and InteractionPairType.DRUG_FOOD in query_plan.interaction_types
        )

    @staticmethod
    def _stable_casefold_unique(candidates: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = candidate.strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                unique.append(normalized)
                seen.add(key)
        return unique

    async def _retrieve_knowledge(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> _KnowledgeRetrievalAttempt:
        try:
            retrieval = await self._knowledge_retriever.search_with_diagnostics(
                execution_plan=execution_plan,
            )
        except Exception as error:
            stage = error.stage.value if isinstance(error, GuidelineRetrievalError) else "UNCLASSIFIED"
            logger.exception(
                "약·영양제 RAG 검색에 실패했습니다: stage=%s error_type=%s",
                stage,
                type(error).__name__,
            )
            return _KnowledgeRetrievalAttempt(
                result=self._empty_retrieval_result(),
                error=error,
            )
        return _KnowledgeRetrievalAttempt(result=retrieval)

    async def _retry_for_missing_coverage(
        self,
        *,
        retrieval: KnowledgeRetrievalResult,
        query_plan: MedicationKnowledgeQueryPlan,
        execution_plan: MedicationSearchExecutionPlan,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        answer_chunks: list[RetrievedKnowledgeChunk],
        prefer_supplement: bool,
        rag_unavailable: bool,
    ) -> _CoverageRetryOutcome:
        evaluator = MedicationEvidenceCoverageEvaluator()
        before = evaluator.evaluate(
            query_plan=query_plan,
            guide_lookup=guide_lookup,
            rules=rules,
            chunks=answer_chunks,
        )
        retry = CoverageGapQueryExpander().build(
            query_plan=query_plan,
            missing_section_types=before.missing_section_types,
        )
        if retry is None:
            return _CoverageRetryOutcome(
                retrieval=retrieval,
                chunks=chunks,
                answer_chunks=answer_chunks,
                rag_unavailable=rag_unavailable,
                evidence_coverage=before,
            )
        if rag_unavailable:
            observation = KnowledgeCoverageRetryObservation(
                attempted=False,
                query_count=1,
                missing_before=before.missing_section_types,
                missing_after=before.missing_section_types,
            )
            return _CoverageRetryOutcome(
                retrieval=retrieval.model_copy(update={"coverage_retry": observation}),
                chunks=chunks,
                answer_chunks=answer_chunks,
                rag_unavailable=True,
                evidence_coverage=before,
            )

        retry_execution_plan = execution_plan.model_copy(
            update={"query_plan": retry.query_plan},
        )
        async with self._tracer.span(
            "rag.coverage_retry",
            run_type="retriever",
        ) as retry_span:
            retry_attempt = await self._retrieve_knowledge(
                execution_plan=retry_execution_plan,
            )
            combined_chunks = self._unique_chunks(
                [*chunks, *retry_attempt.result.chunks],
            )
            combined_answer_chunks = self._authoritative_chunks(
                guide_lookup=guide_lookup,
                chunks=combined_chunks,
                prefer_supplement=prefer_supplement,
            )
            after = evaluator.evaluate(
                query_plan=query_plan,
                guide_lookup=guide_lookup,
                rules=rules,
                chunks=combined_answer_chunks,
            )
            retry_unavailable = rag_unavailable or retry_attempt.unavailable
            observation = KnowledgeCoverageRetryObservation(
                attempted=True,
                query_count=2,
                missing_before=before.missing_section_types,
                missing_after=after.missing_section_types,
            )
            retry_span.end(
                {
                    "attempted": observation.attempted,
                    "query_count": observation.query_count,
                    "missing_before": [section.value for section in observation.missing_before],
                    "missing_after": [section.value for section in observation.missing_after],
                    "rag_unavailable": retry_unavailable,
                }
            )

        return _CoverageRetryOutcome(
            retrieval=retrieval.model_copy(
                update={
                    "chunks": combined_chunks,
                    "coverage_retry": observation,
                }
            ),
            chunks=combined_chunks,
            answer_chunks=combined_answer_chunks,
            rag_unavailable=retry_unavailable,
            evidence_coverage=after,
        )

    @staticmethod
    def _unique_chunks(
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        unique: list[RetrievedKnowledgeChunk] = []
        seen_hashes: set[str] = set()
        for chunk in chunks:
            content_hash = chunk.metadata.content_hash
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            unique.append(chunk)
        return unique

    @classmethod
    def _build_execution_plan(
        cls,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        context: ActiveIntakeContext,
        rules: list[InteractionRuleFact],
        rule_status: InteractionRuleLookupStatus,
        limit: int,
    ) -> MedicationSearchExecutionPlan:
        return MedicationSearchExecutionPlan(
            query_plan=query_plan,
            patient_medication_names=[item.name for item in context.medications],
            patient_supplement_names=[item.name for item in context.supplements],
            approved_rule_pair_keys=[rule.pair_key for rule in rules],
            approved_rule_status=rule_status,
            include_patient_context=bool(
                cls._PATIENT_CONTEXT_CUE_PATTERN.search(
                    query_plan.original_query,
                )
            ),
            context_hash=cls._context_hash(context),
            approved_rules_hash=cls._approved_rules_hash(rules),
            limit=limit,
        )

    @staticmethod
    def _approved_rules_hash(rules: list[InteractionRuleFact]) -> str:
        payload = json.dumps(
            sorted(
                (rule.model_dump(mode="json") for rule in rules),
                key=lambda rule: (
                    rule["pair_key"],
                    rule["interaction_rule_id"],
                ),
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _empty_retrieval_result() -> KnowledgeRetrievalResult:
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
                max_raw_score=None,
                max_score=None,
            )
        )

    @classmethod
    def _resolve_route(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
        interaction_question: bool,
        chunks: list,
    ) -> MedicationChatRoute:
        if request.symptom_interaction_follow_up and context.medications:
            return MedicationChatRoute.ACTIVE_INTAKE
        if cls._can_answer_from_active_context(
            question=request.question,
            context=context,
        ):
            return MedicationChatRoute.ACTIVE_INTAKE
        if interaction_question:
            return MedicationChatRoute.INTERACTION
        if request.care_episode_id is not None and context.medications:
            return MedicationChatRoute.ACTIVE_INTAKE
        if guide_lookup.guide is not None:
            return MedicationChatRoute.MEDICATION_GUIDE
        if cls._has_supplement_evidence(
            request.question,
            chunks=chunks,
        ):
            return MedicationChatRoute.SUPPLEMENT_GUIDE
        if cls._has_drug_encyclopedia_evidence(
            chunks,
        ):
            return MedicationChatRoute.MEDICATION_GUIDE
        if cls._is_supplement_question(request.question):
            return MedicationChatRoute.SUPPLEMENT_GUIDE
        return MedicationChatRoute.GENERAL_GUIDANCE

    @staticmethod
    def _has_drug_encyclopedia_evidence(chunks: list) -> bool:
        return any(chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA for chunk in chunks)

    @staticmethod
    def _authoritative_chunks(
        *,
        guide_lookup: MedicationGuideLookup,
        chunks: list,
        prefer_supplement: bool = False,
    ) -> list:
        if prefer_supplement:
            return [
                chunk for chunk in chunks if chunk.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA
            ]
        if guide_lookup.guide is None:
            return chunks
        product_claim_sections = {
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.DAILY_INTAKE,
            KnowledgeSectionType.CAUTION,
            KnowledgeSectionType.ADVERSE_EVENT,
        }
        return [
            chunk
            for chunk in chunks
            if not (
                chunk.metadata.document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA
                and chunk.metadata.section_type in product_claim_sections
            )
        ]

    @staticmethod
    def _has_supplement_evidence(
        question: str,
        *,
        chunks: list,
    ) -> bool:
        supplement_types = {
            KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            KnowledgeDocumentType.SUPPLEMENT_CODE,
            KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH,
        }
        pair = find_supplement_interaction_pair(question)
        question_key = "".join(question.casefold().split())
        for chunk in chunks:
            metadata = chunk.metadata
            if (
                pair is not None
                and metadata.document_type == KnowledgeDocumentType.RESEARCH_ARTICLE
                and supplement_pair_matches_text(
                    pair,
                    metadata.title,
                    chunk.content,
                    *metadata.ingredient_names,
                )
            ):
                return True
            if metadata.document_type not in supplement_types:
                continue
            if not metadata.ingredient_names:
                return True
            if any("".join(name.casefold().split()) in question_key for name in metadata.ingredient_names):
                return True
        return False

    @staticmethod
    def _product_name_candidates(
        question: str,
        *,
        context: ActiveIntakeContext,
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[str]:
        candidates = [medication.name for medication in context.medications if medication.name in question]
        if "이 약" in question and len(context.medications) == 1:
            candidates.append(context.medications[0].name)
        candidates.extend(
            entity.canonical_name
            for entity in query_plan.entities
            if (
                entity.kind == InteractionEntityKind.DRUG
                and entity.entity_type
                in {
                    MedicationQueryEntityType.PRODUCT_NAME,
                    MedicationQueryEntityType.BRAND_ALIAS,
                    MedicationQueryEntityType.INGREDIENT_NAME,
                }
            )
        )
        return list(dict.fromkeys(candidates))[: AnswerMedicationQuestionUseCase._MAX_PRODUCT_NAME_CANDIDATES]

    @staticmethod
    def _is_interaction_question(question: str) -> bool:
        return is_interaction_question(question)

    @staticmethod
    def _is_supplement_question(question: str) -> bool:
        return bool(known_supplement_names_in(question)) or any(
            keyword in question
            for keyword in (
                "영양제",
                "비타민",
                "오메가",
                "마그네슘",
                "유산균",
                "프로바이오틱스",
            )
        )

    @classmethod
    def _unsupported_interaction_pairs(
        cls,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        chunks: list,
    ) -> list[str]:
        if len(query_plan.interaction_pairs) <= 1:
            return []

        evidence_texts = [
            " ".join(
                [
                    chunk.metadata.title,
                    chunk.content,
                    *chunk.metadata.drug_names,
                    *chunk.metadata.ingredient_names,
                ]
            )
            for chunk in chunks
        ]
        rule_pairs = [
            {
                cls._normalize_entity_name(rule.left_name),
                cls._normalize_entity_name(rule.right_name),
            }
            for rule in rules
        ]
        unsupported: list[str] = []
        for pair in query_plan.interaction_pairs:
            pair_names = {
                cls._normalize_entity_name(pair.left_name),
                cls._normalize_entity_name(pair.right_name),
            }
            has_rule = pair_names in rule_pairs
            has_chunk = any(
                all(name in cls._normalize_entity_name(text) for name in pair_names) for text in evidence_texts
            )
            if not has_rule and not has_chunk:
                unsupported.append(
                    f"{pair.left_name} ↔ {pair.right_name}",
                )
        return unsupported

    @staticmethod
    def _normalize_entity_name(value: str) -> str:
        return "".join(value.casefold().split())

    @staticmethod
    def _context_hash(context: ActiveIntakeContext) -> str:
        payload = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _clarification_result(
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
        execution_plan: MedicationSearchExecutionPlan,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        names = ", ".join(guide_lookup.candidate_names[:5])
        return MedicationChatResult(
            request_id=request.request_id,
            answer=(
                "같은 이름으로 여러 제품이 검색되었습니다. 약봉투의 정확한 "
                f"제품명을 확인해 주세요. 성분명도 함께 알려주면 더 정확히 "
                f"찾을 수 있습니다. 검색된 제품: {names}"
            ),
            route=MedicationChatRoute.CLARIFICATION,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.AMBIGUOUS_MEDICATION_NAME.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=AnswerMedicationQuestionUseCase._context_hash(context),
            question_interpretation=interpretation,
            search_observation=(
                MedicationSearchExecutionObservation.from_execution_plan(
                    execution_plan,
                )
            ),
        )

    @staticmethod
    def _ingredient_family_detail_required(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        return query_plan.ingredient_family is not None and bool(
            {
                KnowledgeSectionType.DAILY_INTAKE,
                KnowledgeSectionType.CAUTION,
                KnowledgeSectionType.INTERACTION,
            }.intersection(query_plan.section_types)
        )

    @staticmethod
    def _ingredient_family_clarification_result(
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        family = execution_plan.query_plan.ingredient_family
        if family is None:
            raise ValueError("성분군 재질문에는 ingredient_family가 필요합니다.")
        members = ", ".join(family.member_names)
        return MedicationChatResult(
            request_id=request.request_id,
            answer=(
                f"{family.canonical_name}는 여러 성분을 묶어 부르는 이름입니다. "
                "성분마다 섭취량·주의사항·상호작용이 다를 수 있어 하나로 "
                "답하면 부정확할 수 있습니다.\n\n"
                f"확인할 성분을 골라 다시 질문해 주세요: {members}"
            ),
            route=MedicationChatRoute.CLARIFICATION,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.INGREDIENT_FAMILY_DETAIL_REQUIRED.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=AnswerMedicationQuestionUseCase._context_hash(context),
            question_interpretation=interpretation,
            search_observation=(
                MedicationSearchExecutionObservation.from_execution_plan(
                    execution_plan,
                )
            ),
        )

    @staticmethod
    def _build_sources(
        *,
        context: ActiveIntakeContext,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list,
    ) -> list[MedicationChatSource]:
        sources = [
            MedicationChatSource(
                kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                title=f"사용자 확정 복약정보 · {item.name}",
                medication_id=item.medication_id,
                care_episode_id=item.care_episode_id,
            )
            for item in context.medications
        ]
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.PATIENT_SUPPLEMENT,
                title=f"사용자 복용 영양제 · {item.name}",
                user_supplement_id=item.registration_id,
            )
            for item in context.supplements
        )
        if guide_lookup.guide is not None:
            sources.append(
                MedicationChatSource(
                    kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                    title=f"e약은요 · {guide_lookup.guide.product_name}",
                    organization="식품의약품안전처",
                    medication_guide_id=(guide_lookup.guide.medication_guide_id),
                )
            )
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.INTERACTION_RULE,
                title=(f"승인된 상호작용 규칙 · {rule.left_name} · {rule.right_name}"),
                url=rule.source_urls[0] if rule.source_urls else None,
                interaction_rule_id=rule.interaction_rule_id,
            )
            for rule in rules
        )
        sources.extend(
            MedicationChatSource(
                kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                title=chunk.metadata.title,
                organization=chunk.metadata.provider,
                url=chunk.metadata.source_url,
                dataset_key="MEDICATION_KNOWLEDGE",
                dataset_version=chunk.metadata.dataset_version,
                vector_chunk_id=chunk.point_id,
                source_page_number=chunk.metadata.page_start,
                similarity_score=chunk.similarity_score,
            )
            for chunk in chunks
        )
        return sources
