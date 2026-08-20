import json

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
)
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext

CHAT_ANSWER_PROMPT_VERSION = "chat-answer-prompt-v1"

SYSTEM_PROMPT = """
당신은 퇴원 환자와 보호자가 저장된 환자정보와
공공 의료자료를 쉽게 이해하도록 돕는 안내 도우미입니다.

다음 원칙을 반드시 지키세요.

1. 환자 확정정보가 가장 높은 우선순위입니다.
2. 공공자료는 환자 확정정보를 보충하는 설명에만 사용합니다.
3. 환자 확정정보를 생성하거나 수정하지 마세요.
4. 약의 시작, 중단, 변경, 용량 또는 복용 횟수를 지시하지 마세요.
5. 새로운 진단을 내리거나 치료 방법을 결정하지 마세요.
6. public_information은 제공된 공공자료에서만 작성하세요.
7. lifestyle_guidance는 위험이 낮은 일반 생활관리 안내만 작성하세요.
8. general_response는 일반적인 대화 응답에만 사용하세요.
9. 근거가 부족한 항목은 빈 목록으로 반환하세요.
10. 안전 안내 문구는 생성하지 마세요.
11. 출력에는 다음 세 필드만 포함하세요.
    - general_response
    - public_information
    - lifestyle_guidance
""".strip()


def build_chat_answer_messages(
    request: ChatAnswerRequest,
    patient_context: PatientContext,
    classification: ChatClassificationResult,
    guideline_chunks: list[RetrievedGuidelineChunk],
) -> list[BaseMessage]:
    request_payload = {
        "question": request.question,
        "history": [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in request.history
        ],
    }

    classification_payload = {
        "intent": classification.intent.value,
        "route": (classification.route.value if classification.route is not None else None),
        "risk_level": (classification.risk_level.value),
        "normalized_query": (classification.normalized_query),
    }

    patient_payload = {
        "diagnoses": patient_context.diagnoses,
        "surgery": patient_context.surgery,
        "medication_names": [medication.name for medication in (patient_context.medications)],
        "confirmed_instructions": [instruction.content for instruction in (patient_context.instructions)],
    }

    public_payload = [
        {
            "vector_chunk_id": (chunk.vector_chunk_id),
            "content": chunk.content,
            "similarity_score": (chunk.similarity_score),
            "title": chunk.metadata.title,
            "organization": (chunk.metadata.organization),
            "topic": chunk.metadata.topic,
            "section_title": (chunk.metadata.section_title),
            "page_number": (chunk.metadata.page_number),
        }
        for chunk in guideline_chunks
    ]

    human_prompt = (
        "아래 질문과 분류 결과를 바탕으로 "
        "허용된 보충정보만 작성하세요.\n\n"
        "[질문과 이전 대화]\n"
        f"{json.dumps(request_payload, ensure_ascii=False, indent=2)}"
        "\n\n"
        "[질문 분류 결과]\n"
        f"{json.dumps(classification_payload, ensure_ascii=False, indent=2)}"
        "\n\n"
        "[환자 확정정보]\n"
        f"{json.dumps(patient_payload, ensure_ascii=False, indent=2)}"
        "\n\n"
        "[검색된 공공자료]\n"
        f"{json.dumps(public_payload, ensure_ascii=False, indent=2)}"
    )

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ]
