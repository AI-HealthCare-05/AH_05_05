from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict

from ai_worker.llm.prompts.intake_report_prompt import (
    build_intake_report_messages,
)
from ai_worker.schemas.intake_report import (
    IntakeReportDraft,
    IntakeReportMarkdownPayload,
)


class IntakeReportChainInput(BaseModel):
    """보고서 Markdown 정제 체인이 받는 근거 기반 초안."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    draft: IntakeReportDraft


def _validate_input(
    value: IntakeReportChainInput | dict[str, Any],
) -> IntakeReportChainInput:
    if isinstance(value, IntakeReportChainInput):
        return value
    return IntakeReportChainInput.model_validate(value)


def _build_messages(value: IntakeReportChainInput):
    return build_intake_report_messages(draft=value.draft)


def _validate_payload(
    value: IntakeReportMarkdownPayload | dict[str, Any],
) -> IntakeReportMarkdownPayload:
    if isinstance(value, IntakeReportMarkdownPayload):
        return value
    return IntakeReportMarkdownPayload.model_validate(value)


def build_intake_report_chain(
    *,
    response_runnable: Runnable,
) -> Runnable:
    """구조화 보고서 초안 → Prompt → 구조화 Markdown 출력 LCEL 체인."""

    input_validator = RunnableLambda(_validate_input).with_config(
        run_name="intake_report.input",
    )
    prompt_builder = RunnableLambda(_build_messages).with_config(
        run_name="intake_report.prompt",
    )
    output_validator = RunnableLambda(_validate_payload).with_config(
        run_name="intake_report.output",
    )
    return (input_validator | prompt_builder | response_runnable | output_validator).with_types(
        input_type=IntakeReportChainInput,
        output_type=IntakeReportMarkdownPayload,
    )
