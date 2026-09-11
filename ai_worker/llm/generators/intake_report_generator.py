import asyncio
import logging
from typing import Any, Protocol

from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.chains.intake_report_chain import (
    IntakeReportChainInput,
    build_intake_report_chain,
)
from ai_worker.domain.errors import IntakeReportGenerationError
from ai_worker.llm.prompts.intake_report_prompt import (
    INTAKE_REPORT_PROMPT_VERSION,
)
from ai_worker.safety.intake_report_validator import IntakeReportGroundingValidator
from ai_worker.schemas.intake_report import (
    IntakeReportDraft,
    IntakeReportGenerationOutcome,
    IntakeReportMarkdownPayload,
)

logger = logging.getLogger(__name__)


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
        max_repair_attempts: int = 2,
        generation_timeout_seconds: float = 90.0,
    ) -> None:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
        if not 0 <= max_repair_attempts <= 2:
            raise ValueError("수정 재생성은 0~2회만 허용합니다.")
        if generation_timeout_seconds <= 0:
            raise ValueError("보고서 생성 제한 시간은 양수여야 합니다.")
        self._max_repair_attempts = max_repair_attempts
        self._generation_timeout_seconds = generation_timeout_seconds
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
            async with asyncio.timeout(self._generation_timeout_seconds):
                return await self._generate_with_repairs(draft=draft)
        except TimeoutError as error:
            raise IntakeReportGenerationError(reason_code="TIMEOUT") from error

    async def _generate_with_repairs(self, *, draft: IntakeReportDraft) -> IntakeReportGenerationOutcome:
        previous_markdown = None
        issues: list[dict[str, str]] = []
        for attempt in range(self._max_repair_attempts + 1):
            try:
                payload = await self._chain.ainvoke(
                    IntakeReportChainInput(
                        draft=draft,
                        previous_markdown=previous_markdown,
                        validation_issues=issues,
                    ),
                    config={
                        "metadata": {
                            "model_name": self._model_name,
                            "prompt_version": INTAKE_REPORT_PROMPT_VERSION,
                            "repair_attempt": attempt,
                            "current_stack_count": len(draft.current_stack),
                            "review_card_count": len(draft.review_cards),
                            "source_count": len(draft.sources),
                        }
                    },
                )
            except Exception as error:
                raise IntakeReportGenerationError(reason_code="CLIENT_ERROR") from error
            issues = self._validator.validation_issues(
                generated_markdown=payload.report_markdown,
                draft=draft,
            )
            if not issues:
                return IntakeReportGenerationOutcome(
                    report_markdown=payload.report_markdown.strip(),
                    fallback_used=False,
                )
            # Never log report text, product names, source content, or credentials.
            logger.warning(
                "intake_report.validation_failed prompt=%s attempt=%d issue_codes=%s",
                INTAKE_REPORT_PROMPT_VERSION,
                attempt,
                ",".join(issue["code"] for issue in issues),
            )
            previous_markdown = payload.report_markdown
        raise IntakeReportGenerationError(
            reason_code="VALIDATION_FAILED",
            issue_codes=tuple(issue["code"] for issue in issues),
        )
