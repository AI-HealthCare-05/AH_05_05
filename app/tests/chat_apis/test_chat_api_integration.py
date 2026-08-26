from httpx import ASGITransport, AsyncClient
from starlette import status

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from app.dependencies.chat import get_chat_application_service
from app.dependencies.security import get_request_user
from app.main import app
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import ChatMessageRole, ChatMessageStatus
from app.models.users import User
from app.repositories.chat_repository import ChatRepository
from app.services.chat import ChatApplicationService


class FakeMedicationChatCore:
    async def answer(self, request, *, limit: int = 5):
        return MedicationChatResult(
            request_id=request.request_id,
            answer=(
                "아세트아미노펜은 확인된 공공 의약품 정보를 기준으로 "
                "안내합니다. 이 안내는 의료진의 진료를 대체하지 않습니다."
            ),
            route=MedicationChatRoute.MEDICATION_GUIDE,
            safety_status=SafetyStatus.SAFE,
            sources=[
                MedicationChatSource(
                    kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                    title="e약은요 · 아세트아미노펜",
                    organization="식품의약품안전처",
                    dataset_key="MFDS_EASY_DRUG",
                    dataset_version="knowledge-baseline-v1",
                    vector_chunk_id="easy-drug-1",
                    similarity_score=0.91,
                )
            ],
            prompt_version="medication-chat-prompt-v1",
            schema_version="medication-chat-result-v1",
        )


async def test_post_chat_persists_conversation_answer_and_sources() -> None:
    user = await User.create(
        id=1,
        email="chat-api@example.com",
        hashed_password="hashed-password",
        name="채팅 사용자",
    )
    service = ChatApplicationService(
        repository=ChatRepository(),
        core_service=FakeMedicationChatCore(),
    )
    app.dependency_overrides[get_request_user] = lambda: user
    app.dependency_overrides[get_chat_application_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "requestId": "6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
                    "recordId": None,
                    "conversationId": None,
                    "message": "타이레놀은 어떤 약인가요?",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["conversationId"] > 0
    assert body["messageId"] > 0
    assert body["sources"] == [
        {
            "scope": "official",
            "title": "e약은요 · 아세트아미노펜",
            "organization": "식품의약품안전처",
            "url": None,
        }
    ]
    assert await ChatSession.filter(user_id=user.id).count() == 1
    messages = await ChatMessage.filter(chat_session_id=body["conversationId"]).order_by("sequence_no")
    assert [message.role for message in messages] == [
        ChatMessageRole.USER,
        ChatMessageRole.ASSISTANT,
    ]
    assert messages[1].status == ChatMessageStatus.COMPLETED
    assert messages[1].content == body["answer"]
    assert await ChatMessageSource.filter(chat_message_id=body["messageId"]).count() == 1
