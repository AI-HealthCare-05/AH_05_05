import hashlib
from contextlib import asynccontextmanager
from datetime import date, datetime

import pytest
from langchain_core.runnables import RunnableLambda

from ai_worker.chains.conditional_question_interpretation_chain import (
    ConditionalQuestionInterpretationOutput,
)
from ai_worker.chains.medication_query_plan_chain import (
    MedicationQueryPlanChainInput,
    MedicationQuestionPlanResult,
    build_medication_query_plan_chain,
)
from ai_worker.chains.semantic_question_router import (
    QuestionRoutingDecision,
    SemanticRouterInput,
)
from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.safety.grounded_claim_validator import (
    RuleBasedGroundedClaimValidator,
)
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import ConversationClassification
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeCandidateDiagnostic,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchTier,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    InteractionRuleFact,
    MedicationAnswerFallbackReason,
    MedicationAnswerGenerationObservation,
    MedicationAnswerGenerationOutcome,
    MedicationAnswerRewriteStatus,
    MedicationChatAnswerDomain,
    MedicationChatProgressStage,
    MedicationChatReasonCode,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRiskProfile,
    MedicationChatRiskScope,
    MedicationChatRoute,
    MedicationChatSessionReference,
    MedicationChatSessionReferenceEntity,
    MedicationChatSourceKind,
    MedicationGuideFact,
    MedicationGuideLookup,
    TherapeuticClassSelection,
    TherapeuticClassSelectionStatus,
)
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQuestionResolution,
)
from ai_worker.schemas.patient import FollowUpSchedule
from ai_worker.use_cases.answer_medication_question import (
    AnswerMedicationQuestionUseCase,
)


class RecordingSpan:
    trace_id = None

    def __init__(self, name: str) -> None:
        self.name = name
        self.outputs = None

    def end(self, outputs=None) -> None:
        self.outputs = outputs


class RecordingChatTracer:
    def __init__(self, *, capture_content: bool = False) -> None:
        self.capture_content = capture_content
        self.spans = []

    @property
    def names(self) -> list[str]:
        return [span.name for span in self.spans]

    @asynccontextmanager
    async def span(self, name, **kwargs):
        span = RecordingSpan(name)
        self.spans.append(span)
        yield span

    def anonymize_identifier(self, value):
        return None

    async def aclose(self) -> None:
        return None


class FakeContextProvider:
    def __init__(self, context: ActiveIntakeContext) -> None:
        self.context = context

    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext:
        return self.context


class StaticFollowUpScheduleProvider:
    def __init__(self, schedules: list[FollowUpSchedule]) -> None:
        self.schedules = schedules
        self.received_input: tuple[int, int] | None = None

    async def list_upcoming_schedules(
        self,
        *,
        user_id: int,
        limit: int,
    ) -> list[FollowUpSchedule]:
        self.received_input = (user_id, limit)
        return self.schedules


class FakeGuideRepository:
    def __init__(self, lookup: MedicationGuideLookup) -> None:
        self.lookup = lookup

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        return self.lookup


class ExactNameGuideRepository:
    def __init__(
        self,
        *,
        expected_name: str,
        lookup: MedicationGuideLookup,
    ) -> None:
        self.expected_name = expected_name
        self.lookup = lookup

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        if product_name == self.expected_name:
            return self.lookup
        return MedicationGuideLookup()


class RecordingGuideRepository:
    def __init__(self, lookup: MedicationGuideLookup | None = None) -> None:
        self.requested_names: list[str] = []
        self.lookup = lookup or MedicationGuideLookup()

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        self.requested_names.append(product_name)
        return self.lookup


class UnexpectedGuideRepository:
    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        raise AssertionError(f"영양제 상호작용 질문에서 의약품 제품 조회를 호출했습니다: {product_name}")


class StaticExpressionCatalog:
    def __init__(self, expressions: list[str]) -> None:
        self.expressions = expressions

    async def list_expressions(self) -> list[str]:
        return self.expressions


class StaticTypedExpressionCatalog(StaticExpressionCatalog):
    def __init__(self, entries: list[MedicationCatalogEntry]) -> None:
        super().__init__([entry.canonical_name for entry in entries])
        self.entries = entries

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        return self.entries


class StaticSupplementIngredientCatalog:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    async def list_names(self) -> list[str]:
        return self.names


class FakeRuleRepository:
    def __init__(self, rules: list[InteractionRuleFact]) -> None:
        self.rules = rules

    async def find_approved_rules(
        self,
        *,
        context: ActiveIntakeContext,
        query_entity_names: list[str] | None = None,
    ) -> list[InteractionRuleFact]:
        return self.rules


class FailingRuleRepository:
    async def find_approved_rules(
        self,
        *,
        context: ActiveIntakeContext,
        query_entity_names: list[str] | None = None,
    ) -> list[InteractionRuleFact]:
        raise RuntimeError("interaction rule DB unavailable")


class StaticTherapeuticClassRepository:
    def __init__(self, selection: TherapeuticClassSelection) -> None:
        self.selection = selection
        self.questions: list[str] = []

    async def select_active_medications(
        self,
        *,
        context: ActiveIntakeContext,
        question: str,
    ) -> TherapeuticClassSelection:
        del context
        self.questions.append(question)
        return self.selection


class FakeKnowledgeRetriever:
    def __init__(
        self,
        chunks: list[RetrievedKnowledgeChunk] | None = None,
        error: Exception | None = None,
        diagnostics: KnowledgeRetrievalDiagnostics | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.error = error
        self.diagnostics = diagnostics or KnowledgeRetrievalDiagnostics(
            raw_candidate_count=len(self.chunks),
            entity_filtered_count=0,
            broad_candidate_count=len(self.chunks),
            fallback_used=False,
            eligible_candidate_count=len(self.chunks),
            rejected_below_score_count=0,
            rejected_entity_mismatch_count=0,
            rejected_pair_mismatch_count=0,
            accepted_count=len(self.chunks),
            max_raw_score=max(
                (chunk.similarity_score for chunk in self.chunks),
                default=None,
            ),
            max_score=max(
                (chunk.similarity_score for chunk in self.chunks),
                default=None,
            ),
        )

    async def search(
        self,
        *,
        question: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        if self.error is not None:
            raise self.error
        return self.chunks

    async def search_with_diagnostics(
        self,
        *,
        execution_plan,
    ) -> KnowledgeRetrievalResult:
        if self.error is not None:
            raise self.error
        return KnowledgeRetrievalResult(
            chunks=self.chunks,
            diagnostics=self.diagnostics,
        )


class RecordingQueryPlanRetriever(FakeKnowledgeRetriever):
    def __init__(self) -> None:
        super().__init__()
        self.received_kwargs = None

    async def search_with_diagnostics(
        self,
        *,
        execution_plan,
    ) -> KnowledgeRetrievalResult:
        self.received_kwargs = {"execution_plan": execution_plan}
        return KnowledgeRetrievalResult(
            chunks=self.chunks,
            diagnostics=self.diagnostics,
        )


class SequencedKnowledgeRetriever(FakeKnowledgeRetriever):
    def __init__(self, responses: list[list[RetrievedKnowledgeChunk]]) -> None:
        super().__init__()
        self.responses = list(responses)
        self.execution_plans = []

    async def search_with_diagnostics(
        self,
        *,
        execution_plan,
    ) -> KnowledgeRetrievalResult:
        self.execution_plans.append(execution_plan)
        chunks = self.responses.pop(0)
        return KnowledgeRetrievalResult(
            chunks=chunks,
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=len(chunks),
                entity_filtered_count=0,
                broad_candidate_count=len(chunks),
                eligible_candidate_count=len(chunks),
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=len(chunks),
                max_raw_score=max(
                    (chunk.similarity_score for chunk in chunks),
                    default=None,
                ),
                max_score=max(
                    (chunk.similarity_score for chunk in chunks),
                    default=None,
                ),
            ),
        )


class RecordingConditionalInterpretationChain:
    def __init__(self, payload: ConditionalQuestionInterpretationOutput) -> None:
        self.payload = payload
        self.inputs = []

    async def ainvoke(self, input, config=None, **kwargs):
        self.inputs.append(input)
        return self.payload


class StaticConversationGate:
    def __init__(self, payload: ConversationClassification) -> None:
        self.payload = payload
        self.inputs = []

    async def ainvoke(self, input, config=None, **kwargs):
        self.inputs.append(input)
        return self.payload


class UnexpectedConversationGate:
    async def ainvoke(self, input, config=None, **kwargs):
        raise AssertionError("카탈로그가 확인한 약 질문에서 Conversation Gate를 호출했습니다.")


class StaticConversationResponseGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.inputs = []

    async def generate(self, input) -> str:
        self.inputs.append(input)
        return self.answer

    def fallback(self, input) -> str:
        self.inputs.append(input)
        return self.answer


class StaticMedicationNoteSummaryUseCase:
    def __init__(self) -> None:
        self.received_scope: MedicationNoteSummaryScope | None = None
        self.received_context_hash: str | None = None

    async def execute(self, *, request, scope, context_hash):
        self.received_scope = scope
        self.received_context_hash = context_hash
        return MedicationChatResult(
            request_id=request.request_id,
            answer="📝 **복약메모 요약**\n- 두통을 기록함.",
            route=MedicationChatRoute.MEDICATION_NOTE_SUMMARY,
            safety_status=SafetyStatus.SAFE,
            safety_reason_codes=["MEDICATION_NOTE_SUMMARY_REQUESTED"],
            prompt_version="medication-note-summary-prompt-v1",
            schema_version="medication-chat-result-v1",
            context_hash=context_hash,
        )


class RecordingSemanticRouter:
    def __init__(self, payload: QuestionRoutingDecision) -> None:
        self.payload = payload
        self.inputs: list[SemanticRouterInput] = []

    async def ainvoke(self, input, **kwargs):
        self.inputs.append(input)
        return self.payload


class PassthroughGenerator:
    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        answer_hash = hashlib.sha256(result.answer.encode("utf-8")).hexdigest()
        return MedicationAnswerGenerationOutcome(
            result=result,
            observation=MedicationAnswerGenerationObservation(
                status=MedicationAnswerRewriteStatus.REWRITTEN,
                fallback_used=False,
                draft_answer_hash=answer_hash,
                generated_answer_hash=answer_hash,
            ),
        )


class ContextRecordingGenerator(PassthroughGenerator):
    def __init__(self) -> None:
        self.context: ActiveIntakeContext | None = None

    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        self.context = context
        return await super().generate(
            request=request,
            context=context,
            result=result,
        )


class PassthroughValidator:
    def diagnose(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ):
        del context, result
        return None

    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        return result


class LongAnswerGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        generated = result.model_copy(update={"answer": self.answer})
        return MedicationAnswerGenerationOutcome(
            result=generated,
            observation=MedicationAnswerGenerationObservation(
                status=MedicationAnswerRewriteStatus.REWRITTEN,
                fallback_used=False,
                draft_answer_hash=hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                generated_answer_hash=hashlib.sha256(self.answer.encode("utf-8")).hexdigest(),
            ),
        )


class FallbackGenerator:
    generated_answer = "하루 10정을 복용해도 안전합니다."

    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        return MedicationAnswerGenerationOutcome(
            result=result,
            observation=MedicationAnswerGenerationObservation(
                status=MedicationAnswerRewriteStatus.DRAFT_FALLBACK,
                fallback_used=True,
                fallback_reason=(MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION),
                draft_answer_hash=hashlib.sha256(result.answer.encode("utf-8")).hexdigest(),
                generated_answer_hash=hashlib.sha256(self.generated_answer.encode("utf-8")).hexdigest(),
            ),
        )


class FailingMedicationGenerator:
    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        raise ChatAnswerGenerationError(
            "생성 실패",
            reason_code=MedicationAnswerFallbackReason.CLIENT_ERROR.value,
        )


class UnexpectedMedicationGenerator:
    async def generate(
        self,
        *,
        request: MedicationChatRequest,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationAnswerGenerationOutcome:
        raise AssertionError("결정론적 응답에서 답변 LLM을 호출하면 안 됩니다.")


class RecordingValidator:
    def __init__(self) -> None:
        self.received: MedicationChatResult | None = None

    def diagnose(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ):
        del context, result
        return None

    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        self.received = result
        return result


def build_request(
    question: str,
    *,
    care_episode_id: int | None = None,
) -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        care_episode_id=care_episode_id,
        question=question,
    )


def build_guide() -> MedicationGuideFact:
    return MedicationGuideFact(
        medication_guide_id=12,
        item_seq="100",
        product_name="타이레놀정500밀리그람",
        manufacturer_name="테스트제약",
        efficacy="통증과 발열을 완화합니다.",
        usage_instructions="제품 설명서와 전문가의 안내를 따릅니다.",
        pre_use_warning="성분을 확인합니다.",
        precautions="정해진 용법을 지킵니다.",
        drug_food_interactions="다른 약 복용 시 전문가에게 알립니다.",
        adverse_reactions="이상반응이 있으면 전문가와 상담합니다.",
        storage_instructions="실온에 보관합니다.",
    )


def build_chunk() -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="point-1",
        chunk_id="a" * 64,
        content="아세트아미노펜 복용 시 제품별 함량과 주의사항을 확인합니다.",
        embedding_text="아세트아미노펜 주의사항",
        token_count=20,
        similarity_score=0.82,
        metadata=KnowledgeChunkMetadata(
            source_id="MFDS",
            document_id="drug-guide-1",
            title="의약품 안전사용 안내",
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
            dataset_version="knowledge-baseline-v1",
            section_type=KnowledgeSectionType.CAUTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


def build_losartan_chunk(
    *,
    section_type: KnowledgeSectionType = KnowledgeSectionType.CAUTION,
    content: str = "로사르탄 단일제는 제품별 주의사항을 확인해야 합니다.",
) -> RetrievedKnowledgeChunk:
    chunk = build_chunk().model_copy(
        update={
            "content": content,
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_id": "losartan-encyclopedia",
                    "title": "로사르탄(losartan)",
                    "document_type": KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    "drug_names": [
                        "로사르탄(losartan)",
                        "로사르탄",
                        "losartan",
                    ],
                    "section_type": section_type,
                }
            ),
        }
    )
    return chunk


