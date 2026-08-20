from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.llm.generators.chat_question_classifier import (
    ChatClassificationError,
)
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
from ai_worker.rag.query_builders.chat_query_builder import (
    ChatQueryBuilder,
)
from ai_worker.safety.chat_input_risk_classifier import (
    RuleBasedChatInputRiskClassifier,
)
from ai_worker.safety.chat_output_safety_validator import (
    RuleBasedChatOutputSafetyValidator,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatAnswerResult,
    ChatClassificationResult,
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientMedication,
)
from ai_worker.schemas.safety import SafetyResult
from ai_worker.use_cases.answer_chat_message import (
    AnswerChatMessageUseCase,
)


class FakePatientContextProvider:
    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        return PatientContext(
            user_id=user_id,
            care_episode_id=care_episode_id,
            confirmation_hash="a" * 64,
            diagnoses=["뇌졸중"],
        )


class LowRiskClassifier:
    def assess(
        self,
        question: str,
    ) -> ChatInputRiskResult:
        return ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        )


class PatientOnlyQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        return ChatClassificationResult(
            intent=ChatIntent.PATIENT_FACT,
            route=ChatRoute.PATIENT_ONLY,
            risk_level=ChatRiskLevel.LOW,
        )


class UnexpectedGuidelineRetriever:
    async def search(
        self,
        search_query: object,
    ) -> list[object]:
        raise AssertionError("PATIENT_ONLY에서는 Qdrant를 호출하면 안 됩니다.")


class PatientOnlyAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[object],
    ) -> ChatAnswerResult:
        if guideline_chunks:
            raise AssertionError("PATIENT_ONLY에는 공공자료 청크를 전달하면 안 됩니다.")

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=(patient_context.care_episode_id),
            answer=("환자 확정정보\n- 진단명: 뇌졸중\n\n이 안내는 의료진의 진료를 대체하지 않습니다."),
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash="a" * 64,
            model_name="gpt-4o-mini",
            prompt_version=("chat-answer-prompt-v1"),
            schema_version=("chat-answer-result-v1"),
        )


class SafeChatOutputValidator:
    async def validate(
        self,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> SafetyResult:
        return SafetyResult(
            status=SafetyStatus.SAFE,
        )


def build_request() -> ChatAnswerRequest:
    return ChatAnswerRequest(
        request_id="chat-request-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        question="내 진단명은 무엇이야?",
    )


async def test_execute_patient_only_does_not_search_qdrant() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(FakePatientContextProvider()),
        input_risk_classifier=(LowRiskClassifier()),
        question_classifier=(PatientOnlyQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=(UnexpectedGuidelineRetriever()),
        answer_generator=(UnexpectedAnswerGenerator()),
        safety_validator=(SafeChatOutputValidator()),
    )

    result = await use_case.execute(
        request=build_request(),
    )

    assert result.route == ChatRoute.PATIENT_ONLY
    assert result.safety_status == SafetyStatus.SAFE
    assert "진단명: 뇌졸중" in result.answer
    assert result.model_name == "rule-based-patient-only"
    assert result.schema_version == "chat-answer-result-v2"
    assert len(result.sources) == 1
    assert result.sources[0].patient_field is not None


class ClarificationQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        return ChatClassificationResult(
            intent=ChatIntent.GENERAL,
            risk_level=ChatRiskLevel.CAUTION,
            needs_clarification=True,
            reason_codes=["AMBIGUOUS_QUESTION"],
        )


async def test_execute_clarification_skips_rag_and_answer_llm() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=FakePatientContextProvider(),
        input_risk_classifier=LowRiskClassifier(),
        question_classifier=ClarificationQuestionClassifier(),
        query_builder=ChatQueryBuilder(),
        retriever=UnexpectedGuidelineRetriever(),
        answer_generator=UnexpectedAnswerGenerator(),
        safety_validator=UnexpectedChatSafetyValidator(),
    )

    result = await use_case.execute(request=build_request())

    assert result.needs_clarification is True
    assert result.route is None
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "질문을 조금 더 구체적으로" in result.answer
    assert "AMBIGUOUS_QUESTION" in result.safety_reason_codes
    assert result.sources == []


class RagQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        return ChatClassificationResult(
            intent=ChatIntent.LIFESTYLE,
            route=ChatRoute.PATIENT_AND_RAG,
            risk_level=ChatRiskLevel.CAUTION,
            normalized_query=("뇌졸중 퇴원 후 안전한 운동"),
        )


