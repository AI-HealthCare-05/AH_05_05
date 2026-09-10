from dataclasses import dataclass
from functools import cache
from importlib.resources import files

_ALLOWED_PROMPT_ASSETS = frozenset(
    {
        "medication_chat_prompt_v3.md",
        "medication_chat_prompt_v4.md",
        "intake_report_prompt_v1.md",
    }
)


@dataclass(frozen=True)
class PromptTemplateDocument:
    system: str
    user: str
    assistant_example: str


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
    def extract(section_name: str) -> str:
        start_marker = f"<!-- prompt:{section_name}:start -->"
        end_marker = f"<!-- prompt:{section_name}:end -->"
        if content.count(start_marker) != 1 or content.count(end_marker) != 1:
            raise ValueError(f"프롬프트 구역 표시는 각각 한 번만 있어야 합니다: {section_name}")
        start_index = content.index(start_marker) + len(start_marker)
        end_index = content.index(end_marker, start_index)
        section = content[start_index:end_index].strip()
        if not section:
            raise ValueError(f"프롬프트 구역은 비어 있을 수 없습니다: {section_name}")
        return section

    return PromptTemplateDocument(
        system=extract("system"),
        user=extract("user"),
        assistant_example=extract("assistant_example"),
    )


@cache
def load_prompt_template_document(
    asset_name: str,
) -> PromptTemplateDocument:
    return parse_prompt_template_document(
        load_prompt_asset(asset_name),
    )
