import json
import re

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ai_worker.llm.prompts.prompt_assets import (
    MedicationPromptStage,
    load_prompt_chain_stage,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)

MEDICATION_CHAT_PROMPT_VERSION = "medication-chat-prompt-v7"

_DOSAGE_VALUE_PATTERN = re.compile(
    r"\d+(?:\s*[|,./~–-]\s*\d+)*\s*"
    r"(?:mg|mcg|μg|㎍|g|mL|ml|IU|mEq|밀리그램|그램|밀리리터|"
    r"국제단위|정|캡슐|포|회|일|시간)",
    flags=re.IGNORECASE,
)

PROMPT_DOCUMENT = load_prompt_chain_stage(
    "medication_chat_prompt_v7.md",
    MedicationPromptStage.ANSWER_GENERATION,
)
SYSTEM_PROMPT = PROMPT_DOCUMENT.compiled_system
USER_PROMPT_TEMPLATE = PROMPT_DOCUMENT.user
ASSISTANT_EXAMPLE = PROMPT_DOCUMENT.examples


def build_medication_chat_messages(
    *,
    request: MedicationChatRequest,
    context: ActiveIntakeContext,
    result: MedicationChatResult,
) -> list[BaseMessage]:
    show_active_medication_section = bool(context.medications) and result.route in {
        MedicationChatRoute.ACTIVE_INTAKE,
        MedicationChatRoute.INTERACTION,
        MedicationChatRoute.MEDICATION_GUIDE,
    }
    payload = {
        "question": request.question,
        "history": (
            [message.model_dump(mode="json") for message in request.history]
            if request.session_reference.entities
            else []
        ),
        "active_medication_names": (
            [item.name for item in context.medications] if show_active_medication_section else []
        ),
        "show_active_medication_section": show_active_medication_section,
        "active_supplement_names": [item.name for item in context.supplements],
        "draft_answer": _draft_answer_for_rewrite(result),
        "source_titles": [source.title for source in result.sources],
        "route": result.route.value,
        "general_supplement_guidance_allowed": (
            "GENERAL_SUPPLEMENT_GUIDANCE" in result.safety_reason_codes
            and result.risk_decision is not None
            and result.risk_decision.scope.value == "EVIDENCE_WITH_GENERAL_GUIDANCE"
        ),
        "requested_section_types": (
            [section.value for section in result.evidence_coverage.requested_section_types]
            if result.evidence_coverage is not None
            else []
        ),
        "covered_section_types": (
            [section.value for section in result.evidence_coverage.covered_section_types]
            if result.evidence_coverage is not None
            else []
        ),
        "evidence_reasoning": (
            result.evidence_reasoning.model_dump(mode="json") if result.evidence_reasoning is not None else None
        ),
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


def _draft_answer_for_rewrite(result: MedicationChatResult) -> str:
    evidence_coverage = result.evidence_coverage
    if evidence_coverage is None or KnowledgeSectionType.DAILY_INTAKE in (evidence_coverage.requested_section_types):
        return result.answer
    return _DOSAGE_VALUE_PATTERN.sub("[용량 정보 생략]", result.answer)
