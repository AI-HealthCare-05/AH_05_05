from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette import status

from ai_worker.schemas.medication_chat import (
    MedicationChatProgress,
    MedicationChatProgressStage,
)
from app.core.exceptions import ChatAnswerTimeoutError
from app.dependencies.chat import get_chat_application_service
from app.dependencies.security import get_request_user
from app.main import app
from app.services.chat import (
    CHAT_ANSWER_TIMEOUT_SECONDS,
    ChatSourceView,
    SendChatResult,
)


class FakeChatApplicationService:
    def __init__(self) -> None:
        self.received_user = None
        self.received_command = None

    async def send(self, *, user, command, progress_callback=None) -> SendChatResult:
        self.received_user = user
        self.received_command = command
        if progress_callback is not None:
            await progress_callback(
                MedicationChatProgress(
                    stage=MedicationChatProgressStage.QUESTION_CHECKING,
                    message="질문 확인 중",
                )
            )
            await progress_callback(
                MedicationChatProgress(
                    stage=MedicationChatProgressStage.SAFETY_CHECKING,
                    message="안전 확인 중",
                )
            )
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


class TimeoutChatApplicationService:
    async def send(self, *, user, command, progress_callback=None):
        raise ChatAnswerTimeoutError


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


async def test_post_chat_stream_returns_progress_then_verified_final_answer() -> None:
    service = FakeChatApplicationService()
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_chat_application_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat/stream",
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
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress\n" in response.text
    assert '"message":"질문 확인 중"' in response.text
    assert '"message":"안전 확인 중"' in response.text
    assert "event: complete\n" in response.text
    assert '"answer":"확인 가능한 근거를 바탕으로 안내합니다."' in response.text
    assert response.text.index("질문 확인 중") < response.text.index("안전 확인 중")
    assert response.text.index("안전 확인 중") < response.text.index("event: complete")


async def test_post_chat_stream_returns_user_safe_timeout_event() -> None:
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_chat_application_service] = lambda: (TimeoutChatApplicationService())

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat/stream",
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
    assert "event: error\n" in response.text
    assert '"code":"API_TIMEOUT"' in response.text
    assert ('"message":"답변 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."') in response.text
    assert "event: complete\n" not in response.text


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
    stream_operation = schema["paths"]["/api/v1/chat/stream"]["post"]
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
    assert stream_operation["summary"] == ("약·영양제 근거 기반 답변 진행 상태 전송")
    assert "text/event-stream" in stream_operation["responses"]["200"]["content"]
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


def test_chat_endpoints_extend_timeout_for_external_ai_calls() -> None:
    chat_paths = {
        "/api/v1/chat",
        "/api/v1/chat/stream",
    }
    route_timeouts = {
        route.path: getattr(
            route.endpoint,
            "__api_timeout_seconds__",
            None,
        )
        for route in app.router.routes
        if getattr(route, "path", None) in chat_paths
    }

    assert route_timeouts == {
        "/api/v1/chat": 31.0,
        "/api/v1/chat/stream": 31.0,
    }
    assert CHAT_ANSWER_TIMEOUT_SECONDS == 30.0


def test_chat_openapi_documents_timeout_response() -> None:
    response_spec = app.openapi()["paths"]["/api/v1/chat"]["post"]["responses"]

    assert response_spec["504"]["description"] == ("30초 안에 답변 생성을 완료하지 못함")
