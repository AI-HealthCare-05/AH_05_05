from contextlib import asynccontextmanager
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette import status

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatProgress,
    MedicationChatProgressStage,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from app.dependencies import chat as chat_dependencies
from app.dependencies.chat import get_chat_application_service
from app.dependencies.security import get_request_user
from app.main import app, lifespan
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import ChatMessageRole, ChatMessageStatus
from app.models.users import User
from app.repositories.chat_repository import ChatRepository
from app.services.chat import ChatApplicationService


class FakeMedicationChatCore:
    async def answer(
        self,
        request,
        *,
        limit: int = 5,
        progress_callback=None,
    ):
        if progress_callback is not None:
            await progress_callback(
                MedicationChatProgress.for_stage(
                    MedicationChatProgressStage.SAFETY_CHECKING,
                )
            )
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


class FixedTraceSpan:
    trace_id = "11111111-1111-4111-8111-111111111111"

    def end(self, outputs=None) -> None:
        return None


class FixedChatTracer:
    capture_content = False

    def __init__(self) -> None:
        self.closed = False

    @asynccontextmanager
    async def span(self, name, **kwargs):
        yield FixedTraceSpan()

    def anonymize_identifier(self, value):
        return None

    async def aclose(self) -> None:
        self.closed = True


class ClosableQdrantClient:
    def __init__(self, events: list[str] | None = None, **kwargs) -> None:
        self.events = events

    async def close(self) -> None:
        if self.events is not None:
            self.events.append("qdrant")


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
        tracer=FixedChatTracer(),
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
    assert messages[1].langsmith_trace_id == FixedTraceSpan.trace_id
    assert await ChatMessageSource.filter(chat_message_id=body["messageId"]).count() == 1


async def test_post_chat_stream_persists_only_completed_answer() -> None:
    user = await User.create(
        id=2,
        email="chat-stream-api@example.com",
        hashed_password="hashed-password",
        name="스트림 사용자",
    )
    service = ChatApplicationService(
        repository=ChatRepository(),
        core_service=FakeMedicationChatCore(),
        tracer=FixedChatTracer(),
    )
    app.dependency_overrides[get_request_user] = lambda: user
    app.dependency_overrides[get_chat_application_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat/stream",
                json={
                    "requestId": "7925e6ec-259c-4a96-8e69-6d5e8a626f1e",
                    "recordId": None,
                    "conversationId": None,
                    "message": "타이레놀은 어떤 약인가요?",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert "event: progress" in response.text
    assert "event: complete" in response.text
    session = await ChatSession.get(user_id=user.id)
    assistant = await ChatMessage.get(
        chat_session_id=session.id,
        role=ChatMessageRole.ASSISTANT,
    )
    assert assistant.status == ChatMessageStatus.COMPLETED
    assert "아세트아미노펜은 확인된 공공 의약품 정보" in assistant.content
    assert assistant.langsmith_trace_id == FixedTraceSpan.trace_id


async def test_chat_dependency_reuses_core_tracer(monkeypatch) -> None:
    tracer = FixedChatTracer()
    core_service = SimpleNamespace(tracer=tracer)
    captured = {}

    monkeypatch.setattr(
        chat_dependencies,
        "AsyncQdrantClient",
        ClosableQdrantClient,
    )
    monkeypatch.setattr(
        chat_dependencies,
        "build_medication_chat_core_service",
        lambda **kwargs: core_service,
    )

    class RecordingApplicationService:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        chat_dependencies,
        "ChatApplicationService",
        RecordingApplicationService,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace()),
    )

    await get_chat_application_service(request)

    assert captured["tracer"] is tracer
    assert request.app.state.chat_tracer is tracer


async def test_lifespan_closes_qdrant_before_chat_tracer() -> None:
    events: list[str] = []
    tracer = FixedChatTracer()

    async def close_tracer() -> None:
        events.append("tracer")

    tracer.aclose = close_tracer
    test_app = SimpleNamespace(
        state=SimpleNamespace(
            chat_qdrant_client=ClosableQdrantClient(events),
            chat_tracer=tracer,
        )
    )

    async with lifespan(test_app):
        pass

    assert events == ["qdrant", "tracer"]
