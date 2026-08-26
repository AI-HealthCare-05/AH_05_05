from fastapi import Request
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config as AIConfig
from ai_worker.domain.errors import AIWorkerError
from ai_worker.services.medication_chat_core_service import (
    build_medication_chat_core_service,
)
from app.core.exceptions import ChatUpstreamUnavailableError
from app.repositories.chat_repository import ChatRepository
from app.services.chat import ChatApplicationService


async def get_chat_application_service(
    request: Request,
) -> ChatApplicationService:
    """FastAPI 프로세스에서 Chat Core와 Qdrant 연결을 한 번만 만든다."""
    existing = getattr(
        request.app.state,
        "chat_application_service",
        None,
    )
    if existing is not None:
        return existing

    settings = AIConfig()
    qdrant_client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )
    try:
        core_service = build_medication_chat_core_service(
            settings=settings,
            qdrant_client=qdrant_client,
        )
    except AIWorkerError as error:
        await qdrant_client.close()
        raise ChatUpstreamUnavailableError("AI 채팅 설정을 확인해 주세요.") from error

    service = ChatApplicationService(
        repository=ChatRepository(),
        core_service=core_service,
    )
    request.app.state.chat_qdrant_client = qdrant_client
    request.app.state.chat_application_service = service
    return service
