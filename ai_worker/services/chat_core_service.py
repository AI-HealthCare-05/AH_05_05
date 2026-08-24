from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.llm.generators.chat_answer_generator import (
    OpenAIChatAnswerGenerator,
)
from ai_worker.llm.generators.chat_question_classifier import (
    OpenAIChatQuestionClassifier,
)
from ai_worker.providers.db_patient_context_provider import (
    DbPatientContextProvider,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.query_builders.chat_query_builder import (
    ChatQueryBuilder,
)
from ai_worker.rag.retrievers.guideline_retriever import (
    GuidelineRetriever,
)
from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)
from ai_worker.safety.chat_input_risk_classifier import (
    RuleBasedChatInputRiskClassifier,
)
from ai_worker.safety.chat_output_safety_validator import (
    RuleBasedChatOutputSafetyValidator,
)
from ai_worker.schemas.chat import ChatAnswerRequest, ChatAnswerResult
from ai_worker.use_cases.answer_chat_message import (
    AnswerChatMessageUseCase,
)


class ChatCoreService:
    """FastAPI에서 직접 재사용하는 챗봇 Core 진입점."""

    def __init__(self, use_case: AnswerChatMessageUseCase) -> None:
        self._use_case = use_case

    async def answer(
        self,
        request: ChatAnswerRequest,
        limit: int = 5,
    ) -> ChatAnswerResult:
        return await self._use_case.execute(
            request=request,
            limit=limit,
        )


def build_chat_use_case(
    *,
    settings: Config,
    qdrant_client: AsyncQdrantClient,
) -> AnswerChatMessageUseCase:
    if settings.OPENAI_API_KEY is None or not settings.OPENAI_API_KEY.get_secret_value().strip():
        raise AIConfigurationError("챗봇 Core를 구성하려면 OPENAI_API_KEY가 필요합니다.")

    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=settings.OPENAI_API_KEY,
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    vector_store = QdrantGuidelineStore(
        client=qdrant_client,
        collection_name=settings.QDRANT_COLLECTION,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )

    return AnswerChatMessageUseCase(
        patient_context_provider=DbPatientContextProvider(),
        input_risk_classifier=RuleBasedChatInputRiskClassifier(),
        question_classifier=OpenAIChatQuestionClassifier(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        ),
        query_builder=ChatQueryBuilder(),
        retriever=GuidelineRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            min_similarity_score=settings.RAG_MIN_SIMILARITY_SCORE,
        ),
        answer_generator=OpenAIChatAnswerGenerator(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        ),
        safety_validator=RuleBasedChatOutputSafetyValidator(),
    )


def build_chat_core_service(
    *,
    settings: Config,
    qdrant_client: AsyncQdrantClient,
) -> ChatCoreService:
    return ChatCoreService(
        use_case=build_chat_use_case(
            settings=settings,
            qdrant_client=qdrant_client,
        )
    )
