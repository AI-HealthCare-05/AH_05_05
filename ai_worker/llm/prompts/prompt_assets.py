from functools import cache
from importlib.resources import files

_ALLOWED_PROMPT_ASSETS = frozenset(
    {
        "chat_answer_principles.md",
        "medication_knowledge_coach_persona.md",
    }
)


@cache
def load_prompt_asset(asset_name: str) -> str:
    if asset_name not in _ALLOWED_PROMPT_ASSETS:
        raise ValueError(f"허용되지 않은 프롬프트 자산입니다: {asset_name}")

    content = files("ai_worker.llm.prompts").joinpath("assets", asset_name).read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError(f"프롬프트 자산은 비어 있을 수 없습니다: {asset_name}")

    return content


MEDICATION_KNOWLEDGE_COACH_PERSONA = load_prompt_asset("medication_knowledge_coach_persona.md")
CHAT_ANSWER_PRINCIPLES = load_prompt_asset("chat_answer_principles.md")
