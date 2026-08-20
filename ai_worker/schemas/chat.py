from typing import Any, Self

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRole,
    ChatRoute,
)


class ChatHistoryMessage(BaseModel):
    role: ChatRole
    content: str = Field(
        min_length=1,
        max_length=2000,
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
        max_length=2000,
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
