from typing import Any

from langchain_core.messages import HumanMessage
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
    format_repair_answer: str | None = None


def _validate_answer_input(
    value: MedicationAnswerChainInput | dict[str, Any],
) -> MedicationAnswerChainInput:
    if isinstance(value, MedicationAnswerChainInput):
        return value
    return MedicationAnswerChainInput.model_validate(value)


def _build_answer_messages(value: MedicationAnswerChainInput):
    messages = build_medication_chat_messages(
        request=value.request,
        context=value.context,
        result=value.result,
    )
    if value.format_repair_answer is None:
        return messages
    return [
        *messages,
        HumanMessage(
            content=(
                "[형식 보정]\n"
                "아래 생성 답변을 같은 근거 범위에서 다시 작성하세요. 원문을 인용하거나 "
                "문장을 잘라내지 말고 의미를 요약하세요. 각 bullet은 10어절 이내로 작성하고, "
                "섹션당 3개를 넘기지 마세요.\n"
                "상호작용은 질문한 pair의 직접 관계만 남기고, 제3 성분·비교 연구·참고문헌은 "
                "제외하세요. 부작용 보고서는 이상사례와 질문에 직접 관련된 경위만 남기세요.\n"
                "기능성 원료 질문은 성분명과 확인된 기능만 남기고 일반 건강 설명은 제외하세요.\n\n"
                "[보정 대상 답변]\n"
                f"{value.format_repair_answer.strip()}"
            )
        ),
    ]


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
