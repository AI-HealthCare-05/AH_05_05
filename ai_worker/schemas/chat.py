from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ai_worker.domain.chat_content_compactor import CHAT_CONTENT_MAX_LENGTH
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRole,
    ChatRoute,
    SafetyStatus,
)
from ai_worker.schemas.guide import GuideSource


class ChatHistoryMessage(BaseModel):
    role: ChatRole
    content: str = Field(
        min_length=1,
        max_length=CHAT_CONTENT_MAX_LENGTH,
    )

    @field_validator(
        "content",
        mode="before",
    )
    @classmethod
    def strip_content(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, str):
            return value.strip()

        return value


class ChatAnswerRequest(BaseModel):
    request_id: str = Field(
        min_length=1,
        max_length=100,
    )
    user_id: int = Field(ge=1)
    care_episode_id: int = Field(ge=1)

    condition: str = Field(
        min_length=1,
        max_length=100,
    )
    care_phase: str = Field(
        default="POST_DISCHARGE",
        min_length=1,
        max_length=100,
    )

    question: str = Field(
        min_length=1,
        max_length=CHAT_CONTENT_MAX_LENGTH,
    )
    history: list[ChatHistoryMessage] = Field(
        default_factory=list,
        max_length=10,
    )

    @field_validator(
        "request_id",
        "question",
        mode="before",
    )
    @classmethod
    def strip_text(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator(
        "condition",
        "care_phase",
        mode="before",
    )
    @classmethod
    def normalize_search_filter(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, str):
            return value.strip().upper()

        return value


class ChatClassificationResult(BaseModel):
    intent: ChatIntent
    route: ChatRoute | None = None
    risk_level: ChatRiskLevel

    normalized_query: str | None = None
    reason_codes: list[str] = Field(
        default_factory=list,
    )
    needs_clarification: bool = False

    @field_validator(
        "normalized_query",
        mode="before",
    )
    @classmethod
    def normalize_query(
        cls,
        value: Any,
    ) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip()

        return normalized or None

    @model_validator(mode="after")
    def validate_route_contract(
        self,
    ) -> Self:
        if self.needs_clarification:
            if self.route is not None or self.normalized_query is not None:
                raise ValueError("추가 확인이 필요하면 route와 normalized_query를 사용할 수 없습니다.")

            return self

        if self.route is None:
            raise ValueError("분류된 질문에는 route가 필요합니다.")

        if self.route == ChatRoute.PATIENT_AND_RAG:
            if self.normalized_query is None:
                raise ValueError("PATIENT_AND_RAG에는 normalized_query가 필요합니다.")

            return self

        if self.normalized_query is not None:
            raise ValueError("PATIENT_AND_RAG가 아니면 normalized_query를 사용할 수 없습니다.")

        return self


class ChatInputRiskResult(BaseModel):
    risk_level: ChatRiskLevel
    reason_codes: list[str] = Field(
        default_factory=list,
    )

    @field_validator("reason_codes")
    @classmethod
    def normalize_reason_codes(
        cls,
        values: list[str],
    ) -> list[str]:
        normalized_codes: list[str] = []

        for value in values:
            normalized = value.strip()

            if normalized and normalized not in normalized_codes:
                normalized_codes.append(normalized)

        return normalized_codes

    @model_validator(mode="after")
    def validate_high_risk_reason(
        self,
    ) -> Self:
        if self.risk_level == ChatRiskLevel.HIGH and not self.reason_codes:
            raise ValueError("HIGH 위험도에는 reason_codes가 필요합니다.")

        return self


CHAT_ANSWER_SCHEMA_VERSION = "chat-answer-result-v2"


class ChatAnswerSupplement(BaseModel):
    """LLM이 생성할 수 있는 채팅 보충정보."""

    model_config = ConfigDict(
        extra="forbid",
    )

    general_response: list[str] = Field(
        default_factory=list,
    )
    public_information: list[str] = Field(
        default_factory=list,
    )
    lifestyle_guidance: list[str] = Field(
        default_factory=list,
    )


class ChatAnswerResult(BaseModel):
    """안전성 검사 전후에 사용하는 최종 채팅 결과."""

    model_config = ConfigDict(
        extra="forbid",
    )

    request_id: str = Field(
        min_length=1,
        max_length=100,
    )
    care_episode_id: int = Field(ge=1)
    answer: str = Field(min_length=1)

    intent: ChatIntent
    route: ChatRoute | None
    risk_level: ChatRiskLevel
    needs_clarification: bool = False

    lifestyle_guidance_label: Literal["AI 생성 일반 안내"] = "AI 생성 일반 안내"

    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(
        default_factory=list,
    )
    sources: list[GuideSource] = Field(
        default_factory=list,
    )

    patient_context_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    model_name: str = Field(min_length=1)
    model_version: str | None = None
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_clarification_contract(self) -> Self:
        if self.needs_clarification and self.route is not None:
            raise ValueError("명확화 응답에는 route를 사용할 수 없습니다.")
        if not self.needs_clarification and self.route is None:
            raise ValueError("명확화 응답이 아니면 route가 필요합니다.")
        return self
