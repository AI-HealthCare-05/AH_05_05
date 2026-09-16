import pytest

from ai_worker.domain.urgent_health_signal_policy import UrgentHealthSignalPolicy


def test_explicit_breathing_difficulty_is_caught_without_llm() -> None:
    assert UrgentHealthSignalPolicy().evaluate("가슴이 심하게 아프고 숨이 잘 안 쉬어져") is True


def test_systemic_allergic_reaction_is_caught_without_llm() -> None:
    assert UrgentHealthSignalPolicy().evaluate("약 먹고 입술이 붓고 온몸에 두드러기가 났어") is True


def test_normal_greeting_is_not_treated_as_health_urgency() -> None:
    assert UrgentHealthSignalPolicy().evaluate("안녕하세요") is False


def test_slurred_speech_is_caught_without_llm() -> None:
    assert UrgentHealthSignalPolicy().evaluate("갑자기 발음이 어눌해졌어요") is True


@pytest.mark.parametrize(
    "question",
    [
        "증상을 말하기 어려워요",
        "부작용이 뭔지 말하기 힘들어요",
        "약 이름이 말이 안 나와요",
        "어이가 없어서 말이 안 나와요",
    ],
)
def test_ordinary_speech_expressions_are_not_treated_as_health_urgency(question: str) -> None:
    """복약 상담에서 정상적으로 나오는 표현이 응급 경로를 가로채면 안 된다."""

    assert UrgentHealthSignalPolicy().evaluate(question) is False
