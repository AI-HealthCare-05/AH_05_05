import time
from collections.abc import Callable
from dataclasses import dataclass

from ai_worker.domain.errors import AIWorkerError
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole
from ai_worker.schemas.medication_chat import (
    MedicationChatRequest,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from ai_worker.services.medication_chat_core_service import (
    MedicationChatCoreService,
)
from app.core.exceptions import (
    ChatCareEpisodeNotFoundError,
    ChatContextConflictError,
    ChatConversationNotFoundError,
    ChatIdempotencyConflictError,
    ChatProcessingFailedError,
    ChatRequestConflictError,
    ChatUpstreamUnavailableError,
)
from app.models.chat import ChatMessageSource
from app.models.enums import ChatMessageRole, ChatSourceType
from app.models.users import User
from app.repositories.chat_repository import (
    CareEpisodeNotFoundError,
    ChatContextMismatchError,
    ChatRepository,
    ChatRequestInProgressError,
    ChatRequestPayloadMismatchError,
    ChatSessionNotFoundError,
)


@dataclass(frozen=True, slots=True)
class SendChatCommand:
    request_id: str
    record_id: int | None
    conversation_id: int | None
    message: str


@dataclass(frozen=True, slots=True)
class ChatSourceView:
    scope: str
    title: str
    organization: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class SendChatResult:
    conversation_id: int
    message_id: int
    answer: str
    sources: list[ChatSourceView]


class ChatApplicationService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        core_service: MedicationChatCoreService,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._repository = repository
        self._core_service = core_service
        self._clock = clock

    async def send(
        self,
        *,
        user: User,
        command: SendChatCommand,
    ) -> SendChatResult:
        try:
            accepted = await self._repository.accept_request(
                user_id=user.id,
                care_episode_id=command.record_id,
                conversation_id=command.conversation_id,
                request_id=command.request_id,
                content=command.message,
            )
        except ChatSessionNotFoundError as error:
            raise ChatConversationNotFoundError from error
        except CareEpisodeNotFoundError as error:
            raise ChatCareEpisodeNotFoundError from error
        except ChatContextMismatchError as error:
            raise ChatContextConflictError from error
        except ChatRequestInProgressError as error:
            raise ChatRequestConflictError from error
        except ChatRequestPayloadMismatchError as error:
            raise ChatIdempotencyConflictError from error

        if accepted.reused_assistant_message is not None:
            saved_message = accepted.reused_assistant_message
            saved_sources = await self._repository.get_message_sources(
                message_id=saved_message.id,
            )
            return SendChatResult(
                conversation_id=accepted.session.id,
                message_id=saved_message.id,
                answer=saved_message.content,
                sources=[self._saved_source_view(source) for source in saved_sources],
            )

        if accepted.assistant_message is None:
            raise ChatProcessingFailedError
        started_at = self._clock()
        request = MedicationChatRequest(
            request_id=command.request_id,
            user_id=user.id,
            care_episode_id=(accepted.session.care_episode_id or command.record_id),
            question=command.message,
            history=[
                ChatHistoryMessage(
                    role=(ChatRole.USER if message.role == ChatMessageRole.USER else ChatRole.ASSISTANT),
                    content=message.content,
                )
                for message in accepted.history
            ],
        )
        try:
            core_result = await self._core_service.answer(request)
            duration_ms = self._duration_ms(started_at)
            completed = await self._repository.complete_request(
                assistant_message_id=accepted.assistant_message.id,
                result=core_result,
                duration_ms=duration_ms,
            )
        except AIWorkerError as error:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code=error.code,
                duration_ms=duration_ms,
            )
            raise ChatUpstreamUnavailableError from error
        except Exception as error:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code="CHAT_PROCESSING_FAILED",
                duration_ms=duration_ms,
            )
            raise ChatProcessingFailedError from error

        return SendChatResult(
            conversation_id=accepted.session.id,
            message_id=completed.id,
            answer=core_result.answer,
            sources=[self._core_source_view(source) for source in core_result.sources],
        )

    def _duration_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1000))

    @staticmethod
    def _core_source_view(
        source: MedicationChatSource,
    ) -> ChatSourceView:
        personal_kinds = {
            MedicationChatSourceKind.PATIENT_MEDICATION,
            MedicationChatSourceKind.PATIENT_SUPPLEMENT,
        }
        return ChatSourceView(
            scope=("personal" if source.kind in personal_kinds else "official"),
            title=source.title,
            organization=source.organization,
            url=source.url,
        )

    @staticmethod
    def _saved_source_view(
        source: ChatMessageSource,
    ) -> ChatSourceView:
        if source.source_type == ChatSourceType.PATIENT_SAVED_FIELD:
            name = source.medication.name if source.medication is not None else "확정 복약정보"
            return ChatSourceView(
                scope="personal",
                title=f"사용자 확정 복약정보 · {name}",
            )
        if source.source_type == ChatSourceType.USER_SUPPLEMENT:
            registration = source.user_suppl_nutrient
            name = registration.supplement_nutrient.name if registration is not None else "복용 영양제"
            return ChatSourceView(
                scope="personal",
                title=f"사용자 복용 영양제 · {name}",
            )
        if source.source_type == ChatSourceType.INTERACTION_RULE:
            rule = source.interaction_rule
            title = "승인된 상호작용 규칙"
            if rule is not None:
                title += f" · {rule.left_entity.canonical_name} · {rule.right_entity.canonical_name}"
            return ChatSourceView(scope="official", title=title)
        return ChatSourceView(
            scope="official",
            title=source.source_title or "공공 의약품·영양제 자료",
            organization=source.source_organization,
            url=source.source_url,
        )
