from ai_worker.schemas.medication_chat import (
    MedicationChatAnswerDomain,
    MedicationChatRiskDecision,
    MedicationChatRiskFlag,
    MedicationChatRiskProfile,
    MedicationChatRiskScope,
)


class MedicationChatRiskPolicy:
    """개인화 위험정보가 부족할 때 답변 범위를 보수적으로 결정한다."""

    _RISK_FLAGS: tuple[tuple[str, str], ...] = (
        ("pregnancy", "PREGNANCY_STATUS"),
        ("breastfeeding", "BREASTFEEDING_STATUS"),
        ("minor", "MINOR_STATUS"),
        ("older_adult", "OLDER_ADULT_STATUS"),
        ("kidney_disease", "KIDNEY_DISEASE_STATUS"),
        ("liver_disease", "LIVER_DISEASE_STATUS"),
        ("scheduled_surgery", "SCHEDULED_SURGERY"),
        ("anticoagulant_use", "ANTICOAGULANT_USE"),
    )

    def evaluate(
        self,
        *,
        profile: MedicationChatRiskProfile,
        domain: MedicationChatAnswerDomain,
        asks_for_personalized_guidance: bool,
    ) -> MedicationChatRiskDecision:
        default_scope = self._default_scope(domain)
        if domain == MedicationChatAnswerDomain.LIFESTYLE:
            return MedicationChatRiskDecision(domain=domain, scope=default_scope)

        risk_reason = self._first_vulnerable_risk_reason(
            profile,
            include_unknown=False,
        )
        if risk_reason is None:
            if not asks_for_personalized_guidance:
                return MedicationChatRiskDecision(domain=domain, scope=default_scope)
            risk_reason = self._first_vulnerable_risk_reason(
                profile,
                include_unknown=True,
            )
        if risk_reason is None:
            return MedicationChatRiskDecision(domain=domain, scope=default_scope)
        return MedicationChatRiskDecision(
            domain=domain,
            scope=MedicationChatRiskScope.WARNING_REQUIRED,
            reason_codes=[risk_reason],
        )

    @staticmethod
    def _default_scope(domain: MedicationChatAnswerDomain) -> MedicationChatRiskScope:
        if domain == MedicationChatAnswerDomain.MEDICATION:
            return MedicationChatRiskScope.EVIDENCE_ONLY
        if domain == MedicationChatAnswerDomain.SUPPLEMENT:
            return MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE
        return MedicationChatRiskScope.GENERAL_GUIDANCE_ONLY

    def _first_vulnerable_risk_reason(
        self,
        profile: MedicationChatRiskProfile,
        *,
        include_unknown: bool,
    ) -> str | None:
        for field_name, reason_prefix in self._RISK_FLAGS:
            value = getattr(profile, field_name)
            if value == MedicationChatRiskFlag.YES:
                return f"{reason_prefix}_YES"
            if include_unknown and value == MedicationChatRiskFlag.UNKNOWN:
                return f"{reason_prefix}_UNKNOWN"
        return None
