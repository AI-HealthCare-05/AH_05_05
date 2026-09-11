import json

import pytest
from pydantic import ValidationError

from ai_worker.chains.conversation_gate_chain import (
    ConversationGateInput,
    build_conversation_gate_chain,
)
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import ConversationClassification
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope


class RecordingConversationGateClient:
    def __init__(self, payload: ConversationClassification) -> None:
        self._payload = payload
        self.rendered_history: list[dict[str, str]] = []
        self.rendered_prompt = ""
        self.rendered_system_prompt = ""

    async def ainvoke(self, messages):
        prompt = messages[-1].content
        self.rendered_system_prompt = messages[0].content
        self.rendered_prompt = prompt
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


def test_classification_accepts_follow_up_schedule_intent() -> None:
    output = ConversationClassification.model_validate(
        {
            "intent": "FOLLOW_UP_SCHEDULE",
            "safety_signal": "NONE",
            "confidence": "HIGH",
        }
    )

    assert output.intent.value == "FOLLOW_UP_SCHEDULE"


def test_classification_accepts_recent_medication_note_summary_scope() -> None:
    output = ConversationClassification.model_validate(
        {
            "intent": "MEDICATION_NOTE_SUMMARY",
            "safety_signal": "NONE",
            "confidence": "HIGH",
            "note_summary_scope": "RECENT_SIX_MONTHS",
        }
    )

    assert output.note_summary_scope is MedicationNoteSummaryScope.RECENT_SIX_MONTHS


def test_note_summary_intent_requires_a_scope() -> None:
    with pytest.raises(ValidationError, match="note_summary_scope"):
        ConversationClassification(
            intent="MEDICATION_NOTE_SUMMARY",
            safety_signal="NONE",
            confidence="HIGH",
        )


async def test_chain_sends_note_summary_scope_instructions_to_model() -> None:
    client = RecordingConversationGateClient(
        ConversationClassification.model_validate(
            {
                "intent": "MEDICATION_NOTE_SUMMARY",
                "safety_signal": "NONE",
                "confidence": "HIGH",
                "note_summary_scope": "ALL_HISTORY",
            }
        )
    )
    chain = build_conversation_gate_chain(
        model="gpt-4o-mini",
        client=client,
    )

    await chain.ainvoke(
        ConversationGateInput(question="전체 복약메모를 진료용으로 정리해줘"),
    )

    assert "MEDICATION_NOTE_SUMMARY" in client.rendered_system_prompt
    assert "ALL_HISTORY" in client.rendered_system_prompt
