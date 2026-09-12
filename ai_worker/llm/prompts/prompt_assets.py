from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib.resources import files

MEDICATION_CHAT_PROMPT_CHAIN_ASSET = "medication_chat_prompt_v7.md"

_ALLOWED_PROMPT_ASSETS = frozenset(
    {
        "medication_chat_prompt_v3.md",
        "medication_chat_prompt_v4.md",
        "medication_chat_prompt_v5.md",
        "medication_chat_prompt_v6.md",
        MEDICATION_CHAT_PROMPT_CHAIN_ASSET,
        "conversation_gate_prompt_v1.md",
        "conversation_response_prompt_v1.md",
        "medication_note_summary_prompt_v1.md",
        "intake_report_prompt_v1.md",
        "intake_report_prompt_v11.md",
        "intake_report_plain_language.md",
        "intake_report_plain_language_review.md",
    }
)


@dataclass(frozen=True)
class PromptTemplateDocument:
    system: str
    user: str
    assistant_example: str


class MedicationPromptStage(StrEnum):
    CONVERSATION_GATE = "conversation_gate"
    DIRECTIONAL_QUERY = "directional_query"
    EVIDENCE_REASONING = "evidence_reasoning"
    ANSWER_GENERATION = "answer_generation"
    CONVERSATION_RESPONSE = "conversation_response"
    MEDICATION_NOTE_SUMMARY = "medication_note_summary"


@dataclass(frozen=True)
class PromptChainStageDocument:
    common: str
    system: str
    user: str
    examples: str

    @property
    def compiled_system(self) -> str:
        return "\n\n".join(
            (
                self.common,
                self.system,
                "[예시(Example)]\n" + self.examples,
            )
        )


@cache
def load_prompt_asset(asset_name: str) -> str:
    if asset_name not in _ALLOWED_PROMPT_ASSETS:
        raise ValueError(f"허용되지 않은 프롬프트 자산입니다: {asset_name}")

    content = files("ai_worker.llm.prompts").joinpath("assets", asset_name).read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError(f"프롬프트 자산은 비어 있을 수 없습니다: {asset_name}")

    return content


def parse_prompt_template_document(
    content: str,
) -> PromptTemplateDocument:
    return PromptTemplateDocument(
        system=_extract_prompt_section(content, marker_name="system"),
        user=_extract_prompt_section(content, marker_name="user"),
        assistant_example=_extract_prompt_section(
            content,
            marker_name="assistant_example",
        ),
    )


def _extract_prompt_section(
    content: str,
    *,
    marker_name: str,
) -> str:
    start_marker = f"<!-- prompt:{marker_name}:start -->"
    end_marker = f"<!-- prompt:{marker_name}:end -->"
    if content.count(start_marker) != 1 or content.count(end_marker) != 1:
        raise ValueError(f"프롬프트 구역 표시는 각각 한 번만 있어야 합니다: {marker_name}")
    start_index = content.index(start_marker) + len(start_marker)
    end_index = content.index(end_marker, start_index)
    section = content[start_index:end_index].strip()
    if not section:
        raise ValueError(f"프롬프트 구역은 비어 있을 수 없습니다: {marker_name}")
    return section


def parse_prompt_chain_stage_document(
    content: str,
    stage: MedicationPromptStage,
) -> PromptChainStageDocument:
    return PromptChainStageDocument(
        common=_extract_prompt_section(
            content,
            marker_name="common:system",
        ),
        system=_extract_prompt_section(
            content,
            marker_name=f"{stage.value}:system",
        ),
        user=_extract_prompt_section(
            content,
            marker_name=f"{stage.value}:user",
        ),
        examples=_extract_prompt_section(
            content,
            marker_name=f"{stage.value}:examples",
        ),
    )


@cache
def load_prompt_template_document(
    asset_name: str,
) -> PromptTemplateDocument:
    return parse_prompt_template_document(
        load_prompt_asset(asset_name),
    )


@cache
def load_prompt_chain_stage(
    stage: MedicationPromptStage,
    asset_name: str = MEDICATION_CHAT_PROMPT_CHAIN_ASSET,
) -> PromptChainStageDocument:
    return parse_prompt_chain_stage_document(
        load_prompt_asset(asset_name),
        stage,
    )
