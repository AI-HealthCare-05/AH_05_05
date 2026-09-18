import asyncio
import hashlib
import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass

from langchain_core.runnables import RunnableLambda, RunnableParallel

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
from ai_worker.chains.interaction_evidence_reasoning_chain import (
    InteractionEvidenceReasoningChain,
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
    is_general_description_question,
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
from ai_worker.domain.supplement_function_goal_detector import (
    is_supplement_function_goal_question,
)
from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy
from ai_worker.llm.assemblers.medication_answer_assembler import (
    MedicationAnswerAssembler,
)
from ai_worker.llm.generators.conversation_response_generator import (
    ConversationResponseGenerator,
    ConversationResponseInput,
)
from ai_worker.llm.prompts.medication_chat_prompt import (
    MEDICATION_CHAT_PROMPT_VERSION,
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
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import (
    ConversationClassification,
    ConversationDisposition,
    ConversationIntent,
    ConversationSafetySignal,
)
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.evidence_reasoning import (
    EvidenceItem,
    EvidenceReasoningInput,
    EvidenceReasoningOutput,
    InteractionEvidenceDecision,
)
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
    _ENTITY_FREE_CONVERSATION_INTENTS = frozenset(
        {
            ConversationIntent.GREETING,
            ConversationIntent.CASUAL,
            ConversationIntent.GENERAL_HEALTH_FOLLOW_UP,
            ConversationIntent.VAGUE_SYMPTOM,
            ConversationIntent.SPECIFIC_SYMPTOM,
            ConversationIntent.MEDICATION_GUIDE,
            ConversationIntent.MEDICATION_GUIDE_FOLLOW_UP,
            ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE,
            ConversationIntent.ACTIVE_MEDICATION_LIST,
            ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
            ConversationIntent.FOLLOW_UP_SCHEDULE,
            ConversationIntent.MEDICATION_NOTE_SUMMARY,
            ConversationIntent.SENSITIVE_REQUEST,
        }
    )
    _PARENTHETICAL_DESCRIPTION_PATTERN = re.compile(r"\s*[\(（][^()（）]*[\)）]")
    _FUNCTIONAL_SUPPLEMENT_GOAL_TITLES = (
        (re.compile(r"피부\s*보습"), "피부 보습"),
        (re.compile(r"장\s*건강"), "장 건강"),
        (re.compile(r"혈행"), "혈행 개선"),
        (re.compile(r"눈\s*건강|눈에\s*좋은"), "눈 건강"),
        (re.compile(r"관절\s*건강"), "관절 건강"),
        (re.compile(r"숙면|수면|잠\s*잘"), "숙면"),
    )
    _EXACT_PRODUCT_REQUIRED_PATTERN = re.compile(
        r"복용법|사용법|어떻게\s*(?:먹|복용)|"
        r"몇\s*(?:정|캡슐|포)|용량|횟수|간격|"
        r"하루|1일|임신|수유|소아|어린이|"
        r"상호작용|같이\s*먹|함께\s*먹"
    )
    _PATIENT_CONTEXT_CUE_PATTERN = re.compile(
        r"등록한|등록된|복용\s*중|먹고\s*있는|"
        r"(?:내가|제가)\s*(?:먹는|복용하는)\s*(?:약|영양제)|"
        r"내\s*(?:약|영양제)|"
        r"현재\s*(?:복용|먹)|지금\s*(?:복용|먹)|복약\s*정보|"
        r"(?:약|영양제|복용)\s*목록|전체\s*상호작용",
    )
    _ACTIVE_INTAKE_LIST_REQUEST_PATTERN = re.compile(
        r"^\s*(?:(?:지금|현재)\s*)?(?:(?:내가|제가)\s*)?"
        r"(?:(?:먹는|먹고\s*있는|복용\s*중인|복용하는|등록된|등록한)\s*)?"
        r"(?:(?:(?:내\s*)?(?P<medication>약(?:품)?))"
        r"(?:\s*(?:과|및)\s*(?P<supplement_after_medication>영양제))?"
        r"|(?P<supplement>영양제)(?:\s*(?:과|및)\s*(?P<medication_after_supplement>약(?:품)?))?"
        r"|(?P<medication_info>복약\s*정보)|(?P<supplement_info>영양제\s*정보))"
        r"(?:\s*(?:목록|내역|정보))?"
        r"(?:\s*(?:알려\s*줘|보여\s*줘|정리해\s*줘|뭐야|어떤\s*거야))?"
        r"\s*[?.!~]*\s*$",
        re.IGNORECASE,
    )
    _ACTIVE_INTAKE_INTERACTION_CUE_PATTERN = re.compile(
        r"상호작용|병용|같이|함께|조심|주의|영향|피해야|중복",
    )
    # 등록 항목 × 지목 대상 대조 쌍의 상한. 쌍마다 검색 질의가 하나씩 늘어난다.
    _MAX_CROSSCHECK_PAIRS = 8
    _INTERACTION_OVERVIEW_PATTERN = re.compile(
        r"안\s*되는\s*(?:것|거|약|음식|영양제)|(?:피해야|피할)\s*(?:할\s*)?(?:것|거|약|음식|영양제)"
    )
    _INTERACTION_RELATION_CUE_PATTERN = re.compile(
        r"상호작용|흡수|생체이용률|병용|동시|함께|영향|"
        r"interaction|absorption|bioavailability|coadministr|"
        r"inhibit|reduce|increase|affect",
        flags=re.IGNORECASE,
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
        interaction_evidence_reasoning_chain: InteractionEvidenceReasoningChain | None = None,
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
        self._interaction_evidence_reasoning_chain = interaction_evidence_reasoning_chain
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

    @classmethod
    def _active_intake_list_response(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> tuple[MedicationChatResult, bool, bool] | None:
        match = cls._ACTIVE_INTAKE_LIST_REQUEST_PATTERN.fullmatch(request.question)
        if match is None:
            return None

        medication_requested = bool(
            match.group("medication") or match.group("medication_after_supplement") or match.group("medication_info")
        )
        supplement_requested = bool(
            match.group("supplement") or match.group("supplement_after_medication") or match.group("supplement_info")
        )
        if not medication_requested and not supplement_requested:
            return None

        sections: list[str] = []
        missing_categories: list[str] = []
        sources: list[MedicationChatSource] = []
        if medication_requested:
            if context.medications:
                medication_names = cls._clean_active_intake_names(item.name for item in context.medications)
                sections.append("💊 **복약정보**\n" + "\n".join(f"- {name}" for name in medication_names))
                sources.extend(
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                        title=f"사용자 확정 복약정보 · {item.name}",
                        medication_id=item.medication_id,
                        care_episode_id=item.care_episode_id,
                    )
                    for item in context.medications
                )
            else:
                missing_categories.append("복약정보")
        if supplement_requested:
            if context.supplements:
                supplement_names = cls._clean_active_intake_names(item.name for item in context.supplements)
                sections.append("💪🏻 **영양제 정보**\n" + "\n".join(f"- {name}" for name in supplement_names))
                sources.extend(
                    MedicationChatSource(
                        kind=MedicationChatSourceKind.PATIENT_SUPPLEMENT,
                        title=f"사용자 복용 영양제 · {item.name}",
                        user_supplement_id=item.registration_id,
                    )
                    for item in context.supplements
                )
            else:
                missing_categories.append("영양제 정보")

        answer_parts = [*sections, *(f"현재 등록된 {category}가 없습니다." for category in missing_categories)]
        result = MedicationChatResult(
            request_id=request.request_id,
            answer="\n\n---\n\n".join(answer_parts),
            route=MedicationChatRoute.ACTIVE_INTAKE,
            safety_status=SafetyStatus.SAFE,
            sources=sources,
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=cls._context_hash(context),
        )
        return result, medication_requested, supplement_requested

    async def execute(  # noqa: C901 - 의료 안전 경로의 단계별 조기 반환을 명시적으로 유지한다.
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
        if context.medications and re.fullmatch(
            r"\s*(?:같이|함께)\s*먹으면\s*안\s*되는\s*(?:것|거)(?:을)?\s*(?:알려\s*줘)?[?.!\s]*",
            request.question,
        ):
            request = request.model_copy(update={"question": f"내가 먹는 약과 {request.question}"})
        if referenced_product_name is not None and is_interaction_question(request.question):
            request = request.model_copy(
                update={"session_interaction_reference_used": True},
            )
        if intake_list_result := self._active_intake_list_response(
            request=request,
            context=context,
        ):
            result, medication_requested, supplement_requested = intake_list_result
            async with self._tracer.span("active_intake.list_response", run_type="tool") as list_span:
                list_span.end(
                    {
                        "medication_requested": medication_requested,
                        "supplement_requested": supplement_requested,
                        "medication_count": len(context.medications) if medication_requested else 0,
                        "supplement_count": len(context.supplements) if supplement_requested else 0,
                    }
                )
            return result
        prepared_question = await self._prepare_question(
            request=request,
            context=context,
        )
        request = prepared_question.request
        resolution = prepared_question.resolution
        early_result = prepared_question.early_result
        if early_result is not None:
            return early_result
        supplement_names = await self._supplement_ingredient_names()
        planning_request = request
        if prepared_question.symptom_context is not None:
            planning_request = request.model_copy(
                update={
                    "question": f"{prepared_question.symptom_context} 의약품 효능 효과",
                }
            )
        planning = await self._plan_question(
            request=planning_request,
            resolution=resolution,
            supplement_names=supplement_names,
            allow_legacy_entity_inference=self._question_resolver is None,
        )
        if planning is None:
            return self._query_plan_failure_result(
                request=request,
                context=context,
            )
        if prepared_question.symptom_context is not None:
            planning = self._with_symptom_guidance_query_plan(
                planning=planning,
                symptom_context=prepared_question.symptom_context,
            )
        elif prepared_question.medication_guide_search:
            planning = self._with_medication_guide_search_plan(planning=planning)
        routing_outcome = await self._semantically_route_question(
            request=planning_request,
            planning=planning,
        )
        planning = routing_outcome.planning
        planning = await self._conditionally_interpret_question(
            request=planning_request,
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
        planning = self._with_interaction_overview(request=request, context=context, planning=planning)
        planning = self._with_active_intake_crosscheck_pairs(context=context, planning=planning)
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
        approved_therapeutic_class_names = await self._approved_classes_for_interaction_overview(
            query_plan=query_plan,
        )
        async with self._tracer.span(
            "interaction_rules.search",
            run_type="tool",
        ) as rules_span:
            try:
                rules = await self._interaction_rule_repository.find_approved_rules(
                    context=context,
                    query_entity_names=query_plan.entity_names,
                    include_query_neighbors=(
                        query_plan.interaction_overview
                        or (
                            len(query_plan.entities) == 1
                            and query_plan.entities[0].kind is InteractionEntityKind.DRUG
                            and not self._PATIENT_CONTEXT_CUE_PATTERN.search(request.question)
                            and not query_plan.interaction_pairs
                            and (interaction_question or not query_plan.section_types)
                        )
                    ),
                    single_entity_overview=self._is_single_entity_interaction_overview(query_plan),
                )
            except Exception:
                rules = []
                rule_status = InteractionRuleLookupStatus.RULE_REPOSITORY_UNAVAILABLE
            else:
                rules = self._rules_for_query_plan(
                    rules=rules,
                    query_plan=query_plan,
                )
                rule_status = (
                    InteractionRuleLookupStatus.MATCHED if rules else InteractionRuleLookupStatus.NO_APPROVED_RULE
                )
            execution_plan = self._build_execution_plan(
                query_plan=query_plan,
                context=context,
                rules=rules,
                rule_status=rule_status,
                approved_therapeutic_class_names=approved_therapeutic_class_names,
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
            inputs={
                "query_variant_count": len(dict.fromkeys([query_plan.expanded_query, *query_plan.alternate_queries])),
                "interaction_pair_count": len(query_plan.interaction_pairs),
                "requested_section_count": len(query_plan.section_types),
            },
        ) as rag_span:
            retrieval_attempt, crosscheck_chunks = await self._retrieve_with_crosscheck(
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
            guide_lookup = await self._with_magnesium_form_cautions(
                query_plan=query_plan,
                guide_lookup=guide_lookup,
                interaction_question=interaction_question,
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
            and not guide_lookup.form_caution_guides
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
        answer_chunks = self._functional_supplement_answer_chunks(
            question=request.question,
            chunks=answer_chunks,
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
            approved_therapeutic_class_names=execution_plan.approved_therapeutic_class_names,
            crosscheck_chunks=crosscheck_chunks,
        )
        retrieval = coverage_retry.retrieval
        chunks = coverage_retry.chunks
        answer_chunks = coverage_retry.answer_chunks
        rag_unavailable = coverage_retry.rag_unavailable
        evidence_coverage = coverage_retry.evidence_coverage
        if self._is_supplement_function_goal_question(request.question) and not rag_unavailable:
            cautions = await self._supplement_goal_cautions(
                execution_plan=execution_plan, answer_chunks=answer_chunks, retrieved_chunks=chunks
            )
            if cautions:
                answer_chunks = self._unique_chunks([*answer_chunks, *cautions])
                coverage_plan = query_plan.model_copy(
                    update={
                        "section_types": list(dict.fromkeys([*query_plan.section_types, KnowledgeSectionType.CAUTION]))
                    }
                )
                evidence_coverage = MedicationEvidenceCoverageEvaluator().evaluate(
                    query_plan=coverage_plan,
                    guide_lookup=guide_lookup,
                    rules=rules,
                    chunks=answer_chunks,
                    approved_therapeutic_class_names=approved_therapeutic_class_names,
                    crosscheck_chunks=crosscheck_chunks,
                )
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
        evidence_reasoning = await self._reason_about_interaction_evidence(
            request=request,
            evidence=evidence,
        )
        evidence_coverage, answer_chunks = self._apply_evidence_reasoning_coverage(
            query_plan=query_plan,
            evidence_coverage=evidence_coverage,
            answer_chunks=answer_chunks,
            evidence_reasoning=evidence_reasoning,
        )
        if prepared_question.symptom_context is not None and not any(
            chunk.metadata.section_type is KnowledgeSectionType.FUNCTION for chunk in answer_chunks
        ):
            return self._conversation_result(
                request=request,
                context=context,
                answer=(
                    "✉️ **증상 안내**\n\n"
                    "- 많이 불편하시겠어요. 확인된 자료만으로 도움이 될 성분을 안내하기 어렵습니다.\n"
                    "- 의사 또는 약사에게 상담하세요."
                ),
                route=MedicationChatRoute.CLARIFICATION,
                safety_status=SafetyStatus.RESTRICTED,
                reason_code=MedicationChatReasonCode.SYMPTOM_FOLLOW_UP_REQUIRED,
            )
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
            symptom_medication_guidance=prepared_question.symptom_context is not None,
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
                    interaction_overview=query_plan.interaction_overview,
                    referenced_product_heading=referenced_product_heading,
                    interaction_overview_subject=(
                        query_plan.entity_names[0] if self._is_single_entity_interaction_overview(query_plan) else None
                    ),
                    family_reference=family_reference,
                    ingredient_family_reference=(ingredient_family_reference),
                    ingredient_family=query_plan.ingredient_family,
                    unsupported_pairs=unsupported_pairs,
                    question_interaction_pairs=(
                        query_plan.interaction_pairs
                        if (
                            interaction_question
                            and not self._is_active_intake_interaction_question(
                                question=request.question,
                                context=context,
                            )
                        )
                        else []
                    ),
                    active_intake_interaction=self._is_active_intake_interaction_question(
                        question=request.question,
                        context=context,
                    ),
                    evidence_coverage=evidence_coverage,
                    response_subject=self._response_subject(
                        query_plan=query_plan,
                        guide_lookup=guide_lookup,
                        interaction_question=interaction_question,
                    ),
                    adverse_reaction_question=self._is_adverse_reaction_question(
                        question=request.question,
                        query_plan=query_plan,
                        chunks=answer_chunks,
                        interaction_question=interaction_question,
                    ),
                    functional_goal_title=self._functional_supplement_goal_title(
                        request.question,
                    ),
                    crosscheck_pairs=query_plan.crosscheck_pairs,
                    crosscheck_chunks=crosscheck_chunks,
                    functional_goal_details=(
                        self._is_supplement_function_goal_question(request.question)
                        and bool(re.search(r"영양제|건강기능식품|기능.*정보", request.question))
                        and not bool(re.search(r"(?:성분|원료)(?:명)?\s*만", request.question))
                    ),
                    form_caution_guides=guide_lookup.form_caution_guides,
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
                evidence_reasoning=evidence_reasoning,
                official_warning_texts=self._official_warning_texts(
                    guide_lookup,
                ),
                answer_context_history=list(prepared_question.answer_context_history),
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
                    ),
                    "answer_observation": outcome.observation,
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

    async def _reason_about_interaction_evidence(
        self,
        *,
        request: MedicationChatRequest,
        evidence: MedicationEvidenceBundle,
    ) -> EvidenceReasoningOutput | None:
        chain = self._interaction_evidence_reasoning_chain
        query_plan = evidence.query_plan
        if query_plan.interaction_overview:
            # Chain 3의 지정된 쌍 판정은 그대로 두고, 탐색 답변은 수집된 직접 근거를 요약한다.
            return None
        execution_plan = evidence.execution_plan
        rules = evidence.rules
        interaction_chunks = self._interaction_evidence_chunks(
            answer_chunks=list(evidence.answer_chunks),
            interaction_pair_keys=execution_plan.interaction_pair_keys,
            interaction_pairs=query_plan.interaction_pairs,
        )
        entity_names = list(
            dict.fromkeys(
                [
                    *query_plan.entity_names,
                    *execution_plan.medication_names,
                    *execution_plan.supplement_names,
                ]
            )
        )
        if (
            chain is None
            or not evidence.interaction_question
            or len(entity_names) < 2
            or (
                not rules
                and not any(
                    self._direct_interaction_pair_keys_for_chunk(
                        chunk=chunk,
                        interaction_pairs=query_plan.interaction_pairs,
                        requested_pair_keys=execution_plan.interaction_pair_keys,
                    )
                    for chunk in interaction_chunks
                )
            )
        ):
            return None

        async with self._tracer.span(
            "medication.evidence_reasoning",
            run_type="llm",
        ) as reasoning_span:
            try:
                approved_rules = [
                    EvidenceItem(
                        evidence_id=f"rule:{rule.interaction_rule_id}",
                        content=" ".join(rule.effect_texts),
                        section_types=[KnowledgeSectionType.INTERACTION],
                        pair_keys=[rule.pair_key],
                        study_scope="APPROVED_RULE",
                    )
                    for rule in rules
                ]
                evidence_items = [
                    EvidenceItem(
                        evidence_id=f"chunk:{chunk.chunk_id}",
                        content=self._evidence_item_content(chunk),
                        section_types=[KnowledgeSectionType.INTERACTION],
                        pair_keys=self._direct_interaction_pair_keys_for_chunk(
                            chunk=chunk,
                            interaction_pairs=query_plan.interaction_pairs,
                            requested_pair_keys=execution_plan.interaction_pair_keys,
                        ),
                        study_scope=chunk.metadata.study_population.value,
                    )
                    for chunk in interaction_chunks
                ]
                reasoning_input = EvidenceReasoningInput(
                    question=request.question,
                    entity_names=entity_names,
                    requested_section_types=query_plan.section_types,
                    interaction_pair_keys=execution_plan.interaction_pair_keys,
                    evidence_items=evidence_items,
                    approved_rules=approved_rules,
                    risk_profile=request.risk_profile.model_dump(mode="json"),
                )
                raw_result = await chain.ainvoke(reasoning_input)
                result = EvidenceReasoningOutput.model_validate(raw_result)
            except Exception as error:
                reasoning_span.end(
                    {
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                    }
                )
                return None
            reasoning_span.end(
                {
                    "status": result.reasoning_status.value,
                    "interaction_decision": result.interaction_decision.value,
                    "claim_count": len(result.claims),
                    "missing_section_types": [section.value for section in result.missing_section_types],
                }
            )
            return result

    @staticmethod
    def _interaction_evidence_chunks(
        *,
        answer_chunks: list[RetrievedKnowledgeChunk],
        interaction_pair_keys: list[str],
        interaction_pairs: list[MedicationInteractionQueryPair] | None = None,
    ) -> list[RetrievedKnowledgeChunk]:
        requested_pair_keys = set(interaction_pair_keys)
        return [
            chunk
            for chunk in answer_chunks
            if (
                chunk.metadata.section_type is KnowledgeSectionType.INTERACTION
                or bool(requested_pair_keys.intersection(chunk.metadata.interaction_pair_keys))
                or bool(
                    interaction_pairs
                    and AnswerMedicationQuestionUseCase._direct_interaction_pair_keys_for_chunk(
                        chunk=chunk,
                        interaction_pairs=interaction_pairs,
                        requested_pair_keys=interaction_pair_keys,
                    )
                )
            )
        ]

    @classmethod
    def _direct_interaction_pair_keys_for_chunk(
        cls,
        *,
        chunk: RetrievedKnowledgeChunk,
        interaction_pairs: list[MedicationInteractionQueryPair],
        requested_pair_keys: list[str],
    ) -> list[str]:
        requested_pair_key_set = set(requested_pair_keys)
        metadata_keys = requested_pair_key_set.intersection(
            chunk.metadata.interaction_pair_keys,
        )
        direct_keys = {
            pair.pair_key
            for pair in interaction_pairs
            if pair.pair_key in requested_pair_key_set
            and cls._chunk_directly_supports_interaction_pair(
                chunk=chunk,
                pair=pair,
            )
        }
        return [pair_key for pair_key in requested_pair_keys if pair_key in metadata_keys or pair_key in direct_keys]

    @staticmethod
    def _evidence_item_content(chunk: RetrievedKnowledgeChunk) -> str:
        """Keep the source title while respecting EvidenceItem's 4,000-character boundary."""
        title = chunk.metadata.title.strip()
        if not title:
            return chunk.content[:4000]
        available_content_length = max(0, 4000 - len(title) - 1)
        return f"{title}\n{chunk.content[:available_content_length]}"

    @classmethod
    def _chunk_directly_supports_interaction_pair(
        cls,
        *,
        chunk: RetrievedKnowledgeChunk,
        pair: MedicationInteractionQueryPair,
    ) -> bool:
        left_name = cls._normalize_entity_name(pair.left_name)
        right_name = cls._normalize_entity_name(pair.right_name)
        if any(
            left_name in cls._normalize_entity_name(sentence) and right_name in cls._normalize_entity_name(sentence)
            for sentence in re.split(r"[.!?。！？\n]+", chunk.content)
            if sentence.strip()
        ):
            return True
        metadata_names = {
            cls._normalize_entity_name(name)
            for name in [
                *chunk.metadata.drug_names,
                *chunk.metadata.ingredient_names,
                *chunk.metadata.food_names,
            ]
        }
        # 메타데이터와 제목은 Chain 3에 후보를 전달하기 위한 조건일 뿐,
        # 직접 상호작용 claim 확정은 Evidence Reasoning의 본문 판정에 맡긴다.
        return bool(
            {left_name, right_name}.issubset(metadata_names)
            and cls._INTERACTION_RELATION_CUE_PATTERN.search(
                f"{chunk.metadata.title}\n{chunk.content}",
            )
        )

    @classmethod
    def _apply_evidence_reasoning_coverage(
        cls,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        evidence_coverage: MedicationEvidenceCoverage,
        answer_chunks: list[RetrievedKnowledgeChunk],
        evidence_reasoning: EvidenceReasoningOutput | None,
    ) -> tuple[MedicationEvidenceCoverage, list[RetrievedKnowledgeChunk]]:
        if (
            evidence_reasoning is None
            or evidence_reasoning.interaction_decision is not InteractionEvidenceDecision.INTERACTION_CONFIRMED
        ):
            return evidence_coverage, answer_chunks
        requested_pair_keys = set(query_plan.interaction_pair_keys)
        confirmed_pair_keys = {
            claim.pair_key
            for claim in evidence_reasoning.claims
            if (
                claim.section_type is KnowledgeSectionType.INTERACTION
                and claim.pair_key is not None
                and claim.pair_key in requested_pair_keys
            )
        }
        if not confirmed_pair_keys:
            return evidence_coverage, answer_chunks

        bound_chunks: list[RetrievedKnowledgeChunk] = []
        for chunk in answer_chunks:
            direct_keys = set(
                cls._direct_interaction_pair_keys_for_chunk(
                    chunk=chunk,
                    interaction_pairs=query_plan.interaction_pairs,
                    requested_pair_keys=query_plan.interaction_pair_keys,
                )
            )
            keys_to_bind = direct_keys.intersection(confirmed_pair_keys)
            if not keys_to_bind:
                bound_chunks.append(chunk)
                continue
            metadata = chunk.metadata.model_copy(
                update={
                    "interaction_pair_keys": list(
                        dict.fromkeys(
                            [
                                *chunk.metadata.interaction_pair_keys,
                                *(
                                    pair_key
                                    for pair_key in query_plan.interaction_pair_keys
                                    if pair_key in keys_to_bind
                                ),
                            ]
                        )
                    )
                }
            )
            bound_chunks.append(chunk.model_copy(update={"metadata": metadata}))

        verified_pair_keys = list(
            dict.fromkeys(
                [
                    *evidence_coverage.verified_interaction_pair_keys,
                    *(pair_key for pair_key in query_plan.interaction_pair_keys if pair_key in confirmed_pair_keys),
                ]
            )
        )
        covered_sections = list(evidence_coverage.covered_section_types)
        if (
            KnowledgeSectionType.INTERACTION in evidence_coverage.requested_section_types
            and KnowledgeSectionType.INTERACTION not in covered_sections
        ):
            covered_sections.append(KnowledgeSectionType.INTERACTION)
        return (
            evidence_coverage.model_copy(
                update={
                    "covered_section_types": covered_sections,
                    "missing_section_types": [
                        section
                        for section in evidence_coverage.missing_section_types
                        if section is not KnowledgeSectionType.INTERACTION
                    ],
                    "verified_interaction_pair_keys": verified_pair_keys,
                }
            ),
            bound_chunks,
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
        guide_lookup: MedicationGuideLookup,
    ) -> list[str]:
        guides = [guide_lookup.guide] if guide_lookup.guide is not None else []
        guides.extend(guide for form_guides in guide_lookup.form_caution_guides.values() for guide in form_guides)
        return [
            warning
            for guide in guides
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
        if not urgent:
            response = await self._conversation_allow_result(
                request=request,
                context=context,
                classification=ConversationClassification(
                    intent=ConversationIntent.GENERAL_HEALTH_FOLLOW_UP,
                    safety_signal=ConversationSafetySignal.NONE,
                    confidence=MedicationQuestionConfidence.HIGH,
                ),
                lifestyle_check_required=True,
            )
            if response is not None:
                return response.model_copy(
                    update={"safety_reason_codes": [MedicationChatReasonCode.FATIGUE_FOLLOW_UP_REQUIRED.value]}
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
        allowed_search_terms = self._conditional_allowed_search_terms(
            planning.query_plan,
        )
        candidate_pair_keys = list(planning.query_plan.interaction_pair_keys)

        async with self._tracer.span("query.plan.conditional") as conditional_span:
            try:
                output = ConditionalQuestionInterpretationOutput.model_validate(
                    await chain.ainvoke(
                        ConditionalQuestionInterpretationInput(
                            question=request.question,
                            candidate_entities=candidate_entities,
                            requested_section_types=planning.query_plan.section_types,
                            trigger_reasons=trigger_reasons,
                            candidate_pair_keys=candidate_pair_keys,
                            allowed_search_terms=allowed_search_terms,
                            session_reference_entities={
                                f"session_{index}": entity.name
                                for index, entity in enumerate(
                                    request.session_reference.entities,
                                )
                            },
                            current_query_plan=planning.query_plan,
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
                candidate_pair_keys=candidate_pair_keys,
                allowed_search_terms=allowed_search_terms,
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

    @classmethod
    def _validated_conditional_plan(
        cls,
        *,
        planning: MedicationQuestionPlanResult,
        output: ConditionalQuestionInterpretationOutput,
        candidate_entities: dict[str, MedicationQueryEntity],
        candidate_pair_keys: list[str],
        allowed_search_terms: list[str],
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
        validated_pair_keys = (
            [pair_key for pair_key in output.interaction_pair_keys if pair_key in candidate_pair_keys]
            if (output.route == MedicationChatRoute.INTERACTION or KnowledgeSectionType.INTERACTION in section_types)
            else []
        )
        validated_stimuli = [
            stimulus.query
            for stimulus in output.stimuli
            if cls._is_allowed_conditional_stimulus(
                query=stimulus.query,
                allowed_search_terms=allowed_search_terms,
                selected_entities=validated_entities,
            )
        ]
        if output.stimuli and not validated_stimuli:
            return planning
        # A question that explicitly resolves three or more targets requests the
        # complete combination set.  The conditional LLM may improve wording or
        # section selection, but it must not silently drop a pair from that set.
        preserve_explicit_pair_set = len(candidate_pair_keys) > 1
        selected_pair_keys = (
            query_plan.interaction_pair_keys
            if preserve_explicit_pair_set
            else (validated_pair_keys or query_plan.interaction_pair_keys)
        )
        if validated_pair_keys and not preserve_explicit_pair_set:
            selected_pair_key_set = set(selected_pair_keys)
            selected_pairs = [pair for pair in query_plan.interaction_pairs if pair.pair_key in selected_pair_key_set]
            selected_interaction_pair = (
                query_plan.interaction_pair
                if (
                    query_plan.interaction_pair is not None
                    and query_plan.interaction_pair.pair_key in selected_pair_key_set
                )
                else None
            )
            alternate_queries = cls._alternate_queries_for_selected_pairs(
                query_plan=query_plan,
                selected_pairs=selected_pairs,
            )
        else:
            selected_pairs = query_plan.interaction_pairs
            selected_interaction_pair = query_plan.interaction_pair
            alternate_queries = query_plan.alternate_queries
        validated_query_plan = query_plan.model_copy(
            update={
                "section_types": section_types,
                "interaction_pair": selected_interaction_pair,
                "interaction_pairs": selected_pairs,
                "interaction_types": list(dict.fromkeys(pair.pair_type for pair in selected_pairs)),
                "interaction_pair_keys": selected_pair_keys,
                "alternate_queries": list(
                    dict.fromkeys(
                        [
                            *alternate_queries,
                            *validated_stimuli,
                        ]
                    )
                ),
            },
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
                "resolved_question": output.normalized_question,
                "requested_section_types": section_types,
                "needs_clarification": output.needs_clarification,
                "clarification_question": output.clarification_question,
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

    @staticmethod
    def _alternate_queries_for_selected_pairs(
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        selected_pairs: list[MedicationInteractionQueryPair],
    ) -> list[str]:
        pair_key_by_query = {
            f"{pair.left_name} {pair.right_name} 상호작용": pair.pair_key for pair in query_plan.interaction_pairs
        }
        if query_plan.interaction_pair is not None:
            pair_key_by_query[query_plan.interaction_pair.english_query] = query_plan.interaction_pair.pair_key
        selected_pair_keys = {pair.pair_key for pair in selected_pairs}
        filtered_queries = [
            query
            for query in query_plan.alternate_queries
            if query not in pair_key_by_query or pair_key_by_query[query] in selected_pair_keys
        ]
        selected_pair_queries = [f"{pair.left_name} {pair.right_name} 상호작용" for pair in selected_pairs]
        return list(dict.fromkeys([*filtered_queries, *selected_pair_queries]))

    @staticmethod
    def _conditional_allowed_search_terms(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[str]:
        values = [
            *(entity.surface for entity in query_plan.entities),
            *(entity.canonical_name for entity in query_plan.entities),
            *query_plan.entity_names,
            *re.findall(
                r"[0-9a-zA-Z가-힣μ㎍%]+",
                query_plan.expanded_query,
            ),
        ]
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @staticmethod
    def _is_allowed_conditional_stimulus(
        *,
        query: str,
        allowed_search_terms: list[str],
        selected_entities: list[MedicationQueryEntity],
    ) -> bool:
        query_tokens = set(re.findall(r"[0-9a-zA-Z가-힣μ㎍%]+", query.casefold()))
        allowed_tokens = {
            token
            for term in allowed_search_terms
            for token in re.findall(
                r"[0-9a-zA-Z가-힣μ㎍%]+",
                term.casefold(),
            )
        }
        selected_entity_tokens = {
            token
            for entity in selected_entities
            for token in re.findall(
                r"[0-9a-zA-Z가-힣μ㎍%]+",
                entity.canonical_name.casefold(),
            )
        }
        return bool(
            query_tokens and selected_entity_tokens.intersection(query_tokens) and query_tokens.issubset(allowed_tokens)
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
    def _with_symptom_guidance_query_plan(
        *,
        planning: MedicationQuestionPlanResult,
        symptom_context: str,
    ) -> MedicationQuestionPlanResult:
        """확인된 증상으로 의약품 효능 근거만 검색하도록 계획을 제한한다."""

        search_question = f"{symptom_context} 의약품 효능 효과"
        section_types = [KnowledgeSectionType.FUNCTION]
        query_plan = planning.query_plan.model_copy(
            update={
                "original_query": search_question,
                "expanded_query": search_question,
                "document_types": [
                    KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    KnowledgeDocumentType.PHARM_REVIEW,
                ],
                "section_types": section_types,
                "alternate_queries": [
                    f"{symptom_context} 증상 완화 의약품 효능",
                    f"{symptom_context} 증상에 사용하는 약 효과",
                ],
            }
        )
        interpretation = planning.interpretation.model_copy(
            update={
                "resolved_question": search_question,
                "intent": MedicationQuestionIntent.MEDICATION_GUIDE,
                "requested_section_types": section_types,
                "needs_clarification": False,
                "clarification_question": None,
                "query_plan_hash": query_plan.query_plan_hash,
            }
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
        )

    @staticmethod
    def _with_medication_guide_search_plan(
        *,
        planning: MedicationQuestionPlanResult,
    ) -> MedicationQuestionPlanResult:
        """카탈로그에서 이름을 확정하지 못한 의약품 질문도 약물 근거만 검색한다."""

        query_plan = planning.query_plan.model_copy(
            update={
                "document_types": [
                    KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    KnowledgeDocumentType.ADVERSE_CASE_REPORT,
                    KnowledgeDocumentType.PHARM_REVIEW,
                ],
            }
        )
        interpretation = planning.interpretation.model_copy(
            update={
                "intent": MedicationQuestionIntent.MEDICATION_GUIDE,
                "query_plan_hash": query_plan.query_plan_hash,
            }
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
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
        if health_result := await self._health_triage_result(
            request=request,
            context=context,
        ):
            return PreparedMedicationQuestion(
                request=request,
                resolution=None,
                early_result=health_result,
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
        resolution = self._bypass_supplement_function_goal_clarification(
            question=request.question,
            resolution=resolution,
        )
        if self._is_active_intake_interaction_question(question=request.question, context=context) and not re.search(
            r"메모|일지|기록", request.question
        ):
            # 등록 목록 참조는 제품명을 입력하지 않아도 검색 가능한 구조화된 대상이다.
            # Gate는 안전 신호만 확인하고, 목록 밖의 메모·일정 작업으로 전환하지 않는다.
            safety_result = await self._conversation_terminal_result(
                request=request,
                context=context,
                allowed_intents=frozenset({ConversationIntent.SENSITIVE_REQUEST}),
            )
            return PreparedMedicationQuestion(
                request=request,
                resolution=resolution.model_copy(
                    update={
                        "scope": MedicationQuestionScope.IN_SCOPE,
                        "status": MedicationExpressionResolutionStatus.UNCHANGED,
                    }
                ),
                early_result=safety_result,
            )
        symptom_context: str | None = None
        answer_context_history: tuple[ChatHistoryMessage, ...] = ()
        medication_guide_search = False
        if self._requires_qdrant_conversation_safety_preflight(resolution):
            conversation_result = await self._conversation_terminal_result(
                request=request,
                context=context,
                allowed_intents=frozenset({ConversationIntent.SENSITIVE_REQUEST}),
            )
            if conversation_result is not None:
                return PreparedMedicationQuestion(
                    request=request,
                    resolution=resolution,
                    early_result=conversation_result,
                )
        request = await self._with_symptom_interaction_follow_up(
            request=request,
            resolution=resolution,
        )
        request, resolution = await self._with_conversation_interaction_references(
            request=request,
            context=context,
            resolution=resolution,
        )
        conversation_preparation = await self._prepare_entity_free_conversation(
            request=request,
            context=context,
            resolution=resolution,
        )
        if conversation_preparation is not None:
            if conversation_preparation.early_result is not None:
                return conversation_preparation
            request = conversation_preparation.request
            resolution = conversation_preparation.resolution or resolution
            symptom_context = conversation_preparation.symptom_context
            answer_context_history = conversation_preparation.answer_context_history
            medication_guide_search = conversation_preparation.medication_guide_search
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
            symptom_context=symptom_context,
            answer_context_history=answer_context_history,
            medication_guide_search=medication_guide_search,
        )

    async def _health_triage_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> MedicationChatResult | None:
        # Continue the immediately preceding questionnaire before product resolution.
        # Current danger still takes the deterministic urgent path below.
        last_assistant = next(
            (message for message in reversed(request.history[-4:]) if message.role is ChatRole.ASSISTANT),
            None,
        )
        if (
            last_assistant is not None
            and any(
                marker in last_assistant.content
                for marker in (
                    FatigueConversationPolicy.FOLLOW_UP_MARKER,
                    FatigueConversationPolicy.LIFESTYLE_SECTION,
                    "🌿 **일반 건강정보**",
                )
            )
            and not self._urgent_health_signal_policy.evaluate(request.question)
        ):
            classification = await self._classify_conversation(request=request)
            if classification is not None and (
                classification.intent is ConversationIntent.GENERAL_HEALTH_FOLLOW_UP
                or classification.safety_signal is not ConversationSafetySignal.NONE
            ):
                result = await self._conversation_classification_result(
                    request=request,
                    context=context,
                    classification=classification,
                )
                if result is not None:
                    return result
        if result := await self._fatigue_triage_result(request=request, context=context):
            return result
        if self._urgent_health_signal_policy.evaluate(request.question):
            return self._urgent_health_result(request=request, context=context)
        return None

    async def _prepare_entity_free_conversation(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution,
    ) -> PreparedMedicationQuestion | None:
        """대상명이 생략된 질문의 의도와 후속 처리를 준비한다."""

        requires_intent_check = (
            not resolution.entities
            or resolution.status is MedicationExpressionResolutionStatus.AUTO_CORRECTED
            or resolution.status is MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED
            or any(
                entity.source is MedicationQueryEntitySource.QDRANT and entity.kind is InteractionEntityKind.DRUG
                for entity in resolution.entities
            )
        )
        if not requires_intent_check or self._is_supplement_function_goal_question(request.question):
            return None

        classification = await self._classify_conversation(request=request)
        if classification is None or not self._is_allowed_entity_free_classification(classification):
            return None

        if (
            classification.intent is ConversationIntent.SPECIFIC_SYMPTOM
            and classification.safety_signal is ConversationSafetySignal.NONE
        ):
            classification = classification.model_copy(
                update={
                    "intent": ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE,
                    "symptom_context": request.question,
                }
            )

        conversation_result = await self._conversation_classification_result(
            request=request,
            context=context,
            classification=classification,
        )
        if conversation_result is not None:
            return PreparedMedicationQuestion(
                request=request,
                resolution=resolution,
                early_result=conversation_result,
            )

        if classification.safety_signal is not ConversationSafetySignal.NONE:
            return None
        if classification.intent is ConversationIntent.MEDICATION_GUIDE_FOLLOW_UP:
            return await self._resolve_medication_guide_follow_up(
                request=request,
                context=context,
            )
        if classification.intent is ConversationIntent.MEDICATION_GUIDE:
            return PreparedMedicationQuestion(
                request=request,
                resolution=self._allow_unresolved_guide_search(resolution),
                early_result=None,
                medication_guide_search=True,
            )
        if classification.intent is ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE:
            return self._prepare_symptom_medication_guidance(
                request=request,
                context=context,
                resolution=resolution,
                classification=classification,
            )
        return None

    @classmethod
    def _is_allowed_entity_free_classification(
        cls,
        classification: ConversationClassification,
    ) -> bool:
        return (
            classification.intent in cls._ENTITY_FREE_CONVERSATION_INTENTS
            or classification.safety_signal is not ConversationSafetySignal.NONE
        )

    @staticmethod
    def _allow_unresolved_guide_search(
        resolution: MedicationQuestionResolution,
    ) -> MedicationQuestionResolution:
        return resolution.model_copy(
            update={
                "scope": MedicationQuestionScope.IN_SCOPE,
                "status": MedicationExpressionResolutionStatus.UNCHANGED,
                "entity_resolution_available": False,
            }
        )

    def _prepare_symptom_medication_guidance(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution,
        classification: ConversationClassification,
    ) -> PreparedMedicationQuestion:
        return PreparedMedicationQuestion(
            request=request,
            resolution=self._allow_unresolved_guide_search(resolution).model_copy(
                update={
                    "resolved_question": request.question,
                    "entities": [],
                    "candidate_names": [],
                    "corrections": [],
                }
            ),
            early_result=self._conversation_result(
                request=request,
                context=context,
                answer=(
                    "✉️ **증상 안내**\n\n"
                    "- 증상만으로는 복약을 안내하기 어렵습니다.\n"
                    "- 궁금하신 제품명이나 성분명을 알려주세요.\n"
                    "- 의사 또는 약사에게 상담해 주세요."
                ),
                route=MedicationChatRoute.CLARIFICATION,
                safety_status=SafetyStatus.SAFE,
                reason_code=MedicationChatReasonCode.SYMPTOM_FOLLOW_UP_REQUIRED,
            ),
        )

    async def _resolve_medication_guide_follow_up(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
    ) -> PreparedMedicationQuestion:
        """최근 확정된 단일 대상을 확인 질문에 연결한 뒤 제품 검색으로 돌린다."""

        supported_types = {
            MedicationQueryEntityType.PRODUCT_NAME,
            MedicationQueryEntityType.BRAND_ALIAS,
            MedicationQueryEntityType.INGREDIENT_NAME,
            MedicationQueryEntityType.INGREDIENT_FAMILY,
        }
        names = list(
            dict.fromkeys(
                entity.name
                for entity in request.session_reference.entities
                if entity.entity_type in supported_types and entity.kind is not None
            )
        )
        if len(names) != 1:
            answer = (
                "어떤 약이나 성분의 주의사항을 확인할까요? 제품명 또는 성분명을 알려주세요."
                if not names
                else "최근 대화에서 확인한 대상이 여러 개입니다. 확인할 제품명이나 성분명을 알려주세요."
            )
            return PreparedMedicationQuestion(
                request=request,
                resolution=None,
                early_result=self._conversation_result(
                    request=request,
                    context=context,
                    answer=answer,
                    route=MedicationChatRoute.CLARIFICATION,
                    safety_status=SafetyStatus.SAFE,
                    reason_code=MedicationChatReasonCode.AMBIGUOUS_QUERY_EXPRESSION,
                ),
            )

        referenced_request = request.model_copy(
            update={"question": f"{names[0]} {request.question}"},
        )
        resolution = await self._resolve_question(
            request=referenced_request,
            context=context,
        )
        if resolution is None or not resolution.entities:
            return PreparedMedicationQuestion(
                request=request,
                resolution=resolution,
                early_result=self._conversation_result(
                    request=request,
                    context=context,
                    answer="확인할 제품을 정확히 찾지 못했습니다. 제품명이나 성분명을 다시 알려주세요.",
                    route=MedicationChatRoute.CLARIFICATION,
                    safety_status=SafetyStatus.SAFE,
                    reason_code=MedicationChatReasonCode.AMBIGUOUS_QUERY_EXPRESSION,
                ),
            )
        return PreparedMedicationQuestion(
            request=referenced_request,
            resolution=resolution,
            early_result=None,
        )

    @staticmethod
    def _validated_symptom_context(
        *,
        request: MedicationChatRequest,
        symptom_context: str | None,
    ) -> tuple[str | None, tuple[ChatHistoryMessage, ...]]:
        if not symptom_context:
            return None, ()
        normalized_context = symptom_context.strip()
        if normalized_context == request.question.strip():
            return normalized_context, ()
        matching_user_messages = [
            message
            for message in request.history
            if message.role is ChatRole.USER and message.content.strip() == normalized_context
        ]
        if not matching_user_messages:
            return None, ()
        return normalized_context, (matching_user_messages[-1],)

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
            or self._INTERACTION_OVERVIEW_PATTERN.search(request.question)
            or (
                self._is_interaction_question(request.question)
                and not self._PATIENT_CONTEXT_CUE_PATTERN.search(request.question)
                and re.search(
                    r"(?:안\s*되|피해야|주의할|조심해야).*(?:것|거|약|음식|영양제)|"
                    r"(?:어떤|무슨|뭐|무엇).*(?:약|음식|영양제)|상호작용\s*(?:목록|종류)",
                    request.question,
                )
            )
            or self._is_explicit_entity_guide_request(
                question=request.question,
                resolution=resolution,
            )
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

    @staticmethod
    def _is_explicit_entity_guide_request(
        *,
        question: str,
        resolution: MedicationQuestionResolution,
    ) -> bool:
        if is_interaction_question(question):
            return False
        if is_general_description_question(question):
            return True
        query_plan = MedicationKnowledgeQueryBuilder(
            catalog_entities=resolution.entities,
        ).build(question)
        return bool(query_plan.section_types)

    async def _with_conversation_interaction_references(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        resolution: MedicationQuestionResolution,
    ) -> tuple[MedicationChatRequest, MedicationQuestionResolution]:
        if not self._is_entity_free_conversation_candidate(resolution):
            return request, resolution

        referenced_request = await self._conversation_interaction_reference_request(
            request=request,
        )
        if referenced_request is None:
            return request, resolution

        referenced_resolution = await self._resolve_question(
            request=referenced_request,
            context=context,
        )
        return referenced_request, referenced_resolution or resolution

    async def _conversation_interaction_reference_request(
        self,
        *,
        request: MedicationChatRequest,
    ) -> MedicationChatRequest | None:
        """최근 대화의 두 대상을 현재 상호작용 질문으로 안전하게 보완한다."""

        if (
            self._conversation_gate_chain is None
            or not request.history
            or not is_interaction_question(request.question)
        ):
            return None

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
            return None

        if (
            classification.intent is not ConversationIntent.SYMPTOM_INTERACTION_FOLLOW_UP
            or classification.safety_signal is not ConversationSafetySignal.NONE
            or len(classification.interaction_reference_names) != 2
        ):
            return None

        reference_text = " ".join(classification.interaction_reference_names)
        return request.model_copy(
            update={
                "question": f"{request.question} {reference_text}",
                "symptom_interaction_follow_up": True,
                "conversation_interaction_reference_names": classification.interaction_reference_names,
            }
        )

    async def _conversation_terminal_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        allowed_intents: frozenset[ConversationIntent] | None = None,
    ) -> MedicationChatResult | None:
        """카탈로그 대상이 없는 대화를 구조화 Gate로 안전하게 처리한다."""

        classification = await self._classify_conversation(request=request)
        if classification is None:
            return None
        if (
            allowed_intents is not None
            and classification.intent not in allowed_intents
            and classification.safety_signal is ConversationSafetySignal.NONE
        ):
            return None
        return await self._conversation_classification_result(
            request=request,
            context=context,
            classification=classification,
        )

    async def _classify_conversation(
        self,
        *,
        request: MedicationChatRequest,
    ) -> ConversationClassification | None:
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
            classification = await self._normalize_note_summary_safety_signal(
                question=request.question,
                history=request.history,
                classification=classification,
            )
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
        return classification

    async def _normalize_note_summary_safety_signal(
        self,
        *,
        question: str,
        history: list[ChatHistoryMessage],
        classification: ConversationClassification,
    ) -> ConversationClassification:
        """과거 기록 요약을 현재 응급 상황으로 오인하지 않도록 한다."""

        if classification.intent is not ConversationIntent.MEDICATION_NOTE_SUMMARY:
            return classification
        if (
            classification.safety_signal is ConversationSafetySignal.HEALTH_URGENCY
            and not self._urgent_health_signal_policy.evaluate(question)
        ):
            return classification.model_copy(
                update={"safety_signal": ConversationSafetySignal.NONE},
            )
        if (
            classification.safety_signal is ConversationSafetySignal.HARMFUL_INSTRUCTIONS
            and history
            and self._conversation_gate_chain is not None
        ):
            try:
                current_question_classification = ConversationClassification.model_validate(
                    await self._conversation_gate_chain.ainvoke(
                        ConversationGateInput(question=question),
                    )
                )
            except Exception:
                return classification
            if (
                current_question_classification.intent is ConversationIntent.MEDICATION_NOTE_SUMMARY
                and current_question_classification.safety_signal is ConversationSafetySignal.NONE
            ):
                return current_question_classification
        return classification

    @staticmethod
    def _is_entity_free_conversation_candidate(
        resolution: MedicationQuestionResolution,
    ) -> bool:
        return (
            resolution.status
            in {
                MedicationExpressionResolutionStatus.UNRESOLVED,
                MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED,
            }
            and resolution.entity_resolution_available
            and not resolution.entities
        )

    @staticmethod
    def _requires_qdrant_conversation_safety_preflight(
        resolution: MedicationQuestionResolution,
    ) -> bool:
        """민감 의약품 후보만 Gate로 보내고 명확한 일반 안내 대상은 검색한다."""

        return any(
            entity.source is MedicationQueryEntitySource.QDRANT
            and entity.kind
            not in {
                InteractionEntityKind.SUPPLEMENT,
                InteractionEntityKind.FOOD,
            }
            for entity in resolution.entities
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
        if classification.intent in {
            ConversationIntent.ACTIVE_MEDICATION_LIST,
            ConversationIntent.ACTIVE_SUPPLEMENT_LIST,
        }:
            return self._active_intake_list_result(
                request=request,
                context=context,
                intent=classification.intent,
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

    @classmethod
    def _active_intake_list_result(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        intent: ConversationIntent,
    ) -> MedicationChatResult:
        if intent is ConversationIntent.ACTIVE_MEDICATION_LIST:
            names = cls._clean_active_intake_names(item.name for item in context.medications)
            answer = (
                "💊 **복약정보**\n" + "\n".join(f"- {name}" for name in names)
                if names
                else "현재 등록된 복약정보가 없습니다."
            )
        else:
            names = cls._clean_active_intake_names(item.name for item in context.supplements)
            answer = (
                "💪🏻 **영양제 정보**\n" + "\n".join(f"- {name}" for name in names)
                if names
                else "현재 등록된 영양제 정보가 없습니다."
            )
        return cls._conversation_result(
            request=request,
            context=context,
            answer=answer,
            route=MedicationChatRoute.ACTIVE_INTAKE,
            safety_status=SafetyStatus.SAFE,
            reason_code=MedicationChatReasonCode.ACTIVE_INTAKE_LIST_REQUESTED,
        )

    @classmethod
    def _clean_active_intake_names(cls, values) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for value in values:
            name = " ".join(cls._PARENTHETICAL_DESCRIPTION_PATTERN.sub("", value).split())
            key = name.casefold()
            if name and key not in seen:
                names.append(name)
                seen.add(key)
        return names

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
        if self._medication_note_summary_use_case is None or classification.note_summary_scope is None:
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
        lifestyle_check_required: bool = False,
    ) -> MedicationChatResult | None:
        if self._conversation_response_generator is None:
            return None

        route_and_reason = {
            ConversationIntent.GENERAL_HEALTH_FOLLOW_UP: (
                MedicationChatRoute.GENERAL_GUIDANCE,
                MedicationChatReasonCode.GENERAL_HEALTH_FOLLOW_UP,
            ),
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
            ConversationIntent.SENSITIVE_REQUEST: (
                MedicationChatRoute.OUT_OF_SCOPE,
                MedicationChatReasonCode.CONVERSATION_SENSITIVE_EDUCATION,
            ),
        }.get(classification.intent)
        if route_and_reason is None:
            return None
        route, reason_code = route_and_reason

        response_input = ConversationResponseInput(
            question=request.question,
            intent=classification.intent,
            follow_up_fields=classification.follow_up_fields,
            recent_history=request.history,
            lifestyle_check_required=lifestyle_check_required,
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
    def _response_subject(
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        guide_lookup: MedicationGuideLookup,
        interaction_question: bool,
    ) -> str | None:
        """공식 제품 가이드가 없는 단일 대상의 공공 근거에만 제목을 붙인다."""

        if guide_lookup.guide is not None or interaction_question:
            return None
        resolved_entities = [
            entity
            for entity in query_plan.entities
            if (entity.kind is not None and entity.entity_type is not MedicationQueryEntityType.TOPIC)
        ]
        if len(resolved_entities) != 1:
            return None
        return resolved_entities[0].canonical_name

    @staticmethod
    def _is_adverse_reaction_question(
        *,
        question: str,
        query_plan: MedicationKnowledgeQueryPlan,
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
    ) -> bool:
        if re.search(r"이상반응|부작용|복용\s*후|사용\s*후|보고된\s*사례", question):
            return True
        if interaction_question or query_plan.section_types:
            return False
        has_adverse_case_evidence = any(
            chunk.metadata.document_type is KnowledgeDocumentType.ADVERSE_CASE_REPORT for chunk in chunks
        )
        # "독사조신 어지러움"처럼 동사가 없는 검색도 조회된 사례 유형을 따른다.
        # 명시한 다른 섹션과 상호작용 요청은 위 조건에서 그대로 유지한다.
        return has_adverse_case_evidence

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
        if interpretation.needs_clarification and interpretation.clarification_question:
            return await self._conditional_clarification_result(
                request=request,
                context=context,
                interpretation=interpretation,
            )
        if self._can_answer_from_active_context(
            question=request.question,
            context=context,
        ):
            return None
        if not (
            should_execute_source_backed_retrieval(resolution)
            or self._is_supplement_function_goal_question(request.question)
        ):
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

    async def _conditional_clarification_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        interpretation: MedicationQuestionInterpretation,
    ) -> MedicationChatResult:
        if not interpretation.clarification_question:
            raise ValueError("조건부 확인 응답에는 확인 질문이 필요합니다.")
        result = MedicationChatResult(
            request_id=request.request_id,
            answer=interpretation.clarification_question,
            route=MedicationChatRoute.CLARIFICATION,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=[
                MedicationChatReasonCode.AMBIGUOUS_QUERY_EXPRESSION.value,
            ],
            prompt_version=MEDICATION_CHAT_PROMPT_VERSION,
            schema_version=MEDICATION_CHAT_SCHEMA_VERSION,
            context_hash=self._context_hash(context),
            question_interpretation=interpretation,
        )
        return await self._grounded_claim_validator.validate(
            context=context,
            result=result,
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
    def _with_interaction_overview(
        cls,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        planning: MedicationQuestionPlanResult,
    ) -> MedicationQuestionPlanResult:
        plan = planning.query_plan
        if KnowledgeSectionType.INTERACTION not in plan.section_types or not plan.entities:
            return planning
        active_names = {
            cls._normalize_entity_name(name)
            for entity in cls._active_intake_query_entities(context)
            for name in (entity.surface, entity.canonical_name)
        }
        asks_for_neighbors = bool(cls._INTERACTION_OVERVIEW_PATTERN.search(request.question))
        active_overview = (
            asks_for_neighbors
            and cls._can_answer_from_active_context(question=request.question, context=context)
            and all(cls._normalize_entity_name(entity.canonical_name) in active_names for entity in plan.entities)
        )
        # `_INTERACTION_OVERVIEW_PATTERN`을 여기에 추가하면 `와파린 상호작용 알려줘`,
        # `병용금기 알려줘` 같은 표준 탐색 표현이 패턴에 없어 3방향 검색을 잃는다.
        # 상대가 해소된 지정 조합은 entities가 둘이 되어 이미 강등되지 않는다.
        named_overview = (
            len(plan.entities) == 1
            and plan.entities[0].kind is InteractionEntityKind.DRUG
            and not cls._PATIENT_CONTEXT_CUE_PATTERN.search(request.question)
        )
        if not (active_overview or named_overview):
            return planning
        targets = [entity for entity in plan.entities if entity.kind is InteractionEntityKind.DRUG]
        if not targets:
            return planning
        target_names = [entity.canonical_name for entity in targets]
        plan = plan.model_copy(
            update={
                "entities": targets,
                "entity_names": target_names,
                "interaction_overview": True,
                "interaction_pair": None,
                "interaction_pairs": [],
                "interaction_pair_keys": [],
                "interaction_types": [
                    InteractionPairType.DRUG_DRUG,
                    InteractionPairType.DRUG_SUPPLEMENT,
                    InteractionPairType.DRUG_FOOD,
                ],
                "alternate_queries": list(
                    dict.fromkeys(
                        [
                            *plan.alternate_queries,
                            f"{' '.join(target_names)} 영양제 음식 상호작용",
                        ]
                    )
                ),
            }
        )
        return planning.model_copy(
            update={
                "query_plan": plan,
                "interpretation": planning.interpretation.model_copy(
                    update={
                        "query_plan_hash": plan.query_plan_hash,
                        "interaction_types": plan.interaction_types,
                        "normalized_entities": targets,
                        "normalized_entity_names": target_names,
                    }
                ),
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
        if request.conversation_interaction_reference_names or request.session_interaction_reference_used:
            return planning
        if request.symptom_interaction_follow_up:
            return cls._with_symptom_interaction_follow_up_query_plan(
                request=request,
                context=context,
                planning=planning,
            )
        if not cls._can_answer_from_active_context(
            question=request.question,
            context=context,
        ):
            return planning

        # An interaction request about the user's registered intake must be
        # rebuilt from the selected active targets even when the first resolver
        # happened to match one of them. That removes incidental topic tokens
        # such as "혈액응고" from metadata filters and restores the full pair set.
        is_interaction = cls._is_active_intake_interaction_question(
            question=request.question,
            context=context,
        )
        if not is_interaction and cls._query_plan_matches_active_context(
            query_plan=planning.query_plan,
            context=context,
        ):
            return planning

        active_entities = cls._active_intake_query_entities(context)
        if not active_entities:
            return planning

        active_entity_keys = {
            (entity.kind, cls._normalize_entity_name(name))
            for entity in active_entities
            for name in (entity.surface, entity.canonical_name)
        }
        explicit_entities = [
            entity
            for entity in planning.query_plan.entities
            if (
                entity.kind is not None
                and entity.entity_type is not MedicationQueryEntityType.TOPIC
                and entity.source is not MedicationQueryEntitySource.REGEX
                and (entity.kind, cls._normalize_entity_name(entity.canonical_name)) not in active_entity_keys
            )
        ]
        entities = [*active_entities, *explicit_entities]

        planning_question = f"{request.question} 상호작용" if is_interaction else request.question
        query_plan = MedicationKnowledgeQueryBuilder(
            catalog_entities=entities,
        ).build(planning_question)
        # The original wording may contain a treatment-class phrase such as
        # "혈액응고와 관련된 약". It supports active-intake selection, but is
        # not itself a medication or supplement search target.
        query_plan = query_plan.model_copy(
            update={
                "entities": entities,
                "entity_names": [entity.canonical_name for entity in entities],
            }
        )
        if is_interaction:
            interaction_pairs = (
                cls._interaction_pairs_between(
                    left_entities=active_entities,
                    right_entities=explicit_entities,
                )
                if explicit_entities
                else cls._interaction_pairs_for_entities(active_entities)
            )
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
            names = (
                item.interaction_names if isinstance(item, ActiveMedication) and item.interaction_names else [item.name]
            )
            for name in names:
                canonical_name = name.strip()
                normalized_name = "".join(canonical_name.casefold().split())
                key = (kind, normalized_name)
                if not canonical_name or key in seen:
                    continue
                seen.add(key)
                entities.append(
                    MedicationQueryEntity(
                        surface=item.name,
                        canonical_name=canonical_name,
                        product_lookup_name=item.name if kind is InteractionEntityKind.DRUG else None,
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
    def _with_active_intake_crosscheck_pairs(
        cls,
        *,
        context: ActiveIntakeContext,
        planning: MedicationQuestionPlanResult,
    ) -> MedicationQuestionPlanResult:
        """질문이 지목한 약·영양제를 등록 복용 항목과 대조할 쌍을 만든다.

        섭취 가부를 묻는 표현을 따로 분류하지 않는다(AGENTS §8.1). 지목한 대상이 있고
        복용 중인 항목이 있으면 언제나 대조하며, 근거로 확인된 쌍만 답변에 올라간다.
        """
        plan = planning.query_plan
        if plan.crosscheck_pairs or plan.interaction_pairs or plan.interaction_pair is not None:
            return planning
        active_entities = cls._active_intake_query_entities(context)
        if not active_entities:
            return planning
        active_keys = {
            (entity.kind, cls._normalize_entity_name(name))
            for entity in active_entities
            for name in (entity.surface, entity.canonical_name)
        }
        explicit_entities = [
            entity
            for entity in plan.entities
            if (
                entity.kind is not None
                and entity.entity_type is not MedicationQueryEntityType.TOPIC
                and (entity.kind, cls._normalize_entity_name(entity.canonical_name)) not in active_keys
            )
        ]
        if not explicit_entities:
            return planning
        pairs = cls._interaction_pairs_between(
            left_entities=active_entities,
            right_entities=explicit_entities,
        )
        if not pairs or len(pairs) > cls._MAX_CROSSCHECK_PAIRS:
            # 상한을 넘으면 검색 비용이 답변 품질보다 커진다. 대조를 생략한다.
            return planning
        query_plan = plan.model_copy(update={"crosscheck_pairs": pairs})
        interpretation = planning.interpretation.model_copy(
            update={"query_plan_hash": query_plan.query_plan_hash},
        )
        return MedicationQuestionPlanResult(
            query_plan=query_plan,
            interpretation=interpretation,
        )

    @classmethod
    def _crosscheck_execution_plan(
        cls,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> MedicationSearchExecutionPlan:
        """교차 확인 전용 검색 계획. 본 검색과 후보·랭킹을 공유하지 않는다."""
        plan = execution_plan.query_plan
        pairs = plan.crosscheck_pairs
        names = list(dict.fromkeys([name for pair in pairs for name in (pair.left_name, pair.right_name)]))
        # 검색은 느슨하게 두고 판정은 `_verified_crosscheck_pair_keys`가 문장 단위로 한다.
        # 여기에 `section_types=[INTERACTION]`과 `interaction_pairs`를 넣으면
        # `_requires_entity_pair_match`가 켜져 제품명 기반 쌍이 전부 PAIR_MISMATCH로 탈락한다.
        crosscheck_plan = plan.model_copy(
            update={
                "entity_names": names,
                "section_types": [],
                "alternate_queries": [f"{pair.left_name} {pair.right_name} 상호작용" for pair in pairs],
                "interaction_pairs": [],
                "interaction_pair_keys": [],
                "interaction_types": [],
                "interaction_pair": None,
                "crosscheck_pairs": [],
            },
        )
        return execution_plan.model_copy(
            update={"query_plan": crosscheck_plan, "approved_rule_pair_keys": []},
        )

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
            question=request.question,
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
            question=request.question,
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

    def _active_intake_no_evidence_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        rag_unavailable: bool,
        interpretation: MedicationQuestionInterpretation,
        evidence_coverage: MedicationEvidenceCoverage,
    ) -> MedicationChatResult:
        answer = EvidenceGapGuidanceBuilder.as_notice(
            self._assembler.assemble(
                context=context,
                guide=None,
                rules=[],
                chunks=[],
                interaction_question=True,
                active_intake_interaction=True,
                evidence_coverage=evidence_coverage,
            )
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
            sources=self._build_sources(
                context=context,
                guide_lookup=MedicationGuideLookup(),
                rules=[],
                chunks=[],
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
        if execution_plan.query_plan.interaction_pairs:
            draft = self._question_interaction_no_evidence_result(
                request=request,
                context=context,
                execution_plan=execution_plan,
                draft=draft,
            )
        if self._allows_general_supplement_guidance_without_direct_evidence(
            question=request.question,
            query_plan=execution_plan.query_plan,
            rag_unavailable=rag_unavailable,
            risk_decision=risk_decision,
        ):
            draft = draft.model_copy(
                update={
                    "route": MedicationChatRoute.INTERACTION,
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

    def _question_interaction_no_evidence_result(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        execution_plan: MedicationSearchExecutionPlan,
        draft: MedicationChatResult,
    ) -> MedicationChatResult:
        """직접 근거가 없는 질문 조합도 대상과 등록 복약정보를 분리해 보여준다."""

        answer_context = self._answer_context_for_route(
            context=context,
            request=request,
            route=MedicationChatRoute.INTERACTION,
        )
        return draft.model_copy(
            update={
                "answer": EvidenceGapGuidanceBuilder.as_notice(
                    self._assembler.assemble(
                        context=answer_context,
                        guide=None,
                        rules=[],
                        chunks=[],
                        interaction_question=True,
                        question_interaction_pairs=execution_plan.query_plan.interaction_pairs,
                    )
                ),
                "route": MedicationChatRoute.INTERACTION,
                "sources": self._build_sources(
                    context=answer_context,
                    guide_lookup=MedicationGuideLookup(),
                    rules=[],
                    chunks=[],
                ),
            }
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
                    ),
                    "answer_observation": outcome.observation,
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
        if query_plan.interaction_overview:
            return bool(rules or KnowledgeSectionType.INTERACTION in evidence_coverage.covered_section_types)
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
        has_drug = InteractionEntityKind.DRUG in entity_kinds
        has_supplement = InteractionEntityKind.SUPPLEMENT in entity_kinds
        # 약과 영양제가 섞인 질문에서 한쪽만 고르면 나머지 확인처를 빠뜨린 안내가 된다.
        if has_drug and has_supplement:
            return EvidenceGapSubject.UNKNOWN
        if has_drug:
            return EvidenceGapSubject.MEDICATION
        if has_supplement:
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
        if guide_lookup.guide is not None or any(guide_lookup.form_caution_guides.values()) or rules or chunks:
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

    async def _with_magnesium_form_cautions(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        guide_lookup: MedicationGuideLookup,
        interaction_question: bool,
    ) -> MedicationGuideLookup:
        """일반 마그네슘 주의사항은 두 제형의 공식 제품 가이드로 보강한다."""

        if (
            guide_lookup.guide is not None
            or interaction_question
            or KnowledgeSectionType.CAUTION not in query_plan.section_types
            or not any(
                entity.canonical_name == "마그네슘" and entity.kind is InteractionEntityKind.SUPPLEMENT
                for entity in query_plan.entities
            )
        ):
            return guide_lookup
        find_caution_guides = getattr(
            self._guide_repository,
            "find_caution_guides_by_ingredient_names",
            None,
        )
        if find_caution_guides is None:
            return guide_lookup
        form_caution_guides = await find_caution_guides(
            ["수산화마그네슘", "산화마그네슘"],
        )
        return guide_lookup.model_copy(
            update={"form_caution_guides": form_caution_guides},
        )

    async def _supplement_goal_cautions(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
        answer_chunks: list[RetrievedKnowledgeChunk],
        retrieved_chunks: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        """검색으로 확인된 원료의 주의사항만 추가 조회한다. 환자 목록은 검색에 섞지 않는다."""
        names = list(
            dict.fromkeys(
                name
                for chunk in answer_chunks
                if chunk.metadata.section_type is KnowledgeSectionType.FUNCTION
                for name in chunk.metadata.ingredient_names
            )
        )[:3]
        if not names:
            return []
        allowed = {self._normalize_entity_name(name) for name in names}

        def matching_cautions(candidates: list[RetrievedKnowledgeChunk]) -> list[RetrievedKnowledgeChunk]:
            return [
                chunk
                for chunk in candidates
                if (
                    chunk.metadata.section_type is KnowledgeSectionType.CAUTION
                    and chunk.metadata.document_type
                    in {KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE, KnowledgeDocumentType.SUPPLEMENT_CODE}
                    # Multi-ingredient paragraphs cannot be safely assigned to a single ingredient.
                    and len(chunk.metadata.ingredient_names) == 1
                    and self._normalize_entity_name(chunk.metadata.ingredient_names[0]) in allowed
                    and chunk.content.strip()
                )
            ]

        existing = matching_cautions(retrieved_chunks)
        covered = {self._normalize_entity_name(chunk.metadata.ingredient_names[0]) for chunk in existing}
        missing_names = [name for name in names if self._normalize_entity_name(name) not in covered]
        if not missing_names:
            return self._unique_chunks(existing)
        query = " ".join(missing_names) + " 섭취 시 주의사항 임신 수유 고령자 간질환 신장질환"
        caution_plan = MedicationKnowledgeQueryPlan(
            original_query=query,
            expanded_query=query,
            entity_names=missing_names,
            entities=[
                MedicationQueryEntity(
                    surface=name,
                    canonical_name=name,
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.SUPPLEMENT,
                    source=MedicationQueryEntitySource.QDRANT,
                )
                for name in missing_names
            ],
            document_types=[KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE, KnowledgeDocumentType.SUPPLEMENT_CODE],
            section_types=[KnowledgeSectionType.CAUTION],
        )
        caution_execution = execution_plan.model_copy(
            update={
                "query_plan": caution_plan,
                "patient_medication_names": [],
                "patient_supplement_names": [],
                "approved_rule_pair_keys": [],
                "approved_therapeutic_class_names": [],
                "include_patient_context": False,
                "limit": 6,
            }
        )
        async with self._tracer.span("supplement_cautions.retrieve", run_type="retriever") as span:
            try:
                async with asyncio.timeout(4.0):
                    attempt = await self._retrieve_knowledge(execution_plan=caution_execution)
                cautions = matching_cautions(attempt.result.chunks)
                span.end(
                    {"status": "UNAVAILABLE" if attempt.unavailable else "COMPLETED", "matched_count": len(cautions)}
                )
                return self._unique_chunks([*existing, *cautions])
            except TimeoutError:
                span.end({"status": "TIMEOUT", "matched_count": len(existing)})
                return self._unique_chunks(existing)

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

    async def _retrieve_with_crosscheck(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> tuple[_KnowledgeRetrievalAttempt, list[RetrievedKnowledgeChunk]]:
        """본 검색과 교차 확인 검색을 함께 돌린다.

        교차 확인 결과는 답변 근거에 합류시키지 않는다. 같은 후보 집합에 넣으면
        상위 선택(`select_diverse`)의 자리를 두고 겨뤄 질문이 요청한 근거를 밀어낸다.
        확인된 쌍을 판정하는 데에만 쓴다.
        """
        if not execution_plan.query_plan.crosscheck_pairs:
            return await self._retrieve_knowledge(execution_plan=execution_plan), []
        crosscheck_execution = self._crosscheck_execution_plan(execution_plan=execution_plan)
        results = await RunnableParallel(
            answer=self._retrieval_runnable(execution_plan=execution_plan),
            crosscheck=self._retrieval_runnable(execution_plan=crosscheck_execution),
        ).ainvoke({})
        return results["answer"], list(results["crosscheck"].result.chunks)

    def _retrieval_runnable(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> RunnableLambda:
        async def retrieve(_input: object) -> _KnowledgeRetrievalAttempt:
            return await self._retrieve_knowledge(execution_plan=execution_plan)

        return RunnableLambda(retrieve, name="medication_knowledge_retrieval")

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
        approved_therapeutic_class_names: list[str],
        crosscheck_chunks: list[RetrievedKnowledgeChunk],
    ) -> _CoverageRetryOutcome:
        evaluator = MedicationEvidenceCoverageEvaluator()
        before = evaluator.evaluate(
            query_plan=query_plan,
            guide_lookup=guide_lookup,
            rules=rules,
            chunks=answer_chunks,
            approved_therapeutic_class_names=approved_therapeutic_class_names,
            crosscheck_chunks=crosscheck_chunks,
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
            inputs={
                "query_variant_count": 1,
                "missing_section_count": len(before.missing_section_types),
            },
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
                approved_therapeutic_class_names=approved_therapeutic_class_names,
                crosscheck_chunks=crosscheck_chunks,
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
        approved_therapeutic_class_names: list[str] | None = None,
    ) -> MedicationSearchExecutionPlan:
        return MedicationSearchExecutionPlan(
            query_plan=query_plan,
            patient_medication_names=[item.name for item in context.medications],
            patient_supplement_names=[item.name for item in context.supplements],
            approved_rule_pair_keys=[rule.pair_key for rule in rules],
            approved_therapeutic_class_names=approved_therapeutic_class_names or [],
            approved_rule_status=rule_status,
            include_patient_context=not query_plan.interaction_overview
            and bool(
                cls._PATIENT_CONTEXT_CUE_PATTERN.search(
                    query_plan.original_query,
                )
            ),
            context_hash=cls._context_hash(context),
            approved_rules_hash=cls._approved_rules_hash(rules),
            limit=limit,
        )

    async def _approved_classes_for_interaction_overview(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[str]:
        if self._therapeutic_class_repository is None or not self._is_single_entity_interaction_overview(query_plan):
            return []
        try:
            return await self._therapeutic_class_repository.find_approved_class_names(
                entity_names=query_plan.entity_names,
            )
        except Exception:
            return []

    @classmethod
    def _is_single_entity_interaction_overview(cls, query_plan: MedicationKnowledgeQueryPlan) -> bool:
        return (
            len(query_plan.entity_names) == 1
            and KnowledgeSectionType.INTERACTION in query_plan.section_types
            and not query_plan.interaction_pairs
            and not cls._PATIENT_CONTEXT_CUE_PATTERN.search(query_plan.original_query)
        )

    @classmethod
    def _rules_for_query_plan(
        cls,
        *,
        rules: list[InteractionRuleFact],
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[InteractionRuleFact]:
        requested_pair_keys = set(query_plan.interaction_pair_keys)
        if cls._is_single_entity_interaction_overview(query_plan):
            name = cls._normalize_entity_name(query_plan.entity_names[0])
            return [
                rule
                for rule in rules
                if name in {cls._normalize_entity_name(rule.left_name), cls._normalize_entity_name(rule.right_name)}
            ]
        if not requested_pair_keys:
            return rules
        return [rule for rule in rules if rule.pair_key in requested_pair_keys]

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
        symptom_medication_guidance: bool = False,
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
        if symptom_medication_guidance and any(
            chunk.metadata.document_type
            in {
                KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                KnowledgeDocumentType.PHARM_REVIEW,
            }
            and chunk.metadata.section_type is KnowledgeSectionType.FUNCTION
            for chunk in chunks
        ):
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

    @classmethod
    def _functional_supplement_answer_chunks(
        cls,
        *,
        question: str,
        chunks: list,
    ) -> list:
        """목표 기반 기능성 질문에는 성분이 명시된 원료 근거만 우선 보여 준다."""

        if not cls._is_supplement_function_goal_question(question):
            return chunks
        source_backed_ingredients = [
            chunk
            for chunk in chunks
            if (
                chunk.metadata.document_type
                in {
                    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    KnowledgeDocumentType.SUPPLEMENT_CODE,
                }
                and chunk.metadata.section_type is KnowledgeSectionType.FUNCTION
                and chunk.metadata.ingredient_names
            )
        ]
        return source_backed_ingredients[:3]

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
            if AnswerMedicationQuestionUseCase._is_supplement_function_goal_question(question):
                return True
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
                "건강기능식품",
                "기능성 원료",
            )
        )

    @staticmethod
    def _is_supplement_function_goal_question(question: str) -> bool:
        return is_supplement_function_goal_question(question)

    @classmethod
    def _functional_supplement_goal_title(cls, question: str) -> str | None:
        """목표형 영양제 질문의 건강 목표를 짧은 사용자용 제목으로 정규화한다."""

        normalized_question = re.sub(r"\s+", " ", question).strip()
        for pattern, title in cls._FUNCTIONAL_SUPPLEMENT_GOAL_TITLES:
            if pattern.search(normalized_question):
                return title
        if "건강" in normalized_question and re.search(r"도움|성분|영양", normalized_question):
            return "건강 증진"
        return None

    @classmethod
    def _bypass_supplement_function_goal_clarification(
        cls,
        *,
        question: str,
        resolution: MedicationQuestionResolution,
    ) -> MedicationQuestionResolution:
        """목표 기반 기능성 질문은 제품 후보 확인보다 원료 근거를 우선 검색한다."""

        if (
            resolution.status is not MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED
            or not cls._is_supplement_function_goal_question(question)
        ):
            return resolution
        return resolution.model_copy(
            update={
                "status": MedicationExpressionResolutionStatus.UNCHANGED,
                "candidate_names": [],
            }
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
                kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                title=f"e약은요 · {guide.product_name}",
                organization="식품의약품안전처",
                medication_guide_id=guide.medication_guide_id,
            )
            for form_guides in guide_lookup.form_caution_guides.values()
            for guide in form_guides
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
        # 출처 카드는 문서당 한 번만 표시하고, 원본 근거 청크 목록은 유지한다.
        document_keys: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            document_key = (
                chunk.metadata.source_id,
                chunk.metadata.document_id,
                chunk.metadata.dataset_version,
            )
            if document_key in document_keys:
                continue
            document_keys.add(document_key)
            sources.append(
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
            )
        return sources
