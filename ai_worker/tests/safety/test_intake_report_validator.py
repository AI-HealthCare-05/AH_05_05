from ai_worker.safety.intake_report_validator import IntakeReportGroundingValidator
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


def test_validator_rejects_new_dosage_change_instruction() -> None:
    markdown = "## 안내\n\n- 마그네슘을 하루 2회로 늘리세요."

    assert (
        IntakeReportGroundingValidator().validate(
            generated_markdown=markdown,
            draft=_draft(),
        )
        is None
    )