def build_use_case(
    *,
    context: ActiveIntakeContext | None = None,
    lookup: MedicationGuideLookup | None = None,
    rules: list[InteractionRuleFact] | None = None,
    rule_repository=None,
    retriever: FakeKnowledgeRetriever | None = None,
    tracer=None,
    answer_generator=None,
    grounded_claim_validator=None,
    question_resolver=None,
    supplement_ingredient_catalog=None,
    query_plan_chain=None,
    conditional_interpretation_chain=None,
    semantic_question_router=None,
    therapeutic_class_repository=None,
    conversation_gate_chain=None,
    conversation_response_generator=None,
    guide_repository=None,
    follow_up_schedule_provider=None,
    medication_note_summary_use_case=None,
) -> AnswerMedicationQuestionUseCase:
    return AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(context or ActiveIntakeContext(user_id=1)),
        guide_repository=(guide_repository or FakeGuideRepository(lookup or MedicationGuideLookup())),
        interaction_rule_repository=(rule_repository or FakeRuleRepository(rules or [])),
        knowledge_retriever=retriever or FakeKnowledgeRetriever(),
        answer_generator=answer_generator or PassthroughGenerator(),
        grounded_claim_validator=(grounded_claim_validator or PassthroughValidator()),
        tracer=tracer,
        question_resolver=question_resolver,
        supplement_ingredient_catalog=supplement_ingredient_catalog,
        query_plan_chain=query_plan_chain,
        conditional_interpretation_chain=conditional_interpretation_chain,
        semantic_question_router=semantic_question_router,
        therapeutic_class_repository=therapeutic_class_repository,
        conversation_gate_chain=conversation_gate_chain,
        conversation_response_generator=conversation_response_generator,
        follow_up_schedule_provider=follow_up_schedule_provider,
        medication_note_summary_use_case=medication_note_summary_use_case,
    )


async def test_vague_symptom_uses_conversation_gate_without_retrieval() -> None:
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="VAGUE_SYMPTOM",
                safety_signal="NONE",
                confidence="HIGH",
                follow_up_fields=["LOCATION", "ONSET"],
            )
        ),
        conversation_response_generator=StaticConversationResponseGenerator(
            "많이 불편하시겠어요. 어디가 언제부터 아픈지 알려주세요."
        ),
    ).execute(build_request("아픈데 어떻게 해?"))

    assert result.route is MedicationChatRoute.CLARIFICATION
    assert result.safety_status is SafetyStatus.SAFE
    assert retriever.received_kwargs is None
    assert "어디" in result.answer


async def test_follow_up_schedule_question_returns_registered_upcoming_visits() -> None:
    schedule_provider = StaticFollowUpScheduleProvider(
        [
            FollowUpSchedule(
                follow_up_visit_id=1,
                visit_at=datetime(2026, 9, 16, 14, 0),
                visit_time=datetime(2026, 9, 16, 14, 0).time(),
                hospital="서울내과",
            ),
            FollowUpSchedule(
                follow_up_visit_id=2,
                visit_at=datetime(2026, 9, 20, 0, 0),
                hospital="대학병원",
            ),
        ]
    )
    result = await build_use_case(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="FOLLOW_UP_SCHEDULE",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        follow_up_schedule_provider=schedule_provider,
    ).execute(build_request("내 진료 일정 알려줘"))

    assert result.route.value == "FOLLOW_UP_SCHEDULE"
    assert "🗓️ **진료 일정**" in result.answer
    assert "- 9월 16일 14:00 · 서울내과" in result.answer
    assert "- 9월 20일 · 대학병원" in result.answer
    assert schedule_provider.received_input == (1, 5)


async def test_follow_up_schedule_question_explains_when_no_upcoming_visit_exists() -> None:
    result = await build_use_case(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="FOLLOW_UP_SCHEDULE",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
        follow_up_schedule_provider=StaticFollowUpScheduleProvider([]),
    ).execute(build_request("진료 일정 알려줘"))

    assert result.route is MedicationChatRoute.FOLLOW_UP_SCHEDULE
    assert result.answer == "등록된 예정 진료일정이 없습니다."


async def test_note_summary_request_bypasses_rag_retrieval() -> None:
    retriever = RecordingQueryPlanRetriever()
    summary_use_case = StaticMedicationNoteSummaryUseCase()
    result = await build_use_case(
        retriever=retriever,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="MEDICATION_NOTE_SUMMARY",
                safety_signal="NONE",
                confidence="HIGH",
                note_summary_scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
            )
        ),
        medication_note_summary_use_case=summary_use_case,
    ).execute(build_request("복약메모 정리해줘"))

    assert result.route is MedicationChatRoute.MEDICATION_NOTE_SUMMARY
    assert retriever.received_kwargs is None
    assert summary_use_case.received_scope is MedicationNoteSummaryScope.RECENT_SIX_MONTHS


async def test_specific_symptom_requests_candidate_medicine_without_exposing_active_medications() -> None:
    response_generator = StaticConversationResponseGenerator(
        "🩺 **상호작용 확인을 위해 필요한 정보**\n- 추가로 복용하려는 약의 제품명 또는 성분명을 알려주세요."
    )
    result = await build_use_case(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="리바록사반정(항응고제)",
                )
            ],
        ),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SPECIFIC_SYMPTOM",
                safety_signal="NONE",
                confidence="HIGH",
                follow_up_fields=["ONSET", "SEVERITY"],
            )
        ),
        conversation_response_generator=response_generator,
    ).execute(build_request("배가 아프고 속이 쓰려"))

    assert result.route is MedicationChatRoute.CLARIFICATION
    assert "제품명 또는 성분명" in result.answer
    assert "active_medication_names" not in response_generator.inputs[0].model_dump()


async def test_specific_symptom_does_not_infer_interaction_from_active_medications() -> None:
    result = await build_use_case(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="리바록사반정",
                ),
                ActiveMedication(
                    medication_id=2,
                    care_episode_id=1,
                    name="파모티딘정",
                ),
            ],
        ),
        rule_repository=FailingRuleRepository(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SPECIFIC_SYMPTOM",
                safety_signal="NONE",
                confidence="HIGH",
                follow_up_fields=["ONSET", "SEVERITY"],
            )
        ),
        conversation_response_generator=StaticConversationResponseGenerator(
            "💊 **복약정보**\n- 리바록사반정\n- 파모티딘정\n\n"
            "🩺 **확인을 위해 필요한 정보**\n- 증상이 시작된 시점과 통증 정도를 알려주세요."
        ),
    ).execute(build_request("배가 아프고 속이 쓰려"))

    assert result.route is MedicationChatRoute.CLARIFICATION
    assert "🔁 **상호작용**" not in result.answer
    assert "상호작용이 있습니다" not in result.answer


async def test_symptom_follow_up_candidate_uses_active_intake_interaction_rules() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=1,
                name="리바록사반정",
            )
        ],
    )
    rule = InteractionRuleFact(
        interaction_rule_id=1,
        pair_key=build_interaction_pair_key(
            InteractionEntity(kind=InteractionEntityKind.DRUG, display_name="리바록사반정"),
            InteractionEntity(kind=InteractionEntityKind.DRUG, display_name="알마겔"),
        ),
        pair_type="DRUG_DRUG",
        left_name="리바록사반정",
        right_name="알마겔",
        risk_level="CAUTION",
        effect_texts=["승인된 병용 확인 근거입니다."],
    )
    request = build_request("알마겔").model_copy(
        update={
            "history": [
                ChatHistoryMessage(
                    role=ChatRole.ASSISTANT,
                    content=(
                        "증상 원인이나 복통약 추천은 할 수 없지만, "
                        "추가로 복용하려는 약의 제품명 또는 성분명을 알려주세요."
                    ),
                )
            ]
        }
    )
    guide_repository = RecordingGuideRepository()

    result = await build_use_case(
        context=context,
        rules=[rule],
        guide_repository=guide_repository,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticTypedExpressionCatalog(
                [
                    MedicationCatalogEntry(
                        canonical_name="알마겔",
                        entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                        kind=InteractionEntityKind.DRUG,
                        source=MedicationQueryEntitySource.CATALOG,
                    )
                ]
            )
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SYMPTOM_INTERACTION_FOLLOW_UP",
                safety_signal="NONE",
                confidence="HIGH",
            )
        ),
    ).execute(request)

    assert result.route is MedicationChatRoute.ACTIVE_INTAKE
    assert any(source.kind is MedicationChatSourceKind.INTERACTION_RULE for source in result.sources)
    assert guide_repository.requested_names == []


