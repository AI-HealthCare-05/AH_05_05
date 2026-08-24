import re
import unicodedata
from datetime import date
from math import isfinite

from app.dtos.medication_guide_ocr import (
    DoseComponents,
    Medication,
    MedicationGuideResult,
    OcrField,
    ReviewIssue,
)

_DATE_RE = re.compile(r"(?P<date>\d{4}-\d{1,2}-\d{1,2})")
_STRENGTH_RE = re.compile(
    r"(?P<strength>\d+(?:\.\d+)?\s*(?:mcg|mg|g|mL|ml|%))$",
    re.IGNORECASE,
)
_CATEGORY_RE = re.compile(r"^\[(?P<category>[^\]]+)]\s*(?P<efficacy>.*)$")
_DOSE_QUANTITY_RE = re.compile(
    r"^(?:1회\s+)?(?P<quantity>.+?)씩(?:\s+1일\b|$)",
    re.IGNORECASE,
)
_DOSE_QUANTITY_FALLBACK_RE = re.compile(
    r"^1회\s+(?P<quantity>.+?)\s+1일\b",
    re.IGNORECASE,
)
_TIMES_PER_DAY_RE = re.compile(r"1일\s*(?P<times>\d+)\s*회")
_DAYS_RE = re.compile(r"(?P<days>\d+)\s*일(?:분|간)")
_STORAGE_LABEL = r"(?:실온보관|기밀용기|냉장보관|차광보관)"
_TRAILING_STORAGE_RE = re.compile(rf"(?:\s*(?:[,/·]\s*)?{_STORAGE_LABEL})+\s*$")

_CONFIRMED_CORRECTIONS = {
    "손상된위점막": "손상된 위점막",
    "뜨거운음료": "뜨거운 음료",
    "상 담하세요": "상담하세요",
}

_DATE_FIELDS = {"next_visit_date", "dispensing_date"}
_ROW_PARTS = ("name", "efficacy", "dose_line", "administration", "precaution")
_ROW_FIELDS = {f"med_{row:02d}_{part}" for row in range(1, 5) for part in _ROW_PARTS}
_ALLOWED_FIELDS = _DATE_FIELDS | _ROW_FIELDS


class OcrPayloadError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = re.sub(r"\s+", " ", text).strip()
    for source, target in _CONFIRMED_CORRECTIONS.items():
        text = text.replace(source, target)
    return text


def normalize_date(value: str) -> date | None:
    match = _DATE_RE.search(unicodedata.normalize("NFKC", value))
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group("date"))
    except ValueError:
        return None


def split_name_strength(value: str) -> tuple[str, str | None]:
    text = normalize_text(value)
    match = _STRENGTH_RE.search(text)
    if match is None:
        return text, None

    name = text[: match.start()].rstrip(" ,-/")
    if not name:
        return text, None
    strength = re.sub(r"\s+", "", match.group("strength"))
    return name, strength


def split_category_efficacy(value: str) -> tuple[str | None, str | None]:
    text = normalize_text(value)
    if not text:
        return None, None

    match = _CATEGORY_RE.match(text)
    if match is None:
        return None, text

    category = normalize_text(match.group("category")) or None
    efficacy = normalize_text(match.group("efficacy")) or None
    return category, efficacy


def strip_storage_labels(value: str) -> str:
    text = normalize_text(value)
    while True:
        stripped = _TRAILING_STORAGE_RE.sub("", text).rstrip(" ,/·")
        if stripped == text:
            return stripped
        text = stripped


def parse_dose_line(value: str) -> DoseComponents:
    text = normalize_text(value)
    quantity_match = _DOSE_QUANTITY_RE.search(text)
    if quantity_match is None:
        quantity_match = _DOSE_QUANTITY_FALLBACK_RE.search(text)
    times_match = _TIMES_PER_DAY_RE.search(text)
    days_match = _DAYS_RE.search(text)

    quantity = None
    if quantity_match is not None:
        quantity = normalize_text(quantity_match.group("quantity")) or None

    return DoseComponents(
        dose_quantity=quantity,
        times_per_day=int(times_match.group("times")) if times_match else None,
        days=int(days_match.group("days")) if days_match else None,
    )


