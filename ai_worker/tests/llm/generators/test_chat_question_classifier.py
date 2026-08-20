from typing import Any

import pytest

from ai_worker.llm.generators.chat_question_classifier import (
    ChatClassificationError,
    OpenAIChatQuestionClassifier,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
    ChatHistoryMessage,
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRiskLevel,
    ChatRole,
    ChatRoute,
)


class FakeClassificationClient:
    def __init__(
        self,
        response: (ChatClassificationResult | dict[str, Any]),
    ) -> None:
        self._response = response
        self.received_messages: list[Any] = []

    async def ainvoke(
        self,
        messages: Any,
    ) -> ChatClassificationResult | dict[str, Any]:
        self.received_messages = list(messages)

        return self._response


class FailingClassificationClient:
    async def ainvoke(
        self,
        messages: Any,
    ) -> ChatClassificationResult:
        raise RuntimeError("OpenAI 질문 분류 호출 실패")


def build_request(
    question: str = "퇴원 후 운동은 어떻게 해야 해?",
) -> ChatAnswerRequest:
    return ChatAnswerRequest(
        request_id="chat-request-1",
        user_id=1,
        care_episode_id=100,
        condition="STROKE",
        question=question,
        history=[
            ChatHistoryMessage(
                role=ChatRole.USER,
                content="아스피린 복용법을 알려줘.",
            ),
            ChatHistoryMessage(
                role=ChatRole.ASSISTANT,
                content="확정된 복약정보를 안내했어요.",
            ),
        ],
    )


async def test_classify_returns_structured_result() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=FakeClassificationClient(
            response=ChatClassificationResult(
                intent=ChatIntent.LIFESTYLE,
                route=ChatRoute.PATIENT_AND_RAG,
                risk_level=ChatRiskLevel.CAUTION,
                normalized_query=("뇌졸중 퇴원 후 안전한 운동과 활동"),
            )
        ),
    )

    result = await classifier.classify(
        request=build_request(),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    assert result.intent == ChatIntent.LIFESTYLE
    assert result.route == ChatRoute.PATIENT_AND_RAG
    assert result.risk_level == ChatRiskLevel.CAUTION
    assert result.normalized_query == ("뇌졸중 퇴원 후 안전한 운동과 활동")


async def test_classify_does_not_lower_rule_based_high_risk() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=FakeClassificationClient(
            response=ChatClassificationResult(
                intent=ChatIntent.MEDICATION,
                route=ChatRoute.PATIENT_ONLY,
                risk_level=ChatRiskLevel.LOW,
            )
        ),
    )

    result = await classifier.classify(
        request=build_request("아스피린을 끊어도 돼?"),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.HIGH,
            reason_codes=[
                "MEDICATION_CHANGE_REQUEST",
            ],
        ),
    )

    assert result.risk_level == ChatRiskLevel.HIGH
    assert result.route == ChatRoute.RESTRICTED
    assert result.normalized_query is None
    assert result.reason_codes == [
        "MEDICATION_CHANGE_REQUEST",
    ]


async def test_classify_forces_llm_high_risk_to_restricted() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=FakeClassificationClient(
            response=ChatClassificationResult(
                intent=ChatIntent.WARNING_SIGN,
                route=ChatRoute.GENERAL_GUIDANCE,
                risk_level=ChatRiskLevel.HIGH,
                reason_codes=[
                    "SYMPTOM_JUDGMENT_REQUEST",
                ],
            )
        ),
    )

    result = await classifier.classify(
        request=build_request("이 증상이 위험한 상태인지 판단해줘."),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    assert result.risk_level == ChatRiskLevel.HIGH
    assert result.route == ChatRoute.RESTRICTED
    assert result.reason_codes == [
        "SYMPTOM_JUDGMENT_REQUEST",
    ]


async def test_classify_builds_prompt_with_question_and_history() -> None:
    fake_client = FakeClassificationClient(
        response=ChatClassificationResult(
            intent=ChatIntent.MEDICATION,
            route=ChatRoute.PATIENT_ONLY,
            risk_level=ChatRiskLevel.LOW,
        )
    )
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=fake_client,
    )

    await classifier.classify(
        request=build_request("그 약은 언제 먹어?"),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    prompt_text = " ".join(str(message.content) for message in fake_client.received_messages)

    assert "아스피린 복용법을 알려줘." in prompt_text
    assert "그 약은 언제 먹어?" in prompt_text
    assert "PATIENT_AND_RAG" in prompt_text
    assert "normalized_query" in prompt_text


async def test_classify_accepts_dictionary_response() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=FakeClassificationClient(
            response={
                "intent": "FOLLOW_UP",
                "route": "PATIENT_ONLY",
                "risk_level": "LOW",
                "normalized_query": None,
                "reason_codes": [],
                "needs_clarification": False,
            }
        ),
    )

    result = await classifier.classify(
        request=build_request("다음 진료는 언제야?"),
        minimum_risk=ChatInputRiskResult(
            risk_level=ChatRiskLevel.LOW,
        ),
    )

    assert result.intent == ChatIntent.FOLLOW_UP
    assert result.route == ChatRoute.PATIENT_ONLY


def test_classifier_rejects_blank_model_name() -> None:
    with pytest.raises(
        ValueError,
        match="모델명",
    ):
        OpenAIChatQuestionClassifier(
            model="   ",
            client=FakeClassificationClient(
                response={
                    "intent": "GENERAL",
                    "route": "GENERAL_GUIDANCE",
                    "risk_level": "LOW",
                }
            ),
        )


async def test_classify_converts_client_failure_to_classification_error() -> None:
    classifier = OpenAIChatQuestionClassifier(
        model="gpt-4o-mini",
        client=FailingClassificationClient(),
    )

    with pytest.raises(
        ChatClassificationError,
        match="질문 분류",
    ) as exc_info:
        await classifier.classify(
            request=build_request(),
            minimum_risk=ChatInputRiskResult(
                risk_level=ChatRiskLevel.LOW,
            ),
        )

    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )q
