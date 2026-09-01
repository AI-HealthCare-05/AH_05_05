from datetime import date, datetime

from ai_worker.llm.assemblers.chat_answer_assembler import (
    ChatAnswerAssembler,
)
from ai_worker.schemas.chat import (
    ChatAnswerSupplement,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
)
from ai_worker.schemas.patient import (
    FollowUpSchedule,
    PatientContext,
    PatientInstruction,
    PatientMedication,
)


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
        surgery="혈관 내 치료",
        discharge_date=date(2026, 8, 10),
        medications=[
            PatientMedication(
                medication_id=101,
                name="아스피린",
                dose="1정",
                times_per_day=1,
                note="아침 식후 복용",
                days=7,
            )
        ],
        instructions=[
            PatientInstruction(
                care_advice_id=201,
                content="무리한 활동은 피하세요.",
                display_order=1,
            )
        ],
        follow_up_schedules=[
            FollowUpSchedule(
                follow_up_visit_id=301,
                visit_at=datetime(
                    2026,
                    8,
                    20,
                    10,
                    0,
                ),
                hospital="테스트병원",
            )
        ],
    )


def test_assemble_medication_uses_confirmed_fact_only() -> None:
    assembler = ChatAnswerAssembler()
    classification = ChatClassificationResult(
        intent=ChatIntent.MEDICATION,
        route=ChatRoute.PATIENT_ONLY,
        risk_level=ChatRiskLevel.LOW,
    )
    supplement = ChatAnswerSupplement(
        general_response=["아스피린 복용을 중단하세요."],
        public_information=["공공자료의 복약 설명"],
        lifestyle_guidance=["매일 두 시간 운동하세요."],
    )

    answer = assembler.assemble(
        patient_context=build_patient_context(),
        classification=classification,
        supplement=supplement,
    )

    assert ("아스피린 · 1정 · 1일 1회 · 아침 식후 복용 · 7일") in answer
    assert "중단하세요" not in answer
    assert "공공자료의 복약 설명" not in answer
    assert "매일 두 시간 운동하세요" not in answer
    assert "의료진의 진료를 대체하지 않습니다" in answer


def test_assemble_lifestyle_orders_information_sources() -> None:
    assembler = ChatAnswerAssembler()
    classification = ChatClassificationResult(
        intent=ChatIntent.LIFESTYLE,
        route=ChatRoute.PATIENT_AND_RAG,
        risk_level=ChatRiskLevel.CAUTION,
        normalized_query=("뇌졸중 퇴원 후 안전한 운동"),
    )
    supplement = ChatAnswerSupplement(
        public_information=["가벼운 활동부터 시작할 수 있습니다."],
        lifestyle_guidance=["피곤하면 쉬면서 활동하세요."],
    )

    answer = assembler.assemble(
        patient_context=build_patient_context(),
        classification=classification,
        supplement=supplement,
    )

    patient_index = answer.index("무리한 활동은 피하세요.")
    public_index = answer.index("가벼운 활동부터 시작할 수 있습니다.")
    ai_index = answer.index("피곤하면 쉬면서 활동하세요.")

    assert patient_index < public_index < ai_index
    assert "환자 확정정보" in answer
    assert "검색 근거 추가 설명" in answer
    assert "AI 생성 일반 안내" in answer
    assert "참고용 정보" in answer


def test_assemble_general_does_not_expose_patient_facts() -> None:
    assembler = ChatAnswerAssembler()
    classification = ChatClassificationResult(
        intent=ChatIntent.GENERAL,
        route=ChatRoute.GENERAL_GUIDANCE,
        risk_level=ChatRiskLevel.LOW,
    )

    answer = assembler.assemble(
        patient_context=build_patient_context(),
        classification=classification,
        supplement=ChatAnswerSupplement(general_response=["안녕하세요. 무엇을 도와드릴까요?"]),
    )

    assert "안녕하세요" in answer
    assert "뇌졸중" not in answer
    assert "아스피린" not in answer


def test_assemble_follow_up_uses_confirmed_schedule() -> None:
    assembler = ChatAnswerAssembler()
    classification = ChatClassificationResult(
        intent=ChatIntent.FOLLOW_UP,
        route=ChatRoute.PATIENT_ONLY,
        risk_level=ChatRiskLevel.LOW,
    )

    answer = assembler.assemble(
        patient_context=build_patient_context(),
        classification=classification,
        supplement=ChatAnswerSupplement(),
    )

    assert "2026-08-20 10:00 · 테스트병원" in answer
