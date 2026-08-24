import pytest

from ai_worker.safety.chat_input_risk_classifier import (
    RuleBasedChatInputRiskClassifier,
)
from ai_worker.schemas.enums import ChatRiskLevel


@pytest.mark.parametrize(
    (
        "question",
        "reason_code",
    ),
    [
        (
            "아스피린을 오늘부터 끊어도 돼?",
            "MEDICATION_CHANGE_REQUEST",
        ),
        (
            "약 복용량을 늘려도 될까?",
            "MEDICATION_CHANGE_REQUEST",
        ),
        (
            "제가 뇌졸중인지 진단해줘.",
            "DIAGNOSIS_REQUEST",
        ),
        (
            "수술을 받아야 하는지 결정해줘.",
            "TREATMENT_DECISION_REQUEST",
        ),
        (
            "가슴이 아프고 숨을 쉬기 힘들어.",
            "EMERGENCY_SYMPTOM",
        ),
    ],
)
def test_assess_marks_explicit_high_risk_question(
    question: str,
    reason_code: str,
) -> None:
    classifier = RuleBasedChatInputRiskClassifier()

    result = classifier.assess(question)

    assert result.risk_level == ChatRiskLevel.HIGH
    assert reason_code in result.reason_codes


@pytest.mark.parametrize(
    "question",
    [
        "아스피린은 언제 먹어?",
        "다음 외래 진료는 언제야?",
        "퇴원 후 운동 방법을 알려줘.",
        "내 진단명을 알려줘.",
    ],
)
def test_assess_keeps_information_question_low(
    question: str,
) -> None:
    classifier = RuleBasedChatInputRiskClassifier()

    result = classifier.assess(question)

    assert result.risk_level == ChatRiskLevel.LOW
    assert result.reason_codes == []


def test_assess_collects_multiple_risk_reasons() -> None:
    classifier = RuleBasedChatInputRiskClassifier()

    result = classifier.assess("약을 끊고 수술을 받아야 하는지도 결정해줘.")

    assert result.risk_level == ChatRiskLevel.HIGH
    assert result.reason_codes == [
        "MEDICATION_CHANGE_REQUEST",
        "TREATMENT_DECISION_REQUEST",
    ]


def test_assess_rejects_blank_question() -> None:
    classifier = RuleBasedChatInputRiskClassifier()

    with pytest.raises(
        ValueError,
        match="질문",
    ):
        classifier.assess("   ")
