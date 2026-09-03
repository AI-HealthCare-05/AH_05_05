import hashlib
from contextlib import asynccontextmanager
from datetime import date

import pytest

from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.enums import SafetyStatus
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
    InteractionRuleFact,
    MedicationAnswerFallbackReason,
    MedicationAnswerGenerationObservation,
    MedicationAnswerGenerationOutcome,
    MedicationAnswerRewriteStatus,
    MedicationChatProgressStage,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationGuideFact,
    MedicationGuideLookup,
)
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
    def __init__(self) -> None:
        self.requested_names: list[str] = []

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        self.requested_names.append(product_name)
        return MedicationGuideLookup()


class UnexpectedGuideRepository:
    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        raise AssertionError(f"영양제 상호작용 질문에서 의약품 제품 조회를 호출했습니다: {product_name}")


class StaticExpressionCatalog:
    def __init__(self, expressions: list[str]) -> None:
        self.expressions = expressions

    async def list_expressions(self) -> list[str]:
        return self.expressions


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


class PassthroughValidator:
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
) -> AnswerMedicationQuestionUseCase:
    return AnswerMedicationQuestionUseCase(
        context_provider=FakeContextProvider(context or ActiveIntakeContext(user_id=1)),
        guide_repository=FakeGuideRepository(lookup or MedicationGuideLookup()),
        interaction_rule_repository=(rule_repository or FakeRuleRepository(rules or [])),
        knowledge_retriever=retriever or FakeKnowledgeRetriever(),
        answer_generator=answer_generator or PassthroughGenerator(),
        grounded_claim_validator=(grounded_claim_validator or PassthroughValidator()),
        tracer=tracer,
        question_resolver=question_resolver,
    )


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
    assert "현재 보유한 승인 규칙과 검색 자료에서는" in result.answer
    assert "안전하다는 의미가 아닙니다" in result.answer


async def test_general_drug_question_runs_without_episode() -> None:
    result = await build_use_case(
        lookup=MedicationGuideLookup(guide=build_guide()),
    ).execute(
        build_request("타이레놀정500밀리그람은 어떤 약인가요?"),
    )

    assert result.route == MedicationChatRoute.MEDICATION_GUIDE
    assert "통증과 발열을 완화합니다" in result.answer
    assert "성분을 확인합니다" in result.answer
    assert "다른 약 복용 시 전문가에게 알립니다" in result.answer


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
        "interaction_rules.search",
        "rag.retrieve",
        "medication_guide.lookup",
        "answer.draft",
        "llm.generate",
        "safety.validate",
    ]
    serialized_outputs = repr(
        [span.outputs for span in tracer.spans],
    )
    assert "타이레놀정500밀리그람" not in serialized_outputs
    assert build_chunk().content not in serialized_outputs
    rag_outputs = tracer.spans[3].outputs
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
    assert len(llm_outputs["draft_answer_hash"]) == 64
    assert len(llm_outputs["generated_answer_hash"]) == 64


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
    assert tracer.spans[3].outputs["document_types"] == [
        "DRUG_ENCYCLOPEDIA",
    ]
    assert tracer.spans[3].outputs["drug_encyclopedia_evidence_count"] == 1
    assert tracer.spans[3].outputs["candidate_diagnostics"][0]["document_id"] == chunk.metadata.document_id


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

    assert result.answer.index("사용자 확정 복약정보") < result.answer.index("일반 제품 안내")
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

    assert "사용자 확정 복약정보" in result.answer
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


async def test_multi_entity_answer_separates_supported_and_unverified_pairs() -> None:
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
    assert "근거를 확인하지 못한 조합" in result.answer
    assert "와파린 ↔ 비타민 K" in result.answer
    assert (
        "칼슘 ↔ 철분"
        not in result.answer.split(
            "근거를 확인하지 못한 조합",
            maxsplit=1,
        )[1]
    )


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
