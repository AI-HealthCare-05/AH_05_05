import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ai_worker.llm.prompts.prompt_assets import load_prompt_template_document
from ai_worker.schemas.intake_report import IntakeReportDraft

INTAKE_REPORT_PROMPT_VERSION = "intake-report-prompt-v1"

PROMPT_DOCUMENT = load_prompt_template_document("intake_report_prompt_v1.md")
SYSTEM_PROMPT = PROMPT_DOCUMENT.system
USER_PROMPT_TEMPLATE = PROMPT_DOCUMENT.user
ASSISTANT_EXAMPLE = PROMPT_DOCUMENT.assistant_example


def build_intake_report_messages(
    *,
    draft: IntakeReportDraft,
) -> list[BaseMessage]:
    payload = {
        "data_availability": draft.data_availability.model_dump(mode="json"),
        "executive_summary": draft.executive_summary.model_dump(mode="json"),
        "current_stack": [item.model_dump(mode="json") for item in draft.current_stack],
        "review_cards": [card.model_dump(mode="json") for card in draft.review_cards],
        "product_guides": [guide.model_dump(mode="json") for guide in draft.product_guides],
        "unverified_items": [item.model_dump(mode="json") for item in draft.unverified_items],
        "sources": [source.model_dump(mode="json") for source in draft.sources],
        "deterministic_markdown": draft.deterministic_markdown,
    }
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=USER_PROMPT_TEMPLATE.format(
                payload_json=json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        ),
    ]
