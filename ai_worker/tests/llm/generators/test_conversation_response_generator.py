from ai_worker.llm.generators.conversation_response_generator import (
    ConversationResponseGenerator,
    ConversationResponseInput,
    ConversationResponsePayload,
)


class StaticConversationResponseClient:
    def __init__(self, payload: ConversationResponsePayload) -> None:
        self._payload = payload

    async def ainvoke(self, messages):
        return self._payload


def vague_symptom_input() -> ConversationResponseInput:
    return ConversationResponseInput(
        question="아픈데 어떻게 해?",
        intent="VAGUE_SYMPTOM",
        follow_up_fields=["LOCATION", "ONSET", "SEVERITY"],
    )


def specific_symptom_input() -> ConversationResponseInput:
    return ConversationResponseInput(
        question="배가 아프고 속이 쓰려",
        intent="SPECIFIC_SYMPTOM",
        follow_up_fields=["ONSET", "SEVERITY"],
    )


async def test_vague_symptom_asks_follow_up_without_medication_claim() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(
            ConversationResponsePayload(
                answer="많이 불편하시겠어요. 어디가 언제부터 얼마나 아픈지 알려주실 수 있을까요?"
            )
        )
    )

    answer = await generator.generate(vague_symptom_input())

    assert "어디" in answer
    assert "언제부터" in answer
    assert "추천" not in answer
    assert "복용" not in answer


async def test_specific_symptom_requests_candidate_medicine_without_exposing_active_medications() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(
            ConversationResponsePayload(
                answer="현재 복용 중인 약과 함께 먹어도 되는지 확인하려면 추가로 복용하려는 약의 제품명 또는 성분명을 알려주세요."
            )
        )
    )

    answer = await generator.generate(specific_symptom_input())

    assert "🩺 **상호작용 확인을 위해 필요한 정보**" in answer
    assert "제품명 또는 성분명" in answer
    assert "복약정보" not in answer
    assert "리바록사반" not in answer


async def test_casual_response_never_exposes_active_medications() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(
            ConversationResponsePayload(answer="그랬군요. 어떤 점이 가장 신경 쓰이는지 말씀해 주세요.")
        )
    )
    input = ConversationResponseInput(
        question="오늘 기분이 별로야",
        intent="CASUAL",
    )

    answer = await generator.generate(input)

    assert "복약정보" not in answer
    assert "리바록사반" not in answer


def test_specific_symptom_fallback_requests_candidate_medicine_without_exposing_active_medications() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(ConversationResponsePayload(answer="사용하지 않습니다."))
    )

    answer = generator.fallback(specific_symptom_input())

    assert "제품명 또는 성분명" in answer
    assert "복약정보" not in answer
    assert "리바록사반" not in answer
    assert "복용하세요" not in answer
