from importlib import import_module

from ai_worker.llm.prompts.chat_answer_prompt import (
    CHAT_ANSWER_PROMPT_VERSION,
    build_chat_answer_messages,
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
from ai_worker.schemas.patient import PatientContext


def test_prompt_asset_loader_is_independent_of_working_directory(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    module = import_module("ai_worker.llm.prompts.prompt_assets")
    module.load_prompt_asset.cache_clear()

    persona = module.load_prompt_asset("medication_knowledge_coach_persona.md")

    assert "친절한 임상영양사" in persona
    assert "스스로 판단" in persona
    assert "추측하지" in persona


def test_chat_answer_prompt_uses_versioned_persona_and_principles() -> None:
    messages = build_chat_answer_messages(
        request=ChatAnswerRequest(
            request_id="chat-request-1",
            user_id=1,
            care_episode_id=100,
            condition="STROKE",
            question="퇴원 후 운동은 어떻게 시작해?",
        ),
        patient_context=PatientContext(
            user_id=1,
            care_episode_id=100,
            confirmation_hash="a" * 64,
            diagnoses=["뇌졸중"],
        ),
        classification=ChatClassificationResult(
            intent=ChatIntent.LIFESTYLE,
            route=ChatRoute.PATIENT_AND_RAG,
            risk_level=ChatRiskLevel.LOW,
            normalized_query="뇌졸중 퇴원 후 안전한 운동",
        ),
        guideline_chunks=[],
    )

    system_prompt = str(messages[0].content)

    assert CHAT_ANSWER_PROMPT_VERSION == ("chat-answer-prompt-v3")
    assert "친절한 임상영양사" in system_prompt
    assert "환자 확정정보가 가장 높은 우선순위" in system_prompt
    assert "복용 결정을 대신하지" in system_prompt
    assert "검색된 근거" in system_prompt
    assert "간결하고 명확" in system_prompt
    assert "근거가 없으면 추측" in system_prompt