async def test_explicit_active_medication_interaction_uses_approved_rule() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=1,
                name="리바록사반정",
            ),
            ActiveMedication(
                medication_id=2,
                care_episode_id=1,
                name="파모티딘정",
            ),
        ],
    )
    rule = InteractionRuleFact(
        interaction_rule_id=1,
        pair_key=build_interaction_pair_key(
            InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name="리바록사반정",
            ),
            InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name="파모티딘정",
            ),
        ),
        pair_type="DRUG_DRUG",
        left_name="리바록사반정",
        right_name="파모티딘정",
        risk_level="CAUTION",
        effect_texts=["승인된 상호작용 근거입니다."],
    )

    result = await build_use_case(
        context=context,
        rules=[rule],
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(build_request("현재 먹는 두 약 사이에 상호작용이 있어?"))

    assert result.route is MedicationChatRoute.ACTIVE_INTAKE
    assert any(source.kind is MedicationChatSourceKind.INTERACTION_RULE for source in result.sources)


async def test_active_medication_interaction_without_approved_rule_states_uncertainty() -> None:
    result = await build_use_case(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="리바록사반정",
                ),
                ActiveMedication(
                    medication_id=2,
                    care_episode_id=1,
                    name="파모티딘정",
                ),
            ],
        ),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(build_request("현재 먹는 두 약 사이에 상호작용이 있어?"))

    assert "상호작용을 확인하지 못했습니다" in result.answer
    assert "안전하다는 의미는 아닙니다" in result.answer


async def test_harmful_request_is_blocked_before_rag() -> None:
    result = await build_use_case(
        retriever=RecordingQueryPlanRetriever(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SENSITIVE_REQUEST",
                safety_signal="HARMFUL_INSTRUCTIONS",
                confidence="HIGH",
            )
        ),
    ).execute(build_request("핵폭탄 만드는 법 알려줘"))

    assert result.route is MedicationChatRoute.RESTRICTED
    assert result.safety_status is SafetyStatus.BLOCKED


async def test_conversation_trace_records_decision_without_sensitive_content() -> None:
    tracer = RecordingChatTracer(capture_content=False)

    await build_use_case(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=1,
                    name="리바록사반정",
                )
            ],
        ),
        tracer=tracer,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
        conversation_gate_chain=StaticConversationGate(
            ConversationClassification(
                intent="SPECIFIC_SYMPTOM",
                safety_signal="NONE",
                confidence="HIGH",
                follow_up_fields=["ONSET", "SEVERITY"],
            )
        ),
        conversation_response_generator=StaticConversationResponseGenerator(
            "💊 **복약정보**\n- 리바록사반정\n\n"
            "🩺 **확인을 위해 필요한 정보**\n- 증상이 시작된 시점과 통증 정도를 알려주세요."
        ),
    ).execute(build_request("배가 아프고 속이 쓰려"))

    classify_outputs = next(span.outputs for span in tracer.spans if span.name == "conversation.classify")
    respond_outputs = next(span.outputs for span in tracer.spans if span.name == "conversation.respond")
    assert classify_outputs["intent"] == "SPECIFIC_SYMPTOM"
    assert classify_outputs["safety_signal"] == "NONE"
    assert classify_outputs["history_count"] == 0
    assert classify_outputs["status"] == "COMPLETED"
    assert classify_outputs["duration_ms"] >= 0
    assert "question" not in classify_outputs
    assert "active_medication_names" not in classify_outputs
    assert respond_outputs["intent"] == "SPECIFIC_SYMPTOM"
    assert respond_outputs["disposition"] == "ALLOW"
    assert respond_outputs["fallback_used"] is False
    assert respond_outputs["status"] == "COMPLETED"
    assert respond_outputs["duration_ms"] >= 0


async def test_medication_question_bypasses_conversation_gate() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀"]),
        ),
        conversation_gate_chain=UnexpectedConversationGate(),
    ).execute(build_request("타이레놀은 어디에 좋아?"))

    assert result.route is MedicationChatRoute.MEDICATION_GUIDE


async def test_execute_uses_injected_query_plan_chain() -> None:
    async def force_magnesium_plan(
        value: MedicationQueryPlanChainInput,
    ) -> dict:
        planning: MedicationQuestionPlanResult = await build_medication_query_plan_chain().ainvoke(
            value.model_copy(
                update={"question": "마그네슘은 왜 먹나요?"},
            )
        )
        return planning.model_dump()

    retriever = RecordingQueryPlanRetriever()

    await build_use_case(
        retriever=retriever,
        query_plan_chain=RunnableLambda(force_magnesium_plan),
    ).execute(build_request("원래 질문"))

    assert retriever.received_kwargs is not None
    query_plan = retriever.received_kwargs["execution_plan"].query_plan
    assert query_plan.entity_names == ["마그네슘"]
    assert query_plan.section_types == [KnowledgeSectionType.FUNCTION]


async def test_execute_asks_for_dose_details_before_personal_dose_increase() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
    ).execute(
        build_request("두통이 심한데 타이레놀을 평소보다 두 배 먹어도 될까?"),
    )

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == [
        MedicationChatReasonCode.PERSONAL_DOSE_CHANGE_CONFIRMATION_REQUIRED.value,
    ]
    assert "- 현재 등록된 1회 용량: 등록 정보가 없어 확인할 수 없음" in result.answer
    assert "- 현재 등록된 복용 횟수: 등록 정보가 없어 확인할 수 없음" in result.answer
    assert "- 오늘 실제 누적 복용량: 확인할 수 없음" in result.answer
    assert "- 마지막 실제 복용 시각: 확인할 수 없음" in result.answer
    assert "- 다른 함께 복용한 제품: 확인 필요" in result.answer
    assert "제품 설명서와 전문가의 안내를 따릅니다" not in result.answer
    assert result.sources == []


async def test_execute_shows_matching_registered_dose_but_not_unattributable_intake_history() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="타이레놀정500밀리그람",
                dose="1정",
                times_per_day=3,
            )
        ],
    )

    result = await build_use_case(
        context=context,
        lookup=MedicationGuideLookup(guide=build_guide()),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀정500밀리그람"]),
        ),
    ).execute(
        build_request("두통이 심한데 타이레놀정500밀리그람을 평소보다 두 배 먹어도 될까?"),
    )

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert "- 현재 등록된 1회 용량: 1정" in result.answer
    assert "- 현재 등록된 복용 횟수: 하루 3회" in result.answer
    assert "- 오늘 실제 누적 복용량: 확인할 수 없음" in result.answer
    assert "- 마지막 실제 복용 시각: 확인할 수 없음" in result.answer
    assert "- 다른 함께 복용한 제품: 확인 필요" in result.answer


async def test_execute_escalates_possible_overdose_without_product_guide() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
    ).execute(
        build_request("실수로 타이레놀을 평소보다 두 배 먹었어."),
    )

    assert result.route == MedicationChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == [
        MedicationChatReasonCode.POSSIBLE_OVERDOSE.value,
    ]
    assert "추가 복용은 보류" in result.answer
    assert "제품 설명서와 전문가의 안내를 따릅니다" not in result.answer
    assert result.sources == []


async def test_active_intake_summary_executes_without_explicit_entity_in_question() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="와파린",
            )
        ],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 K",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 9, 9),
            )
        ],
    )
    rule = InteractionRuleFact(
        interaction_rule_id=1,
        pair_key=build_interaction_pair_key(
            InteractionEntity(
                kind=InteractionEntityKind.DRUG,
                display_name="와파린",
            ),
            InteractionEntity(
                kind=InteractionEntityKind.SUPPLEMENT,
                display_name="비타민 K",
            ),
        ),
        pair_type="DRUG_SUPPLEMENT",
        left_name="와파린",
        right_name="비타민 K",
        risk_level="HIGH",
        effect_texts=["비타민 K 섭취 변화는 와파린 효과에 영향을 줄 수 있습니다."],
    )

    result = await build_use_case(
        context=context,
        rules=[rule],
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(
        build_request("내가 현재 복용 중인 약과 영양제를 정리하고 가장 먼저 확인할 상호작용을 알려줘."),
    )

    assert result.route == MedicationChatRoute.ACTIVE_INTAKE
    assert result.safety_reason_codes == []
    assert "복약정보" in result.answer
    assert "영양제 정보" in result.answer
    assert "와파린" in result.answer
    assert "비타민 K" in result.answer
    assert "확인된 상호작용" in result.answer


async def test_active_intake_question_without_external_evidence_uses_registered_targets_and_guidance() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="와파린",
            )
        ],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 K",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 9, 9),
            )
        ],
    )
    retriever = RecordingQueryPlanRetriever()

    result = await build_use_case(
        context=context,
        retriever=retriever,
        answer_generator=PassthroughGenerator(),
    ).execute(
        build_request("혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 해?"),
    )

    assert retriever.received_kwargs is not None
    execution_plan = retriever.received_kwargs["execution_plan"]
    assert execution_plan.query_plan.entity_names == ["와파린", "비타민 K"]
    assert execution_plan.medication_names == ["와파린"]
    assert execution_plan.supplement_names == ["비타민 K"]
    assert result.route == MedicationChatRoute.ACTIVE_INTAKE
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "복약정보\n- 와파린" in result.answer
    assert "영양제 정보\n- 비타민 K" in result.answer
    assert "직접 근거를 확인하지 못했습니다" in result.answer
    assert "의료진·약사에게 확인할 내용" in result.answer
    assert "오메가3" not in result.answer


async def test_active_intake_therapeutic_class_question_uses_only_classified_registered_medication() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="와파린",
            ),
            ActiveMedication(
                medication_id=2,
                care_episode_id=10,
                name="타이레놀정500밀리그람",
            ),
        ],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 K",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 9, 9),
            )
        ],
    )
    retriever = RecordingQueryPlanRetriever()
    tracer = RecordingChatTracer()
    therapeutic_class_repository = StaticTherapeuticClassRepository(
        TherapeuticClassSelection(
            status=TherapeuticClassSelectionStatus.MATCHED,
            class_codes=["ANTICOAGULANT"],
            medication_ids=[1],
        )
    )

    result = await build_use_case(
        context=context,
        retriever=retriever,
        tracer=tracer,
        answer_generator=PassthroughGenerator(),
        therapeutic_class_repository=therapeutic_class_repository,
    ).execute(
        build_request("혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 해?"),
    )

    assert therapeutic_class_repository.questions == ["혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 해?"]
    assert retriever.received_kwargs is not None
    execution_plan = retriever.received_kwargs["execution_plan"]
    assert execution_plan.query_plan.entity_names == ["와파린", "비타민 K"]
    assert execution_plan.medication_names == ["와파린"]
    assert "타이레놀정500밀리그람" not in execution_plan.query_plan.entity_names
    assert "복약정보\n- 와파린" in result.answer
    assert "타이레놀정500밀리그람" not in result.answer
    class_span = next(span for span in tracer.spans if span.name == "therapeutic_class.resolve")
    assert class_span.outputs == {
        "status": "MATCHED",
        "matched_class_count": 1,
        "matched_medication_count": 1,
    }


