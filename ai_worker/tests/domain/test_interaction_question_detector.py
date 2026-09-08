import pytest

from ai_worker.domain.interaction_question_detector import (
    is_interaction_question,
)


@pytest.mark.parametrize(
    "question",
    [
        "성분 하나랑 성분 둘 먹어도 돼?",
        "첫 번째와 두 번째를 먹어도 되나요?",
    ],
)
def test_detects_relation_question_without_explicit_interaction_keyword(
    question: str,
) -> None:
    assert is_interaction_question(question)


def test_does_not_detect_single_target_intake_question_as_interaction() -> None:
    assert not is_interaction_question("이 영양제는 먹어도 돼?")
