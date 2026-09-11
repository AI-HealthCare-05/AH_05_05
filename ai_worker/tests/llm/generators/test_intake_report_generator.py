import asyncio
from typing import Any

import pytest

from ai_worker.domain.errors import AIWorkerError
from ai_worker.llm.generators.intake_report_generator import (
    OpenAIIntakeReportGenerator,
)
from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportExecutiveSummary,
)


class UnsafeReportClient:
    calls = 0

    async def ainvoke(self, _: Any) -> dict[str, str]:
        self.calls += 1
        return {"report_markdown": "## 안내\n\n- 마그네슘을 하루 2회로 늘리세요."}


def _draft() -> IntakeReportDraft:
    return IntakeReportDraft(
        data_availability=IntakeReportDataAvailability(),
        executive_summary=IntakeReportExecutiveSummary(
            summary="등록된 복용 정보를 확인했습니다.",
        ),
        chart_data=IntakeReportChartData(),
        deterministic_markdown="# 약·영양제 생활관리 보고서\n\n등록된 복용 정보를 확인했습니다.",
    )


async def test_generator_rejects_exhausted_validation_without_basic_report() -> None:
    draft = _draft()
    client = UnsafeReportClient()
    generator = OpenAIIntakeReportGenerator(
        model="test-model",
        client=client,
    )

    with pytest.raises(AIWorkerError) as caught:
        await generator.generate(draft=draft)

    assert caught.value.code == "INTAKE_REPORT_GENERATION_FAILED"
    assert "UNSAFE_CONTENT" in caught.value.issue_codes
    assert client.calls == 3


async def test_generator_repairs_invalid_output_using_feedback_and_original_evidence() -> None:
    class RepairClient:
        calls = 0

        async def ainvoke(self, messages: Any) -> dict[str, str]:
            self.calls += 1
            if self.calls == 1:
                return {"report_markdown": "## 안내\n용량을 늘리세요."}
            assert "UNSAFE_CONTENT" in messages[-1].content
            assert "deterministic_markdown" in messages[1].content
            return {"report_markdown": "# 내 약, 꼭 알아둘 점\n\n복용 변경은 전문가에게 확인하세요."}

    client = RepairClient()
    outcome = await OpenAIIntakeReportGenerator(model="test-model", client=client).generate(draft=_draft())
    assert client.calls == 2
    assert outcome.fallback_used is False
    assert outcome.report_markdown.startswith("# 내 약")


async def test_generator_client_failure_never_returns_basic_report() -> None:
    class BrokenClient:
        async def ainvoke(self, _: Any) -> dict[str, str]:
            raise RuntimeError("private upstream detail")

    with pytest.raises(AIWorkerError) as caught:
        await OpenAIIntakeReportGenerator(model="test-model", client=BrokenClient()).generate(draft=_draft())
    assert "private upstream detail" not in str(caught.value)
    assert caught.value.reason_code == "CLIENT_ERROR"


async def test_generator_timeout_cancels_pending_model_without_fallback() -> None:
    class BlockingClient:
        cancelled = False

        async def ainvoke(self, _: Any) -> dict[str, str]:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    client = BlockingClient()
    with pytest.raises(AIWorkerError) as caught:
        await OpenAIIntakeReportGenerator(
            model="test-model",
            client=client,
            generation_timeout_seconds=0.05,
        ).generate(draft=_draft())
    assert caught.value.reason_code == "TIMEOUT"
    assert client.cancelled


async def test_external_cancellation_is_not_converted_to_a_report_or_retried() -> None:
    class CancelledClient:
        async def ainvoke(self, _: Any) -> dict[str, str]:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await OpenAIIntakeReportGenerator(model="test-model", client=CancelledClient()).generate(draft=_draft())
