from ai_worker.schemas.intake_report import (
    IntakeReportNutrientTotal,
    IntakeReportResult,
    IntakeReportStatus,
)


def test_empty_report_has_no_cards_or_current_intakes() -> None:
    report = IntakeReportResult.empty(user_id=1)

    assert report.status == IntakeReportStatus.EMPTY
    assert report.current_stack == []
    assert report.review_cards == []
    assert "현재 복용 중으로 등록된" in report.report_markdown


def test_unknown_nutrient_amount_remains_null() -> None:
    total = IntakeReportNutrientTotal(
        nutrient_name="칼슘",
        daily_total="함량 미확인",
        calculation_status="UNKNOWN",
        amount=None,
        unit="mg",
        reference_value=None,
        reference_kind=None,
        reference_percent=None,
        unknown_product_names=["미확인 제품"],
    )
    assert total.amount is None and total.reference_percent is None
    assert total.unknown_product_names == ["미확인 제품"]


def test_api_dto_preserves_generated_report_and_visible_fallback_metadata() -> None:
    from ai_worker.schemas.intake_report import IntakeReportFallbackReason
    from app.dtos.intake_reports import IntakeReportResponse

    result = IntakeReportResult.empty(user_id=1).model_copy(
        update={
            "status": IntakeReportStatus.PARTIAL,
            "presentation_version": "ai-report-v2",
            "report_markdown": "## 생성 결과가 아닌 기본 정보",
            "fallback_used": True,
            "fallback_reason": IntakeReportFallbackReason.VALIDATION_FAILED,
        }
    )
    payload = IntakeReportResponse.from_result(result).model_dump(mode="json", by_alias=True)
    assert payload["presentationVersion"] == "ai-report-v2"
    assert payload["fallbackUsed"] is True
    assert payload["fallbackReason"] == "VALIDATION_FAILED"
    assert payload["reportMarkdown"] == "## 생성 결과가 아닌 기본 정보"


def test_api_dto_preserves_v11_cards_and_same_email_markdown() -> None:
    from app.dtos.intake_reports import IntakeReportResponse

    cards = {
        "medications": [
            {
                "itemId": 73,
                "productName": "새로 등록한 약",
                "efficacy": {"text": "확인한 효능", "sourceIds": ["guide:9"]},
                "caution": {"text": "확인한 주의", "sourceIds": ["guide:9"]},
                "contraindication": {"text": "금기 확인 필요", "sourceIds": []},
                "details": [],
                "sourceIds": ["guide:9"],
            }
        ],
        "interactions": [],
        "overlaps": [],
        "lifestyle": [],
        "sources": [
            {
                "id": "guide:9",
                "title": "공공 안내",
                "organization": None,
                "url": "https://example.org/guide/9",
                "evidenceLevel": "PUBLIC_GUIDE",
            }
        ],
    }
    values = IntakeReportResult.empty(user_id=1).model_dump()
    values.update(
        status="COMPLETED",
        presentation_version="ai-report-v11",
        cards=cards,
        report_markdown="# 동일한 이메일 본문\n\n새로 등록한 약",
    )
    result = IntakeReportResult.model_validate(values)
    payload = IntakeReportResponse.from_result(result).model_dump(mode="json", by_alias=True)
    assert payload["cards"] == cards
    assert payload["presentationVersion"] == "ai-report-v11"
    assert payload["reportMarkdown"] == values["report_markdown"]
    assert payload["emailToken"] is None

    # The existing encryption path receives this exact canonical projection;
    # rendering a second independent clinical summary would change the snapshot.
    from cryptography.fernet import Fernet

    from app.models.users import User
    from app.services.intake_report_email import IntakeReportEmailService

    user = User(id=1, email="v11@example.invalid", hashed_password="unused", name="테스트")
    email = IntakeReportEmailService(encryption_key=Fernet.generate_key().decode())
    token = email.create_snapshot_token(user=user, report_markdown=result.report_markdown)
    assert token is not None
    assert email.consume_snapshot_token(token=token, user=user).report_markdown == payload["reportMarkdown"]
