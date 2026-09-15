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
                "가능하면 6어절 안팎으로 줄이세요. 약명과 대상 목록도 포함해 공백 단위로 세고, "
                "10개를 초과하는 문장은 중복 수식어를 덜어 다시 쓰세요. "
                "숫자·가능성 표현·주의 이유는 유지하세요. 공식 복용 중단·상담 지시는 초안 표현을 그대로 보존하고, "
                "증상 목록과 부연 설명을 요약하세요. "
                "섹션당 최대 5개로 정리하세요. 소제목과 목록 사이, 섹션 사이에는 빈 줄을 두세요.\n"
                "section_types는 입력의 covered_section_types 안에서만 선택하세요. "
                "covered_section_types가 빈 목록이면 section_types도 빈 목록으로 반환하고, "
                "초안의 소제목을 유지하면서 실제로 있는 사실만 짧은 bullet로 요약하세요. "
                "초안에 🧬 **약과 상호작용**, 🍗 **그 외 상호작용**이 있으면 "
                "근거가 있는 각 제목과 해당 관계를 그대로 유지해 요약하세요. "
                "evidence_reasoning이 null인 탐색 답변도 초안의 승인 규칙·검색 근거를 사용합니다. "
                "초안이 ✉️ **안내사항**이면 그 아래에 요약하세요. "
                "섹션이 미분류되었다는 이유로 자료가 없다고 바꾸거나 새 의료 정보를 보태지 마세요.\n"
                "원문 키워드 목록·목차·항목 번호는 제외하고 띄어쓰기를 복원하세요. "
                "질문한 pair가 있으면 그 직접 관계만, 단일 약물 질문이면 그 약과 직접 관련된 사실만 남기세요. "
                "비교 연구·참고문헌은 제외하세요. "
                "부작용 보고서는 이상사례와 질문에 직접 관련된 경위만 남기세요.\n"
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
