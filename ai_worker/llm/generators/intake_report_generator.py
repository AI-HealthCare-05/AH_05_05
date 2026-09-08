from typing import Any, Protocol

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.chains.intake_report_chain import (
    IntakeReportChainInput,
    build_intake_report_chain,
)
from ai_worker.llm.prompts.intake_report_prompt import (
    INTAKE_REPORT_PROMPT_VERSION,
)
from ai_worker.safety.intake_report_validator import IntakeReportGroundingValidator
from ai_worker.schemas.intake_report import (
    IntakeReportDraft,
    IntakeReportFallbackReason,
    IntakeReportGenerationOutcome,
    IntakeReportMarkdownPayload,
)


class AsyncIntakeReportClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> IntakeReportMarkdownPayload | dict[str, Any]: ...


class OpenAIIntakeReportGenerator:
    """Generate wording only; deterministic data remains the source of truth."""

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncIntakeReportClient | None = None,
        validator: IntakeReportGroundingValidator | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        self._model_name = normalized_model
        self._validator = validator or IntakeReportGroundingValidator()
        response_runnable: Runnable
        if client is not None:
            response_runnable = RunnableLambda(client.ainvoke).with_config(
                run_name="intake_report.client",
            )
        else:
            chat_model = ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            response_runnable = chat_model.with_structured_output(
                IntakeReportMarkdownPayload,
                method="json_schema",
                strict=True,
            ).with_config(run_name="intake_report.model")
        self._chain = build_intake_report_chain(
            response_runnable=response_runnable,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate(
        self,
        *,
        draft: IntakeReportDraft,
    ) -> IntakeReportGenerationOutcome:
        try:
            payload = await self._chain.ainvoke(
                IntakeReportChainInput(draft=draft),
                config={
                    "metadata": {
                        "model_name": self._model_name,
                        "prompt_version": INTAKE_REPORT_PROMPT_VERSION,
                        "current_stack_count": len(draft.current_stack),
                        "review_card_count": len(draft.review_cards),
                        "source_count": len(draft.sources),
                    }
                },
            )
        except Exception:
            return self._fallback(
                draft=draft,
                reason=IntakeReportFallbackReason.CLIENT_ERROR,
            )
        validated_markdown = self._validator.validate(
            generated_markdown=payload.report_markdown,
            draft=draft,
        )
        if validated_markdown is None:
            return self._fallback(
                draft=draft,
                reason=IntakeReportFallbackReason.VALIDATION_FAILED,
            )
        return IntakeReportGenerationOutcome(
            report_markdown=validated_markdown,
            fallback_used=False,
        )

    @staticmethod
    def _fallback(
        *,
        draft: IntakeReportDraft,
        reason: IntakeReportFallbackReason,
    ) -> IntakeReportGenerationOutcome:
        return IntakeReportGenerationOutcome(
            report_markdown=draft.deterministic_markdown,
            fallback_used=True,
            fallback_reason=reason,
        )
