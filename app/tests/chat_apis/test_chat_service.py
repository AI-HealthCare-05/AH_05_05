import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.schemas.enums import ChatRole, SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from app.core.exceptions import (
    ChatProcessingFailedError,
    ChatUpstreamUnavailableError,
)
from app.models.enums import ChatMessageRole
from app.repositories.chat_repository import AcceptedChatRequest
from app.services.chat import (
    ChatApplicationService,
    SendChatCommand,
)

TRACE_ID = "11111111-1111-4111-8111-111111111111"


class RecordingSpan:
    def __init__(self, trace_id: str | None) -> None:
        self.trace_id = trace_id
        self.outputs = None

    def end(self, outputs=None) -> None:
        self.outputs = outputs


class RecordingChatTracer:
    capture_content = False

    def __init__(self, trace_id: str = TRACE_ID) -> None:
        self.trace_id = trace_id
        self.names = []

    @asynccontextmanager
    async def span(self, name, **kwargs):
        self.names.append(name)
        yield RecordingSpan(
            self.trace_id if kwargs.get("root") else None,
        )

    def anonymize_identifier(self, value):
        return f"key-{value}"

    async def aclose(self) -> None:
        return None


class FakeRepository:
    def __init__(self, history=None) -> None:
        self.history = history or []
        self.completed = None
        self.failed = None

    async def accept_request(self, **kwargs) -> AcceptedChatRequest:
        return AcceptedChatRequest(
            session=SimpleNamespace(id=42, care_episode_id=None),
            user_message=SimpleNamespace(id=100),
            assistant_message=SimpleNamespace(id=101),
            history=self.history,
        )

    async def complete_request(self, **kwargs):
        self.completed = kwargs
        return SimpleNamespace(id=kwargs["assistant_message_id"])

    async def fail_request(self, **kwargs) -> None:
        self.failed = kwargs


class FakeCore:
    def __init__(
        self,
        result: MedicationChatResult | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests = []

    async def answer(
        self,
        request,
        *,
        limit: int = 5,
        progress_callback=None,
    ):
        self.requests.append(request)
        self.progress_callback = progress_callback
        if self.error is not None:
            raise self.error
        return self.result


def build_result() -> MedicationChatResult:
    return MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer="근거 기반 답변",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                title="의약품 안전사용 안내",
                organization="식품의약품안전처",
            )
        ],
        prompt_version="medication-chat-prompt-v1",
        schema_version="medication-chat-result-v1",
    )


def build_command() -> SendChatCommand:
    return SendChatCommand(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        record_id=None,
        conversation_id=None,
        message="타이레놀은 어떤 약인가요?",
    )


async def test_send_passes_server_loaded_history_to_core() -> None:
    history = [
        SimpleNamespace(
            role=ChatMessageRole.USER,
            content="앞선 질문",
        ),
        SimpleNamespace(
            role=ChatMessageRole.ASSISTANT,
            content="앞선 답변",
        ),
    ]
    repository = FakeRepository(history=history)
    core = FakeCore(result=build_result())
    service = ChatApplicationService(
        repository=repository,
        core_service=core,
        clock=lambda: 1.0,
    )

    response = await service.send(
        user=SimpleNamespace(id=1),
        command=build_command(),
    )

    assert [message.role for message in core.requests[0].history] == [
        ChatRole.USER,
        ChatRole.ASSISTANT,
    ]
    assert repository.completed is not None
    assert response.conversation_id == 42
    assert response.message_id == 101
    assert response.sources[0].scope == "official"


async def test_send_forwards_progress_callback_to_core() -> None:
    repository = FakeRepository()
    core = FakeCore(result=build_result())
    service = ChatApplicationService(
        repository=repository,
        core_service=core,
        clock=lambda: 1.0,
    )

    async def callback(progress) -> None:
        return None

    await service.send(
        user=SimpleNamespace(id=1),
        command=build_command(),
        progress_callback=callback,
    )

    assert core.progress_callback is callback


async def test_send_persists_root_trace_id_on_success() -> None:
    repository = FakeRepository()
    tracer = RecordingChatTracer()
    service = ChatApplicationService(
        repository=repository,
        core_service=FakeCore(result=build_result()),
        tracer=tracer,
    )

    await service.send(
        user=SimpleNamespace(id=1),
        command=build_command(),
    )

    assert repository.completed is not None
    assert repository.completed["langsmith_trace_id"] == TRACE_ID
    assert tracer.names == ["chat.answer"]


async def test_send_marks_assistant_failed_before_raising_503() -> None:
    repository = FakeRepository()
    tracer = RecordingChatTracer()
    service = ChatApplicationService(
        repository=repository,
        core_service=FakeCore(error=ChatAnswerGenerationError("OpenAI 호출 실패")),
        tracer=tracer,
        clock=iter([1.0, 2.2]).__next__,
    )

    with pytest.raises(ChatUpstreamUnavailableError):
        await service.send(
            user=SimpleNamespace(id=1),
            command=build_command(),
        )

    assert repository.failed == {
        "assistant_message_id": 101,
        "error_code": "CHAT_ANSWER_GENERATION_FAILED",
        "duration_ms": 1200,
        "langsmith_trace_id": TRACE_ID,
    }


async def test_send_marks_assistant_failed_after_unexpected_error() -> None:
    repository = FakeRepository()
    tracer = RecordingChatTracer()
    service = ChatApplicationService(
        repository=repository,
        core_service=FakeCore(error=RuntimeError("unexpected")),
        tracer=tracer,
        clock=iter([1.0, 2.2]).__next__,
    )

    with pytest.raises(ChatProcessingFailedError):
        await service.send(
            user=SimpleNamespace(id=1),
            command=build_command(),
        )

    assert repository.failed == {
        "assistant_message_id": 101,
        "error_code": "CHAT_PROCESSING_FAILED",
        "duration_ms": 1200,
        "langsmith_trace_id": TRACE_ID,
    }


async def test_send_marks_assistant_failed_when_stream_is_cancelled() -> None:
    repository = FakeRepository()
    tracer = RecordingChatTracer()
    service = ChatApplicationService(
        repository=repository,
        core_service=FakeCore(error=asyncio.CancelledError()),
        tracer=tracer,
        clock=iter([1.0, 2.2]).__next__,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.send(
            user=SimpleNamespace(id=1),
            command=build_command(),
        )

    assert repository.failed == {
        "assistant_message_id": 101,
        "error_code": "CHAT_REQUEST_CANCELLED",
        "duration_ms": 1200,
        "langsmith_trace_id": TRACE_ID,
    }
