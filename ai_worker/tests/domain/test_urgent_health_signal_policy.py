from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy


def test_explicit_breathing_difficulty_is_caught_without_llm() -> None:
    assert UrgentHealthSignalPolicy().evaluate("가슴이 심하게 아프고 숨이 잘 안 쉬어져") is True


def test_normal_greeting_is_not_treated_as_health_urgency() -> None:
    assert UrgentHealthSignalPolicy().evaluate("안녕하세요") is False
