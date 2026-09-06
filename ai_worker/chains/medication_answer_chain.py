from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict

from ai_worker.llm.prompts.medication_chat_prompt import (
    build_medication_chat_messages,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationAnswerPayload,
    MedicationChatRequest,
    MedicationChatResult,
)


class MedicationAnswerChainInput(BaseModel):
    """근거 기반 답변 정제 체인이 받는 구조화 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: MedicationChatRequest
    context: ActiveIntakeContext
    result: MedicationChatResult


def _validate_answer_input(
    value: MedicationAnswerChainInput | dict[str, Any],
) -> MedicationAnswerChainInput:
    if isinstance(value, MedicationAnswerChainInput):
        return value
    return MedicationAnswerChainInput.model_validate(value)


def _build_answer_messages(value: MedicationAnswerChainInput):
    return build_medication_chat_messages(
        request=value.request,
        context=value.context,
        result=value.result,
    )


def _validate_answer_payload(
    value: MedicationAnswerPayload | dict[str, Any],
) -> MedicationAnswerPayload:
    if isinstance(value, MedicationAnswerPayload):
        return value
    return MedicationAnswerPayload.model_validate(value)


def build_medication_answer_chain(
    *,
    response_runnable: Runnable,
) -> Runnable:
    """구조화 입력 → 프롬프트 → 구조화 출력 LCEL 체인을 만든다."""

    input_validator = RunnableLambda(_validate_answer_input).with_config(
        run_name="medication.answer.input",
    )
    prompt_builder = RunnableLambda(_build_answer_messages).with_config(
        run_name="medication.answer.prompt",
    )
    output_validator = RunnableLambda(_validate_answer_payload).with_config(
        run_name="medication.answer.output",
    )
    return (input_validator | prompt_builder | response_runnable | output_validator).with_types(
        input_type=MedicationAnswerChainInput,
        output_type=MedicationAnswerPayload,
    )
