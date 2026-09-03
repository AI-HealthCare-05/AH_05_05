from httpx import ASGITransport, AsyncClient
from starlette import status

from app.dependencies.security import get_request_user
from app.main import app
from app.models.chat import ChatSession
from app.models.common_codes import CommonCode, CommonCodeGroup
from app.models.users import User


async def update_feedback(*, user: User, session_id: int, payload: dict):
    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.put(f"/api/v1/chat/sessions/{session_id}/feedback", json=payload)
    finally:
        app.dependency_overrides.clear()


async def create_reason(group_code: str, detail_code: str, *, active: bool = True) -> None:
    group = await CommonCodeGroup.create(
        category="CHAT",
        group_code=group_code,
        group_name=group_code,
        is_active=active,
    )
    await CommonCode.create(
        group=group,
        detail_code=detail_code,
        detail_name=detail_code,
        is_active=True,
    )


async def test_feedback_saves_optional_positive_reason_for_owned_session() -> None:
    user = await User.create(email="feedback@example.com", hashed_password="hashed", name="평가 사용자")
    session = await ChatSession.create(user=user)
    await create_reason("P_REASON", "HELPFUL")

    response = await update_feedback(
        user=user,
        session_id=session.id,
        payload={"isLike": True, "reasonCode": " helpful "},
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json() == {
        "success": True,
        "data": {"sessionId": session.id, "isLike": True, "reasonCode": "HELPFUL"},
        "error": None,
    }
    await session.refresh_from_db()
    assert session.is_like is True
    assert session.reason_code == "HELPFUL"


async def test_feedback_rejects_reason_from_opposite_evaluation_group() -> None:
    user = await User.create(email="feedback-wrong@example.com", hashed_password="hashed", name="평가 사용자")
    session = await ChatSession.create(user=user)
    await create_reason("P_REASON", "HELPFUL")

    response = await update_feedback(
        user=user,
        session_id=session.id,
        payload={"isLike": False, "reasonCode": "HELPFUL"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["code"] == "INVALID_CHAT_FEEDBACK_REASON"


async def test_feedback_can_be_saved_without_reason_and_cleared() -> None:
    user = await User.create(email="feedback-clear@example.com", hashed_password="hashed", name="평가 사용자")
    session = await ChatSession.create(user=user)

    saved = await update_feedback(user=user, session_id=session.id, payload={"isLike": False, "reasonCode": None})
    cleared = await update_feedback(user=user, session_id=session.id, payload={"isLike": None, "reasonCode": None})

    assert saved.status_code == status.HTTP_200_OK
    assert cleared.status_code == status.HTTP_200_OK
    await session.refresh_from_db()
    assert session.is_like is None
    assert session.reason_code is None


async def test_feedback_rejects_foreign_session_without_mutation() -> None:
    owner = await User.create(email="feedback-owner@example.com", hashed_password="hashed", name="소유자")
    requester = await User.create(email="feedback-other@example.com", hashed_password="hashed", name="요청자")
    session = await ChatSession.create(user=owner)

    response = await update_feedback(
        user=requester,
        session_id=session.id,
        payload={"isLike": True, "reasonCode": None},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "CHAT_SESSION_ACCESS_DENIED"
    await session.refresh_from_db()
    assert session.is_like is None
