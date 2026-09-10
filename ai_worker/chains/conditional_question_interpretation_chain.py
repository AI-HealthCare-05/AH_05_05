from enum import StrEnum
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import MedicationChatRoute
from ai_worker.schemas.medication_search import (
    MedicationQueryEntity,
    MedicationQuestionConfidence,
)

CONDITIONAL_QUESTION_INTERPRETATION_VERSION = "conditional-question-interpretation-v2"


class ConditionalInterpretationReasonCode(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MULTI_ENTITY = "MULTI_ENTITY"
    SESSION_REFERENCE = "SESSION_REFERENCE"


class ConditionalQuestionInterpretationInput(BaseModel):
    """카탈로그로 확인된 후보만 모델에 전달하는 구조화 질문 해석 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    candidate_entities: dict[str, MedicationQueryEntity] = Field(min_length=1, max_length=12)
    requested_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    trigger_reasons: list[ConditionalInterpretationReasonCode] = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("candidate_entities")
    @classmethod
    def normalize_candidate_keys(
        cls,
        values: dict[str, MedicationQueryEntity],
    ) -> dict[str, MedicationQueryEntity]:
        normalized: dict[str, MedicationQueryEntity] = {}
        for key, entity in values.items():
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("후보 키는 비어 있을 수 없습니다.")
            if normalized_key in normalized:
                raise ValueError("후보 키는 중복될 수 없습니다.")
            normalized[normalized_key] = entity
        return normalized


class ConditionalQuestionInterpretationOutput(BaseModel):
    """모델의 자유 추론문 없이, 후속 검증에 쓸 값만 받는 출력 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation_version: str = Field(
        default=CONDITIONAL_QUESTION_INTERPRETATION_VERSION,
        min_length=1,
    )
    route: MedicationChatRoute | None = None
    candidate_entity_keys: list[str] = Field(default_factory=list, max_length=12)
    requested_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    confidence: MedicationQuestionConfidence
    reason_codes: list[ConditionalInterpretationReasonCode] = Field(default_factory=list)

    @field_validator("candidate_entity_keys")
    @classmethod
    def normalize_keys(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ConditionalQuestionInterpretationChain(Protocol):
    async def ainvoke(
        self,
        input: ConditionalQuestionInterpretationInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> ConditionalQuestionInterpretationOutput | dict[str, Any]: ...


class AsyncConditionalQuestionInterpretationClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> ConditionalQuestionInterpretationOutput | dict[str, Any]: ...


def build_conditional_question_interpretation_chain(
    *,
    model: str,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 0,
    client: AsyncConditionalQuestionInterpretationClient | None = None,
) -> ConditionalQuestionInterpretationChain:
    """기본 비활성 실험용 JSON Schema 체인.

    호출자는 기존 카탈로그 후보를 다시 검증하며, 이 체인은 후보를 새로 만들지 않는다.
    """

    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
    response_runnable: Runnable
    if client is not None:
        response_runnable = RunnableLambda(client.ainvoke).with_config(
            run_name="medication.conditional_interpretation.client",
        )
    else:
        response_runnable = (
            ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            .with_structured_output(
                ConditionalQuestionInterpretationOutput,
                method="json_schema",
                strict=True,
            )
            .with_config(run_name="medication.conditional_interpretation.model")
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 의약품·영양제 질문의 구조만 정리합니다. "
                "제시된 후보 키 밖의 키를 만들지 마세요. 추론 과정·설명문은 출력하지 말고 "
                "JSON Schema에 정의된 필드만 반환하세요.",
            ),
            (
                "human",
                "질문: {question}\n"
                "카탈로그 후보: {candidate_options}\n"
                "현재 요청 항목: {requested_sections}\n"
                "호출 이유: {trigger_reasons}",
            ),
        ]
    )

    def validate(
        value: ConditionalQuestionInterpretationInput | dict[str, Any],
    ) -> ConditionalQuestionInterpretationInput:
        return (
            value
            if isinstance(value, ConditionalQuestionInterpretationInput)
            else ConditionalQuestionInterpretationInput.model_validate(value)
        )

    def render(value: ConditionalQuestionInterpretationInput):
        return prompt.format_messages(
            question=value.question,
            candidate_options=", ".join(
                f"{key}: {entity.canonical_name}" for key, entity in value.candidate_entities.items()
            ),
            requested_sections=", ".join(section.value for section in value.requested_section_types),
            trigger_reasons=", ".join(reason.value for reason in value.trigger_reasons),
        )

    return (
        RunnableLambda(validate).with_config(
            run_name="medication.conditional_interpretation.input",
        )
        | RunnableLambda(render).with_config(
            run_name="medication.conditional_interpretation.prompt",
        )
        | response_runnable
    ).with_types(
        input_type=ConditionalQuestionInterpretationInput,
        output_type=ConditionalQuestionInterpretationOutput,
    )