async def test_active_intake_therapeutic_class_question_uses_approved_rule_and_exact_pair_evidence() -> None:
    pair_key = build_interaction_pair_key(
        InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="와파린",
        ),
        InteractionEntity(
            kind=InteractionEntityKind.SUPPLEMENT,
            display_name="비타민 K",
        ),
    )
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="와파린",
            ),
            ActiveMedication(
                medication_id=2,
                care_episode_id=10,
                name="타이레놀정500밀리그람",
            ),
        ],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 K",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 9, 9),
            )
        ],
    )
    evidence_chunk = build_chunk().model_copy(
        update={
            "content": "와파린의 항응고 효과는 비타민 K 섭취 변화의 영향을 받을 수 있습니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_id": "warfarin-vitamin-k-review",
                    "document_type": KnowledgeDocumentType.PHARM_REVIEW,
                    "section_type": KnowledgeSectionType.INTERACTION,
                    "drug_names": ["와파린"],
                    "ingredient_names": ["비타민 K"],
                    "interaction_type": "DRUG_SUPPLEMENT",
                    "interaction_pair_keys": [pair_key],
                }
            ),
        }
    )
    rule = InteractionRuleFact(
        interaction_rule_id=1,
        pair_key=pair_key,
        pair_type="DRUG_SUPPLEMENT",
        left_name="와파린",
        right_name="비타민 K",
        risk_level="HIGH_CAUTION",
        effect_texts=["비타민 K 섭취 변화는 와파린 효과에 영향을 줄 수 있습니다."],
        source_titles=["승인 규칙"],
    )

    result = await build_use_case(
        context=context,
        rules=[rule],
        retriever=FakeKnowledgeRetriever(chunks=[evidence_chunk]),
        therapeutic_class_repository=StaticTherapeuticClassRepository(
            TherapeuticClassSelection(
                status=TherapeuticClassSelectionStatus.MATCHED,
                class_codes=["ANTICOAGULANT"],
                medication_ids=[1],
            )
        ),
    ).execute(
        build_request("혈액응고와 관련된 약은 등록한 영양제와 어떤 점을 조심해야 해?"),
    )

    assert result.route == MedicationChatRoute.ACTIVE_INTAKE
    assert result.safety_status == SafetyStatus.SAFE
    assert result.evidence_coverage.verified_interaction_pair_keys == [pair_key]
    assert {source.kind for source in result.sources} == {
        MedicationChatSourceKind.PATIENT_MEDICATION,
        MedicationChatSourceKind.PATIENT_SUPPLEMENT,
        MedicationChatSourceKind.INTERACTION_RULE,
        MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
    }
    assert "타이레놀정500밀리그람" not in result.answer


async def test_execute_auto_corrects_unique_typo_before_search() -> None:
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(ActiveIntakeContext(user_id=1)),
        guide_repository=ExactNameGuideRepository(
            expected_name="타이레놀",
            lookup=MedicationGuideLookup(guide=build_guide()),
        ),
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀"]),
        ),
    )

    result = await use_case.execute(
        build_request("타이래놀"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert result.answer.startswith(
        "입력하신 ‘타이래놀’을 ‘타이레놀’로 이해하고 검색했습니다.",
    )
    assert "통증과 발열을 완화합니다" in result.answer


async def test_execute_uses_trailing_typo_correction_for_product_lookup() -> None:
    guide_repository = ExactNameGuideRepository(
        expected_name="타이레놀",
        lookup=MedicationGuideLookup(guide=build_guide()),
    )
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(
            ActiveIntakeContext(user_id=1),
        ),
        guide_repository=guide_repository,
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀"]),
        ),
    )

    result = await use_case.execute(
        build_request("타이레놀ㄹ 복용법 알려줘"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert result.answer.startswith(
        "입력하신 ‘타이레놀ㄹ’을 ‘타이레놀’로 이해하고 검색했습니다.",
    )
    assert "제품 설명서와 전문가의 안내를 따릅니다" in result.answer


async def test_execute_requests_clarification_before_search_for_tied_typo() -> None:
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        answer_generator=UnexpectedMedicationGenerator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀", "타이레널"]),
        ),
    ).execute(build_request("타이레늘 복용법 알려줘"))

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == ["AMBIGUOUS_QUERY_EXPRESSION"]
    assert "타이레널, 타이레놀" in result.answer
    assert retriever.received_kwargs is None


@pytest.mark.parametrize(
    ("question", "expected_text"),
    [
        (
            "안녕하세요",
            "의약품의 효능·사용법·주의사항",
        ),
        (
            "오늘 너무 배고파요",
            "의약품·복약·영양제 정보와 상호작용",
        ),
    ],
)
async def test_execute_returns_deterministic_out_of_scope_guidance(
    question: str,
    expected_text: str,
) -> None:
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        answer_generator=UnexpectedMedicationGenerator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(build_request(question))

    assert result.route == MedicationChatRoute.OUT_OF_SCOPE
    assert result.safety_status == SafetyStatus.SAFE
    assert expected_text in result.answer
    assert retriever.received_kwargs is None


async def test_execute_routes_fatigue_to_question_first_guidance_before_retrieval_or_llm() -> None:
    retriever = RecordingQueryPlanRetriever()
    tracer = RecordingChatTracer()

    result = await build_use_case(
        retriever=retriever,
        tracer=tracer,
        answer_generator=UnexpectedMedicationGenerator(),
    ).execute(build_request("요즘 피곤해요"))

    assert result.route == MedicationChatRoute.GENERAL_GUIDANCE
    assert result.safety_status == SafetyStatus.SAFE
    assert result.safety_reason_codes == ["FATIGUE_FOLLOW_UP_REQUIRED"]
    assert retriever.received_kwargs is None
    assert tracer.names == [
        "patient_context.load",
        "fatigue.triage",
        "query.plan",
    ]


async def test_execute_routes_fatigue_red_flag_to_restricted_urgent_assistance() -> None:
    result = await build_use_case(
        answer_generator=UnexpectedMedicationGenerator(),
    ).execute(build_request("피곤하고 숨이 차서 실신할 것 같아요"))

    assert result.route == MedicationChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == ["FATIGUE_URGENT_ASSISTANCE"]


async def test_execute_records_interpretation_before_out_of_scope_return() -> None:
    tracer = RecordingChatTracer()
    result = await build_use_case(
        tracer=tracer,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(build_request("안녕하세요"))

    assert tracer.names == [
        "patient_context.load",
        "question.resolve",
        "query.plan",
    ]
    assert result.question_interpretation is not None
    assert result.question_interpretation.intent.value == "GREETING"
    assert result.question_interpretation.confidence.value == "LOW"
    query_outputs = tracer.spans[-1].outputs
    assert query_outputs["intent"] == "GREETING"
    assert query_outputs["needs_clarification"] is False


async def test_execute_records_question_resolution_diagnostics_without_content() -> None:
    tracer = RecordingChatTracer()
    result = await build_use_case(
        tracer=tracer,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["비타민 D"]),
        ),
    ).execute(build_request("비타민 디의 주의사항을 알려줘"))

    resolution_outputs = next(span.outputs for span in tracer.spans if span.name == "question.resolve")
    query_plan_outputs = next(span.outputs for span in tracer.spans if span.name == "query.plan")

    assert result.question_interpretation is not None
    assert resolution_outputs["normalization_strategy"] == "LETTER_PRONUNCIATION"
    assert resolution_outputs["confidence_tier"] == "HIGH"
    assert resolution_outputs["shortlisted_candidate_count"] == 1
    assert resolution_outputs["tie_count"] == 0
    assert resolution_outputs["relation_resolution_status"] == "NOT_APPLICABLE"
    assert resolution_outputs["catalog_source_counts"] == {"CATALOG": 1}
    assert resolution_outputs["catalog_type_counts"] == {"INGREDIENT_NAME": 1}
    assert "question" not in resolution_outputs
    assert query_plan_outputs["legacy_entity_inference_used"] is False


async def test_execute_restricts_query_plan_chain_failure_before_search() -> None:
    async def fail_query_plan(value):
        raise RuntimeError("query plan failed")

    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        answer_generator=UnexpectedMedicationGenerator(),
        query_plan_chain=RunnableLambda(fail_query_plan),
    ).execute(build_request("타이레놀 주의사항"))

    assert result.route == MedicationChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == ["QUERY_PLAN_FAILED"]
    assert "질문을 안전하게 해석하지 못했습니다" in result.answer
    assert retriever.received_kwargs is None


async def test_execute_distinguishes_in_scope_question_without_evidence() -> None:
    result = await build_use_case(
        answer_generator=UnexpectedMedicationGenerator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(
        build_request("처음 보는 약의 복용 시 주의사항을 알려줘"),
    )

    assert result.route == MedicationChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == ["IN_SCOPE_NO_EVIDENCE"]
    assert "✉️ **안내사항**" in result.answer
    assert "📭 **공식 확인 경로**" not in result.answer
    assert "의료진·약사에게 확인할 내용" not in result.answer
    assert "안전한 조합" not in result.answer


async def test_execute_routes_fatigue_product_request_to_follow_up_without_product_lookup() -> None:
    guide_repository = RecordingGuideRepository()
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(ActiveIntakeContext(user_id=1)),
        guide_repository=guide_repository,
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=UnexpectedMedicationGenerator(),
        grounded_claim_validator=PassthroughValidator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    )

    result = await use_case.execute(
        build_request("피곤할 때 가장 좋은 영양제 하나 추천해줘"),
    )

    assert result.route == MedicationChatRoute.GENERAL_GUIDANCE
    assert result.safety_reason_codes == ["FATIGUE_FOLLOW_UP_REQUIRED"]
    assert guide_repository.requested_names == []


async def test_execute_skips_rag_for_fatigue_product_request() -> None:
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        answer_generator=UnexpectedMedicationGenerator(),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(
        build_request("피곤할 때 가장 좋은 영양제 하나 추천해줘"),
    )

    assert result.route == MedicationChatRoute.GENERAL_GUIDANCE
    assert result.safety_reason_codes == ["FATIGUE_FOLLOW_UP_REQUIRED"]
    assert retriever.received_kwargs is None


