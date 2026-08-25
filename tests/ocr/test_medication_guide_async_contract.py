import json
from datetime import date, datetime
from pathlib import Path

from pydantic import TypeAdapter

from app.dtos.medication_guide_ocr import (
    DocumentOcrReadyResponse,
    DocumentOcrStatusResponse,
    DocumentOcrUploadResponse,
    MedicationGuideConfirmRequest,
    MedicationGuideReviewResult,
    OcrConfirmationResponse,
    OcrJobAcceptedResponse,
    OcrJobStatusResponse,
)
from app.models.enums import OcrJobStatus
from app.services.medication_guide_normalizer import normalize_clova_response
from app.services.medication_guide_ocr_jobs import build_review_result

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "template_ocr_exact_02_response.json"


def test_review_contract_exposes_only_editable_medication_fields() -> None:
    provider_payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    normalized = normalize_clova_response(provider_payload, expected_template_id=43199)

    review = build_review_result(normalized)
    payload = review.model_dump(mode="json", by_alias=True)

    assert isinstance(review, MedicationGuideReviewResult)
    assert payload["dispensingDate"] == "2025-04-02"
    assert payload["nextVisitDate"] == "2025-04-16"
    assert payload["medications"][0] == {
        "rowId": "med-1",
        "name": "에스오메프라졸캡슐",
        "dose": "20mg",
        "efficacy": "위산 과다, 속쓰림, 역류 증상 완화",
        "administration": "아침 식사 30분 전에 물과 함께 복용하세요.",
        "precautions": "캡슐을 씹거나 열지 마세요. 복통이나 설사가 지속되면 상담하세요.",
        "timesPerDay": 1,
        "days": 14,
        "confidence": 0.9995,
        "needsReview": False,
    }
    assert "strength" not in payload["medications"][0]
    assert "category" not in payload["medications"][0]
    assert "doseQuantity" not in payload["medications"][0]
    assert "ocrFields" not in payload


def test_confirm_request_accepts_the_rdb_shape_and_an_empty_medication_list() -> None:
    request = MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-08-25",
            "nextVisitDate": "2026-09-01",
            "medications": [
                {
                    "name": "약품명",
                    "dose": "1회 1정",
                    "efficacy": "효능",
                    "administration": "복용 방법",
                    "precautions": "주의사항",
                    "timesPerDay": 3,
                    "days": 5,
                }
            ],
        }
    )

    assert request.dispensing_date == date(2026, 8, 25)
    assert request.medications[0].times_per_day == 3

    empty = MedicationGuideConfirmRequest.model_validate({"dispensingDate": "2026-08-25", "medications": []})
    assert empty.medications == []

    try:
        MedicationGuideConfirmRequest.model_validate({"medications": [{"name": "약품명"}]})
    except ValueError:
        pass
    else:
        raise AssertionError("dispensingDate must be confirmed before persistence")


def test_job_responses_serialize_bigint_ids_as_strings() -> None:
    accepted = OcrJobAcceptedResponse(
        ocr_job_id="123",
        status=OcrJobStatus.QUEUED,
        status_url="/api/v1/ocr/jobs/123",
    )
    status_response = OcrJobStatusResponse(
        ocr_job_id="123",
        status=OcrJobStatus.PROCESSING,
    )
    confirmed = OcrConfirmationResponse(
        ocr_job_id="123",
        care_episode_id="456",
        confirmed_at=datetime.fromisoformat("2026-08-25T14:10:00+09:00"),
    )

    assert accepted.model_dump(mode="json", by_alias=True)["ocrJobId"] == "123"
    assert status_response.model_dump(mode="json", by_alias=True)["status"] == "PROCESSING"
    assert confirmed.model_dump(mode="json", by_alias=True) == {
        "ocrJobId": "123",
        "careEpisodeId": "456",
        "status": "COMPLETE",
        "confirmedAt": "2026-08-25T14:10:00+09:00",
    }


def test_public_job_contract_exposes_the_document_statuses() -> None:
    schema = json.dumps(OcrJobStatusResponse.model_json_schema())

    for status in ("QUEUED", "PROCESSING", "READY_FOR_REVIEW", "COMPLETE", "FAILED", "CANCELLED"):
        assert status in schema


def test_document_contract_uses_lowercase_status_and_a_discriminated_ready_result() -> None:
    uploaded = DocumentOcrUploadResponse(batch_id="b_123", document_ids=[123], ocr_status="queued")
    ready = DocumentOcrReadyResponse(
        batch_id="b_123",
        ocr_status="ready_for_review",
        document_image_url="/api/v1/ocr/jobs/123/image",
        fields={"dispensedDate": {"value": "2026-08-25", "confidence": "low"}},
        medications=[
            {
                "tempId": "med-1",
                "name": "약품명",
                "dose": "1회 1정",
                "efficacy": "효능",
                "administration": "복용 방법",
                "precautions": "주의사항",
                "timesPerDay": 3,
                "days": 5,
                "confidence": "high",
            }
        ],
        low_confidence_count=1,
    )

    assert uploaded.model_dump(mode="json", by_alias=True) == {
        "batchId": "b_123",
        "documentIds": [123],
        "ocrStatus": "queued",
    }
    assert ready.model_dump(mode="json", by_alias=True)["fields"]["dispensedDate"]["confidence"] == "low"
    assert ready.model_dump(mode="json", by_alias=True)["medications"][0]["precautions"] == "주의사항"
    parsed = TypeAdapter(DocumentOcrStatusResponse).validate_python(ready.model_dump(mode="json", by_alias=True))
    assert isinstance(parsed, DocumentOcrReadyResponse)
