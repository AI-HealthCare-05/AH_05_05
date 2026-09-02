from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.dtos.base import CamelModel
from app.services.chat import ChatSessionSummaryView, ChatSourceView, SendChatResult


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


class ChatErrorResponse(CamelModel):
    code: str
    message: str
    field: str | None = None
