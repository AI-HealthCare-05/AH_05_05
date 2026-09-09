from ai_worker.domain.fatigue_conversation_policy import (
    FatigueConversationDisposition,
    FatigueConversationPolicy,
)


def test_routes_general_fatigue_to_question_first_guidance_without_product_recommendation() -> None:
    result = FatigueConversationPolicy().evaluate("요즘 계속 피곤해요")

    assert result is not None
    assert result.disposition == FatigueConversationDisposition.FOLLOW_UP
    assert "현재 복용 중인 약과 영양제" in result.answer
    assert "추천" not in result.answer
    assert "복용량" not in result.answer
    assert "진단" not in result.answer


def test_routes_fatigue_with_red_flags_to_urgent_assistance_boundary() -> None:
    result = FatigueConversationPolicy().evaluate("피곤하고 숨이 차며 실신할 것 같아요")

    assert result is not None
    assert result.disposition == FatigueConversationDisposition.URGENT
    assert "119" in result.answer
    assert "영양제" not in result.answer


def test_ignores_non_fatigue_medication_question() -> None:
    assert FatigueConversationPolicy().evaluate("타이레놀 복용법을 알려줘") is None
