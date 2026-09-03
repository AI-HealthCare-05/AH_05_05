from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.dtos.base import CamelModel
from app.services.chat import (
    ChatFeedbackView,
    ChatSessionDetailView,
    ChatSessionMessageView,
    ChatSessionSourceView,
    ChatSessionSummaryView,
    ChatSourceView,
    DeletedChatSessionView,
    SendChatResult,
)


class SendChatRequest(CamelModel):
    request_id: UUID
    record_id: int | None = Field(default=None, gt=0)
    conversation_id: int | None = Field(default=None, gt=0)
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ChatSourceResponse(CamelModel):
    scope: Literal["personal", "official"]
    title: str
    organization: str | None = None
    url: str | None = None

    @classmethod
    def from_view(cls, source: ChatSourceView) -> "ChatSourceResponse":
        return cls(
            scope=source.scope,
            title=source.title,
            organization=source.organization,
            url=source.url,
        )


class SendChatResponse(CamelModel):
    conversation_id: int
    message_id: int
    answer: str
    sources: list[ChatSourceResponse]

    @classmethod
    def from_result(cls, result: SendChatResult) -> "SendChatResponse":
        return cls(
            conversation_id=result.conversation_id,
            message_id=result.message_id,
            answer=result.answer,
            sources=[ChatSourceResponse.from_view(source) for source in result.sources],
        )


class ChatSessionSummaryResponse(CamelModel):
    session_id: int
    title: str
    last_message_preview: str
    last_message_at: datetime

    @classmethod
    def from_view(cls, view: ChatSessionSummaryView) -> "ChatSessionSummaryResponse":
        return cls(
            session_id=view.session_id,
            title=view.title,
            last_message_preview=view.last_message_preview,
            last_message_at=view.last_message_at,
        )


class ChatSessionListResponse(CamelModel):
    items: list[ChatSessionSummaryResponse]


class ChatSessionSourceResponse(CamelModel):
    source_type: Literal["PATIENT_DOCUMENT", "PUBLIC_DATA"]
    source_name: str
    vector_chunk_id: str | None = None
    source_organization: str | None = None
    source_url: str | None = None
    dataset_version: str | None = None

    @classmethod
    def from_view(cls, view: ChatSessionSourceView) -> "ChatSessionSourceResponse":
        return cls(
            source_type=view.source_type,
            source_name=view.source_name,
            vector_chunk_id=view.vector_chunk_id,
            source_organization=view.source_organization,
            source_url=view.source_url,
            dataset_version=view.dataset_version,
        )


class ChatSessionMessageResponse(CamelModel):
    message_id: int
    role: Literal["USER", "ASSISTANT"]
    content: str
    status: Literal["PENDING", "STREAMING", "COMPLETED", "FAILED"]
    reply_to_message_id: int | None = None
    guide_id: int | None = None
    sources: list[ChatSessionSourceResponse]
    created_at: datetime

    @classmethod
    def from_view(cls, view: ChatSessionMessageView) -> "ChatSessionMessageResponse":
        return cls(
            message_id=view.message_id,
            role=view.role,
            content=view.content,
            status=view.status,
            reply_to_message_id=view.reply_to_message_id,
            guide_id=view.guide_id,
            sources=[ChatSessionSourceResponse.from_view(source) for source in view.sources],
            created_at=view.created_at,
        )


class ChatSessionDetailDataResponse(CamelModel):
    session_id: int
    care_episode_key: str | None = None
    status: Literal["ACTIVE"]
    last_message_at: datetime | None = None
    created_at: datetime
    messages: list[ChatSessionMessageResponse]

    @classmethod
    def from_view(cls, view: ChatSessionDetailView) -> "ChatSessionDetailDataResponse":
        return cls(
            session_id=view.session_id,
            care_episode_key=view.care_episode_key,
            status=view.status,
            last_message_at=view.last_message_at,
            created_at=view.created_at,
            messages=[ChatSessionMessageResponse.from_view(message) for message in view.messages],
        )


class ChatSessionDetailResponse(CamelModel):
    success: Literal[True] = True
    data: ChatSessionDetailDataResponse
    error: None = None


class DeletedChatSessionDataResponse(CamelModel):
    session_id: int
    status: Literal["DELETED"]
    deleted_at: datetime

    @classmethod
    def from_view(cls, view: DeletedChatSessionView) -> "DeletedChatSessionDataResponse":
        return cls(
            session_id=view.session_id,
            status=view.status,
            deleted_at=view.deleted_at,
        )


class DeletedChatSessionResponse(CamelModel):
    success: Literal[True] = True
    data: DeletedChatSessionDataResponse
    error: None = None


class ChatFeedbackRequest(CamelModel):
    is_like: bool | None
    reason_code: str | None = Field(default=None, max_length=20)

    @field_validator("reason_code", mode="before")
    @classmethod
    def normalize_reason_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        return normalized or None


class ChatFeedbackDataResponse(CamelModel):
    session_id: int
    is_like: bool | None
    reason_code: str | None

    @classmethod
    def from_view(cls, view: ChatFeedbackView) -> "ChatFeedbackDataResponse":
        return cls(session_id=view.session_id, is_like=view.is_like, reason_code=view.reason_code)


class ChatFeedbackResponse(CamelModel):
    success: Literal[True] = True
    data: ChatFeedbackDataResponse
    error: None = None


class ChatErrorResponse(CamelModel):
    code: str
    message: str
    field: str | None = None
