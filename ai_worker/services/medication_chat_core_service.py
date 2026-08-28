from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.llm.generators.medication_answer_generator import (
    OpenAIMedicationAnswerGenerator,
)
from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.repositories.interaction_rule_repository import (
    DbInteractionRuleRepository,
)
from ai_worker.repositories.medication_product_guide_repository import (
    DbMedicationProductGuideRepository,
)
from ai_worker.safety.grounded_claim_validator import (
    RuleBasedGroundedClaimValidator,
)
from ai_worker.schemas.medication_chat import (
    MedicationChatProgressCallback,
    MedicationChatRequest,
    MedicationChatResult,
)
from ai_worker.use_cases.answer_medication_question import (
    AnswerMedicationQuestionUseCase,
)


class MedicationChatCoreService:
    def __init__(
        self,
        *,
        use_case: AnswerMedicationQuestionUseCase,
    ) -> None:
        self._use_case = use_case

    async def answer(
        self,
        request: MedicationChatRequest,
        *,
        limit: int = 5,
        progress_callback: MedicationChatProgressCallback | None = None,
    ) -> MedicationChatResult:
        return await self._use_case.execute(
            request,
            limit=limit,
            progress_callback=progress_callback,
        )


def build_medication_chat_core_service(
    *,
    settings: Config,
    qdrant_client: AsyncQdrantClient,
) -> MedicationChatCoreService:
    if settings.OPENAI_API_KEY is None or not settings.OPENAI_API_KEY.get_secret_value().strip():
        raise AIConfigurationError("약·영양제 Chat Core를 구성하려면 OPENAI_API_KEY가 필요합니다.")
    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=settings.OPENAI_API_KEY,
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    vector_store = QdrantKnowledgeStore(
        client=qdrant_client,
        collection_name=settings.KNOWLEDGE_QDRANT_COLLECTION,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=DbActiveIntakeContextProvider(),
        guide_repository=DbMedicationProductGuideRepository(),
        interaction_rule_repository=DbInteractionRuleRepository(),
        knowledge_retriever=MedicationKnowledgeRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            dataset_version=settings.KNOWLEDGE_DATASET_VERSION,
            min_similarity_score=settings.RAG_MIN_SIMILARITY_SCORE,
        ),
        answer_generator=OpenAIMedicationAnswerGenerator(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        ),
        grounded_claim_validator=RuleBasedGroundedClaimValidator(),
    )
    return MedicationChatCoreService(use_case=use_case)
