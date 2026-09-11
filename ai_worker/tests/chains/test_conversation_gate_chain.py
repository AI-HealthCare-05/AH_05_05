import json

from ai_worker.chains.conversation_gate_chain import (
    ConversationGateInput,
    build_conversation_gate_chain,
)
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import ConversationClassification


class RecordingConversationGateClient:
    def __init__(self, payload: ConversationClassification) -> None:
        self._payload = payload
        self.rendered_history: list[dict[str, str]] = []

    async def ainvoke(self, messages):
        prompt = messages[-1].content
        history_json = prompt.split("최근 대화 JSON: ", maxsplit=1)[1].split("\n", maxsplit=1)[0]
        self.rendered_history = json.loads(history_json)
        return self._payload


def build_gate_input(history_count: int) -> ConversationGateInput:
    return ConversationGateInput(
        question="아픈데 어떻게 해?",
        recent_history=[
            ChatHistoryMessage(
                role="USER" if index % 2 == 0 else "ASSISTANT",
                content=f"대화 {index}",
            )
            for index in range(history_count)
        ],
    )


async def test_chain_sends_only_four_recent_messages_and_returns_structured_output() -> None:
    client = RecordingConversationGateClient(
        ConversationClassification(
            intent="VAGUE_SYMPTOM",
            safety_signal="NONE",
            confidence="HIGH",
            follow_up_fields=["LOCATION", "ONSET", "SEVERITY"],
        )
    )
    chain = build_conversation_gate_chain(
        model="gpt-4o-mini",
        client=client,
        max_history_messages=4,
    )

    output = await chain.ainvoke(build_gate_input(history_count=7))

    assert output.intent == "VAGUE_SYMPTOM"
    assert [message["content"] for message in client.rendered_history] == [
        "대화 3",
        "대화 4",
        "대화 5",
        "대화 6",
    ]
