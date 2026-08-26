from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette import status

from app.dependencies.chat import get_chat_application_service
from app.dependencies.security import get_request_user
from app.main import app
from app.services.chat import ChatSourceView, SendChatResult


class FakeChatApplicationService:
    def __init__(self) -> None:
        self.received_user = None
        self.received_command = None

    async def send(self, *, user, command) -> SendChatResult:
        self.received_user = user
        self.received_command = command
        return SendChatResult(
            conversation_id=42,
            message_id=101,
            answer="확인 가능한 근거를 바탕으로 안내합니다.",
            sources=[
                ChatSourceView(
                    scope="official",
                    title="e약은요 · 아세트아미노펜",
                    organization="식품의약품안전처",
                    url="https://example.com/medicine",
                )
            ],
        )


async def test_post_chat_returns_camel_case_response() -> None:
    service = FakeChatApplicationService()
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7)
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
    assert response.json() == {
        "conversationId": 42,
        "messageId": 101,
        "answer": "확인 가능한 근거를 바탕으로 안내합니다.",
        "sources": [
            {
                "scope": "official",
                "title": "e약은요 · 아세트아미노펜",
                "organization": "식품의약품안전처",
                "url": "https://example.com/medicine",
            }
        ],
    }
    assert service.received_user.id == 7
    assert service.received_command.record_id is None
    assert service.received_command.message == "타이레놀은 어떤 약인가요?"


async def test_post_chat_rejects_invalid_request_without_calling_service() -> None:
    service = FakeChatApplicationService()
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_chat_application_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "requestId": "not-a-uuid",
                    "recordId": None,
                    "conversationId": None,
                    "message": "   ",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert service.received_command is None


async def test_chat_api_is_documented_in_openapi_and_redoc() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/api/openapi.json")).json()
        redoc = await client.get("/api/redoc")

    operation = schema["paths"]["/api/v1/chat"]["post"]
    assert operation["summary"] == "약·영양제 근거 기반 답변 생성"
    assert set(operation["responses"]) >= {
        "200",
        "401",
        "404",
        "409",
        "422",
        "503",
    }
    assert operation["responses"]["200"]["description"] == ("근거 기반 채팅 답변 생성 및 저장 완료")
    assert operation["responses"]["409"]["description"] == ("기존 대화 정보 또는 동일 요청 식별자와 충돌")
    assert redoc.status_code == status.HTTP_200_OK


async def test_post_chat_requires_authentication_in_common_error_format() -> None:
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

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "인증이 필요합니다.",
    }
