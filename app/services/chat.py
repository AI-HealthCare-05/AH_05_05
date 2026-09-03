import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ai_worker.domain.chat_content_compactor import (
    HISTORY_COMPACTION_MARKER,
    compact_chat_content,
)
from ai_worker.domain.errors import AIWorkerError
from ai_worker.observability.chat_tracer import (
    ChatSpan,
    ChatTracer,
    NoOpChatTracer,
)
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole
from ai_worker.schemas.medication_chat import (
    MedicationChatProgressCallback,
    MedicationChatRequest,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from ai_worker.services.medication_chat_core_service import (
    MedicationChatCoreService,
)
from app.core.exceptions import (
    ChatAnswerTimeoutError,
    ChatCareEpisodeNotFoundError,
    ChatContextConflictError,
    ChatConversationNotFoundError,
    ChatIdempotencyConflictError,
    ChatProcessingFailedError,
    ChatRequestConflictError,
    ChatSessionAccessDeniedError,
    ChatUpstreamUnavailableError,
    InvalidChatFeedbackReasonError,
)
from app.models.chat import ChatMessageSource
from app.models.enums import ChatMessageRole, ChatMessageStatus, ChatSessionStatus, ChatSourceType
from app.models.users import User
from app.repositories.chat_repository import (
    AcceptedChatRequest,
    CareEpisodeNotFoundError,
    ChatContextMismatchError,
    ChatFeedbackRecord,
    ChatRepository,
    ChatRequestInProgressError,
    ChatRequestPayloadMismatchError,
    ChatSessionAccessDeniedRepositoryError,
    ChatSessionNotFoundError,
)
from app.services.common_codes import CommonCodeService, normalize_common_code

CHAT_ANSWER_TIMEOUT_SECONDS = 30.0
CHAT_API_GUARD_TIMEOUT_SECONDS = 31.0


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


@dataclass(frozen=True, slots=True)
class ChatSessionSummaryView:
    session_id: int
    title: str
    last_message_preview: str
    last_message_at: datetime


@dataclass(frozen=True, slots=True)
class ChatSessionSourceView:
    source_type: str
    source_name: str
    vector_chunk_id: str | None
    source_organization: str | None
    source_url: str | None
    dataset_version: str | None


@dataclass(frozen=True, slots=True)
class ChatSessionMessageView:
    message_id: int
    role: ChatMessageRole
    content: str
    status: ChatMessageStatus
    reply_to_message_id: int | None
    guide_id: int | None
    sources: list[ChatSessionSourceView]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ChatSessionDetailView:
    session_id: int
    care_episode_key: str | None
    status: ChatSessionStatus
    last_message_at: datetime | None
    created_at: datetime
    messages: list[ChatSessionMessageView]


@dataclass(frozen=True, slots=True)
class DeletedChatSessionView:
    session_id: int
    status: ChatSessionStatus
    deleted_at: datetime


@dataclass(frozen=True, slots=True)
class ChatFeedbackView:
    session_id: int
    is_like: bool | None
    reason_code: str | None


class ChatSessionService:
    def __init__(
        self,
        repository: ChatRepository | None = None,
        common_code_service: CommonCodeService | None = None,
    ) -> None:
        self._repository = repository or ChatRepository()
        self._common_code_service = common_code_service or CommonCodeService()

    async def list_sessions(self, *, user: User) -> list[ChatSessionSummaryView]:
        records = await self._repository.list_session_summaries(user_id=user.id)
        return [
            ChatSessionSummaryView(
                session_id=record.session_id,
                title=record.title,
                last_message_preview=record.last_message_preview,
                last_message_at=record.last_message_at,
            )
            for record in records
        ]

    async def get_session(self, *, user: User, session_id: int) -> ChatSessionDetailView:
        try:
            record = await self._repository.get_session_detail(
                user_id=user.id,
                session_id=session_id,
            )
        except ChatSessionNotFoundError as error:
            raise ChatConversationNotFoundError from error

        session = record.session
        return ChatSessionDetailView(
            session_id=session.id,
            care_episode_key=(
                f"care_episode_{session.care_episode_id}" if session.care_episode_id is not None else None
            ),
            status=session.status,
            last_message_at=session.last_message_at,
            created_at=session.created_at,
            messages=[
                ChatSessionMessageView(
                    message_id=message.id,
                    role=message.role,
                    content=message.content,
                    status=message.status,
                    reply_to_message_id=message.reply_to_message_id,
                    guide_id=message.guide_id,
                    sources=[
                        _session_source_view(source) for source in record.sources_by_message_id.get(message.id, [])
                    ],
                    created_at=message.created_at,
                )
                for message in record.messages
            ],
        )

    async def delete_session(
        self,
        *,
        user: User,
        session_id: int,
    ) -> DeletedChatSessionView:
        try:
            record = await self._repository.delete_session(
                user_id=user.id,
                session_id=session_id,
            )
        except ChatSessionAccessDeniedRepositoryError as error:
            raise ChatSessionAccessDeniedError from error
        except ChatSessionNotFoundError as error:
            raise ChatConversationNotFoundError from error
        return DeletedChatSessionView(
            session_id=record.session_id,
            status=record.status,
            deleted_at=record.deleted_at,
        )

    async def update_feedback(
        self,
        *,
        user: User,
        session_id: int,
        is_like: bool | None,
        reason_code: str | None,
    ) -> ChatFeedbackView:
        normalized_reason = normalize_common_code(reason_code) if reason_code else None
        if is_like is None and normalized_reason is not None:
            raise InvalidChatFeedbackReasonError()
        if normalized_reason is not None:
            group_code = "P_REASON" if is_like else "N_REASON"
            if not await self._common_code_service.is_active_code("CHAT", group_code, normalized_reason):
                raise InvalidChatFeedbackReasonError()

        try:
            record: ChatFeedbackRecord = await self._repository.update_feedback(
                user_id=user.id,
                session_id=session_id,
                is_like=is_like,
                reason_code=normalized_reason,
            )
        except ChatSessionAccessDeniedRepositoryError as error:
            raise ChatSessionAccessDeniedError from error
        except ChatSessionNotFoundError as error:
            raise ChatConversationNotFoundError from error
        return ChatFeedbackView(
            session_id=record.session_id,
            is_like=record.is_like,
            reason_code=record.reason_code,
        )


class ChatApplicationService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        core_service: MedicationChatCoreService,
        tracer: ChatTracer | None = None,
        clock: Callable[[], float] = time.perf_counter,
        answer_timeout_seconds: float = CHAT_ANSWER_TIMEOUT_SECONDS,
    ) -> None:
        self._repository = repository
        self._core_service = core_service
        self._tracer = tracer or NoOpChatTracer()
        self._clock = clock
        self._answer_timeout_seconds = answer_timeout_seconds

    async def send(
        self,
        *,
        user: User,
        command: SendChatCommand,
        progress_callback: MedicationChatProgressCallback | None = None,
    ) -> SendChatResult:
        inputs = (
            {"question": command.message} if self._tracer.capture_content else {"question_length": len(command.message)}
        )
        metadata = {
            "request_key": self._tracer.anonymize_identifier(
                command.request_id,
            ),
            "user_key": self._tracer.anonymize_identifier(user.id),
            "care_episode_present": command.record_id is not None,
            "conversation_present": command.conversation_id is not None,
            "streaming": progress_callback is not None,
        }
        async with self._tracer.span(
            "chat.answer",
            root=True,
            inputs=inputs,
            metadata={key: value for key, value in metadata.items() if value is not None},
        ) as root_span:
            try:
                return await self._send_in_trace(
                    user=user,
                    command=command,
                    progress_callback=progress_callback,
                    root_span=root_span,
                )
            except BaseException as error:
                root_span.end(
                    {
                        "status": "FAILED",
                        "error_type": type(error).__name__,
                    }
                )
                raise

    async def _send_in_trace(
        self,
        *,
        user: User,
        command: SendChatCommand,
        progress_callback: MedicationChatProgressCallback | None,
        root_span: ChatSpan,
    ) -> SendChatResult:
        accepted = await self._accept_request(
            user=user,
            command=command,
        )

        if accepted.reused_assistant_message is not None:
            saved_message = accepted.reused_assistant_message
            saved_sources = await self._repository.get_message_sources(
                message_id=saved_message.id,
            )
            root_span.end(
                {
                    "status": "COMPLETED",
                    "cache_hit": True,
                    "source_count": len(saved_sources),
                }
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
        try:
            request = MedicationChatRequest(
                request_id=command.request_id,
                user_id=user.id,
                care_episode_id=(accepted.session.care_episode_id or command.record_id),
                question=command.message,
                history=[
                    ChatHistoryMessage(
                        role=(ChatRole.USER if message.role == ChatMessageRole.USER else ChatRole.ASSISTANT),
                        content=compact_chat_content(
                            message.content,
                            marker=HISTORY_COMPACTION_MARKER,
                        ),
                    )
                    for message in accepted.history
                ],
            )
            async with asyncio.timeout(self._answer_timeout_seconds):
                core_result = await self._core_service.answer(
                    request,
                    progress_callback=progress_callback,
                )
            duration_ms = self._duration_ms(started_at)
            completed = await self._repository.complete_request(
                assistant_message_id=accepted.assistant_message.id,
                result=core_result,
                duration_ms=duration_ms,
                langsmith_trace_id=root_span.trace_id,
            )
        except TimeoutError as error:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code="API_TIMEOUT",
                duration_ms=duration_ms,
                langsmith_trace_id=root_span.trace_id,
            )
            raise ChatAnswerTimeoutError from error
        except asyncio.CancelledError:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code="CHAT_REQUEST_CANCELLED",
                duration_ms=duration_ms,
                langsmith_trace_id=root_span.trace_id,
            )
            raise
        except AIWorkerError as error:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code=error.code,
                duration_ms=duration_ms,
                langsmith_trace_id=root_span.trace_id,
            )
            raise ChatUpstreamUnavailableError from error
        except Exception as error:
            duration_ms = self._duration_ms(started_at)
            await self._repository.fail_request(
                assistant_message_id=accepted.assistant_message.id,
                error_code="CHAT_PROCESSING_FAILED",
                duration_ms=duration_ms,
                langsmith_trace_id=root_span.trace_id,
            )
            raise ChatProcessingFailedError from error

        result = SendChatResult(
            conversation_id=accepted.session.id,
            message_id=completed.id,
            answer=core_result.answer,
            sources=[self._core_source_view(source) for source in core_result.sources],
        )
        root_span.end(
            {
                "status": "COMPLETED",
                "cache_hit": False,
                "source_count": len(result.sources),
                "route": core_result.route.value,
                "safety_status": core_result.safety_status.value,
            }
        )
        return result

    async def _accept_request(
        self,
        *,
        user: User,
        command: SendChatCommand,
    ) -> AcceptedChatRequest:
        try:
            return await self._repository.accept_request(
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
    def _saved_source_view(source: ChatMessageSource) -> ChatSourceView:
        return _saved_source_view(source)


def _session_source_view(source: ChatMessageSource) -> ChatSessionSourceView:
    display = _saved_source_view(source)
    return ChatSessionSourceView(
        source_type=(
            "PATIENT_DOCUMENT"
            if source.source_type
            in {
                ChatSourceType.PATIENT_SAVED_FIELD,
                ChatSourceType.USER_SUPPLEMENT,
            }
            else "PUBLIC_DATA"
        ),
        source_name=display.title,
        vector_chunk_id=source.vector_chunk_id,
        source_organization=source.source_organization,
        source_url=source.source_url,
        dataset_version=source.dataset_version,
    )


def _saved_source_view(source: ChatMessageSource) -> ChatSourceView:
    if source.source_type == ChatSourceType.PATIENT_SAVED_FIELD:
        name = source.medication.name if source.medication is not None else "확정 복약정보"
        return ChatSourceView(
            scope="personal",
            title=f"사용자 확정 복약정보 · {name}",
        )
    if source.source_type == ChatSourceType.USER_SUPPLEMENT:
        registration = source.user_suppl_nutrient
        if registration is None:
            name = "복용 영양제"
        elif registration.supplement_nutrient is not None:
            name = registration.supplement_nutrient.name
        else:
            name = registration.custom_name or "복용 영양제"
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
