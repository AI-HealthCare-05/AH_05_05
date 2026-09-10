import json
from datetime import date, datetime, timedelta
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core import config
from app.core.config import Config
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


def test_review_contract_exposes_only_editable_medication_fields() -> None:
    review = MedicationGuideReviewResult.model_validate(
        {
            "fields": {"dispensedDate": {"value": "2025-04-02", "confidence": "high"}},
            "medications": [
                {
                    "tempId": "med-1",
                    "name": "에스오메프라졸캡슐",
                    "strength": "20mg",
                    "doseQuantity": "1캡슐",
                    "timesPerDay": 1,
                    "days": 14,
                    "confidence": "high",
                    "category": "소화기",
                    "efficacy": "시험용 설명",
                    "administration": "식후",
                    "precautions": "시험용 주의사항",
                }
            ],
            "lowConfidenceCount": 0,
        }
    )
    payload = review.model_dump(mode="json", by_alias=True)

    assert isinstance(review, MedicationGuideReviewResult)
    assert payload["fields"] == {"dispensedDate": {"value": "2025-04-02", "confidence": "high"}}
    assert payload["medications"][0] == {
        "tempId": "med-1",
        "name": "에스오메프라졸캡슐",
        "strength": "20mg",
        "doseQuantity": "1캡슐",
        "timesPerDay": 1,
        "days": 14,
        "confidence": "high",
    }
    assert "category" not in payload["medications"][0]
    assert "dose" not in payload["medications"][0]
    assert "efficacy" not in payload["medications"][0]
    assert "administration" not in payload["medications"][0]
    assert "precautions" not in payload["medications"][0]
    assert payload["lowConfidenceCount"] == 0
    assert set(payload) == {"fields", "medications", "lowConfidenceCount"}


def test_confirm_request_accepts_the_six_field_rdb_shape_and_an_empty_medication_list() -> None:
    request = MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-08-25",
            "medications": [
                {
                    "tempId": "med-1",
                    "name": "약품명",
                    "strength": "500mg",
                    "doseQuantity": "1정",
                    "timesPerDay": 3,
                    "days": 5,
                },
                {"tempId": "med-2", "name": "단위 없는 약", "doseQuantity": "1"},
            ],
        }
    )

    assert request.dispensing_date == date(2026, 8, 25)
    assert request.medications[0].strength == "500mg"
    assert request.medications[0].dose_quantity == "1정"
    assert request.medications[0].times_per_day == 3
    assert request.medications[1].dose_quantity == "1"

    empty = MedicationGuideConfirmRequest.model_validate({"dispensingDate": "2026-08-25", "medications": []})
    assert empty.medications == []

    try:
        MedicationGuideConfirmRequest.model_validate({"medications": [{"name": "약품명"}]})
    except ValueError:
        pass
    else:
        raise AssertionError("dispensingDate must be confirmed before persistence")


def test_hospital_name_is_optional_editable_text_with_a_255_character_limit() -> None:
    review = MedicationGuideReviewResult.model_validate(
        {
            "fields": {
                "hospitalName": {
                    "value": "송도센트럴이비인후과의원",
                    "confidence": "medium",
                }
            }
        }
    )
    request = MedicationGuideConfirmRequest.model_validate(
        {
            "hospitalName": "송도센트럴이비인후과의원",
            "dispensingDate": "2026-08-25",
            "medications": [],
        }
    )

    assert review.model_dump(mode="json", by_alias=True)["fields"]["hospitalName"]["value"] == (
        "송도센트럴이비인후과의원"
    )
    assert request.hospital_name == "송도센트럴이비인후과의원"

    for invalid in ("   ", "병" * 256):
        try:
            MedicationGuideConfirmRequest.model_validate(
                {"hospitalName": invalid, "dispensingDate": "2026-08-25", "medications": []}
            )
        except ValueError:
            pass
        else:
            raise AssertionError("blank or oversized hospitalName must be rejected")


def test_confirm_request_accepts_explicit_prn_but_rejects_null_ocr_optionals_and_legacy_fields() -> None:
    prn = MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-08-25",
            "medications": [{"tempId": "med-prn", "name": "필요 시 약", "timesPerDay": None}],
        }
    )
    assert prn.medications[0].times_per_day is None

    for medication in (
        {"tempId": "med-1", "name": "약", "strength": None},
        {"tempId": "med-1", "name": "약", "days": None},
        {"tempId": "med-1", "name": "약", "doseQuantity": ""},
        {"tempId": "med-1", "name": "약", "doseQuantity": "   "},
        {"tempId": "med-1", "name": "약", "doseQuantity": {"value": 1, "unit": "정"}},
        {"tempId": "med-1", "name": "약", "dose": "1정"},
        {"tempId": "med-1", "name": "약", "efficacy": "효능"},
    ):
        try:
            MedicationGuideConfirmRequest.model_validate({"dispensingDate": "2026-08-25", "medications": [medication]})
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid confirmation medication must be rejected: {medication}")


