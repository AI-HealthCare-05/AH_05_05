import json

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from ai_worker.schemas.guideline import (
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import PatientContext

SYSTEM_PROMPT = """
당신은 퇴원 환자와 보호자가 공공 의료자료와
일반적인 생활관리 정보를 쉽게 이해하도록 돕는
안내 도우미입니다.

다음 원칙을 반드시 지키세요.

1. 환자 확정 정보가 가장 높은 우선순위입니다.
2. 공공 가이드라인은 추가 설명에만 사용합니다.
3. 환자 확정 정보와 공공자료가 다르면
   환자 확정 정보를 따릅니다.
4. public_information에는 제공된 공공자료의
   내용을 쉬운 한국어로 설명합니다.
5. lifestyle_guide에는 진단이나 치료 판단이
   필요하지 않은 일반적이고 위험이 낮은
   생활관리 안내만 작성합니다.
6. 약의 시작, 중단, 변경, 용량, 횟수 또는
   복용 시점을 지시하지 마세요.
7. 새로운 진단을 내리거나 치료 방법을
   결정하지 마세요.
8. 제공된 근거가 부족하면 해당 목록을
   빈 목록으로 반환하세요.
9. 환자 확정 복약정보, 의료진 권고사항,
   진료 일정은 생성하거나 수정하지 마세요.
10. 출력은 public_information과
    lifestyle_guide 두 필드만 포함합니다.
""".strip()


def build_recovery_guide_messages(
    patient_context: PatientContext,
    guideline_chunks: list[RetrievedGuidelineChunk],
) -> list[BaseMessage]:
    patient_payload = {
        "diagnoses": patient_context.diagnoses,
        "surgery": patient_context.surgery,
        "medication_names": [medication.name for medication in patient_context.medications],
        "confirmed_instructions": [instruction.content for instruction in patient_context.instructions],
    }

    public_payload = [
        {
            "vector_chunk_id": (chunk.vector_chunk_id),
            "content": chunk.content,
            "similarity_score": (chunk.similarity_score),
            "title": chunk.metadata.title,
            "organization": (chunk.metadata.organization),
            "topic": chunk.metadata.topic,
            "page_number": (chunk.metadata.page_number),
        }
        for chunk in guideline_chunks
    ]

    human_prompt = (
        "아래 환자 확정 정보와 공공 가이드라인을 "
        "참고하여 보충정보만 작성하세요.\n\n"
        "출력 필드:\n"
        "- public_information\n"
        "- lifestyle_guide\n\n"
        "[환자 확정 정보]\n"
        f"{json.dumps(patient_payload, ensure_ascii=False, indent=2)}"
        "\n\n"
        "[공공 가이드라인]\n"
        f"{json.dumps(public_payload, ensure_ascii=False, indent=2)}"
    )

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ]
