from ai_worker.schemas.intake_report import (
    IntakeReportResult,
    IntakeReportStatus,
)


def test_empty_report_has_no_cards_or_current_intakes() -> None:
    report = IntakeReportResult.empty(user_id=1)

    assert report.status == IntakeReportStatus.EMPTY
    assert report.current_stack == []
    assert report.review_cards == []
    assert "현재 복용 중으로 등록된" in report.report_markdown
