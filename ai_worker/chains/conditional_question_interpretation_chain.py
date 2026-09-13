import json
from enum import StrEnum
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from ai_worker.llm.prompts.prompt_assets import (
    MedicationPromptStage,
    load_prompt_chain_stage,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import MedicationChatRoute
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQuestionConfidence,
)

CONDITIONAL_QUESTION_INTERPRETATION_VERSION = "conditional-question-interpretation-v3"


class ConditionalInterpretationReasonCode(StrEnum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MULTI_ENTITY = "MULTI_ENTITY"
    SESSION_REFERENCE = "SESSION_REFERENCE"


class DirectionalSearchTarget(StrEnum):
    MEDICATION_PRODUCT_GUIDE = "MEDICATION_PRODUCT_GUIDE"
    SUPPLEMENT_GUIDE = "SUPPLEMENT_GUIDE"
    INTERACTION_EVIDENCE = "INTERACTION_EVIDENCE"
    ACTIVE_INTAKE = "ACTIVE_INTAKE"


class DirectionalSearchStimulus(BaseModel):
    """모델이 제안하고 서버가 다시 검증하는 제한된 검색 방향."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=300)
    target: DirectionalSearchTarget
    section_types: list[KnowledgeSectionType] = Field(default_factory=list, max_length=4)
    purpose: str = Field(min_length=1, max_length=240)

    @field_validator("query", "purpose")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ConditionalQuestionInterpretationInput(BaseModel):
    """카탈로그로 확인된 후보만 모델에 전달하는 구조화 질문 해석 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    candidate_entities: dict[str, MedicationQueryEntity] = Field(min_length=1, max_length=12)
    requested_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    trigger_reasons: list[ConditionalInterpretationReasonCode] = Field(min_length=1)
    candidate_pair_keys: list[str] = Field(default_factory=list)
    allowed_search_terms: list[str] = Field(default_factory=list)
    session_reference_entities: dict[str, str] = Field(default_factory=dict)
    current_query_plan: MedicationKnowledgeQueryPlan | None = None

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

    @field_validator("candidate_pair_keys", "allowed_search_terms")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ConditionalQuestionInterpretationOutput(BaseModel):
    """모델의 자유 추론문 없이, 후속 검증에 쓸 값만 받는 출력 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation_version: str = Field(
        default=CONDITIONAL_QUESTION_INTERPRETATION_VERSION,
        min_length=1,
        max_length=80,
    )
    normalized_question: str = Field(min_length=1, max_length=500)
    route: MedicationChatRoute | None = None
    candidate_entity_keys: list[str] = Field(default_factory=list, max_length=12)
    requested_section_types: list[KnowledgeSectionType] = Field(default_factory=list, max_length=4)
    interaction_pair_keys: list[str] = Field(default_factory=list, max_length=16)
    stimuli: list[DirectionalSearchStimulus] = Field(default_factory=list, max_length=3)
    confidence: MedicationQuestionConfidence
    reason_codes: list[ConditionalInterpretationReasonCode] = Field(default_factory=list, max_length=3)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)

    @field_validator("candidate_entity_keys")
    @classmethod
    def normalize_keys(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("normalized_question")
    @classmethod
    def strip_normalized_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("interaction_pair_keys")
    @classmethod
    def normalize_pair_keys(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("clarification_question")
    @classmethod
    def normalize_clarification_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_clarification_contract(self) -> "ConditionalQuestionInterpretationOutput":
        if self.needs_clarification and self.clarification_question is None:
            raise ValueError("확인 질문이 필요한 경우 clarification_question을 제공해야 합니다.")
        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError("확인 질문은 needs_clarification일 때만 사용할 수 있습니다.")
        if self.needs_clarification and self.stimuli:
            raise ValueError("확인 질문이 필요한 경우 검색 자극을 만들 수 없습니다.")
        return self


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

    prompt_document = load_prompt_chain_stage(
        MedicationPromptStage.DIRECTIONAL_QUERY,
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", prompt_document.compiled_system),
            ("human", prompt_document.user),
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
        query_plan = value.current_query_plan
        current_classification = (
            {
                "section_types": [section.value for section in query_plan.section_types],
                "document_types": [document_type.value for document_type in query_plan.document_types],
                "alternate_query_count": len(query_plan.alternate_queries),
                "entity_count": len(query_plan.entities),
                "interaction_pair_count": len(query_plan.interaction_pairs),
                "has_medication_product_cue": query_plan.has_medication_product_cue,
            }
            if query_plan is not None
            else {
                "section_types": [section.value for section in value.requested_section_types],
                "interaction_pair_count": len(value.candidate_pair_keys),
            }
        )
        return prompt.format_messages(
            question=value.question,
            session_reference_json=json.dumps(
                value.session_reference_entities,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            candidate_entities_json=json.dumps(
                {key: entity.model_dump(mode="json") for key, entity in value.candidate_entities.items()},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            candidate_pair_keys_json=json.dumps(
                value.candidate_pair_keys,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            allowed_search_terms_json=json.dumps(
                value.allowed_search_terms,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            current_query_plan_json=json.dumps(
                current_classification,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            trigger_reasons_json=json.dumps(
                [reason.value for reason in value.trigger_reasons],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    def validate_output(
        value: ConditionalQuestionInterpretationOutput | dict[str, Any],
    ) -> ConditionalQuestionInterpretationOutput:
        if isinstance(value, ConditionalQuestionInterpretationOutput):
            return value
        return ConditionalQuestionInterpretationOutput.model_validate(value)

    return (
        RunnableLambda(validate).with_config(
            run_name="medication.conditional_interpretation.input",
        )
        | RunnableLambda(render).with_config(
            run_name="medication.conditional_interpretation.prompt",
        )
        | response_runnable
        | RunnableLambda(validate_output).with_config(
            run_name="medication.conditional_interpretation.output",
        )
    ).with_types(
        input_type=ConditionalQuestionInterpretationInput,
        output_type=ConditionalQuestionInterpretationOutput,
    )
