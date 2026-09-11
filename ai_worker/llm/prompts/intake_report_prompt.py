import json

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ai_worker.llm.prompts.prompt_assets import load_prompt_template_document
from ai_worker.schemas.intake_report import IntakeReportDraft

INTAKE_REPORT_PROMPT_VERSION = "intake-report-prompt-v11"

PROMPT_DOCUMENT = load_prompt_template_document("intake_report_prompt_v11.md")
SYSTEM_PROMPT = PROMPT_DOCUMENT.system
USER_PROMPT_TEMPLATE = PROMPT_DOCUMENT.user
ASSISTANT_EXAMPLE = PROMPT_DOCUMENT.assistant_example


def build_intake_report_messages(
    *,
    draft: IntakeReportDraft,
) -> list[BaseMessage]:
    payload = draft.model_dump(mode="json")
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
