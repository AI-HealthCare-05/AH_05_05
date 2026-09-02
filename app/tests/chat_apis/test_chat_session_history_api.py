from datetime import datetime

from httpx import ASGITransport, AsyncClient
from starlette import status

from app.dependencies.security import get_request_user
from app.main import app
from app.models.chat import ChatMessage, ChatMessageSource, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatMessageStatus,
    ChatSessionStatus,
    ChatSourceType,
)
from app.models.users import User


async def _create_message(
    session: ChatSession,
    *,
    sequence_no: int,
    role: ChatMessageRole,
    content: str,
    message_status: ChatMessageStatus = ChatMessageStatus.COMPLETED,
    created_at: datetime,
) -> ChatMessage:
    message = await ChatMessage.create(
        chat_session=session,
        sequence_no=sequence_no,
        role=role,
        content=content,
        status=message_status,
    )
    await ChatMessage.filter(id=message.id).update(created_at=created_at)
    return await ChatMessage.get(id=message.id)


async def _get_history(*, user: User, session_id: int):
    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get(f"/api/v1/chat/sessions/{session_id}")
    finally:
        app.dependency_overrides.clear()


async def test_get_chat_session_messages_returns_completed_history_with_sources_in_sequence() -> None:
    user = await User.create(
        id=1,
        email="history-owner@example.com",
        hashed_password="hashed-password",
        name="이력 소유자",
    )
    created_at = datetime(2026, 9, 2, 9, 0)
    last_message_at = datetime(2026, 9, 2, 9, 5)
    session = await ChatSession.create(user=user, last_message_at=last_message_at)
    await ChatSession.filter(id=session.id).update(created_at=created_at)
    await _create_message(
        session,
        sequence_no=3,
        role=ChatMessageRole.USER,
        content="두 번째 질문",
        created_at=datetime(2026, 9, 2, 9, 4),
    )
    await _create_message(
        session,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="첫 질문",
        created_at=datetime(2026, 9, 2, 9, 1),
    )
    answer = await _create_message(
        session,
        sequence_no=2,
        role=ChatMessageRole.ASSISTANT,
        content="첫 답변",
        created_at=datetime(2026, 9, 2, 9, 2),
    )
    await ChatMessageSource.create(
        chat_message=answer,
        source_type=ChatSourceType.PUBLIC_RAG_CHUNK,
        source_title="의약품안전나라",
        source_organization="식품의약품안전처",
        source_url="https://example.com/medicine",
        citation_order=1,
    )
    await _create_message(
        session,
        sequence_no=4,
        role=ChatMessageRole.ASSISTANT,
        content="처리 중 답변",
        message_status=ChatMessageStatus.PENDING,
        created_at=datetime(2026, 9, 2, 9, 5),
    )
    await _create_message(
        session,
        sequence_no=5,
        role=ChatMessageRole.ASSISTANT,
        content="실패한 답변",
        message_status=ChatMessageStatus.FAILED,
        created_at=datetime(2026, 9, 2, 9, 6),
    )
    await _create_message(
        session,
        sequence_no=6,
        role=ChatMessageRole.ASSISTANT,
        content="",
        created_at=datetime(2026, 9, 2, 9, 7),
    )

    response = await _get_history(user=user, session_id=session.id)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "success": True,
        "data": {
            "sessionId": session.id,
            "careEpisodeKey": None,
            "status": "ACTIVE",
            "lastMessageAt": "2026-09-02T09:05:00+09:00",
            "createdAt": "2026-09-02T09:00:00+09:00",
            "messages": [
                {
                    "messageId": 2,
                    "role": "USER",
                    "content": "첫 질문",
                    "status": "COMPLETED",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [],
                    "createdAt": "2026-09-02T09:01:00+09:00",
                },
                {
                    "messageId": 3,
                    "role": "ASSISTANT",
                    "content": "첫 답변",
                    "status": "COMPLETED",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [
                        {
                            "sourceType": "PUBLIC_DATA",
                            "sourceName": "의약품안전나라",
                            "vectorChunkId": None,
                            "sourceOrganization": "식품의약품안전처",
                            "sourceUrl": "https://example.com/medicine",
                            "datasetVersion": None,
                        }
                    ],
                    "createdAt": "2026-09-02T09:02:00+09:00",
                },
                {
                    "messageId": 1,
                    "role": "USER",
                    "content": "두 번째 질문",
                    "status": "COMPLETED",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [],
                    "createdAt": "2026-09-02T09:04:00+09:00",
                },
                {
                    "messageId": 4,
                    "role": "ASSISTANT",
                    "content": "처리 중 답변",
                    "status": "PENDING",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [],
                    "createdAt": "2026-09-02T09:05:00+09:00",
                },
                {
                    "messageId": 5,
                    "role": "ASSISTANT",
                    "content": "실패한 답변",
                    "status": "FAILED",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [],
                    "createdAt": "2026-09-02T09:06:00+09:00",
                },
                {
                    "messageId": 6,
                    "role": "ASSISTANT",
                    "content": "",
                    "status": "COMPLETED",
                    "replyToMessageId": None,
                    "guideId": None,
                    "sources": [],
                    "createdAt": "2026-09-02T09:07:00+09:00",
                },
            ],
        },
        "error": None,
    }


async def test_get_chat_session_messages_hides_foreign_deleted_and_inactive_sessions() -> None:
    user = await User.create(
        id=1,
        email="history-owner@example.com",
        hashed_password="hashed-password",
        name="이력 소유자",
    )
    other_user = await User.create(
        id=2,
        email="other-history-owner@example.com",
        hashed_password="hashed-password",
        name="다른 사용자",
    )
    foreign = await ChatSession.create(user=other_user)
    deleted = await ChatSession.create(user=user, deleted_at="2026-09-02T10:00:00+09:00")
    inactive = await ChatSession.create(user=user, status=ChatSessionStatus.DELETED)

    for hidden_session in (foreign, deleted, inactive):
        response = await _get_history(user=user, session_id=hidden_session.id)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {
            "code": "CHAT_SESSION_NOT_FOUND",
            "message": "채팅 세션을 찾을 수 없습니다.",
        }


async def test_get_chat_session_messages_requires_authentication() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/chat/sessions/1")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "인증이 필요합니다.",
    }


def test_chat_session_history_is_registered_in_openapi() -> None:
    operation = app.openapi()["paths"]["/api/v1/chat/sessions/{session_id}"]["get"]

    assert operation["summary"] == "내 채팅 세션 상세 및 메시지 조회"
    assert set(operation["responses"]) >= {"200", "401", "404"}
