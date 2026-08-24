import pytest

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


async def test_validate_blocks_new_diagnosis_even_when_confirmed_diagnosis_is_mentioned() -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(
        answer=(
            "기존 진단명은 뇌졸중입니다. 현재 증상은 폐렴으로 진단됩니다.\n\n"
            "이 안내는 의료진의 진료를 대체하지 않습니다."
        )
    )

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "DIAGNOSTIC_ASSERTION" in safety_result.reason_codes


@pytest.mark.parametrize(
    "answer",
    [
        "아스피린을 안 먹어도 됩니다.",
        "아스피린 복용을 건너뛰세요.",
        "아스피린 용량을 증량하세요.",
        "아스피린 용량을 감량하세요.",
        "아스피린 복용을\n중단하세요.",
    ],
)
async def test_validate_blocks_medication_change_variants(
    answer: str,
) -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=(f"{answer}\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in safety_result.reason_codes


@pytest.mark.parametrize(
    "answer",
    [
        "처방받은 약을 임의로 중단하지 마세요.",
        "약을 임의로 변경하지 마세요.",
        "복용량을 임의로 줄이지 마세요.",
        "처방받은 약을 임의로 중단하\n지 마세요.",
    ],
)
async def test_validate_allows_medication_safety_warning(
    answer: str,
) -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=(f"{answer}\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.SAFE
    assert safety_result.reason_codes == []


@pytest.mark.parametrize(
    "answer",
    [
        "약을 중단해야 합니다.",
        "약을 중단 하세요.",
        "약을 중단\n하세요.",
        "약 용량을 증량\n해야 합니다.",
        "약 용량을 감량해야 합니다.",
        ("약을 임의로 중단하지 마세요. 하지만 내일부터 감량하세요."),
    ],
)
async def test_validate_blocks_explicit_medication_change_directive(
    answer: str,
) -> None:
    validator = RuleBasedChatOutputSafetyValidator()
    result = build_result(answer=(f"{answer}\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await validator.validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in (safety_result.reason_codes)


@pytest.mark.parametrize(
    "answer",
    [
        "약을 중단해도 됩니다.",
        "약을 중단해 주세요.",
        "약을 건너뛰어도 됩니다.",
        "약 용량을 줄여도 됩니다.",
        "약을 중단해도\n됩니다.",
    ],
)
async def test_validate_blocks_medication_change_permission_or_request(
    answer: str,
) -> None:
    result = build_result(answer=(f"{answer}\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await RuleBasedChatOutputSafetyValidator().validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in (safety_result.reason_codes)


@pytest.mark.parametrize(
    "answer",
    [
        "약을 중단하셔도 됩니다.",
        "약 용량을 줄이셔야 합니다.",
        "약을 변경하시기 바랍니다.",
        "약을 중단하셔도\n됩니다.",
    ],
)
async def test_validate_blocks_honorific_medication_change_directive(
    answer: str,
) -> None:
    result = build_result(answer=(f"{answer}\n\n이 안내는 의료진의 진료를 대체하지 않습니다."))

    safety_result = await RuleBasedChatOutputSafetyValidator().validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in (safety_result.reason_codes)


async def test_validate_allows_non_medication_permission() -> None:
    result = build_result(
        answer=(
            "약을 임의로 중단하지 마세요. 운동은 하지 않아도 됩니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."
        )
    )

    safety_result = await RuleBasedChatOutputSafetyValidator().validate(
        patient_context=build_patient_context(),
        result=result,
    )

    assert safety_result.status == SafetyStatus.SAFE
    assert safety_result.reason_codes == []


async def test_validate_blocks_directive_for_confirmed_medication_name() -> None:
    patient_context = PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
        medications=[
            PatientMedication(
                medication_id=101,
                name="와파린",
                dose="1정",
                times_per_day=1,
                days=7,
            )
        ],
    )
    result = build_result(answer=("와파린을 중단하세요.\n\n이 안내는 의료진의 진료를 대체하지 않습니다.")).model_copy(
        update={
            "intent": ChatIntent.LIFESTYLE,
            "route": ChatRoute.PATIENT_AND_RAG,
        }
    )

    safety_result = await RuleBasedChatOutputSafetyValidator().validate(
        patient_context=patient_context,
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in (safety_result.reason_codes)


async def test_validate_blocks_cross_sentence_medication_directive() -> None:
    patient_context = PatientContext(
        user_id=1,
        care_episode_id=100,
        confirmation_hash="a" * 64,
        diagnoses=["뇌졸중"],
        medications=[
            PatientMedication(
                medication_id=101,
                name="와파린",
                dose="1정",
                times_per_day=1,
                days=7,
            )
        ],
    )
    result = build_result(
        answer=(
            "와파린은 현재 복용 중입니다. 내일부터 중단해도 됩니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."
        )
    ).model_copy(
        update={
            "intent": ChatIntent.LIFESTYLE,
            "route": ChatRoute.PATIENT_AND_RAG,
        }
    )

    safety_result = await RuleBasedChatOutputSafetyValidator().validate(
        patient_context=patient_context,
        result=result,
    )

    assert safety_result.status == SafetyStatus.BLOCKED
    assert "MEDICATION_CHANGE_INSTRUCTION" in (safety_result.reason_codes)


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
