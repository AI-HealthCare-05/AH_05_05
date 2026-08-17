from ai_worker.safety.output_safety_validator import (
    RuleBasedOutputSafetyValidator,
)
from ai_worker.schemas.enums import (
    InstructionType,
    SafetyStatus,
)
from ai_worker.schemas.guide import (
    RecoveryGuideContent,
    RecoveryGuideResult,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientInstruction,
)


def build_patient_context(
    *,
    instructions: list[
        PatientInstruction
    ] | None = None,
) -> PatientContext:
    return PatientContext(
        user_id=1,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
        instructions=instructions or [],
    )


def build_result(
    *,
    medication_guide: list[str] | None = None,
    patient_instructions: list[str] | None = None,
    lifestyle_guide: list[str] | None = None,
    safety_notice: str = (
        "이 안내는 의료진의 진료를 "
        "대체하지 않습니다."
    ),
) -> RecoveryGuideResult:
    return RecoveryGuideResult(
        care_episode_id=100,
        guide_content=RecoveryGuideContent(
            medication_guide=(
                medication_guide or []
            ),
            patient_instructions=(
                patient_instructions or []
            ),
            public_information=[],
            lifestyle_guide=(
                lifestyle_guide or []
            ),
            warning_signs=[],
            follow_up_schedule=[],
            safety_notice=safety_notice,
        ),
        safety_status=SafetyStatus.PENDING,
    )


async def test_validate_returns_safe_for_safe_guide() -> None:
    validator = (
        RuleBasedOutputSafetyValidator()
    )
    result = build_result(
        medication_guide=[
            "처방받은 방법대로 복용하세요.",
            "임의로 약을 중단하지 마세요.",
        ],
        lifestyle_guide=[
            "충분히 쉬고 무리하지 마세요."
        ],
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.SAFE
    )
    assert safety_result.reason_codes == []


async def test_validate_blocks_medication_change_instruction() -> None:
    validator = (
        RuleBasedOutputSafetyValidator()
    )
    result = build_result(
        medication_guide=[
            "오늘부터 아스피린 복용을 중단하세요."
        ]
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.BLOCKED
    )
    assert (
        "MEDICATION_CHANGE_INSTRUCTION"
        in safety_result.reason_codes
    )


async def test_validate_blocks_new_diagnostic_assertion() -> None:
    validator = (
        RuleBasedOutputSafetyValidator()
    )
    result = build_result(
        patient_instructions=[
            "현재 증상은 폐렴으로 진단됩니다."
        ]
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.BLOCKED
    )
    assert (
        "DIAGNOSTIC_ASSERTION"
        in safety_result.reason_codes
    )


async def test_validate_blocks_treatment_decision() -> None:
    validator = (
        RuleBasedOutputSafetyValidator()
    )
    result = build_result(
        patient_instructions=[
            "현재 상태에는 수술이 필요합니다."
        ]
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.BLOCKED
    )
    assert (
        "TREATMENT_DECISION"
        in safety_result.reason_codes
    )


async def test_validate_restricts_missing_safety_notice() -> None:
    validator = (
        RuleBasedOutputSafetyValidator()
    )
    result = build_result(
        medication_guide=[
            "처방받은 방법대로 복용하세요."
        ],
        safety_notice="참고용 안내입니다.",
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.RESTRICTED
    )
    assert (
        "MISSING_MEDICAL_DISCLAIMER"
        in safety_result.reason_codes
    )


async def test_validate_allows_confirmed_patient_instruction() -> None:
    confirmed_instruction = PatientInstruction(
        instruction_type=(
            InstructionType.DISCHARGE_INSTRUCTION
        ),
        content=(
            "의료진 지시에 따라 아스피린 "
            "복용을 중단하세요."
        ),
        source_field_id=1001,
    )
    patient_context = build_patient_context(
        instructions=[confirmed_instruction]
    )
    result = build_result(
        patient_instructions=[
            confirmed_instruction.content
        ]
    )
    validator = (
        RuleBasedOutputSafetyValidator()
    )

    safety_result = await validator.validate(
        patient_context=patient_context,
        result=result,
    )

    assert (
        safety_result.status
        == SafetyStatus.SAFE
    )
    assert safety_result.reason_codes == []
