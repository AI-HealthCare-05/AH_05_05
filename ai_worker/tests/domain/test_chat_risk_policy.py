from ai_worker.domain.chat_risk_policy import MedicationChatRiskPolicy
from ai_worker.schemas.medication_chat import (
    MedicationChatAnswerDomain,
    MedicationChatRiskFlag,
    MedicationChatRiskProfile,
    MedicationChatRiskScope,
)


def test_unknown_pregnancy_status_restricts_personalized_supplement_guidance() -> None:
    decision = MedicationChatRiskPolicy().evaluate(
        profile=MedicationChatRiskProfile(),
        domain=MedicationChatAnswerDomain.SUPPLEMENT,
        asks_for_personalized_guidance=True,
    )

    assert decision.scope == MedicationChatRiskScope.WARNING_REQUIRED
    assert decision.reason_codes == ["PREGNANCY_STATUS_UNKNOWN"]


def test_explicit_no_risk_flags_allow_general_supplement_guidance() -> None:
    decision = MedicationChatRiskPolicy().evaluate(
        profile=MedicationChatRiskProfile.all_no(),
        domain=MedicationChatAnswerDomain.SUPPLEMENT,
        asks_for_personalized_guidance=True,
    )

    assert decision.scope == MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE
    assert decision.reason_codes == []


def test_medication_facts_remain_evidence_only_even_without_vulnerable_risk() -> None:
    decision = MedicationChatRiskPolicy().evaluate(
        profile=MedicationChatRiskProfile.all_no(),
        domain=MedicationChatAnswerDomain.MEDICATION,
        asks_for_personalized_guidance=False,
    )

    assert decision.scope == MedicationChatRiskScope.EVIDENCE_ONLY
    assert decision.reason_codes == []


def test_confirmed_scheduled_surgery_requires_warning_for_supplement_guidance() -> None:
    decision = MedicationChatRiskPolicy().evaluate(
        profile=MedicationChatRiskProfile(
            pregnancy=MedicationChatRiskFlag.NO,
            breastfeeding=MedicationChatRiskFlag.NO,
            minor=MedicationChatRiskFlag.NO,
            older_adult=MedicationChatRiskFlag.NO,
            kidney_disease=MedicationChatRiskFlag.NO,
            liver_disease=MedicationChatRiskFlag.NO,
            scheduled_surgery=MedicationChatRiskFlag.YES,
            anticoagulant_use=MedicationChatRiskFlag.NO,
        ),
        domain=MedicationChatAnswerDomain.SUPPLEMENT,
        asks_for_personalized_guidance=True,
    )

    assert decision.scope == MedicationChatRiskScope.WARNING_REQUIRED
    assert decision.reason_codes == ["SCHEDULED_SURGERY_YES"]
