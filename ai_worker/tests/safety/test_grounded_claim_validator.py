import pytest

from ai_worker.safety.grounded_claim_validator import (
    RuleBasedGroundedClaimValidator,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatResult,
    MedicationChatRoute,
)


def build_result(answer: str) -> MedicationChatResult:
    return MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer=answer,
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="medication-chat-prompt-v1",
        schema_version="medication-chat-result-v1",
    )


async def test_validator_replaces_medication_change_instruction() -> None:
    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1),
        result=build_result("오늘부터 약 복용을 중단하세요. 이 안내는 의료진의 진료를 대체하지 않습니다."),
    )

    assert result.safety_status == SafetyStatus.BLOCKED
    assert "중단하세요" not in result.answer
    assert "MEDICATION_CHANGE_INSTRUCTION" in result.safety_reason_codes


async def test_validator_restricts_answer_without_disclaimer() -> None:
    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1),
        result=build_result("제품 설명서의 주의사항을 확인하세요."),
    )

    assert result.safety_status == SafetyStatus.RESTRICTED
    assert "MISSING_MEDICAL_DISCLAIMER" in result.safety_reason_codes


async def test_validator_preserves_existing_restricted_status() -> None:
    initial = build_result("자료 검색에 실패했습니다. 이 안내는 의료진의 진료를 대체하지 않습니다.").model_copy(
        update={
            "safety_status": SafetyStatus.RESTRICTED,
            "safety_reason_codes": ["RAG_UNAVAILABLE"],
        }
    )

    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert result.safety_status == SafetyStatus.RESTRICTED
    assert result.safety_reason_codes == ["RAG_UNAVAILABLE"]


@pytest.mark.parametrize(
    "instruction",
    [
        "오늘부터 약을 끊으세요.",
        "오늘부터 복용량을 줄이세요.",
        "오늘부터 복용량을 늘리세요.",
    ],
)
async def test_validator_blocks_natural_korean_medication_change_imperatives(
    instruction: str,
) -> None:
    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1),
        result=build_result(f"{instruction} 이 안내는 의료진의 진료를 대체하지 않습니다."),
    )

    assert result.safety_status == SafetyStatus.BLOCKED
    assert instruction not in result.answer
    assert "MEDICATION_CHANGE_INSTRUCTION" in result.safety_reason_codes