class ValidatingGuidelineRetriever:
    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        if search_query.query != ("뇌졸중 퇴원 후 안전한 운동"):
            raise AssertionError("분류된 normalized_query가 검색에 사용되어야 합니다.")

        if search_query.condition != "STROKE":
            raise AssertionError("검증된 condition이 검색 필터로 사용되어야 합니다.")

        if search_query.topic != "LIFESTYLE":
            raise AssertionError("LIFESTYLE intent가 검색 topic으로 변환되어야 합니다.")

        if search_query.limit != 3:
            raise AssertionError("UseCase의 검색 limit이 전달되어야 합니다.")

        return [
            RetrievedGuidelineChunk(
                vector_chunk_id="chunk-1",
                content=("퇴원 후에는 가벼운 활동부터 점진적으로 시작할 수 있습니다."),
                similarity_score=0.91,
                metadata=GuidelineMetadata(
                    dataset_key=("PUBLIC_GUIDELINE"),
                    dataset_version="2020-v1",
                    document_id=("canadian-stroke-2020"),
                    title=("Canadian Stroke Guideline"),
                    organization=("Heart and Stroke Foundation"),
                    condition="STROKE",
                    care_phase="POST_DISCHARGE",
                    topic="LIFESTYLE",
                ),
            )
        ]


class RagAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        chunk_ids = [chunk.vector_chunk_id for chunk in guideline_chunks]

        if chunk_ids != ["chunk-1"]:
            raise AssertionError("Qdrant 검색 결과가 답변 Generator에 전달되어야 합니다.")

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=(patient_context.care_episode_id),
            answer=(
                "공공자료 추가 설명\n"
                "- 가벼운 활동부터 시작할 수 있습니다.\n\n"
                "이 안내는 의료진의 진료를 "
                "대체하지 않습니다."
            ),
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash="a" * 64,
            model_name="gpt-4o-mini",
            prompt_version=("chat-answer-prompt-v1"),
            schema_version=("chat-answer-result-v1"),
        )


async def test_execute_patient_and_rag_searches_qdrant() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(FakePatientContextProvider()),
        input_risk_classifier=(LowRiskClassifier()),
        question_classifier=(RagQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=(ValidatingGuidelineRetriever()),
        answer_generator=(RagAnswerGenerator()),
        safety_validator=(SafeChatOutputValidator()),
    )

    result = await use_case.execute(
        request=build_request(),
        limit=3,
    )

    assert result.route == ChatRoute.PATIENT_AND_RAG
    assert result.safety_status == SafetyStatus.SAFE
    assert "가벼운 활동부터 시작할 수 있습니다." in result.answer


class FailingGuidelineRetriever:
    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        raise GuidelineRetrievalError(
            stage=RetrievalFailureStage.VECTOR_STORE,
            message="Qdrant 검색 실패",
        )


async def test_execute_falls_back_to_confirmed_data_when_rag_fails() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=FakePatientContextProvider(),
        input_risk_classifier=LowRiskClassifier(),
        question_classifier=RagQuestionClassifier(),
        query_builder=ChatQueryBuilder(),
        retriever=FailingGuidelineRetriever(),
        answer_generator=UnexpectedAnswerGenerator(),
        safety_validator=UnexpectedChatSafetyValidator(),
    )

    result = await use_case.execute(request=build_request())

    assert result.route == ChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "GUIDELINE_RETRIEVAL_FAILED" in result.safety_reason_codes
    assert "확정된 정보만" in result.answer
    assert result.sources == []


class FailingAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        raise ChatAnswerGenerationError("OpenAI 답변 생성 실패")


async def test_execute_falls_back_to_confirmed_data_when_answer_llm_fails() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=FakePatientContextProvider(),
        input_risk_classifier=LowRiskClassifier(),
        question_classifier=RagQuestionClassifier(),
        query_builder=ChatQueryBuilder(),
        retriever=ValidatingGuidelineRetriever(),
        answer_generator=FailingAnswerGenerator(),
        safety_validator=UnexpectedChatSafetyValidator(),
    )

    result = await use_case.execute(request=build_request(), limit=3)

    assert result.route == ChatRoute.RESTRICTED
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "CHAT_ANSWER_GENERATION_FAILED" in result.safety_reason_codes
    assert "확정된 정보만" in result.answer


class ConfirmedMedicationPatientContextProvider:
    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        return PatientContext(
            user_id=user_id,
            care_episode_id=care_episode_id,
            confirmation_hash="a" * 64,
            diagnoses=["뇌졸중"],
            medications=[
                PatientMedication(
                    medication_id=101,
                    name="아스피린",
                    dose="1정",
                    times_per_day=1,
                    note="아침 식후 복용",
                    days=7,
                )
            ],
        )


class RestrictedQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        if minimum_risk.risk_level != ChatRiskLevel.HIGH:
            raise AssertionError("복약 변경 질문은 규칙 검사에서 HIGH여야 합니다.")

        return ChatClassificationResult(
            intent=ChatIntent.MEDICATION,
            route=ChatRoute.RESTRICTED,
            risk_level=ChatRiskLevel.HIGH,
            reason_codes=list(minimum_risk.reason_codes),
        )


class UnexpectedAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        raise AssertionError("RESTRICTED에서는 답변 LLM을 호출하면 안 됩니다.")


