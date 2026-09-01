import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ai_worker.llm.prompts.prompt_assets import (
    CHAT_ANSWER_PRINCIPLES,
    MEDICATION_KNOWLEDGE_COACH_PERSONA,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatRequest,
    MedicationChatResult,
)

MEDICATION_CHAT_PROMPT_VERSION = "medication-chat-prompt-v2"

SYSTEM_PROMPT = "\n\n".join(
    (
        MEDICATION_KNOWLEDGE_COACH_PERSONA,
        CHAT_ANSWER_PRINCIPLES,
        (
            "아래 초안에 이미 포함된 사실만 자연스러운 한국어로 정리하세요. "
            "새로운 제품명, 성분, 용량, 효능, 부작용, 상호작용 또는 안전 "
            "결론을 추가하지 마세요. 의료 면책 문구는 유지하세요.\n"
            "제품 질문에는 질문과 직접 관련된 핵심 항목을 먼저 쓰고, 제품명만 "
            "입력한 경우에는 효능, 사용법, 핵심 주의사항을 간결하게 정리하세요. "
            "함께 주의할 약·음식은 초안에 실제 내용이 있을 때만 출력하고 빈 항목은 "
            "출력하지 마세요. 보관법처럼 질문하지 않은 부가정보는 꼭 필요한 경우가 "
            "아니면 생략하세요. 각 항목은 한두 문장으로 요약하세요.\n"
            "상호작용 질문은 초안의 연구 근거가 두 질문 성분을 모두 다룰 때만 "
            "설명하세요. 연구의 대상과 한계를 유지하고, 근거에 없는 복용 간격·용량 "
            "또는 안전 결론을 만들어내지 마세요. 동물·세포 연구를 사람에게 확인된 "
            "결론처럼 표현하지 마세요.\n"
            "정확 제품의 RDBMS 안내를 우선하고, 성분 계열 일반 정보가 함께 "
            "있더라도 제품별 효능·사용법·주의사항과 충돌하는 내용은 출력하지 "
            "마세요. 성분 계열 일반 정보는 개인 처방이 아니라는 점과 제품·복합제별 "
            "차이를 유지하세요. 영어 자료는 원문을 그대로 붙이지 말고 한국어로 "
            "핵심만 요약하세요. 효능·복용법·주의사항 중 초안에 근거가 없는 항목은 "
            "만들지 말고 확인하지 못했다고 분명히 표현하세요.\n"
            "답변에는 #, ** 같은 Markdown 기호를 사용하지 말고 일반 텍스트 제목과 "
            "`사용법:`, `주의사항:` 같은 짧은 항목명만 사용하세요."
        ),
    )
)


def build_medication_chat_messages(
    *,
    request: MedicationChatRequest,
    context: ActiveIntakeContext,
    result: MedicationChatResult,
) -> list[BaseMessage]:
    payload = {
        "question": request.question,
        "history": [message.model_dump(mode="json") for message in request.history],
        "active_medication_names": [item.name for item in context.medications],
        "active_supplement_names": [item.name for item in context.supplements],
        "draft_answer": result.answer,
        "source_titles": [source.title for source in result.sources],
        "route": result.route.value,
    }
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        ),
    ]
