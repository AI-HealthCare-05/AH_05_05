import pytest

from ai_worker.rag.query_builders.chat_query_builder import (
    ChatQueryBuilder,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRoute,
)


def build_request() -> ChatAnswerRequest:
    return ChatAnswerRequest(
        request_id="chat-request-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        care_phase="POST_DISCHARGE",
        question="퇴원 후 운동은 어떻게 해야 해?",
    )


def build_rag_classification(
    intent: ChatIntent,
) -> ChatClassificationResult:
    return ChatClassificationResult(
        intent=intent,
        route=ChatRoute.PATIENT_AND_RAG,
        risk_level=ChatRiskLevel.CAUTION,
        normalized_query=("뇌졸중 퇴원 후 안전한 운동과 활동"),
    )


@pytest.mark.parametrize(
    (
        "intent",
        "expected_topic",
    ),
    [
        (
            ChatIntent.MEDICATION,
            "MEDICATION",
        ),
        (
            ChatIntent.WARNING_SIGN,
            "WARNING_SIGN",
        ),
        (
            ChatIntent.LIFESTYLE,
            "LIFESTYLE",
        ),
        (
            ChatIntent.PATIENT_FACT,
            None,
        ),
    ],
)
def test_build_maps_intent_to_guideline_topic(
    intent: ChatIntent,
    expected_topic: str | None,
) -> None:
    builder = ChatQueryBuilder()

    result = builder.build(
        request=build_request(),
        classification=(build_rag_classification(intent)),
        limit=5,
    )

    assert result.query == ("뇌졸중 퇴원 후 안전한 운동과 활동")
    assert result.condition == "STROKE"
    assert result.care_phase == "POST_DISCHARGE"
    assert result.topic == expected_topic
    assert result.limit == 5


def test_build_accepts_custom_search_limit() -> None:
    builder = ChatQueryBuilder()

    result = builder.build(
        request=build_request(),
        classification=(build_rag_classification(ChatIntent.LIFESTYLE)),
        limit=3,
    )

    assert result.limit == 3


def test_build_rejects_non_rag_route() -> None:
    builder = ChatQueryBuilder()
    classification = ChatClassificationResult(
        intent=ChatIntent.MEDICATION,
        route=ChatRoute.PATIENT_ONLY,
        risk_level=ChatRiskLevel.LOW,
    )

    with pytest.raises(
        ValueError,
        match="PATIENT_AND_RAG",
    ):
        builder.build(
            request=build_request(),
            classification=classification,
        )


@pytest.mark.parametrize(
    "limit",
    [
        0,
        21,
    ],
)
def test_build_rejects_invalid_search_limit(
    limit: int,
) -> None:
    builder = ChatQueryBuilder()

    with pytest.raises(ValueError):
        builder.build(
            request=build_request(),
            classification=(build_rag_classification(ChatIntent.LIFESTYLE)),
            limit=limit,
        )
