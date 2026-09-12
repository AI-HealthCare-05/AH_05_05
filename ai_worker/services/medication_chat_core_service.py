from qdrant_client import AsyncQdrantClient

from ai_worker.chains.conditional_question_interpretation_chain import (
    build_conditional_question_interpretation_chain,
)
from ai_worker.chains.conversation_gate_chain import build_conversation_gate_chain
from ai_worker.chains.interaction_evidence_reasoning_chain import (
    build_interaction_evidence_reasoning_chain,
)
from ai_worker.chains.semantic_question_router import (
    LocalSemanticQuestionRouter,
    SentenceTransformerQuestionEmbeddingModel,
)
from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.llm.generators.conversation_response_generator import (
    build_conversation_response_generator,
)
from ai_worker.llm.generators.medication_answer_generator import (
    OpenAIMedicationAnswerGenerator,
)
from ai_worker.llm.generators.medication_note_summary_generator import (
    build_medication_note_summary_generator,
)
from ai_worker.observability.chat_tracer import (
    ChatTracer,
    NoOpChatTracer,
    build_chat_tracer,
)
from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)
from ai_worker.providers.db_follow_up_schedule_provider import (
    DbFollowUpScheduleProvider,
)
from ai_worker.providers.db_medication_note_summary_provider import (
    DbMedicationNoteSummaryProvider,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import (
    QdrantHybridKnowledgeStore,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.repositories.interaction_rule_repository import (
    DbInteractionRuleRepository,
)
from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
)
from ai_worker.repositories.medication_product_guide_repository import (
    DbMedicationProductGuideRepository,
)
from ai_worker.repositories.supplement_ingredient_catalog_repository import (
    CompositeSupplementIngredientCatalog,
    DbSupplementIngredientCatalog,
    QdrantSupplementIngredientCatalog,
)
from ai_worker.repositories.therapeutic_class_repository import (
    DbTherapeuticClassRepository,
)
from ai_worker.safety.grounded_claim_validator import (
    RuleBasedGroundedClaimValidator,
)
from ai_worker.schemas.knowledge import (
    KnowledgeSearchMode,
)
from ai_worker.schemas.medication_chat import (
    MedicationChatProgressCallback,
    MedicationChatRequest,
    MedicationChatResult,
)
from ai_worker.use_cases.answer_medication_question import (
    AnswerMedicationQuestionUseCase,
)
from ai_worker.use_cases.medication_note_summary import MedicationNoteSummaryUseCase


class MedicationChatCoreService:
    def __init__(
        self,
        *,
        use_case: AnswerMedicationQuestionUseCase,
        tracer: ChatTracer | None = None,
    ) -> None:
        self._use_case = use_case
        self._tracer = tracer or NoOpChatTracer()

    @property
    def tracer(self) -> ChatTracer:
        return self._tracer

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

    async def current_medication_names(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> list[str]:
        return await self._use_case.current_medication_names(
            user_id=user_id,
            care_episode_id=care_episode_id,
        )


def build_medication_chat_core_service(
    *,
    settings: Config,
    qdrant_client: AsyncQdrantClient,
    tracer: ChatTracer | None = None,
) -> MedicationChatCoreService:
    if settings.OPENAI_API_KEY is None or not settings.OPENAI_API_KEY.get_secret_value().strip():
        raise AIConfigurationError("약·영양제 Chat Core를 구성하려면 OPENAI_API_KEY가 필요합니다.")
    chat_tracer = tracer or build_chat_tracer(settings)
    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=settings.OPENAI_API_KEY,
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    vector_store_kwargs = {
        "client": qdrant_client,
        "collection_name": settings.KNOWLEDGE_QDRANT_COLLECTION,
        "vector_size": settings.OPENAI_EMBEDDING_DIMENSIONS,
        "distance": settings.KNOWLEDGE_VECTOR_DISTANCE,
    }
    if settings.KNOWLEDGE_SEARCH_MODE == KnowledgeSearchMode.DENSE:
        vector_store = QdrantKnowledgeStore(**vector_store_kwargs)
    else:
        vector_store = QdrantHybridKnowledgeStore(
            search_mode=settings.KNOWLEDGE_SEARCH_MODE,
            **vector_store_kwargs,
        )
    supplement_ingredient_catalog = CompositeSupplementIngredientCatalog(
        sources=[
            DbSupplementIngredientCatalog(),
            QdrantSupplementIngredientCatalog(
                client=qdrant_client,
                collection_name=settings.KNOWLEDGE_QDRANT_COLLECTION,
                dataset_version=settings.KNOWLEDGE_DATASET_VERSION,
            ),
        ]
    )
    expression_catalog = DbMedicationExpressionCatalog(
        supplement_catalog=supplement_ingredient_catalog,
    )
    conditional_interpretation_chain = (
        build_conditional_question_interpretation_chain(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=0,
        )
        if settings.CONDITIONAL_QUESTION_INTERPRETATION_ENABLED
        else None
    )
    interaction_evidence_reasoning_chain = (
        build_interaction_evidence_reasoning_chain(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=0,
        )
        if settings.INTERACTION_EVIDENCE_REASONING_ENABLED
        else None
    )
    conversation_gate_chain = (
        build_conversation_gate_chain(
            model=settings.CONVERSATION_GATE_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.CONVERSATION_GATE_TIMEOUT_SECONDS,
            max_retries=0,
            max_history_messages=settings.CONVERSATION_GATE_MAX_HISTORY_MESSAGES,
        )
        if settings.CONVERSATION_GATE_ENABLED
        else None
    )
    conversation_response_generator = (
        build_conversation_response_generator(
            model=settings.CONVERSATION_GATE_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.CONVERSATION_GATE_TIMEOUT_SECONDS,
            max_retries=0,
        )
        if settings.CONVERSATION_GATE_ENABLED
        else None
    )
    medication_note_summary_use_case = MedicationNoteSummaryUseCase(
        provider=DbMedicationNoteSummaryProvider(),
        generator=build_medication_note_summary_generator(
            model=settings.CONVERSATION_GATE_MODEL,
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.CONVERSATION_GATE_TIMEOUT_SECONDS,
            max_retries=0,
        ),
        tracer=chat_tracer,
    )
    semantic_question_router = (
        LocalSemanticQuestionRouter(
            embedder=SentenceTransformerQuestionEmbeddingModel(
                model_name=settings.SEMANTIC_ROUTER_MODEL,
            ),
            min_score=settings.SEMANTIC_ROUTER_MIN_SCORE,
            min_margin=settings.SEMANTIC_ROUTER_MIN_MARGIN,
        )
        if settings.SEMANTIC_ROUTER_ENABLED
        else None
    )
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=DbActiveIntakeContextProvider(),
        guide_repository=DbMedicationProductGuideRepository(),
        interaction_rule_repository=DbInteractionRuleRepository(
            active_dataset_version=(settings.INTERACTION_RULE_DATASET_VERSION),
        ),
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
        tracer=chat_tracer,
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=expression_catalog,
        ),
        supplement_ingredient_catalog=supplement_ingredient_catalog,
        conditional_interpretation_chain=conditional_interpretation_chain,
        interaction_evidence_reasoning_chain=interaction_evidence_reasoning_chain,
        conversation_gate_chain=conversation_gate_chain,
        conversation_response_generator=conversation_response_generator,
        semantic_question_router=semantic_question_router,
        therapeutic_class_repository=DbTherapeuticClassRepository(
            active_dataset_version=settings.THERAPEUTIC_CLASS_DATASET_VERSION,
        ),
        follow_up_schedule_provider=DbFollowUpScheduleProvider(),
        medication_note_summary_use_case=medication_note_summary_use_case,
    )
    return MedicationChatCoreService(
        use_case=use_case,
        tracer=chat_tracer,
    )