async def test_general_drug_question_runs_without_episode() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
    ).execute(
        build_request("타이레놀정500밀리그람은 어떤 약인가요?"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer
    assert result.answer.startswith("일반 제품 안내\n")
    assert "성분을 확인합니다" in result.answer
    assert "다른 약 복용 시 전문가에게 알립니다" in result.answer


async def test_execute_keeps_tylenol_efficacy_and_caution_without_global_disclaimer() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        answer_generator=LongAnswerGenerator(
            "효능\n- 통증과 발열을 완화합니다.\n\n주의사항\n- 정해진 용법을 지킵니다."
        ),
        grounded_claim_validator=RuleBasedGroundedClaimValidator(),
    ).execute(
        build_request("타이레놀은 어디에 좋고 먹을 때 뭘 조심해야 해?"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert result.safety_status == SafetyStatus.SAFE
    assert "통증과 발열을 완화합니다" in result.answer
    assert "정해진 용법을 지킵니다" in result.answer
    assert "의료진의 진료, 진단 또는 처방을 대체하지 않습니다" not in result.answer


async def test_execute_resolves_single_drug_reference_from_explicit_session_memory() -> None:
    request = build_request("그 약의 복용법도 알려줘.").model_copy(
        update={
            "session_reference": MedicationChatSessionReference(
                entities=[
                    MedicationChatSessionReferenceEntity(
                        name="타이레놀정500밀리그람",
                        entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                        kind=InteractionEntityKind.DRUG,
                    )
                ]
            )
        }
    )

    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(request)

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert result.question_interpretation is not None
    assert result.question_interpretation.normalized_entity_names == ["타이레놀정500밀리그람"]
    assert result.answer.startswith("타이레놀정500밀리그람의 복용법\n")
    assert "제품 설명서와 전문가의 안내" in result.answer


async def test_execute_preserves_reference_product_heading_after_answer_rewrite() -> None:
    request = build_request("그 약의 복용법도 알려줘.").model_copy(
        update={
            "session_reference": MedicationChatSessionReference(
                entities=[
                    MedicationChatSessionReferenceEntity(
                        name="타이레놀정500밀리그람",
                        entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                        kind=InteractionEntityKind.DRUG,
                    )
                ]
            )
        }
    )

    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        answer_generator=LongAnswerGenerator("복용법은 제품 설명서를 따르세요."),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog([]),
        ),
    ).execute(request)

    assert result.answer.startswith("타이레놀정500밀리그람의 복용법\n")
    assert "복용법은 제품 설명서를 따르세요." in result.answer


async def test_execute_uses_dynamic_supplement_names_in_query_plan() -> None:
    retriever = RecordingQueryPlanRetriever()

    await build_use_case(
        retriever=retriever,
        supplement_ingredient_catalog=(StaticSupplementIngredientCatalog(["루테인"])),
    ).execute(
        build_request("루테인은 왜 먹나요?"),
    )

    assert retriever.received_kwargs is not None
    query_plan = retriever.received_kwargs["execution_plan"].query_plan
    assert query_plan.entities[0].kind == InteractionEntityKind.SUPPLEMENT
    assert query_plan.document_types == [
        KnowledgeDocumentType.SUPPLEMENT_CODE,
        KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
    ]


async def test_execute_routes_general_ingredient_to_supplement_guide_when_drug_metadata_collides() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": "오메가3는 일반적인 영양제 안내와 주의사항을 확인합니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["오메가3"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticTypedExpressionCatalog(
                [
                    MedicationCatalogEntry(
                        canonical_name="오메가-3",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.DRUG,
                        source=MedicationQueryEntitySource.QDRANT,
                    ),
                    MedicationCatalogEntry(
                        canonical_name="오메가3",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.SUPPLEMENT,
                        source=MedicationQueryEntitySource.CATALOG,
                    ),
                ]
            ),
        ),
    ).execute(
        build_request("오메가3의 효능, 일일 섭취량, 주의사항을 알려줘."),
    )

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert result.question_interpretation is not None
    assert result.question_interpretation.normalized_entity_names == ["오메가3"]


async def test_execute_requests_product_or_purpose_when_product_and_supplement_collide() -> None:
    retriever = RecordingQueryPlanRetriever()
    result = await build_use_case(
        retriever=retriever,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticTypedExpressionCatalog(
                [
                    MedicationCatalogEntry(
                        canonical_name="테스트오션",
                        entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                        kind=InteractionEntityKind.DRUG,
                        source=MedicationQueryEntitySource.RDBMS,
                    ),
                    MedicationCatalogEntry(
                        canonical_name="테스트오션",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.SUPPLEMENT,
                        source=MedicationQueryEntitySource.CATALOG,
                    ),
                ]
            ),
        ),
    ).execute(build_request("테스트오션의 효능을 알려줘."))

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert "제품명 또는 복용 목적(의약품/영양제)을 알려주세요" in result.answer
    assert retriever.received_kwargs is None


async def test_execute_forwards_question_query_plan_without_patient_or_rule_signals() -> None:
    retriever = RecordingQueryPlanRetriever()

    await build_use_case(
        context=ActiveIntakeContext(user_id=1),
        rules=[],
        retriever=retriever,
    ).execute(
        build_request("와파린과 비타민 K 영양제를 같이 먹어도 되나요?"),
    )

    assert retriever.received_kwargs is not None
    execution_plan = retriever.received_kwargs["execution_plan"]
    assert execution_plan.patient_medication_names == []
    assert execution_plan.patient_supplement_names == []
    assert execution_plan.approved_rule_pair_keys == []
    query_plan = execution_plan.query_plan
    assert query_plan.entity_names == ["와파린", "비타민 K"]
    assert query_plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert execution_plan.interaction_pair_keys == query_plan.interaction_pair_keys
    assert execution_plan.query_plan_hash == query_plan.query_plan_hash
    assert len(execution_plan.execution_plan_hash) == 64


async def test_execute_applies_patient_context_only_for_explicit_context_question() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="아스피린",
                dose="1정",
                times_per_day=1,
                days=7,
            )
        ],
    )
    general_retriever = RecordingQueryPlanRetriever()
    context_retriever = RecordingQueryPlanRetriever()

    await build_use_case(
        context=context,
        retriever=general_retriever,
    ).execute(build_request("마그네슘은 왜 먹나요?"))
    await build_use_case(
        context=context,
        retriever=context_retriever,
    ).execute(build_request("등록한 약과 비타민 K의 상호작용을 알려줘"))

    general_plan = general_retriever.received_kwargs["execution_plan"]
    context_plan = context_retriever.received_kwargs["execution_plan"]
    assert general_plan.patient_medication_names == ["아스피린"]
    assert general_plan.medication_names == []
    assert context_plan.medication_names == ["아스피린"]


async def test_execute_distinguishes_rule_repository_failure_from_no_rules() -> None:
    retriever = RecordingQueryPlanRetriever()

    result = await build_use_case(
        rule_repository=FailingRuleRepository(),
        retriever=retriever,
    ).execute(build_request("와파린과 비타민 K를 같이 먹어도 되나요?"))

    execution_plan = retriever.received_kwargs["execution_plan"]
    assert execution_plan.approved_rule_status.value == ("RULE_REPOSITORY_UNAVAILABLE")
    assert execution_plan.interaction_pair_keys
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "INTERACTION_RULE_REPOSITORY_UNAVAILABLE" in (result.safety_reason_codes)


async def test_drug_encyclopedia_evidence_uses_medication_guide_route() -> None:
    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(
            chunks=[build_losartan_chunk()],
        ),
    ).execute(
        build_request("로사르탄의 주의사항을 알려줘"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "성분 계열 일반 정보" in result.answer
    assert "제품·복합제별" in result.answer
    assert "사용자 확정 복약정보" not in result.answer
    assert any(source.kind.value == "PUBLIC_KNOWLEDGE" for source in result.sources)


async def test_general_ingredient_evidence_bypasses_product_ambiguity() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            candidate_names=["코자정", "로자탄정"],
        ),
        retriever=FakeKnowledgeRetriever(
            chunks=[build_losartan_chunk()],
        ),
    ).execute(
        build_request("로사르탄의 주의사항을 알려줘"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "제품명을 확인해 주세요" not in result.answer
    assert "성분 계열 일반 정보" in result.answer


async def test_exact_product_guide_suppresses_conflicting_encyclopedia_claim() -> None:
    conflicting_claim = "로사르탄은 한 번에 99정을 복용합니다."
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(
            chunks=[
                build_losartan_chunk(
                    section_type=KnowledgeSectionType.DAILY_INTAKE,
                    content=conflicting_claim,
                )
            ],
        ),
    ).execute(
        build_request("타이레놀정500밀리그람 복용법을 알려줘"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "제품 설명서와 전문가의 안내를 따릅니다" in result.answer
    assert conflicting_claim not in result.answer


async def test_execute_reports_only_fixed_safe_progress_stages() -> None:
    stages: list[MedicationChatProgressStage] = []
    messages: list[str] = []

    async def record_progress(progress) -> None:
        stages.append(progress.stage)
        messages.append(progress.message)

    await build_use_case().execute(
        build_request("마그네슘은 왜 먹나요?"),
        progress_callback=record_progress,
    )

    assert stages == [
        MedicationChatProgressStage.QUESTION_CHECKING,
        MedicationChatProgressStage.EVIDENCE_SEARCHING,
        MedicationChatProgressStage.ANSWER_GENERATING,
        MedicationChatProgressStage.SAFETY_CHECKING,
    ]
    assert messages == [
        "질문 확인 중",
        "근거 검색 중",
        "답변 정리 중",
        "안전 확인 중",
    ]


async def test_execute_records_safe_stage_summaries_without_raw_content() -> None:
    tracer = RecordingChatTracer()
    use_case = build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[build_chunk()]),
        tracer=tracer,
    )

    await use_case.execute(
        build_request("타이레놀정500밀리그람은 어떤 약인가요?"),
    )

    assert tracer.names == [
        "patient_context.load",
        "query.plan",
        "risk.policy",
        "interaction_rules.search",
        "rag.retrieve",
        "medication_guide.lookup",
        "answer.evidence_coverage",
        "answer.draft",
        "llm.generate",
        "safety.validate",
    ]
    serialized_outputs = repr(
        [span.outputs for span in tracer.spans],
    )
    assert "타이레놀정500밀리그람" not in serialized_outputs
    assert build_chunk().content not in serialized_outputs
    query_outputs = tracer.spans[1].outputs
    assert query_outputs["intent"] == "MEDICATION_GUIDE"
    assert query_outputs["confidence"] == "LOW"
    assert query_outputs["needs_clarification"] is False
    assert query_outputs["reason_codes"] == [
        "QUESTION_RESOLUTION_UNAVAILABLE",
        "ENTITY_IDENTIFIED",
    ]
    assert query_outputs["normalized_entity_count"] == 2
    assert query_outputs["requested_section_types"] == []
    assert tracer.spans[2].outputs == {
        "domain": "MEDICATION",
        "scope": "EVIDENCE_ONLY",
        "reason_codes": [],
        "personalized_guidance_requested": False,
    }
    rag_outputs = tracer.spans[4].outputs
    assert len(rag_outputs.pop("query_plan_hash")) == 64
    assert len(rag_outputs.pop("execution_plan_hash")) == 64
    assert rag_outputs == {
        "raw_candidate_count": 1,
        "entity_filtered_count": 0,
        "broad_candidate_count": 1,
        "fallback_used": False,
        "eligible_candidate_count": 1,
        "rejected_below_score_count": 0,
        "rejected_entity_mismatch_count": 0,
        "rejected_pair_mismatch_count": 0,
        "accepted_count": 1,
        "parent_context_child_count": 0,
        "parent_context_attached_count": 0,
        "parent_context_rejected_mismatch_count": 0,
        "rag_unavailable": False,
        "document_types": ["DRUG_ENCYCLOPEDIA"],
        "drug_encyclopedia_evidence_count": 1,
        "max_raw_score": 0.82,
        "max_score": 0.82,
        "attempted_search_tiers": [],
        "selected_search_tier": None,
    }
    safety_outputs = tracer.spans[-1].outputs
    assert len(safety_outputs.pop("query_plan_hash")) == 64
    assert len(safety_outputs.pop("execution_plan_hash")) == 64
    assert safety_outputs == {
        "status": "SAFE",
        "reason_codes": [],
    }

    llm_outputs = next(span.outputs for span in tracer.spans if span.name == "llm.generate")
    assert llm_outputs["rewrite_status"] == "REWRITTEN"
    assert llm_outputs["fallback_used"] is False
    assert llm_outputs["fallback_reason"] is None
    assert llm_outputs["declared_section_types"] == []
    assert llm_outputs["covered_section_types"] == []
    assert len(llm_outputs["draft_answer_hash"]) == 64
    assert len(llm_outputs["generated_answer_hash"]) == 64


async def test_execute_records_hashed_safety_match_without_raw_content() -> None:
    tracer = RecordingChatTracer()
    unsafe_answer = "오늘부터 약 복용을 중단하세요. 이 안내는 의료진의 진료를 대체하지 않습니다."

    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[build_chunk()]),
        tracer=tracer,
        answer_generator=LongAnswerGenerator(unsafe_answer),
        grounded_claim_validator=RuleBasedGroundedClaimValidator(),
    ).execute(
        build_request("타이레놀정500밀리그람은 어떤 약인가요?"),
    )

    safety_outputs = next(span.outputs for span in tracer.spans if span.name == "safety.validate")
    assert result.safety_status == SafetyStatus.BLOCKED
    assert safety_outputs.get("matched_rule_code") == "MEDICATION_CHANGE_INSTRUCTION"
    assert safety_outputs.get("matched_action") == "STOP"
    assert safety_outputs.get("matched_target") == "MEDICATION"
    assert len(safety_outputs["matched_fragment_hash"]) == 64
    assert "중단하세요" not in repr(safety_outputs)


