from datetime import UTC, datetime
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from starlette import status

from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportCurrentStackItem,
    IntakeReportDataAvailability,
    IntakeReportEvidenceLevel,
    IntakeReportExecutiveSummary,
    IntakeReportItemType,
    IntakeReportResult,
    IntakeReportStatus,
)
from app.dependencies.intake_report import get_intake_report_application_service
from app.dependencies.security import get_request_user
from app.main import app


def _report() -> IntakeReportResult:
    return IntakeReportResult(
        status=IntakeReportStatus.COMPLETED,
        generated_at=datetime(2026, 9, 8, tzinfo=UTC),
        data_availability=IntakeReportDataAvailability(
            active_medication_count=1,
            active_supplement_count=1,
            approved_interaction_rule_available=True,
            rag_evidence_available=True,
        ),
        executive_summary=IntakeReportExecutiveSummary(
            reviewed_product_count=2,
            potential_redundancy_count=0,
            interaction_check_count=1,
            summary="등록한 약과 영양제 2개를 함께 확인했습니다.",
        ),
        current_stack=[
            IntakeReportCurrentStackItem(
                item_type=IntakeReportItemType.MEDICATION,
                item_id=10,
                product_name="예시 의약품",
                ingredient_name="예시 성분",
                registered_intake_info="1정",
                scheduled_slots=["MORNING"],
                evidence_level=IntakeReportEvidenceLevel.REGISTERED_INTAKE,
            )
        ],
        chart_data=IntakeReportChartData(
            medication_count=1,
            supplement_count=1,
            interaction_card_count=1,
        ),
        report_markdown="# 약·영양제 생활관리 보고서\n\n등록 정보를 확인했습니다.",
    )


class FakeIntakeReportApplicationService:
    def __init__(self) -> None:
        self.received_user = None

    async def generate(self, *, user) -> IntakeReportResult:
        self.received_user = user
        return _report()


async def test_post_intake_report_returns_authenticated_camel_case_report() -> None:
    service = FakeIntakeReportApplicationService()
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_intake_report_application_service] = lambda: service

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/intake-reports", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "reportStatus": "COMPLETED",
        "generatedAt": "2026-09-08T00:00:00Z",
        "dataAvailability": {
            "activeMedicationCount": 1,
            "activeSupplementCount": 1,
            "approvedInteractionRuleAvailable": True,
            "ragEvidenceAvailable": True,
        },
        "executiveSummary": {
            "reviewedProductCount": 2,
            "potentialRedundancyCount": 0,
            "interactionCheckCount": 1,
            "summary": "등록한 약과 영양제 2개를 함께 확인했습니다.",
            "summaryCards": [
                {"key": "reviewedProductCount", "label": "검토한 제품", "value": 2, "unit": "개"},
                {"key": "potentialRedundancyCount", "label": "중복 확인 항목", "value": 0, "unit": "건"},
                {"key": "interactionCheckCount", "label": "상호작용 확인 항목", "value": 1, "unit": "건"},
            ],
        },
        "currentStack": [
            {
                "itemType": "MEDICATION",
                "itemId": 10,
                "productName": "예시 의약품",
                "ingredientName": "예시 성분",
                "registeredIntakeInfo": "1정",
                "scheduledSlots": ["MORNING"],
                "evidenceLevel": "REGISTERED_INTAKE",
            }
        ],
        "reviewCards": [],
        "nutrientTotals": [],
        "chartData": {
            "medicationCount": 1,
            "supplementCount": 1,
            "interactionCardCount": 1,
            "redundancyCardCount": 0,
            "cautionCardCount": 0,
            "missingInfoCardCount": 0,
        },
        "productGuides": [],
        "unverifiedItems": [],
        "reportMarkdown": "# 약·영양제 생활관리 보고서\n\n등록 정보를 확인했습니다.",
    }
    assert service.received_user.id == 7


async def test_post_intake_report_requires_authentication() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/intake-reports", json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "인증이 필요합니다.",
    }


async def test_intake_report_api_is_documented_in_openapi_and_redoc() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        schema = (await client.get("/api/openapi.json")).json()
        redoc = await client.get("/api/redoc")

    operation = schema["paths"]["/api/v1/intake-reports"]["post"]
    assert operation["summary"] == "내 복용약·영양제 생활관리 보고서 생성"
    assert set(operation["responses"]) >= {"200", "401", "503", "504"}
    assert operation["responses"]["200"]["description"] == ("현재 활성 복용정보 기반 보고서 생성 완료")
    assert redoc.status_code == status.HTTP_200_OK
