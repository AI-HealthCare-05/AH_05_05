from decimal import Decimal

from ai_worker.domain.supplement_registration_safety import (
    SupplementRegistrationSafetyEvaluator,
)
from ai_worker.schemas.medication_chat import (
    InteractionRuleFact,
    MedicationChatRiskFlag,
    MedicationChatRiskProfile,
    SupplementRegistrationIngredient,
    SupplementRegistrationSafetyInput,
    SupplementRegistrationSafetyStatus,
)


def ingredient(
    name: str,
    amount: str | None,
    unit: str | None,
) -> SupplementRegistrationIngredient:
    return SupplementRegistrationIngredient(
        name=name,
        amount=Decimal(amount) if amount is not None else None,
        unit=unit,
    )


def test_restricts_duplicate_ingredient_and_calculates_same_unit_total() -> None:
    result = SupplementRegistrationSafetyEvaluator().evaluate(
        SupplementRegistrationSafetyInput(
            proposed_ingredients=[ingredient("마그네슘", "100", "mg")],
            existing_ingredients=[ingredient("마그네슘", "200", "mg")],
            risk_profile=MedicationChatRiskProfile.all_no(),
        )
    )

    assert result.status == SupplementRegistrationSafetyStatus.RESTRICTED
    assert result.duplicate_ingredient_names == ["마그네슘"]
    assert result.total_amounts[0].amount == Decimal("300")
    assert result.total_amounts[0].unit == "mg"


def test_restricts_when_an_approved_rule_matches_proposed_and_existing_ingredient() -> None:
    result = SupplementRegistrationSafetyEvaluator().evaluate(
        SupplementRegistrationSafetyInput(
            proposed_ingredients=[ingredient("비타민 K", "100", "mcg")],
            existing_ingredients=[ingredient("와파린", "1", "정")],
            approved_rules=[
                InteractionRuleFact(
                    interaction_rule_id=1,
                    pair_key="warfarin-vitamin-k",
                    pair_type="DRUG_SUPPLEMENT",
                    left_name="와파린",
                    right_name="비타민 K",
                    risk_level="HIGH",
                    effect_texts=["승인 규칙"],
                )
            ],
            risk_profile=MedicationChatRiskProfile.all_no(),
        )
    )

    assert result.status == SupplementRegistrationSafetyStatus.RESTRICTED
    assert result.matched_rule_ids == [1]


def test_marks_unknown_when_ingredient_amount_or_unit_is_missing() -> None:
    result = SupplementRegistrationSafetyEvaluator().evaluate(
        SupplementRegistrationSafetyInput(
            proposed_ingredients=[ingredient("오메가3", None, None)],
            existing_ingredients=[],
            risk_profile=MedicationChatRiskProfile.all_no(),
        )
    )

    assert result.status == SupplementRegistrationSafetyStatus.UNKNOWN
    assert result.reason_codes == ["AMOUNT_OR_UNIT_MISSING"]


def test_restricts_high_risk_profile_without_asking_an_llm_to_decide() -> None:
    profile_values = {field: MedicationChatRiskFlag.NO for field in MedicationChatRiskProfile.model_fields}
    profile_values["scheduled_surgery"] = MedicationChatRiskFlag.YES
    result = SupplementRegistrationSafetyEvaluator().evaluate(
        SupplementRegistrationSafetyInput(
            proposed_ingredients=[ingredient("오메가3", "1000", "mg")],
            existing_ingredients=[],
            risk_profile=MedicationChatRiskProfile(**profile_values),
        )
    )

    assert result.status == SupplementRegistrationSafetyStatus.RESTRICTED
    assert result.reason_codes == ["HIGH_RISK_PROFILE"]