async def test_execute_allows_conditioned_official_product_warning() -> None:
    warning = "이 약 복용 후 피부 발진 또는 과민반응의 징후가 나타나는 경우 즉시 복용을 중단하십시오."
    guide = build_guide().model_copy(
        update={"pre_use_warning": warning},
    )
    tracer = RecordingChatTracer()

    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=guide),
        retriever=FakeKnowledgeRetriever(chunks=[build_chunk()]),
        tracer=tracer,
        grounded_claim_validator=RuleBasedGroundedClaimValidator(),
    ).execute(
        build_request("타이레놀의 효능과 주의사항을 알려줘."),
    )

    safety_outputs = next(span.outputs for span in tracer.spans if span.name == "safety.validate")
    assert result.safety_status == SafetyStatus.SAFE
    assert warning in result.answer
    assert safety_outputs["official_warning_allowed"] is True
    assert "MEDICATION_CHANGE_INSTRUCTION" not in safety_outputs["reason_codes"]


async def test_execute_records_retrieval_failure_stage_without_error_message() -> None:
    tracer = RecordingChatTracer()
    retrieval_error = GuidelineRetrievalError(
        stage=RetrievalFailureStage.VECTOR_STORE,
        message="약·영양제 Knowledge 벡터 검색에 실패했습니다.",
    )
    retrieval_error.__cause__ = RuntimeError(
        "private upstream error detail",
    )

    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(error=retrieval_error),
        tracer=tracer,
    ).execute(
        build_request("마그네슘은 왜 먹나요?"),
    )

    rag_outputs = next(span.outputs for span in tracer.spans if span.name == "rag.retrieve")
    assert rag_outputs["rag_unavailable"] is True
    assert rag_outputs["rag_error_stage"] == "VECTOR_STORE"
    assert rag_outputs["rag_error_type"] == "GuidelineRetrievalError"
    assert rag_outputs["rag_error_cause_type"] == "RuntimeError"
    assert "private upstream error detail" not in repr(rag_outputs)
    assert "RAG_UNAVAILABLE" in result.safety_reason_codes


async def test_execute_records_requested_covered_and_missing_answer_sections() -> None:
    tracer = RecordingChatTracer()
    await build_use_case(
        lookup=MedicationGuideLookup(
            guide=build_guide().model_copy(
                update={"usage_instructions": ""},
            )
        ),
        tracer=tracer,
    ).execute(
        build_request("타이레놀의 효능과 복용법을 알려줘"),
    )

    outputs = next(span.outputs for span in tracer.spans if span.name == "answer.evidence_coverage")
    assert outputs == {
        "requested_section_types": ["FUNCTION", "DAILY_INTAKE"],
        "covered_section_types": ["FUNCTION"],
        "missing_section_types": ["DAILY_INTAKE"],
        "verified_interaction_pair_count": 0,
    }


async def test_execute_retries_once_for_missing_evidence_section() -> None:
    function_chunk = build_chunk().model_copy(
        update={
            "content": "마그네슘은 정상적인 근육 기능에 필요합니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_id": "magnesium-function",
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    caution_chunk = function_chunk.model_copy(
        update={
            "chunk_id": "c" * 64,
            "content": "섭취 전 개인 상태와 다른 복용 제품을 확인합니다.",
            "metadata": function_chunk.metadata.model_copy(
                update={
                    "section_type": KnowledgeSectionType.CAUTION,
                    "chunk_index": 1,
                    "content_hash": "d" * 64,
                }
            ),
        }
    )
    retriever = SequencedKnowledgeRetriever([[function_chunk], [caution_chunk]])
    tracer = RecordingChatTracer()

    result = await build_use_case(
        retriever=retriever,
        tracer=tracer,
        supplement_ingredient_catalog=StaticSupplementIngredientCatalog(["마그네슘"]),
    ).execute(build_request("마그네슘의 효능과 주의사항을 알려줘"))

    assert len(retriever.execution_plans) == 2
    assert retriever.execution_plans[1].query_plan.expanded_query == "마그네슘 주의사항 이상반응"
    assert result.evidence_coverage is not None
    assert result.evidence_coverage.missing_section_types == []
    retry_outputs = next(span.outputs for span in tracer.spans if span.name == "rag.coverage_retry")
    assert retry_outputs == {
        "attempted": True,
        "query_count": 2,
        "missing_before": ["CAUTION"],
        "missing_after": [],
        "rag_unavailable": False,
    }


async def test_execute_does_not_retry_when_initial_evidence_is_complete() -> None:
    chunk = build_chunk().model_copy(
        update={
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    retriever = SequencedKnowledgeRetriever([[chunk]])

    await build_use_case(
        retriever=retriever,
        supplement_ingredient_catalog=StaticSupplementIngredientCatalog(["마그네슘"]),
    ).execute(build_request("마그네슘은 왜 먹나요?"))

    assert len(retriever.execution_plans) == 1


async def test_execute_skips_conditional_llm_for_high_confidence_single_entity() -> None:
    chain = RecordingConditionalInterpretationChain(
        ConditionalQuestionInterpretationOutput(
            candidate_entity_keys=["candidate_0"],
            requested_section_types=[KnowledgeSectionType.CAUTION],
            confidence="HIGH",
            reason_codes=[],
        )
    )
    use_case = build_use_case(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(["타이레놀"]),
        ),
        conditional_interpretation_chain=chain,
    )

    await use_case.execute(build_request("타이레놀의 효능을 알려줘"))

    assert chain.inputs == []


async def test_execute_adds_catalog_backed_interaction_pairs_from_semantic_route() -> None:
    router = RecordingSemanticRouter(
        QuestionRoutingDecision.semantic(
            route=MedicationChatRoute.INTERACTION,
            top_score=0.91,
            second_score=0.52,
        )
    )
    retriever = RecordingQueryPlanRetriever()
    resolution = MedicationQuestionResolution(
        original_question="마그네슘과 아연 가치 먹어도 돼?",
        resolved_question="마그네슘과 아연 같이 먹어도 돼?",
        scope="IN_SCOPE",
        status="AUTO_CORRECTED",
        entity_resolution_available=True,
        entities=[
            MedicationQueryEntity(
                surface="마그네슘",
                canonical_name="마그네슘",
                entity_type="INGREDIENT_NAME",
                kind="SUPPLEMENT",
                source="RDBMS",
            ),
            MedicationQueryEntity(
                surface="아연",
                canonical_name="아연",
                entity_type="INGREDIENT_NAME",
                kind="SUPPLEMENT",
                source="RDBMS",
            ),
        ],
    )

    async def plan_with_resolved_entities(
        value: MedicationQueryPlanChainInput,
    ) -> MedicationQuestionPlanResult:
        return await build_medication_query_plan_chain().ainvoke(
            value.model_copy(update={"resolution": resolution}),
        )

    await build_use_case(
        retriever=retriever,
        query_plan_chain=RunnableLambda(plan_with_resolved_entities),
        semantic_question_router=router,
    ).execute(build_request(resolution.original_question))

    assert router.inputs == [
        SemanticRouterInput(
            question=resolution.original_question,
            candidate_count=2,
            has_session_reference=False,
        )
    ]
    assert retriever.received_kwargs is not None
    query_plan = retriever.received_kwargs["execution_plan"].query_plan
    assert query_plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert [pair.pair_type for pair in query_plan.interaction_pairs] == [
        InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    ]


async def test_execute_uses_general_guidance_for_low_risk_supplement_pair_without_direct_evidence() -> None:
    resolution = MedicationQuestionResolution(
        original_question="마그네슘과 아연을 같이 먹어도 돼?",
        resolved_question="마그네슘과 아연을 같이 먹어도 돼?",
        scope="IN_SCOPE",
        status="UNCHANGED",
        entity_resolution_available=True,
        entities=[
            MedicationQueryEntity(
                surface="마그네슘",
                canonical_name="마그네슘",
                entity_type="INGREDIENT_NAME",
                kind="SUPPLEMENT",
                source="RDBMS",
            ),
            MedicationQueryEntity(
                surface="아연",
                canonical_name="아연",
                entity_type="INGREDIENT_NAME",
                kind="SUPPLEMENT",
                source="RDBMS",
            ),
        ],
    )

    async def plan_with_resolved_entities(
        value: MedicationQueryPlanChainInput,
    ) -> MedicationQuestionPlanResult:
        return await build_medication_query_plan_chain().ainvoke(
            value.model_copy(update={"resolution": resolution}),
        )

    result = await build_use_case(
        query_plan_chain=RunnableLambda(plan_with_resolved_entities),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticTypedExpressionCatalog(
                [
                    MedicationCatalogEntry(
                        canonical_name="마그네슘",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.SUPPLEMENT,
                        source=MedicationQueryEntitySource.RDBMS,
                    ),
                    MedicationCatalogEntry(
                        canonical_name="아연",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.SUPPLEMENT,
                        source=MedicationQueryEntitySource.RDBMS,
                    ),
                ]
            )
        ),
    ).execute(build_request(resolution.original_question))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert result.safety_status == SafetyStatus.SAFE
    assert result.safety_reason_codes == ["GENERAL_SUPPLEMENT_GUIDANCE"]
    assert result.risk_decision is not None
    assert result.risk_decision.domain == MedicationChatAnswerDomain.SUPPLEMENT
    assert result.risk_decision.scope == MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE


async def test_current_medication_names_omit_parenthetical_descriptions_and_duplicates() -> None:
    use_case = build_use_case(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=10,
                    name="타이레놀정500밀리그램(아세트아미노펜)",
                ),
                ActiveMedication(
                    medication_id=2,
                    care_episode_id=10,
                    name=" 타이레놀정500밀리그램 ",
                ),
                ActiveMedication(
                    medication_id=3,
                    care_episode_id=10,
                    name="리바록사반정(항응고제)",
                ),
            ],
        )
    )

    assert await use_case.current_medication_names(
        user_id=1,
        care_episode_id=10,
    ) == ["타이레놀정500밀리그램", "리바록사반정"]


