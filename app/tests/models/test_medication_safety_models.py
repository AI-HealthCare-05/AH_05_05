from app.models.enums import (
    ChatSourceType,
    MedicationSafetyRuleType,
    SafetyComparisonOperator,
    SafetyConditionKind,
)


def test_medication_safety_enums_define_supported_rules() -> None:
    assert {item.value for item in MedicationSafetyRuleType} == {
        "PREGNANCY_CONTRAINDICATION",
        "AGE_CONTRAINDICATION",
        "ELDERLY_CAUTION",
        "DOSE_CAUTION",
        "DURATION_CAUTION",
        "DAILY_MAX_DOSE",
        "EXCIPIENT_CAUTION",
    }
    assert SafetyConditionKind.DAILY_DOSE.value == "DAILY_DOSE"
    assert SafetyComparisonOperator.BETWEEN.value == "BETWEEN"
    assert ChatSourceType.MEDICATION_SAFETY_RULE.value == (
        "MEDICATION_SAFETY_RULE"
    )
