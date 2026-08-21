from ai_worker.domain.chat_source_builder import ChatSourceBuilder
from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.domain.interfaces import (
    ChatAnswerGenerator,
    ChatInputRiskClassifier,
    ChatOutputSafetyValidator,
    ChatQuestionClassifier,
    GuidelineRetriever,
    PatientContextProvider,
)
from ai_worker.domain.patient_context_hasher import (
    resolve_patient_context_hash,
)
from ai_worker.llm.assemblers.chat_answer_assembler import (
    ChatAnswerAssembler,
)
from ai_worker.llm.generators.chat_question_classifier import (
    ChatClassificationError,
)
from ai_worker.rag.errors import GuidelineRetrievalError
from ai_worker.rag.query_builders.chat_query_builder import (
    ChatQueryBuilder,
)
from ai_worker.schemas.chat import (
    CHAT_ANSWER_SCHEMA_VERSION,
    ChatAnswerRequest,
    ChatAnswerResult,
    ChatAnswerSupplement,
    ChatClassificationResult,
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    SafetyStatus,
)
from ai_worker.schemas.guide import GuideSource
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import SafetyResult


class AnswerChatMessageUseCase:
    RESTRICTED_MODEL_NAME = "rule-based-restricted"
    RESTRICTED_PROMPT_VERSION = "chat-restricted-v1"
    PATIENT_ONLY_MODEL_NAME = "rule-based-patient-only"
    PATIENT_ONLY_PROMPT_VERSION = "chat-patient-only-v1"
    CLARIFICATION_MODEL_NAME = "rule-based-clarification"
    CLARIFICATION_PROMPT_VERSION = "chat-clarification-v1"

    RESTRICTED_NOTICE = (
        "요청하신 내용은 의료적 판단 또는 복약 변경에 해당할 수 있어 사용자가 확인하고 저장한 확정된 정보만 안내합니다."
    )

    BLOCKED_NOTICE = "안전성 검사를 통과하지 못해 현재 답변을 제공할 수 없습니다. 의료진 또는 의료기관에 문의하세요."
    CLARIFICATION_NOTICE = (
        "질문을 조금 더 구체적으로 알려주세요. 복약, 다음 진료 일정, 생활관리 중 어떤 내용을 묻는지 확인이 필요합니다."
    )

    def __init__(
        self,
        patient_context_provider: PatientContextProvider,
        input_risk_classifier: ChatInputRiskClassifier,
        question_classifier: ChatQuestionClassifier,
        query_builder: ChatQueryBuilder,
        retriever: GuidelineRetriever,
        answer_generator: ChatAnswerGenerator,
        safety_validator: ChatOutputSafetyValidator,
    ) -> None:
        self._patient_context_provider = patient_context_provider
        self._input_risk_classifier = input_risk_classifier
        self._question_classifier = question_classifier
        self._query_builder = query_builder
        self._retriever = retriever
        self._answer_generator = answer_generator
        self._safety_validator = safety_validator
        self._answer_assembler = ChatAnswerAssembler()

    async def execute(
        self,
        request: ChatAnswerRequest,
        limit: int = 5,
    ) -> ChatAnswerResult:
        patient_context = await self._patient_context_provider.get_patient_context(
            user_id=request.user_id,
            care_episode_id=request.care_episode_id,
        )

        minimum_risk = self._input_risk_classifier.assess(request.question)

        try:
            classification = await self._question_classifier.classify(
                request=request,
                minimum_risk=minimum_risk,
            )
        except ChatClassificationError:
            classification = self._build_classification_failure(minimum_risk)

        if classification.needs_clarification:
            return self._build_clarification_result(
                request=request,
                patient_context=patient_context,
                classification=classification,
            )

        if classification.route == ChatRoute.RESTRICTED:
            return self._build_restricted_result(
                request=request,
                patient_context=patient_context,
                classification=classification,
            )

        if classification.route == ChatRoute.PATIENT_ONLY:
            result = self._build_patient_only_result(
                request=request,
                patient_context=patient_context,
                classification=classification,
            )
            safety_result = await self._safety_validator.validate(
                patient_context=patient_context,
                result=result,
            )

            return self._apply_safety_result(
                request=request,
                patient_context=patient_context,
                classification=classification,
                result=result,
                safety_result=safety_result,
            )

        guideline_chunks: list[RetrievedGuidelineChunk] = []

        if classification.route == ChatRoute.PATIENT_AND_RAG:
            search_query = self._query_builder.build(
                request=request,
                classification=classification,
                limit=limit,
            )
            try:
                guideline_chunks = await self._retriever.search(search_query)
            except GuidelineRetrievalError:
                fallback_classification = ChatClassificationResult(
                    intent=classification.intent,
                    route=ChatRoute.RESTRICTED,
                    risk_level=classification.risk_level,
                    reason_codes=list(
                        dict.fromkeys(
                            [
                                *classification.reason_codes,
                                "GUIDELINE_RETRIEVAL_FAILED",
                            ]
                        )
                    ),
                )
                return self._build_restricted_result(
                    request=request,
                    patient_context=patient_context,
                    classification=fallback_classification,
                )

        try:
            result = await self._answer_generator.generate(
                request=request,
                patient_context=patient_context,
                classification=classification,
                guideline_chunks=guideline_chunks,
            )
        except ChatAnswerGenerationError as error:
            fallback_classification = ChatClassificationResult(
                intent=classification.intent,
                route=ChatRoute.RESTRICTED,
                risk_level=classification.risk_level,
                reason_codes=list(
                    dict.fromkeys(
                        [
                            *classification.reason_codes,
                            error.code,
                        ]
                    )
                ),
            )
            return self._build_restricted_result(
                request=request,
                patient_context=patient_context,
                classification=fallback_classification,
            )

        safety_result = await self._safety_validator.validate(
            patient_context=patient_context,
            result=result,
        )

        return self._apply_safety_result(
            request=request,
            patient_context=patient_context,
            classification=classification,
            result=result,
            safety_result=safety_result,
        )

    def _apply_safety_result(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
        result: ChatAnswerResult,
        safety_result: SafetyResult,
    ) -> ChatAnswerResult:
        if safety_result.status == SafetyStatus.RESTRICTED:
            restricted_classification = ChatClassificationResult(
                intent=classification.intent,
                route=ChatRoute.RESTRICTED,
                risk_level=(classification.risk_level),
                reason_codes=list(
                    dict.fromkeys(
                        [
                            *classification.reason_codes,
                            *safety_result.reason_codes,
                        ]
                    )
                ),
            )

            return self._build_restricted_result(
                request=request,
                patient_context=patient_context,
                classification=(restricted_classification),
            )

        update_data: dict[str, object] = {
            "safety_status": safety_result.status,
            "safety_reason_codes": list(safety_result.reason_codes),
        }

        if safety_result.status == SafetyStatus.BLOCKED:
            update_data.update(
                {
                    "answer": self.BLOCKED_NOTICE,
                    "sources": [],
                }
            )

        return result.model_copy(
            update=update_data,
            deep=True,
        )

    @staticmethod
    def _build_classification_failure(
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        if minimum_risk.risk_level == ChatRiskLevel.HIGH:
            fallback_risk = ChatRiskLevel.HIGH
        else:
            fallback_risk = ChatRiskLevel.CAUTION

        reason_codes = list(
            dict.fromkeys(
                [
                    *minimum_risk.reason_codes,
                    ChatClassificationError.code,
                ]
            )
        )

        return ChatClassificationResult(
            intent=ChatIntent.GENERAL,
            route=ChatRoute.RESTRICTED,
            risk_level=fallback_risk,
            reason_codes=reason_codes,
        )

    def _build_restricted_result(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
    ) -> ChatAnswerResult:
        confirmed_answer = self._answer_assembler.assemble(
            patient_context=patient_context,
            classification=classification,
            supplement=ChatAnswerSupplement(),
        )

        reason_codes = list(classification.reason_codes)

        if not reason_codes:
            reason_codes.append("RESTRICTED_REQUEST")

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=(patient_context.care_episode_id),
            answer=(f"{self.RESTRICTED_NOTICE}\n\n{confirmed_answer}"),
            intent=classification.intent,
            route=ChatRoute.RESTRICTED,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=reason_codes,
            patient_context_hash=(resolve_patient_context_hash(patient_context)),
            model_name=self.RESTRICTED_MODEL_NAME,
            model_version=None,
            prompt_version=(self.RESTRICTED_PROMPT_VERSION),
            schema_version=(CHAT_ANSWER_SCHEMA_VERSION),
            sources=self._build_restricted_sources(
                patient_context=patient_context,
                classification=classification,
            ),
        )

    def _build_patient_only_result(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
    ) -> ChatAnswerResult:
        answer = self._answer_assembler.assemble(
            patient_context=patient_context,
            classification=classification,
            supplement=ChatAnswerSupplement(),
        )

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=patient_context.care_episode_id,
            answer=answer,
            intent=classification.intent,
            route=classification.route,
            risk_level=classification.risk_level,
            safety_status=SafetyStatus.PENDING,
            patient_context_hash=resolve_patient_context_hash(patient_context),
            model_name=self.PATIENT_ONLY_MODEL_NAME,
            model_version=None,
            prompt_version=self.PATIENT_ONLY_PROMPT_VERSION,
            schema_version=CHAT_ANSWER_SCHEMA_VERSION,
            sources=self._build_restricted_sources(
                patient_context=patient_context,
                classification=classification,
            ),
        )

    def _build_clarification_result(
        self,
        request: ChatAnswerRequest,
        patient_context: PatientContext,
        classification: ChatClassificationResult,
    ) -> ChatAnswerResult:
        reason_codes = list(classification.reason_codes)
        if not reason_codes:
            reason_codes.append("NEEDS_CLARIFICATION")

        return ChatAnswerResult(
            request_id=request.request_id,
            care_episode_id=patient_context.care_episode_id,
            answer=self.CLARIFICATION_NOTICE,
            intent=classification.intent,
            route=None,
            risk_level=classification.risk_level,
            needs_clarification=True,
            safety_status=SafetyStatus.RESTRICTED,
            safety_reason_codes=reason_codes,
            patient_context_hash=resolve_patient_context_hash(patient_context),
            model_name=self.CLARIFICATION_MODEL_NAME,
            model_version=None,
            prompt_version=self.CLARIFICATION_PROMPT_VERSION,
            schema_version=CHAT_ANSWER_SCHEMA_VERSION,
            sources=[],
        )

    @staticmethod
    def _build_restricted_sources(
        patient_context: PatientContext,
        classification: ChatClassificationResult,
    ) -> list[GuideSource]:
        return ChatSourceBuilder.build_patient_sources(
            patient_context=patient_context,
            intent=classification.intent,
        )
