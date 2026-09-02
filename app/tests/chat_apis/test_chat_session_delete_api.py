from httpx import ASGITransport, AsyncClient
from starlette import status

from app.dependencies.security import get_request_user
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import (
    ChatMessageRole,
    ChatMessageStatus,
    ChatSessionStatus,
)
from app.models.users import User


async def _delete_session(*, user: User, session_id: int):
    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.delete(f"/api/v1/chat/sessions/{session_id}")
    finally:
        app.dependency_overrides.clear()


async def test_delete_chat_session_soft_deletes_owned_active_session() -> None:
    user = await User.create(
        id=1,
        email="delete-owner@example.com",
        hashed_password="hashed-password",
        name="삭제 소유자",
    )
    session = await ChatSession.create(user=user)
    await ChatMessage.create(
        chat_session=session,
        sequence_no=1,
        role=ChatMessageRole.USER,
        content="삭제 뒤에도 보존할 질문",
        status=ChatMessageStatus.COMPLETED,
    )

    response = await _delete_session(user=user, session_id=session.id)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body == {
        "success": True,
        "data": {
            "sessionId": session.id,
            "status": "DELETED",
            "deletedAt": body["data"]["deletedAt"],
        },
        "error": None,
    }
    assert body["data"]["deletedAt"].endswith("+09:00")

    await session.refresh_from_db()
    assert session.status == ChatSessionStatus.DELETED
    assert session.deleted_at is not None
    assert await ChatMessage.filter(chat_session_id=session.id).count() == 1

    second_response = await _delete_session(user=user, session_id=session.id)
    assert second_response.status_code == status.HTTP_404_NOT_FOUND
    assert second_response.json() == {
        "code": "CHAT_SESSION_NOT_FOUND",
        "message": "채팅 세션을 찾을 수 없습니다.",
    }


async def test_delete_chat_session_rejects_foreign_session_without_mutation() -> None:
    user = await User.create(
        id=1,
        email="delete-owner@example.com",
        hashed_password="hashed-password",
        name="삭제 요청자",
    )
    other_user = await User.create(
        id=2,
        email="other-delete-owner@example.com",
        hashed_password="hashed-password",
        name="다른 소유자",
    )
    session = await ChatSession.create(user=other_user)

    response = await _delete_session(user=user, session_id=session.id)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {
        "code": "CHAT_SESSION_ACCESS_DENIED",
        "message": "해당 채팅 세션을 삭제할 권한이 없습니다.",
    }
    await session.refresh_from_db()
    assert session.status == ChatSessionStatus.ACTIVE
    assert session.deleted_at is None


async def test_delete_chat_session_returns_not_found_for_missing_session() -> None:
    user = await User.create(
        id=1,
        email="delete-owner@example.com",
        hashed_password="hashed-password",
        name="삭제 요청자",
    )

    response = await _delete_session(user=user, session_id=999)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {
        "code": "CHAT_SESSION_NOT_FOUND",
        "message": "채팅 세션을 찾을 수 없습니다.",
    }


async def test_delete_chat_session_requires_authentication() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.delete("/api/v1/chat/sessions/1")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "인증이 필요합니다.",
    }


def test_chat_session_delete_is_registered_in_openapi() -> None:
    operation = app.openapi()["paths"]["/api/v1/chat/sessions/{session_id}"]["delete"]

    assert operation["summary"] == "내 채팅 세션 삭제"
    assert set(operation["responses"]) >= {"200", "401", "403", "404"}