def test_answer_context_displays_only_active_medications_for_medication_and_interaction_routes() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=10,
                name="타이레놀정500밀리그램",
            )
        ],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 D",
                dose_amount="1",
                dose_unit="정",
                start_date="2026-09-01",
            )
        ],
    )
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀의 효능을 알려줘",
    )

    medication_context = AnswerMedicationQuestionUseCase._answer_context_for_route(
        context=context,
        request=request,
        route=MedicationChatRoute.MEDICATION_GUIDE,
    )
    interaction_context = AnswerMedicationQuestionUseCase._answer_context_for_route(
        context=context,
        request=request,
        route=MedicationChatRoute.INTERACTION,
    )
    general_context = AnswerMedicationQuestionUseCase._answer_context_for_route(
        context=context,
        request=request,
        route=MedicationChatRoute.GENERAL_GUIDANCE,
    )

    assert [item.name for item in medication_context.medications] == ["타이레놀정500밀리그램"]
    assert medication_context.supplements == []
    assert [item.name for item in interaction_context.medications] == ["타이레놀정500밀리그램"]
    assert interaction_context.supplements == []
    assert general_context.medications == []
    assert general_context.supplements == []


async def test_execute_discards_unknown_conditional_llm_entity_before_search() -> None:
    chain = RecordingConditionalInterpretationChain(
        ConditionalQuestionInterpretationOutput(
            candidate_entity_keys=["unknown_candidate"],
            requested_section_types=[KnowledgeSectionType.CAUTION],
            confidence="MEDIUM",
            reason_codes=["LOW_CONFIDENCE"],
        )
    )
    retriever = RecordingQueryPlanRetriever()

    await build_use_case(
        retriever=retriever,
        supplement_ingredient_catalog=StaticSupplementIngredientCatalog(["마그네슘"]),
        conditional_interpretation_chain=chain,
    ).execute(build_request("마그네슘은 왜 먹나요?"))

    assert len(chain.inputs) == 1
    assert retriever.received_kwargs is not None
    query_plan = retriever.received_kwargs["execution_plan"].query_plan
    assert query_plan.entity_names == ["마그네슘"]
    assert query_plan.section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.CAUTION,
    ]


async def test_execute_records_fallback_reason_without_answer_content() -> None:
    tracer = RecordingChatTracer()
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        answer_generator=FallbackGenerator(),
        tracer=tracer,
    ).execute(build_request("타이레놀의 주의사항을 알려줘"))

    llm_outputs = next(span.outputs for span in tracer.spans if span.name == "llm.generate")
    assert llm_outputs["rewrite_status"] == "DRAFT_FALLBACK"
    assert llm_outputs["fallback_used"] is True
    assert llm_outputs["fallback_reason"] == "UNSUPPORTED_SAFETY_ASSERTION"
    assert FallbackGenerator.generated_answer not in repr(llm_outputs)
    assert result.answer not in repr(llm_outputs)


async def test_execute_records_provider_failure_reason_and_reraises() -> None:
    tracer = RecordingChatTracer()
    use_case = build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        answer_generator=FailingMedicationGenerator(),
        tracer=tracer,
    )

    with pytest.raises(ChatAnswerGenerationError):
        await use_case.execute(build_request("타이레놀의 주의사항을 알려줘"))

    llm_outputs = next(span.outputs for span in tracer.spans if span.name == "llm.generate")
    assert llm_outputs == {
        "rewrite_status": "FAILED",
        "fallback_used": False,
        "fallback_reason": "CLIENT_ERROR",
        "route": "MEDICATION_GUIDE",
        "source_count": 1,
    }


async def test_execute_records_losartan_search_diagnostics_in_content_mode() -> None:
    tracer = RecordingChatTracer(capture_content=True)
    chunk = build_losartan_chunk()
    use_case = build_use_case(
        retriever=FakeKnowledgeRetriever(
            chunks=[chunk],
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=1,
                entity_filtered_count=1,
                broad_candidate_count=0,
                eligible_candidate_count=1,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=1,
                candidate_diagnostics=[
                    KnowledgeCandidateDiagnostic(
                        document_id=chunk.metadata.document_id,
                        chunk_id=chunk.chunk_id,
                        search_tier=KnowledgeSearchTier.ENTITY,
                        raw_rank=1,
                        raw_similarity_score=chunk.similarity_score,
                        boost_score=0.2,
                        adjusted_score=1.02,
                        adjusted_rank=1,
                        entity_matched=True,
                        section_matched=True,
                        eligible=True,
                        selected_in_top_5=True,
                    )
                ],
            ),
        ),
        tracer=tracer,
    )

    await use_case.execute(
        build_request("로사르탄의 주의사항을 알려줘"),
    )

    assert tracer.spans[1].outputs["entity_names"] == ["로사르탄"]
    assert tracer.spans[4].outputs["document_types"] == [
        "DRUG_ENCYCLOPEDIA",
    ]
    assert tracer.spans[4].outputs["drug_encyclopedia_evidence_count"] == 1
    assert tracer.spans[4].outputs["candidate_diagnostics"][0]["document_id"] == chunk.metadata.document_id


async def test_execute_records_selected_and_candidate_entity_roles() -> None:
    tracer = RecordingChatTracer(capture_content=True)
    await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            representative_guide=build_guide(),
            candidate_names=[
                "타이레놀정500밀리그람",
                "타이레놀8시간이알서방정",
            ],
        ),
        tracer=tracer,
    ).execute(
        build_request("타이레놀의 효능과 주의사항을 알려줘."),
    )

    query_outputs = tracer.spans[1].outputs
    assert query_outputs["entity_names"] == ["타이레놀"]
    assert query_outputs["entity_roles"] == ["BRAND_ALIAS"]
    assert query_outputs["entity_source_counts"] == {"ALIAS": 1}
    assert query_outputs["entity_type_counts"] == {"BRAND_ALIAS": 1}
    assert query_outputs["interaction_pair_types"] == []
    assert query_outputs["legacy_entity_inference_used"] is True
    assert query_outputs["entity_role_candidates"] == [
        ["PRODUCT_NAME", "BRAND_ALIAS", "INGREDIENT_NAME"],
    ]


async def test_execute_compacts_answer_before_final_safety_validation() -> None:
    disclaimer = "이 안내는 의료진의 진료를 대체하지 않습니다."
    evidence_sentence = ("가" * 190) + " 문장 끝입니다.\n"
    validator = RecordingValidator()
    use_case = build_use_case(
        answer_generator=LongAnswerGenerator("핵심 문장입니다.\n" + (evidence_sentence * 30) + f"\n{disclaimer}"),
        grounded_claim_validator=validator,
    )

    result = await use_case.execute(
        build_request("마그네슘은 왜 먹나요?"),
    )

    assert validator.received is not None
    assert result.answer == validator.received.answer
    assert len(result.answer) <= 2000
    visible_head = result.answer.split("[긴 답변 축약]", maxsplit=1)[0].rstrip()
    assert visible_head.endswith("문장 끝입니다.")
    assert result.answer.endswith(disclaimer)


async def test_confirmed_medication_precedes_general_guide_and_rag() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="타이레놀정500밀리그람",
                dose="1정",
                times_per_day=3,
                days=3,
                prescribed_at=date(2026, 8, 25),
            )
        ],
    )
    background_chunk = build_chunk().model_copy(
        update={
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "section_type": KnowledgeSectionType.OVERVIEW,
                }
            )
        }
    )
    result = await build_use_case(
        context=context,
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[background_chunk]),
    ).execute(
        build_request(
            "이 약을 어떻게 먹어야 하나요?",
            care_episode_id=100,
        )
    )

    assert result.answer.index("복약정보") < result.answer.index("일반 제품 안내")
    assert result.answer.index("일반 제품 안내") < result.answer.index("공공자료 추가 설명")


async def test_no_interaction_evidence_never_claims_safe() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="아스피린",
            )
        ],
    )
    result = await build_use_case(context=context).execute(
        build_request("아스피린과 오메가3를 같이 먹어도 괜찮나요?"),
    )

    assert result.route == MedicationChatRoute.INTERACTION
    assert "안전합니다" not in result.answer
    assert "확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다" in result.answer


async def test_qdrant_failure_falls_back_to_rdbms_facts() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        preferred_care_episode_id=100,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="타이레놀정500밀리그람",
                dose="1정",
            )
        ],
    )
    result = await build_use_case(
        context=context,
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(error=RuntimeError("qdrant down")),
    ).execute(
        build_request("타이레놀정500밀리그람 주의사항을 알려줘", care_episode_id=100),
    )

    assert "복약정보" in result.answer
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "RAG_UNAVAILABLE" in result.safety_reason_codes


async def test_ambiguous_medication_name_requests_clarification() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            candidate_names=[
                "타이레놀정500밀리그람",
                "타이레놀8시간이알서방정",
            ],
        ),
    ).execute(build_request("타이레놀은 한 번에 몇 정 먹나요?"))

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert "제품명을 확인" in result.answer


async def test_vitamin_b_family_daily_intake_requests_specific_member() -> None:
    result = await build_use_case().execute(
        build_request("비타민 B는 하루에 얼마나 먹어야 하나요?"),
    )

    assert result.route == MedicationChatRoute.CLARIFICATION
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "비타민 B는 여러 성분을 묶어 부르는 이름" in result.answer
    assert "비타민 B1(티아민)" in result.answer
    assert "비타민 B12(코발라민)" in result.answer
    assert "INGREDIENT_FAMILY_DETAIL_REQUIRED" in result.safety_reason_codes


