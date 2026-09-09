from ai_worker.domain.medication_dose_question_policy import (
    MedicationDoseQuestionKind,
    MedicationDoseQuestionPolicy,
)


def test_classifies_official_daily_limit_question() -> None:
    decision = MedicationDoseQuestionPolicy().classify(
        "타이레놀은 하루 최대 몇 정까지 먹을 수 있나요?",
    )

    assert decision.kind == MedicationDoseQuestionKind.OFFICIAL_REFERENCE


def test_classifies_personal_dose_increase_as_confirmation_required() -> None:
    decision = MedicationDoseQuestionPolicy().classify(
        "두통이 심한데 타이레놀을 평소보다 두 배 먹어도 될까?",
    )

    assert decision.kind == MedicationDoseQuestionKind.PERSONAL_CHANGE


def test_classifies_already_taken_extra_dose_as_possible_overdose() -> None:
    decision = MedicationDoseQuestionPolicy().classify(
        "실수로 타이레놀을 평소보다 두 배 먹었어.",
    )

    assert decision.kind == MedicationDoseQuestionKind.POSSIBLE_OVERDOSE
