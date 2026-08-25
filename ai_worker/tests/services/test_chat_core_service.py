import pytest
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.rag.retrievers.knowledge_guideline_retriever import (
    KnowledgeGuidelineRetriever,
)
from ai_worker.schemas.chat import ChatAnswerRequest, ChatAnswerResult
from ai_worker.services.chat_core_service import (
    ChatCoreService,
    build_chat_use_case,
)
from ai_worker.use_cases.answer_chat_message import (
    AnswerChatMessageUseCase,
)


class FakeChatUseCase:
    def __init__(self, result: ChatAnswerResult) -> None:
        self.result = result
        self.received_request: ChatAnswerRequest | None = None
        self.received_limit: int | None = None

    async def execute(
        self,
        request: ChatAnswerRequest,
        limit: int = 5,
    ) -> ChatAnswerResult:
        self.received_request = request
        self.received_limit = limit
        return self.result


async def test_chat_core_service_delegates_to_reusable_use_case() -> None:
    expected = ChatAnswerResult(
        request_id="request-1",
        care_episode_id=100,
        answer="확정정보 답변",
        intent="PATIENT_FACT",
        route="PATIENT_ONLY",
        risk_level="LOW",
        safety_status="SAFE",
        patient_context_hash="a" * 64,
        model_name="rule-based-patient-only",
        prompt_version="chat-patient-only-v1",
        schema_version="chat-answer-result-v1",
    )
    use_case = FakeChatUseCase(expected)
    service = ChatCoreService(use_case=use_case)
    request = ChatAnswerRequest(
        request_id="request-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        question="내 진단명은 무엇이야?",
    )

    result = await service.answer(request=request, limit=3)

    assert result == expected
    assert use_case.received_request == request
    assert use_case.received_limit == 3


async def test_build_chat_use_case_connects_ai_components() -> None:
    qdrant_client = AsyncQdrantClient(location=":memory:")
    try:
        use_case = build_chat_use_case(
            settings=Config(
                OPENAI_API_KEY="test-api-key",
                KNOWLEDGE_QDRANT_COLLECTION=("medication_knowledge_pilot_v1"),
                KNOWLEDGE_DATASET_VERSION="knowledge-pilot-v1",
                _env_file=None,
            ),
            qdrant_client=qdrant_client,
        )

        assert isinstance(use_case, AnswerChatMessageUseCase)
        assert isinstance(
            use_case._retriever,
            KnowledgeGuidelineRetriever,
        )
        assert use_case._retriever._dataset_version == "knowledge-pilot-v1"
        assert use_case._retriever._vector_store.collection_name == "medication_knowledge_pilot_v1"
    finally:
        await qdrant_client.close()


async def test_build_chat_use_case_rejects_blank_openai_key() -> None:
    qdrant_client = AsyncQdrantClient(location=":memory:")
    try:
        with pytest.raises(
            AIConfigurationError,
            match="OPENAI_API_KEY",
        ):
            build_chat_use_case(
                settings=Config(
                    OPENAI_API_KEY="   ",
                    _env_file=None,
                ),
                qdrant_client=qdrant_client,
            )
    finally:
        await qdrant_client.close()
