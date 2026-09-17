"""RAG provenance remains visible and escaped in both email render modes."""

import pytest

from ai_worker.tests.reports.test_intake_email_parity import sample_email_report
from app.core.email.intake_report_renderer import render_intake_report_email
from app.dtos.intake_reports import IntakeReportResponse


def rag_email_fixture():
    data = sample_email_report().model_dump()
    data["cards"]["section_statuses"] = [
        {
            "section_id": "additional_precautions",
            "status": "unverified",
            "reason": "관련 자료를 확인하지 못했어요.",
            "target_item_ids": [1],
        }
    ]
    data["cards"]["sources"].append(
        {
            "id": "rag-source",
            "title": "검색된 원문",
            "url": "https://example.org/evidence",
            "evidence_level": "PUBLIC_GUIDE",
            "quote": "시험 원문 <script>unsafe</script>",
            "chunk_id": "fixture-chunk",
            "dataset_version": "fixture-v1",
        }
    )
    data["cards"]["lifestyle"][0]["source_ids"] = ["rag-source"]
    return IntakeReportResponse.model_validate(data)


@pytest.mark.parametrize("standalone", [False, True])
def test_rag_email_keeps_sources_without_internal_section_status(standalone):
    report = rag_email_fixture()
    markup, plain = render_intake_report_email(report, standalone=standalone)
    assert "추가 안내 확인 상태" not in plain
    assert "관련 자료를 확인하지 못했어요." not in plain
    assert "시험 원문 <script>unsafe</script>" in plain
    assert "<script>unsafe</script>" not in markup
    assert 'href="https://example.org/evidence"' in markup
    assert "제품 안내의 효능입니다." in plain
    assert "두 번째 원문입니다." in plain
    assert "600" in plain and "33" in plain
