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
당신은 퇴원 환자와 보호자가 복약 정보와
회복 지침을 쉽게 이해하도록 돕는 안내 도우미입니다.

다음 원칙을 반드시 지키세요.

1. 환자 확정 정보가 가장 높은 우선순위입니다.
2. 공공 가이드라인은 추가 설명에만 사용합니다.
3. 두 정보가 다르면 환자 확정 정보를 따릅니다.
4. 약의 용량, 횟수, 복용 시점과 환자 지침을
   임의로 변경하거나 추측하지 마세요.
5. 약을 시작, 중단 또는 변경하라고 지시하지 마세요.
6. 진단하거나 치료 방법을 결정하지 마세요.
7. 생활습관 안내는 일반적이고 위험이 낮은
   내용으로만 작성하세요.
8. 근거가 없는 내용은 생성하지 마세요.
9. 환자와 보호자가 이해하기 쉬운 한국어로 작성하세요.
10. 의료진의 진료를 대체하지 않는다는 안내를
    safety_notice에 포함하세요.
""".strip()


def build_recovery_guide_messages(
    patient_context: PatientContext,
    guideline_chunks: list[
        RetrievedGuidelineChunk
    ],
) -> list[BaseMessage]:
    patient_payload = {
        "diagnoses": patient_context.diagnoses,
        "medications": [
            {
                "drug_name": medication.drug_name,
                "dose": medication.dose,
                "frequency": medication.frequency,
                "duration": medication.duration,
                "administration_instruction": (
                    medication
                    .administration_instruction
                ),
            }
            for medication
            in patient_context.medications
        ],
        "instructions": [
            {
                "instruction_type": (
                    instruction
                    .instruction_type.value
                ),
                "content": instruction.content,
            }
            for instruction
            in patient_context.instructions
        ],
        "follow_up_schedules": [
            {
                "description": schedule.description,
                "scheduled_at": schedule.scheduled_at,
                "institution_name": (
                    schedule.institution_name
                ),
            }
            for schedule
            in patient_context.follow_up_schedules
        ],
    }

    public_payload = [
        {
            "vector_chunk_id": (
                chunk.vector_chunk_id
            ),
            "content": chunk.content,
            "similarity_score": (
                chunk.similarity_score
            ),
            "title": chunk.metadata.title,
            "organization": (
                chunk.metadata.organization
            ),
            "topic": chunk.metadata.topic,
            "page_number": (
                chunk.metadata.page_number
            ),
        }
        for chunk in guideline_chunks
    ]

    human_prompt = (
        "아래 환자 확정 정보와 공공 가이드라인을 "
        "바탕으로 구조화된 회복 가이드를 작성하세요.\n\n"
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
