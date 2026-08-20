from ai_worker.safety.chat_output_safety_validator import (
    RuleBasedChatOutputSafetyValidator,
)
from ai_worker.schemas.chat import (
    ChatAnswerResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
    SafetyStatus,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientMedication,
)


def build_patient_context() -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
    )


def build_result(
    answer: str,
) -> ChatAnswerResult:
    return ChatAnswerResult(
        request_id="chat-request-1",
        care_episode_id=100,
        answer=answer,
        intent=ChatIntent.MEDICATION,
        route=ChatRoute.PATIENT_ONLY,
        risk_level=ChatRiskLevel.LOW,
        safety_status=SafetyStatus.PENDING,
        patient_context_hash="a" * 64,
        model_name="gpt-4o-mini",
        prompt_version=("chat-answer-prompt-v1"),
        schema_version=("chat-answer-result-v1"),
    )


async def test_validate_blocks_medication_change_instruction() -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(
        answer=("오늘부터 아스피린 복용을 중단하세요.\n\n이 안내는 의료진의 진료를 대체하지 않습니다.")
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in safety_result.reason_codes


async def test_validate_blocks_new_diagnostic_assertion() -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=("현재 증상은 폐렴으로 진단됩니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "DIAGNOSTIC_ASSERTION" in safety_result.reason_codes


async def test_validate_blocks_treatment_decision() -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=("현재 상태에는 수술이 필요합니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "TREATMENT_DECISION" in safety_result.reason_codes


async def test_validate_restricts_missing_medical_disclaimer() -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=("퇴원 후에는 무리하지 말고 충분히 쉬세요."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.RESTRICTED
    assert "MISSING_MEDICAL_DISCLAIMER" in safety_result.reason_codes


async def test_validate_blocks_patient_medication_mismatch() -> None:
    patient_context = PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
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
    )
    result = build_result(
        answer=(
            "환자 확정정보\n"
            "- 아스피린 · 2정 · 1일 1회 · "
            "아침 식후 복용 · 7일\n\n"
            "이 안내는 의료진의 진료를 "
            "대체하지 않습니다."
        )
    )
    validator = RuleBasedChatOutputSafetyValidator()

    safety_result = await validator.validate(
        patient_context=patient_context,
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "PATIENT_MEDICATION_MISMATCH" in safety_result.reason_codes
