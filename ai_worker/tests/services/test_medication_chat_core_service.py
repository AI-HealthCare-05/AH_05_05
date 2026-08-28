import pytest

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.observability.chat_tracer import NoOpChatTracer
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatProgress,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)
from ai_worker.services.medication_chat_core_service import (
    MedicationChatCoreService,
    build_medication_chat_core_service,
)


class FakeUseCase:
    def __init__(self) -> None:
        self.request = None

    async def execute(
        self,
        request: MedicationChatRequest,
        *,
        limit: int = 5,
        progress_callback=None,
    ) -> MedicationChatResult:
        self.request = request
        self.progress_callback = progress_callback
        return MedicationChatResult(
            request_id=request.request_id,
            answer="근거 기반 답변",
            route=MedicationChatRoute.GENERAL_GUIDANCE,
            safety_status=SafetyStatus.SAFE,
            prompt_version="medication-chat-prompt-v1",
            schema_version="medication-chat-result-v1",
        )


async def test_service_reuses_use_case_entrypoint() -> None:
    use_case = FakeUseCase()
    service = MedicationChatCoreService(use_case=use_case)
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="마그네슘은 어떤 영양제인가요?",
    )

    result = await service.answer(request)

    assert result.answer == "근거 기반 답변"
    assert use_case.request == request


async def test_service_forwards_progress_callback() -> None:
    use_case = FakeUseCase()
    service = MedicationChatCoreService(use_case=use_case)
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="마그네슘은 어떤 영양제인가요?",
    )

    async def callback(progress: MedicationChatProgress) -> None:
        return None

    await service.answer(request, progress_callback=callback)

    assert use_case.progress_callback is callback


def test_builder_rejects_missing_openai_key() -> None:
    settings = Config(OPENAI_API_KEY=None, _env_file=None)

    with pytest.raises(AIConfigurationError):
        build_medication_chat_core_service(
            settings=settings,
            qdrant_client=object(),
        )


def test_builder_reuses_injected_chat_tracer() -> None:
    tracer = NoOpChatTracer(hash_salt="test")

    service = build_medication_chat_core_service(
        settings=Config(
            OPENAI_API_KEY="test-key",
            _env_file=None,
        ),
        qdrant_client=object(),
        tracer=tracer,
    )

    assert service.tracer is tracer