class UnexpectedChatSafetyValidator:
    async def validate(
        self,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> SafetyResult:
        raise AssertionError("RESTRICTED 단축 응답에는 생성 결과 안전성 검사를 호출하면 안 됩니다.")


async def test_execute_restricted_skips_rag_and_answer_llm() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(ConfirmedMedicationPatientContextProvider()),
        input_risk_classifier=(RuleBasedChatInputRiskClassifier()),
        question_classifier=(RestrictedQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=(UnexpectedGuidelineRetriever()),
        answer_generator=(UnexpectedAnswerGenerator()),
        safety_validator=(UnexpectedChatSafetyValidator()),
    )

    result = await use_case.execute(
        request=ChatAnswerRequest(
            request_id="restricted-request-1",
            user_id=1,
            care_episode_id=100,
            condition="STROKE",
            question=("아스피린 복용을 중단해도 돼?"),
        )
    )

    assert result.route == ChatRoute.RESTRICTED
    assert result.risk_level == ChatRiskLevel.HIGH
    assert result.safety_status == SafetyStatus.RESTRICTED

    assert ("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일") in result.answer
    assert "확정된 정보만" in result.answer
    assert "MEDICATION_CHANGE_REQUEST" in (result.safety_reason_codes)

    assert len(result.sources) == 1

    source = result.sources[0]

    assert source.source_type == (SourceType.PATIENT_SAVED_FIELD)
    assert source.patient_source_kind == (PatientSourceKind.MEDICATION)
    assert source.medication_id == 101


class FailingQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        raise ChatClassificationError("OpenAI 질문 분류 호출 실패")


async def test_execute_converts_classification_failure_to_restricted() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(FakePatientContextProvider()),
        input_risk_classifier=(LowRiskClassifier()),
        question_classifier=(FailingQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=(UnexpectedGuidelineRetriever()),
        answer_generator=(UnexpectedAnswerGenerator()),
        safety_validator=(UnexpectedChatSafetyValidator()),
    )

    result = await use_case.execute(
        request=build_request(),
    )

    assert result.route == ChatRoute.RESTRICTED
    assert result.intent == ChatIntent.GENERAL
    assert result.risk_level == ChatRiskLevel.CAUTION
    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "CHAT_CLASSIFICATION_FAILED" in result.safety_reason_codes
    assert "확정된 정보만" in result.answer
    assert result.sources == []


class UnsafeAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=(patient_context.care_episode_id),
            answer=("오늘부터 아스피린 복용을 중단하세요.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."),
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash="a" * 64,
            model_name="gpt-4o-mini",
            prompt_version=("chat-answer-prompt-v1"),
            schema_version=("chat-answer-result-v1"),
        )


class BlockedChatSafetyValidator:
    async def validate(
        self,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> SafetyResult:
        return SafetyResult(
            status=SafetyStatus.BLOCKED,
            reason_codes=[("MEDICATION_CHANGE_INSTRUCTION")],
        )


async def test_execute_replaces_blocked_answer_with_safe_notice() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(FakePatientContextProvider()),
        input_risk_classifier=(LowRiskClassifier()),
        question_classifier=(PatientOnlyQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=(UnexpectedGuidelineRetriever()),
        answer_generator=(UnsafeAnswerGenerator()),
        safety_validator=(BlockedChatSafetyValidator()),
    )

    result = await use_case.execute(
        request=build_request(),
    )

    assert result.safety_status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in result.safety_reason_codes

    assert "중단하세요" not in result.answer
    assert "안전성 검사를 통과하지 못해" in result.answer
    assert "의료진 또는 의료기관에 문의하세요" in result.answer
    assert result.sources == []


class MedicationPatientOnlyQuestionClassifier:
    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        return ChatClassificationResult(
            intent=ChatIntent.MEDICATION,
            route=ChatRoute.PATIENT_ONLY,
            risk_level=ChatRiskLevel.LOW,
        )


class SupplementalMedicationAnswerGenerator:
    async def generate(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        guideline_chunks: list[RetrievedGuidelineChunk],
    ) -> ChatAnswerResult:
        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=patient_context.care_episode_id,
            answer=("환자 확정정보\n- 아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일\n\nLLM이 만든 추가 복약 설명"),
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash="a" * 64,
            model_name="gpt-4o-mini",
            prompt_version="chat-answer-prompt-v1",
            schema_version="chat-answer-result-v1",
        )


async def test_execute_patient_only_returns_confirmed_medication_without_llm() -> None:
    use_case = AnswerChatMessageUseCase(
        patient_context_provider=(ConfirmedMedicationPatientContextProvider()),
        input_risk_classifier=LowRiskClassifier(),
        question_classifier=(MedicationPatientOnlyQuestionClassifier()),
        query_builder=ChatQueryBuilder(),
        retriever=UnexpectedGuidelineRetriever(),
        answer_generator=UnexpectedAnswerGenerator(),
        safety_validator=(RuleBasedChatOutputSafetyValidator()),
    )

    result = await use_case.execute(
        request=ChatAnswerRequest(
            request_id="restricted-output-request-1",
            user_id=1,
            care_episode_id=100,
            condition="STROKE",
            question="아스피린은 언제 먹어?",
        )
    )

    assert result.route == ChatRoute.PATIENT_ONLY
    assert result.safety_status == SafetyStatus.SAFE

    assert ("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일") in result.answer
    assert "LLM이 만든 추가 복약 설명" not in result.answer

    assert len(result.sources) == 1
    assert result.sources[0].medication_id == 101
