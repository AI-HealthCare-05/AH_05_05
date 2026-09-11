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


def specific_symptom_input(active_medication_names: list[str]) -> ConversationResponseInput:
    return ConversationResponseInput(
        question="배가 아프고 속이 쓰려",
        intent="SPECIFIC_SYMPTOM",
        follow_up_fields=["ONSET", "SEVERITY"],
        active_medication_names=active_medication_names,
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


async def test_specific_symptom_shows_only_clean_active_medication_names() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(
            ConversationResponsePayload(answer="증상이 시작된 시점과 통증 정도를 알려주세요.")
        )
    )

    answer = await generator.generate(
        specific_symptom_input(active_medication_names=["리바록사반정(항응고제)"])
    )

    assert "💊 **복약정보**" in answer
    assert "- 리바록사반정" in answer
    assert "(항응고제)" not in answer


async def test_casual_response_never_exposes_active_medications() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(
            ConversationResponsePayload(answer="그랬군요. 어떤 점이 가장 신경 쓰이는지 말씀해 주세요.")
        )
    )
    input = ConversationResponseInput(
        question="오늘 기분이 별로야",
        intent="CASUAL",
        active_medication_names=["리바록사반정"],
    )

    answer = await generator.generate(input)

    assert "복약정보" not in answer
    assert "리바록사반" not in answer


def test_specific_symptom_fallback_keeps_medication_names_without_medical_claim() -> None:
    generator = ConversationResponseGenerator(
        client=StaticConversationResponseClient(ConversationResponsePayload(answer="사용하지 않습니다."))
    )

    answer = generator.fallback(
        specific_symptom_input(active_medication_names=["리바록사반정(항응고제)"])
    )

    assert "💊 **복약정보**" in answer
    assert "- 리바록사반정" in answer
    assert "복용하세요" not in answer