async def test_general_brand_name_uses_reference_efficacy_without_guessing_dose() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            representative_guide=build_guide(),
            candidate_names=[
                "타이레놀정500밀리그람",
                "타이레놀8시간이알서방정",
            ],
        ),
    ).execute(
        build_request(
            "타이레놀의 효능과 복용 시 주의사항을 알려줘.",
        )
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer
    assert "제품별 성분·함량·제형" in result.answer
    assert "제품 설명서와 전문가의 안내를 따릅니다" not in result.answer


async def test_general_brand_name_removes_possessive_particle_before_lookup() -> None:
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(
            ActiveIntakeContext(user_id=1),
        ),
        guide_repository=ExactNameGuideRepository(
            expected_name="타이레놀",
            lookup=MedicationGuideLookup(
                is_ambiguous=True,
                representative_guide=build_guide(),
                candidate_names=[
                    "타이레놀정500밀리그람",
                    "타이레놀8시간이알서방정",
                ],
            ),
        ),
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )

    result = await use_case.execute(
        build_request(
            "타이레놀의 효능과 복용 시 주의사항을 알려줘.",
        )
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer


async def test_guide_lookup_uses_only_normalized_drug_entity() -> None:
    guide_repository = RecordingGuideRepository()
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(
            ActiveIntakeContext(user_id=1),
        ),
        guide_repository=guide_repository,
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )

    await use_case.execute(
        build_request(
            "내가 복용 중인 로사르탄의 복용법과 주의사항을 알려줘.",
        )
    )

    assert guide_repository.requested_names == ["로사르탄"]


async def test_supplement_evidence_prevents_partial_drug_name_clarification() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            )
        }
    )
    result = await build_use_case(
        lookup=MedicationGuideLookup(
            is_ambiguous=True,
            candidate_names=["마그밀정", "산화마그네슘정"],
        ),
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
    ).execute(build_request("마그네슘은 왜 먹어?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "제품명을 확인" not in result.answer
    assert "공공자료 추가 설명" in result.answer


async def test_general_supplement_question_hides_unrelated_active_intakes_from_answer_and_sources() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": "마그네슘은 에너지 이용과 신경·근육 기능 유지에 필요합니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="타이레놀정500밀리그람",
            )
        ],
        supplements=[
            ActiveSupplement(
                registration_id=20,
                supplement_nutrient_id=30,
                name="오메가3",
                dose_amount="1",
                dose_unit="캡슐",
                start_date=date(2026, 9, 1),
            )
        ],
    )

    generator = ContextRecordingGenerator()
    result = await build_use_case(
        context=context,
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
        answer_generator=generator,
    ).execute(build_request("마그네슘은 왜 먹나요?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "사용자 확정 복약정보" not in result.answer
    assert "타이레놀정500밀리그람" not in result.answer
    assert "오메가3" not in result.answer
    assert all(source.kind.value not in {"PATIENT_MEDICATION", "PATIENT_SUPPLEMENT"} for source in result.sources)
    assert generator.context is not None
    assert generator.context.medications == []
    assert generator.context.supplements == []


async def test_vitamin_b_family_function_answer_includes_member_choices() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": "비타민 B군은 여러 수용성 비타민으로 구성됩니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": (KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE),
                    "ingredient_names": ["비타민 B1"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticExpressionCatalog(
                ["비타민 B1", "비타민 B2", "비타민 B12"],
            ),
        ),
    ).execute(build_request("비타민 B는 왜 먹나요?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "비타민 B군은 여러 수용성 비타민" in result.answer
    assert "비타민 B는 여러 성분을 묶어 부르는 이름" in result.answer
    assert "비타민 B1(티아민)" in result.answer
    assert "비타민 B12(코발라민)" in result.answer


async def test_supplement_evidence_precedes_single_partial_medication_match() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": ("마그네슘은 에너지 이용과 신경·근육 기능 유지에 필요합니다."),
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
    ).execute(build_request("마그네슘은 왜 먹어?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "에너지 이용" in result.answer
    assert "일반 제품 안내" not in result.answer
    assert all(source.medication_guide_id is None for source in result.sources)


async def test_supplement_function_route_ignores_co_retrieved_drug_encyclopedia() -> None:
    supplement_chunk = build_chunk().model_copy(
        update={
            "content": "마그네슘은 에너지 이용과 신경·근육 기능 유지에 필요합니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            ),
        }
    )
    medication_chunk = build_losartan_chunk(
        section_type=KnowledgeSectionType.FUNCTION,
        content="산화마그네슘 의약품은 제품별 허가사항을 확인합니다.",
    ).model_copy(
        update={
            "metadata": build_losartan_chunk().metadata.model_copy(
                update={
                    "title": "산화마그네슘",
                    "drug_names": ["산화마그네슘"],
                    "section_type": KnowledgeSectionType.FUNCTION,
                }
            )
        }
    )

    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(
            chunks=[medication_chunk, supplement_chunk],
        ),
    ).execute(build_request("마그네슘은 왜 먹어?"))

    assert result.route == MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "에너지 이용" in result.answer
    assert "산화마그네슘 의약품" not in result.answer


async def test_supplement_pair_question_skips_medication_product_lookup() -> None:
    interaction_chunk = build_chunk().model_copy(
        update={
            "content": ("Supplemental zinc lowered measures of iron status in young women with low iron reserves."),
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "title": "Supplemental Zinc Lowers Measures of Iron Status",
                    "document_type": KnowledgeDocumentType.RESEARCH_ARTICLE,
                    "ingredient_names": ["아연", "철분"],
                    "section_type": KnowledgeSectionType.SUMMARY,
                }
            ),
        }
    )
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(ActiveIntakeContext(user_id=1)),
        guide_repository=UnexpectedGuideRepository(),
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(chunks=[interaction_chunk]),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
    )

    result = await use_case.execute(
        build_request("철분이 부족한 사람이 아연 영양제를 먹어도 되나요?"),
    )

    assert result.route == MedicationChatRoute.INTERACTION
    assert "검색된 상호작용 연구 근거" in result.answer
    assert "제품명을 확인" not in result.answer


async def test_product_name_drug_food_question_uses_official_guide_with_supplementary_rag_evidence() -> None:
    interaction_chunk = build_chunk().model_copy(
        update={
            "content": "아세트아미노펜 복용 중 알코올 섭취는 주의가 필요합니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
                    "drug_names": ["아세트아미노펜"],
                    "food_names": ["알코올"],
                    "interaction_type": InteractionPairType.DRUG_FOOD.value,
                    "section_type": KnowledgeSectionType.INTERACTION,
                }
            ),
        }
    )
    guide_repository = RecordingGuideRepository(
        MedicationGuideLookup(guide=build_guide()),
    )
    question_resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="타이레놀정500밀리그람(아세트아미노펜)",
                    aliases=["타이레놀"],
                    entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
                MedicationCatalogEntry(
                    canonical_name="아세트아미노펜",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
                MedicationCatalogEntry(
                    canonical_name="알코올",
                    aliases=["술"],
                    entity_type=MedicationQueryEntityType.FOOD_CATEGORY,
                    kind=InteractionEntityKind.FOOD,
                    source=MedicationQueryEntitySource.QDRANT,
                ),
            ]
        ),
    )
    result = await AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(ActiveIntakeContext(user_id=1)),
        guide_repository=guide_repository,
        interaction_rule_repository=FakeRuleRepository([]),
        knowledge_retriever=FakeKnowledgeRetriever(chunks=[interaction_chunk]),
        answer_generator=PassthroughGenerator(),
        grounded_claim_validator=PassthroughValidator(),
        question_resolver=question_resolver,
    ).execute(
        build_request("타이레놀과 술을 같이 먹어도 돼?"),
    )

    assert guide_repository.requested_names == ["타이레놀정500밀리그람(아세트아미노펜)"]
    assert {source.kind for source in result.sources} == {
        MedicationChatSourceKind.MEDICATION_GUIDE,
        MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
    }


async def test_multi_entity_answer_uses_generic_notice_for_unverified_pairs() -> None:
    calcium_iron_chunk = build_chunk().model_copy(
        update={
            "content": "칼슘은 한 끼 식사에서 철 흡수에 영향을 줄 수 있습니다.",
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "title": "Calcium and Iron Absorption",
                    "document_type": KnowledgeDocumentType.RESEARCH_ARTICLE,
                    "ingredient_names": ["칼슘", "철분"],
                    "section_type": KnowledgeSectionType.SUMMARY,
                }
            ),
        }
    )

    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(chunks=[calcium_iron_chunk]),
    ).execute(
        build_request(
            "와파린, 비타민 K, 칼슘, 철분의 상호작용을 우선순위로 요약해줘.",
        )
    )

    assert result.route == MedicationChatRoute.INTERACTION
    assert "검색된 상호작용 연구 근거" in result.answer
    assert "☑️ **확인하지 못한 조합**" in result.answer
    assert "🔁 **확인된 상호작용**" not in result.answer
    assert "와파린 ↔ 비타민 K" not in result.answer
    assert "칼슘 ↔ 철분" not in result.answer


async def test_unknown_risk_does_not_restrict_general_omega3_intake_guidance() -> None:
    validator = RecordingValidator()
    supplement_chunk = build_chunk().model_copy(
        update={
            "metadata": build_chunk().metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.SUPPLEMENT_CODE,
                    "ingredient_names": ["오메가3"],
                    "section_type": KnowledgeSectionType.DAILY_INTAKE,
                }
            ),
        }
    )
    request = build_request("오메가3를 하루에 얼마나 먹어야 하나요?").model_copy(
        update={"risk_profile": MedicationChatRiskProfile()}
    )

    result = await build_use_case(
        retriever=FakeKnowledgeRetriever(chunks=[supplement_chunk]),
        grounded_claim_validator=validator,
    ).execute(request)

    assert result.risk_decision is not None
    assert result.risk_decision.scope == MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE
    assert result.safety_status == SafetyStatus.SAFE
    assert "PREGNANCY_STATUS_UNKNOWN" not in result.safety_reason_codes
    assert validator.received is not None
    assert validator.received.risk_decision == result.risk_decision
    assert "임신·수유" not in validator.received.answer


def test_product_name_candidates_are_bounded_for_long_questions() -> None:
    question = " ".join(f"후보{index}" for index in range(100))
    candidates = AnswerMedicationQuestionUseCase._product_name_candidates(
        question,
        context=ActiveIntakeContext(user_id=1),
        query_plan=MedicationKnowledgeQueryBuilder().build(question),
    )

    assert len(candidates) <= 12


def test_this_medicine_does_not_choose_between_multiple_active_medications() -> None:
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=1,
                care_episode_id=100,
                name="아스피린",
            ),
            ActiveMedication(
                medication_id=2,
                care_episode_id=100,
                name="타이레놀",
            ),
        ],
    )

    candidates = AnswerMedicationQuestionUseCase._product_name_candidates(
        "이 약은 어떻게 먹어?",
        context=context,
        query_plan=MedicationKnowledgeQueryBuilder().build(
            "이 약은 어떻게 먹어?",
        ),
    )

    assert "아스피린" not in candidates
    assert "타이레놀" not in candidates


def test_avoidance_question_uses_interaction_route_without_assuming_pair_type() -> None:
    questions = [
        "펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
        "케토롤락 복용 중 아스피린을 피해야 하나요?",
        "와파린 복용 중 비타민 K를 피해야 하나요?",
        "마그네슘 복용 중 아연을 피해야 하나요?",
    ]

    assert all(AnswerMedicationQuestionUseCase._is_interaction_question(question) for question in questions)


def test_single_drug_contraindication_does_not_use_interaction_route() -> None:
    assert not AnswerMedicationQuestionUseCase._is_interaction_question(
        "아스피린은 임신 중 피해야 하나요?",
    )
