from datetime import datetime

from httpx import ASGITransport, AsyncClient
from starlette import status

from app.dependencies.security import get_request_user
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import ChatMessageRole, ChatMessageStatus, ChatSessionStatus
from app.models.users import User


async def _create_message(
    session: ChatSession,
    *,
    sequence_no: int,
    role: ChatMessageRole,
    content: str,
    message_status: ChatMessageStatus = ChatMessageStatus.COMPLETED,
    completed_at: datetime | None = None,
) -> ChatMessage:
    return await ChatMessage.create(
        chat_session=session,
        sequence_no=sequence_no,
        role=role,
        content=content,
        status=message_status,
        completed_at=completed_at,
    )


async def test_get_chat_sessions_returns_only_visible_owned_sessions_in_summary_order() -> None:
    user = await User.create(
        id=1,
        email="session-owner@example.com",
        hashed_password="hashed-password",
        name="세션 소유자",
    )
    other_user = await User.create(
        id=2,
        email="other-session-owner@example.com",
        hashed_password="hashed-password",
        name="다른 사용자",
    )
    first_question_at = datetime(2026, 9, 2, 9, 30)
    answer_at = datetime(2026, 9, 2, 10, 0)
    tie_at = datetime(2026, 9, 2, 12, 0)

    conversation = await ChatSession.create(user=user, last_message_at=answer_at)
    await _create_message(
        conversation,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="첫 번째 질문",
        completed_at=first_question_at,
    )
    await _create_message(
        conversation,
        sequence_no=2,
        role=ChatMessageRole.ASSISTANT,
        content="",
        message_status=ChatMessageStatus.PENDING,
    )
    await _create_message(
        conversation,
        sequence_no=3,
        role=ChatMessageRole.ASSISTANT,
        content="최신 답변",
        completed_at=answer_at,
    )
    await _create_message(
        conversation,
        sequence_no=4,
        role=ChatMessageRole.ASSISTANT,
        content="실패한 답변",
        message_status=ChatMessageStatus.FAILED,
        completed_at=datetime(2026, 9, 2, 11, 0),
    )

    question_only = await ChatSession.create(user=user, last_message_at=first_question_at)
    await _create_message(
        question_only,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="답변 전 질문",
        completed_at=first_question_at,
    )

    lower_tie = await ChatSession.create(user=user, last_message_at=tie_at)
    await _create_message(
        lower_tie,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="동률 먼저 생성",
        completed_at=tie_at,
    )
    higher_tie = await ChatSession.create(user=user, last_message_at=tie_at)
    await _create_message(
        higher_tie,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="동률 나중 생성",
        completed_at=tie_at,
    )

    await ChatSession.create(user=user)
    deleted = await ChatSession.create(user=user, last_message_at=tie_at, deleted_at=tie_at)
    await _create_message(
        deleted,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="삭제된 대화",
        completed_at=tie_at,
    )
    inactive = await ChatSession.create(
        user=user,
        status=ChatSessionStatus.DELETED,
        last_message_at=tie_at,
    )
    await _create_message(
        inactive,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="비활성 대화",
        completed_at=tie_at,
    )
    other_users_session = await ChatSession.create(user=other_user, last_message_at=tie_at)
    await _create_message(
        other_users_session,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="다른 사용자의 대화",
        completed_at=tie_at,
    )

    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/chat/sessions")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "items": [
            {
                "sessionId": higher_tie.id,
                "title": "동률 나중 생성",
                "lastMessagePreview": "동률 나중 생성",
                "lastMessageAt": "2026-09-02T12:00:00+09:00",
            },
            {
                "sessionId": lower_tie.id,
                "title": "동률 먼저 생성",
                "lastMessagePreview": "동률 먼저 생성",
                "lastMessageAt": "2026-09-02T12:00:00+09:00",
            },
            {
                "sessionId": conversation.id,
                "title": "첫 번째 질문",
                "lastMessagePreview": "최신 답변",
                "lastMessageAt": "2026-09-02T10:00:00+09:00",
            },
            {
                "sessionId": question_only.id,
                "title": "답변 전 질문",
                "lastMessagePreview": "답변 전 질문",
                "lastMessageAt": "2026-09-02T09:30:00+09:00",
            },
        ]
    }


async def test_get_chat_sessions_requires_authentication_in_common_error_format() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/chat/sessions")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "인증이 필요합니다.",
    }


def test_chat_session_list_is_registered_in_openapi() -> None:
    operation = app.openapi()["paths"]["/api/v1/chat/sessions"]["get"]

    assert operation["summary"] == "내 채팅 세션 목록 조회"
    assert set(operation["responses"]) >= {"200", "401"}
