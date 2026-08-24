import copy
import json
from datetime import date
from pathlib import Path

from app.services.medication_guide_normalizer import normalize_clova_response

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "template_ocr_exact_02_response.json"


def load_fixture() -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_exact_template_response_normalizes_four_medications() -> None:
    result = normalize_clova_response(load_fixture(), expected_template_id=43199)

    assert result.dispensing_date == date(2025, 4, 2)
    assert result.next_visit_date == date(2025, 4, 16)
    assert len(result.medications) == 4
    assert len(result.ocr_fields) == 22
    assert result.review_issues == []

    first = result.medications[0]
    assert first.name == "에스오메프라졸캡슐"
    assert first.strength == "20mg"
    assert first.category == "위산분비억제제"
    assert first.efficacy == "위산 과다, 속쓰림, 역류 증상 완화"
    assert first.dose_quantity == "1캡슐"
    assert first.times_per_day == 1
    assert first.days == 14
    assert first.needs_review is False


def test_normalized_response_uses_project_camel_case_contract() -> None:
    result = normalize_clova_response(load_fixture(), expected_template_id=43199)

    payload = result.model_dump(mode="json", by_alias=True)

    assert payload["schemaVersion"] == "medication-guide-template/v2"
    assert payload["medications"][0]["rowId"] == "med-1"
    assert payload["medications"][0]["timesPerDay"] == 1
    assert payload["medications"][0]["needsReview"] is False


def test_low_confidence_marks_only_affected_medication() -> None:
    payload = load_fixture()
    images = payload["images"]
    assert isinstance(images, list)
    image = images[0]
    assert isinstance(image, dict)
    fields = image["fields"]
    assert isinstance(fields, list)
    first_name = next(field for field in fields if field["name"] == "med_01_name")
    first_name["inferConfidence"] = 0.5

    result = normalize_clova_response(payload, review_threshold=0.9)

    assert result.medications[0].needs_review is True
    assert result.medications[1].needs_review is False
    assert ("LOW_CONFIDENCE", "medications.med-1") in {(issue.code, issue.path) for issue in result.review_issues}


def test_storage_label_only_precaution_requires_review() -> None:
    payload = load_fixture()
    images = payload["images"]
    assert isinstance(images, list)
    image = images[0]
    assert isinstance(image, dict)
    fields = image["fields"]
    assert isinstance(fields, list)
    precaution = next(field for field in fields if field["name"] == "med_01_precaution")
    precaution["inferText"] = "실온보관"

    result = normalize_clova_response(payload)

    first = result.medications[0]
    assert first.precautions is None
    assert first.needs_review is True
    assert ("MISSING_REQUIRED", "medications.med-1.precautions") in {
        (issue.code, issue.path) for issue in result.review_issues
    }


def test_normalizer_does_not_mutate_provider_payload() -> None:
    payload = load_fixture()
    original = copy.deepcopy(payload)

    normalize_clova_response(payload)

    assert payload == original