def _payload_image(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise OcrPayloadError("INVALID_PAYLOAD")
    images = payload.get("images")
    if not isinstance(images, list) or len(images) != 1:
        raise OcrPayloadError("INVALID_PAYLOAD")
    image = images[0]
    if not isinstance(image, dict):
        raise OcrPayloadError("INVALID_PAYLOAD")
    if image.get("inferResult") != "SUCCESS":
        raise OcrPayloadError("OCR_PROVIDER_ERROR")
    return image


def _validate_template(image: dict[str, object], expected_template_id: int | None) -> None:
    if expected_template_id is None:
        return
    matched = image.get("matchedTemplate")
    if not isinstance(matched, dict):
        raise OcrPayloadError("TEMPLATE_NOT_MATCHED")
    raw_id = matched.get("id")
    if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
        raise OcrPayloadError("TEMPLATE_NOT_MATCHED")
    try:
        template_id = int(raw_id)
    except ValueError as error:
        raise OcrPayloadError("TEMPLATE_NOT_MATCHED") from error
    if template_id != expected_template_id:
        raise OcrPayloadError("TEMPLATE_NOT_MATCHED")


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise OcrPayloadError("OCR_PROVIDER_ERROR")
    try:
        confidence = float(value)
    except ValueError as error:
        raise OcrPayloadError("OCR_PROVIDER_ERROR") from error
    if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise OcrPayloadError("OCR_PROVIDER_ERROR")
    return confidence


def _accepted_fields(image: dict[str, object]) -> dict[str, OcrField]:
    raw_fields = image.get("fields")
    if not isinstance(raw_fields, list):
        raise OcrPayloadError("INVALID_PAYLOAD")

    accepted: dict[str, OcrField] = {}
    for candidate in raw_fields:
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("name")
        if not isinstance(name, str) or name not in _ALLOWED_FIELDS or name in accepted:
            continue
        raw_text = candidate.get("inferText")
        text = "" if raw_text is None else str(raw_text).strip()
        accepted[name] = OcrField(
            name=name,
            text=text,
            confidence=_confidence(candidate.get("inferConfidence")),
        )
    return accepted


def _field_text(by_name: dict[str, OcrField], name: str) -> str | None:
    field = by_name.get(name)
    if field is None or not field.text.strip():
        return None
    return field.text


def _date_result(
    by_name: dict[str, OcrField],
    field_name: str,
    output_path: str,
    issues: list[ReviewIssue],
) -> date | None:
    raw = _field_text(by_name, field_name)
    if raw is None:
        return None
    normalized = normalize_date(raw)
    if normalized is None:
        issues.append(ReviewIssue(code="INVALID_DATE", path=output_path))
    return normalized


def _row_issues_for_missing_values(
    row_path: str,
    values: dict[str, str | None],
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    for output_name in ("efficacy", "doseLine", "administration", "precautions"):
        if values[output_name] is None:
            issues.append(ReviewIssue(code="MISSING_REQUIRED", path=f"{row_path}.{output_name}"))
    return issues


def normalize_clova_response(
    payload: object,
    *,
    expected_template_id: int | None = None,
    review_threshold: float = 0.90,
) -> MedicationGuideResult:
    if isinstance(review_threshold, bool) or not 0.0 <= review_threshold <= 1.0:
        raise ValueError("review_threshold must be between 0 and 1")

    image = _payload_image(payload)
    _validate_template(image, expected_template_id)
    by_name = _accepted_fields(image)
    issues: list[ReviewIssue] = []

    dispensing_date = _date_result(by_name, "dispensing_date", "dispensingDate", issues)
    next_visit_date = _date_result(by_name, "next_visit_date", "nextVisitDate", issues)

    medications: list[Medication] = []
    for row in range(1, 5):
        prefix = f"med_{row:02d}"
        row_id = f"med-{row}"
        row_path = f"medications.{row_id}"
        source_names = [f"{prefix}_{part}" for part in _ROW_PARTS]
        name_text = _field_text(by_name, source_names[0])
        other_values = [_field_text(by_name, name) for name in source_names[1:]]
        if name_text is None:
            if any(value is not None for value in other_values):
                issues.append(ReviewIssue(code="ORPHAN_ROW", path=row_path))
            continue

        normalized_name, strength = split_name_strength(name_text)
        efficacy_text = _field_text(by_name, f"{prefix}_efficacy")
        category, efficacy = split_category_efficacy(efficacy_text) if efficacy_text is not None else (None, None)
        raw_dose_line = _field_text(by_name, f"{prefix}_dose_line")
        dose_line = normalize_text(raw_dose_line) if raw_dose_line is not None else None
        dose = parse_dose_line(dose_line) if dose_line is not None else DoseComponents()
        raw_administration = _field_text(by_name, f"{prefix}_administration")
        administration = normalize_text(raw_administration) if raw_administration is not None else None
        raw_precautions = _field_text(by_name, f"{prefix}_precaution")
        precautions = (strip_storage_labels(raw_precautions) or None) if raw_precautions is not None else None

        row_issues = _row_issues_for_missing_values(
            row_path,
            {
                "efficacy": efficacy,
                "doseLine": dose_line,
                "administration": administration,
                "precautions": precautions,
            },
        )
        if dose_line is not None and (dose.times_per_day is None or dose.days is None):
            row_issues.append(ReviewIssue(code="UNPARSEABLE_DOSE_LINE", path=f"{row_path}.doseLine"))

        present_fields = [by_name[name] for name in source_names if name in by_name]
        confidence = min(item.confidence for item in present_fields)
        if confidence < review_threshold:
            row_issues.append(ReviewIssue(code="LOW_CONFIDENCE", path=row_path))

        issues.extend(row_issues)
        medications.append(
            Medication(
                row_id=row_id,
                name=normalized_name,
                strength=strength,
                category=category,
                efficacy=efficacy,
                dose_line=dose_line,
                dose_quantity=dose.dose_quantity,
                times_per_day=dose.times_per_day,
                days=dose.days,
                administration=administration,
                precautions=precautions,
                confidence=confidence,
                needs_review=bool(row_issues),
                source_field_names=source_names,
            )
        )

    if not medications:
        raise OcrPayloadError("NO_MEDICATIONS_FOUND")

    return MedicationGuideResult(
        dispensing_date=dispensing_date,
        next_visit_date=next_visit_date,
        medications=medications,
        review_issues=issues,
        ocr_fields=list(by_name.values()),
    )
