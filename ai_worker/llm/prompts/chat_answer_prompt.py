import json

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from ai_worker.llm.prompts.prompt_assets import (
    CHAT_ANSWER_PRINCIPLES,
    LIFESTYLE_MEDICINE_COACH_PERSONA,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
)
from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext

CHAT_ANSWER_PROMPT_VERSION = "chat-answer-prompt-v2"

SYSTEM_PROMPT = "\n\n".join(
    (
        LIFESTYLE_MEDICINE_COACH_PERSONA,
        CHAT_ANSWER_PRINCIPLES,
    )
)


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
