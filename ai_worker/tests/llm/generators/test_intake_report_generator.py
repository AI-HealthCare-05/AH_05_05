from typing import Any

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
    async def ainvoke(self, _: Any) -> dict[str, str]:
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


async def test_generator_returns_deterministic_markdown_after_validation_failure() -> None:
    draft = _draft()
    generator = OpenAIIntakeReportGenerator(
        model="test-model",
        client=UnsafeReportClient(),
    )

    outcome = await generator.generate(draft=draft)

    assert outcome.fallback_used is True
    assert outcome.report_markdown == draft.deterministic_markdown
