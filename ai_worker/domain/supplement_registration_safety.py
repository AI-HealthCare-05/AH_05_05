from collections import defaultdict
from decimal import Decimal

from ai_worker.schemas.medication_chat import (
    MedicationChatRiskFlag,
    SupplementRegistrationIngredient,
    SupplementRegistrationSafetyInput,
    SupplementRegistrationSafetyResult,
    SupplementRegistrationSafetyStatus,
    SupplementRegistrationTotalAmount,
)


class SupplementRegistrationSafetyEvaluator:
    """LLM 없이 신규 영양제 등록 전 안전성 판단을 수행한다."""

    def evaluate(
        self,
        value: SupplementRegistrationSafetyInput,
    ) -> SupplementRegistrationSafetyResult:
        proposed_names = {self._normalized(ingredient.name) for ingredient in value.proposed_ingredients}
        existing_names = {self._normalized(ingredient.name) for ingredient in value.existing_ingredients}
        duplicate_names = self._duplicate_names(
            proposed=value.proposed_ingredients,
            existing_names=existing_names,
        )
        total_amounts, totals_are_computable = self._total_amounts(
            ingredients=[
                *value.proposed_ingredients,
                *value.existing_ingredients,
            ],
        )
        matched_rule_ids = self._matched_rule_ids(
            proposed_names=proposed_names,
            existing_names=existing_names,
            approved_rules=value.approved_rules,
        )
        reason_codes = self._reason_codes(
            has_duplicates=bool(duplicate_names),
            has_matched_rules=bool(matched_rule_ids),
            totals_are_computable=totals_are_computable,
            risk_flags=list(value.risk_profile.model_dump().values()),
        )
        return SupplementRegistrationSafetyResult(
            status=self._status(reason_codes),
            duplicate_ingredient_names=duplicate_names,
            total_amounts=total_amounts,
            matched_rule_ids=matched_rule_ids,
            reason_codes=reason_codes,
        )

    @classmethod
    def _duplicate_names(
        cls,
        *,
        proposed: list[SupplementRegistrationIngredient],
        existing_names: set[str],
    ) -> list[str]:
        return list(
            dict.fromkeys(
                ingredient.name for ingredient in proposed if cls._normalized(ingredient.name) in existing_names
            )
        )

    @classmethod
    def _total_amounts(
        cls,
        *,
        ingredients: list[SupplementRegistrationIngredient],
    ) -> tuple[list[SupplementRegistrationTotalAmount], bool]:
        grouped: dict[str, list[SupplementRegistrationIngredient]] = defaultdict(list)
        for ingredient in ingredients:
            grouped[cls._normalized(ingredient.name)].append(ingredient)

        totals: list[SupplementRegistrationTotalAmount] = []
        computable = True
        for group in grouped.values():
            amounts = [ingredient.amount for ingredient in group]
            units = {ingredient.unit.casefold() for ingredient in group if ingredient.unit is not None}
            if None in amounts or any(ingredient.unit is None for ingredient in group) or len(units) != 1:
                computable = False
                continue
            totals.append(
                SupplementRegistrationTotalAmount(
                    name=group[0].name,
                    amount=sum(amounts, Decimal("0")),
                    unit=group[0].unit or "",
                )
            )
        return totals, computable

    @classmethod
    def _matched_rule_ids(
        cls,
        *,
        proposed_names: set[str],
        existing_names: set[str],
        approved_rules,
    ) -> list[int]:
        available = proposed_names.union(existing_names)
        matched: list[int] = []
        for rule in approved_rules:
            rule_names = {
                cls._normalized(rule.left_name),
                cls._normalized(rule.right_name),
            }
            if (
                rule_names.issubset(available)
                and rule_names.intersection(proposed_names)
                and rule_names.intersection(existing_names)
            ):
                matched.append(rule.interaction_rule_id)
        return list(dict.fromkeys(matched))

    @staticmethod
    def _reason_codes(
        *,
        has_duplicates: bool,
        has_matched_rules: bool,
        totals_are_computable: bool,
        risk_flags: list[MedicationChatRiskFlag],
    ) -> list[str]:
        reasons: list[str] = []
        if has_duplicates:
            reasons.append("DUPLICATE_INGREDIENT")
        if has_matched_rules:
            reasons.append("APPROVED_INTERACTION_RULE")
        if MedicationChatRiskFlag.YES in risk_flags:
            reasons.append("HIGH_RISK_PROFILE")
        if not totals_are_computable:
            reasons.append("AMOUNT_OR_UNIT_MISSING")
        if MedicationChatRiskFlag.UNKNOWN in risk_flags:
            reasons.append("RISK_PROFILE_UNKNOWN")
        return reasons

    @staticmethod
    def _status(reason_codes: list[str]) -> SupplementRegistrationSafetyStatus:
        if {
            "DUPLICATE_INGREDIENT",
            "APPROVED_INTERACTION_RULE",
            "HIGH_RISK_PROFILE",
        }.intersection(reason_codes):
            return SupplementRegistrationSafetyStatus.RESTRICTED
        if reason_codes:
            return SupplementRegistrationSafetyStatus.UNKNOWN
        return SupplementRegistrationSafetyStatus.SAFE

    @staticmethod
    def _normalized(value: str) -> str:
        return "".join(value.casefold().split())
