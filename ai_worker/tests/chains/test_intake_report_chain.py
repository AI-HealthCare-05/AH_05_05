from langchain_core.runnables import RunnableLambda

from ai_worker.chains.intake_report_chain import (
    IntakeReportChainInput,
    build_intake_report_chain,
)
from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportExecutiveSummary,
)


def _draft() -> IntakeReportDraft:
    return IntakeReportDraft(
        data_availability=IntakeReportDataAvailability(),
        executive_summary=IntakeReportExecutiveSummary(
            summary="등록된 복용 정보를 확인했습니다.",
        ),
        chart_data=IntakeReportChartData(),
        deterministic_markdown="# 약·영양제 생활관리 보고서\n\n등록된 복용 정보를 확인했습니다.",
    )


async def _response(_: object) -> dict[str, str]:
    return {
        "report_markdown": "# 약·영양제 생활관리 보고서\n\n등록된 복용 정보를 확인했습니다.",
    }


async def test_chain_validates_structured_markdown_payload() -> None:
    chain = build_intake_report_chain(
        response_runnable=RunnableLambda(_response),
    )

    payload = await chain.ainvoke(IntakeReportChainInput(draft=_draft()))

    assert payload.report_markdown.startswith("# 약·영양제 생활관리 보고서")