def test_internal_confirm_request_accepts_day_31_and_rejects_day_32() -> None:
    today = datetime.now(config.TIMEZONE).date()

    accepted = MedicationGuideConfirmRequest.model_validate(
        {"dispensingDate": (today + timedelta(days=31)).isoformat(), "medications": []}
    )
    assert accepted.dispensing_date == today + timedelta(days=31)

    try:
        MedicationGuideConfirmRequest.model_validate(
            {"dispensingDate": (today + timedelta(days=32)).isoformat(), "medications": []}
        )
    except ValueError:
        pass
    else:
        raise AssertionError("internal confirmation must reject dates beyond day 31")


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
                "strength": "500mg",
                "doseQuantity": "1정",
                "timesPerDay": 3,
                "days": 5,
                "confidence": "high",
            }
        ],
        low_confidence_count=1,
        preprocess_version="v3.1.8",
        preprocess_elapsed_ms=321,
    )

    assert uploaded.model_dump(mode="json", by_alias=True) == {
        "batchId": "b_123",
        "documentIds": [123],
        "ocrStatus": "queued",
    }
    assert ready.model_dump(mode="json", by_alias=True)["fields"]["dispensedDate"]["confidence"] == "low"
    assert ready.model_dump(mode="json", by_alias=True)["preprocessVersion"] == "v3.1.8"
    assert ready.model_dump(mode="json", by_alias=True)["preprocessElapsedMs"] == 321
    medication = ready.model_dump(mode="json", by_alias=True)["medications"][0]
    assert medication == {
        "tempId": "med-1",
        "name": "약품명",
        "strength": "500mg",
        "doseQuantity": "1정",
        "timesPerDay": 3,
        "days": 5,
        "confidence": "high",
    }
    parsed = TypeAdapter(DocumentOcrStatusResponse).validate_python(ready.model_dump(mode="json", by_alias=True))
    assert isinstance(parsed, DocumentOcrReadyResponse)


@pytest.mark.parametrize("version", get_args(Config.model_fields["OCR_PREPROCESS_VERSION"].annotation))
def test_document_ready_contract_accepts_every_configurable_preprocess_version(version: str) -> None:
    ready = DocumentOcrReadyResponse(
        batch_id="b_123",
        ocr_status="ready_for_review",
        document_image_url="/api/v1/ocr/jobs/123/image",
        fields={},
        medications=[],
        low_confidence_count=0,
        preprocess_version=version,
    )
    assert ready.model_dump(mode="json", by_alias=True)["preprocessVersion"] == version


@pytest.mark.parametrize("version", ["v3.1.9", "v3.2.0", "v3.3.2", "v3.4.0", "v3.4.4", "v4.1.1"])
def test_document_ready_contract_rejects_unsupported_preprocess_versions(version: str) -> None:
    with pytest.raises(ValidationError) as exc:
        DocumentOcrReadyResponse(
            batch_id="b_123",
            ocr_status="ready_for_review",
            document_image_url="/api/v1/ocr/jobs/123/image",
            fields={},
            medications=[],
            low_confidence_count=0,
            preprocess_version=version,
        )
    assert [(error["loc"], error["type"]) for error in exc.value.errors()] == [
        (("preprocess_version",), "string_pattern_mismatch")
    ]


def test_document_ready_contract_omits_unread_optional_fields_and_missing_date() -> None:
    ready = DocumentOcrReadyResponse.model_validate(
        {
            "batchId": "b_123",
            "ocrStatus": "ready_for_review",
            "documentImageUrl": "/api/v1/ocr/jobs/123/image",
            "fields": {},
            "medications": [{"tempId": "med-1", "name": "원문 약품명", "confidence": "low"}],
            "lowConfidenceCount": 2,
        }
    )

    assert ready.model_dump(mode="json", by_alias=True) == {
        "batchId": "b_123",
        "ocrStatus": "ready_for_review",
        "documentImageUrl": "/api/v1/ocr/jobs/123/image",
        "fields": {},
        "medications": [{"tempId": "med-1", "name": "원문 약품명", "confidence": "low"}],
        "lowConfidenceCount": 2,
    }


def test_document_ready_contract_rejects_a_non_iso_dispensed_date() -> None:
    try:
        DocumentOcrReadyResponse.model_validate(
            {
                "batchId": "b_123",
                "ocrStatus": "ready_for_review",
                "documentImageUrl": "/api/v1/ocr/jobs/123/image",
                "fields": {"dispensedDate": {"value": "2026/08/25", "confidence": "high"}},
                "medications": [],
                "lowConfidenceCount": 0,
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("dispensedDate.value must use an ISO date")
