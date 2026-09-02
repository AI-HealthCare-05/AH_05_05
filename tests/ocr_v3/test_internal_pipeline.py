from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline import grounding as grounding_module
from app.services.medication_ocr_v3.pipeline import medication_rows as medication_rows_module
from app.services.medication_ocr_v3.pipeline import review_projection as review_projection_module
from app.services.medication_ocr_v3.pipeline.grounding import (
    parse_dispensed_date,
    parse_strength,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows
from app.services.medication_ocr_v3.pipeline.ocr_layout import build_ocr_layout
from app.services.medication_ocr_v3.pipeline.review_projection import build_project_review


def _block(block_id: str, text: str, x: float, y: float, width: float) -> OcrBlock:
    return OcrBlock(
        block_id=block_id,
        text=text,
        confidence=0.99,
        bbox=(
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + 10),
            Point(x, y + 10),
        ),
        line_break=False,
        issues=(),
    )


def test_v3_core_imports_are_resolved_inside_the_project() -> None:
    package_root = Path(__file__).parents[2] / "app" / "services" / "medication_ocr_v3"

    for module in (
        grounding_module,
        medication_rows_module,
        review_projection_module,
    ):
        assert Path(module.__file__).resolve().is_relative_to(package_root.resolve())


def test_units_are_normalized_without_rewriting_the_drug_name() -> None:
    blocks = (
        _block("block-0001", "약품명", 10, 10, 45),
        _block("block-0002", "투약량", 120, 10, 45),
        _block("block-0003", "횟수", 180, 10, 35),
        _block("block-0004", "일수", 240, 10, 35),
        _block("block-0005", "감마정100밀리그램", 10, 40, 100),
        _block("block-0006", "1정", 125, 40, 25),
        _block("block-0007", "2", 190, 40, 20),
        _block("block-0008", "5", 250, 40, 20),
    )

    rows = materialize_medication_rows(build_ocr_layout(OcrResult(blocks)))

    assert rows.medications[0].name == "감마정100밀리그램"
    assert parse_strength("100밀리그램") == "100mg"
    assert parse_strength("15밀리리터") == "15mL"


def test_real_core_joins_a_split_row_and_projects_only_extracted_fields() -> None:
    blocks = (
        _block("block-0001", "약품명", 10, 10, 45),
        _block("block-0002", "투약량", 120, 10, 45),
        _block("block-0003", "횟수", 180, 10, 35),
        _block("block-0004", "일수", 240, 10, 35),
        _block("block-0005", "긴 약품", 10, 40, 70),
        _block("block-0006", "이름 캡슐", 10, 52, 70),
        _block("block-0007", "0.5정", 125, 52, 35),
        _block("block-0008", "1", 190, 52, 20),
        _block("block-0009", "5", 250, 52, 20),
    )

    rows = materialize_medication_rows(build_ocr_layout(OcrResult(blocks)))
    review = build_project_review(rows)
    medication = review["medications"][0]

    assert rows.medications[0].name == "긴 약품 이름 캡슐"
    assert medication == {
        "tempId": "med-1",
        "name": "긴 약품 이름 캡슐",
        "doseQuantity": "0.5정",
        "timesPerDay": 1,
        "days": 5,
        "confidence": "low",
    }
    assert review["fields"] == {}


def test_numeric_only_dose_quantity_is_projected_as_one_combined_value() -> None:
    blocks = (
        _block("block-0001", "약품명", 10, 10, 45),
        _block("block-0002", "투약량", 120, 10, 45),
        _block("block-0003", "횟수", 180, 10, 35),
        _block("block-0004", "일수", 240, 10, 35),
        _block("block-0005", "단위없는정", 10, 40, 80),
        _block("block-0006", "1", 125, 40, 20),
        _block("block-0007", "2", 190, 40, 20),
        _block("block-0008", "5", 250, 40, 20),
    )

    rows = materialize_medication_rows(build_ocr_layout(OcrResult(blocks)))
    medication = build_project_review(rows)["medications"][0]

    assert medication["name"] == "단위없는정"
    assert medication["doseQuantity"] == "1"
    assert medication["timesPerDay"] == 2
    assert medication["days"] == 5


def test_two_digit_dispensed_date_normalizes_to_the_2000s() -> None:
    assert parse_dispensed_date("25.8.31", today=date(2025, 8, 1)) == "2025-08-31"


def test_two_digit_dispensed_date_accepts_today_plus_31_and_rejects_plus_32() -> None:
    today = date(2025, 8, 1)

    assert parse_dispensed_date("25.9.1", today=today) == "2025-09-01"
    assert parse_dispensed_date("25.9.2", today=today) is None


def test_invalid_calendar_dispensed_date_is_rejected() -> None:
    assert parse_dispensed_date("25.2.29", today=date(2025, 1, 1)) is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2025.8.31", "2025-08-31"),
        ("2025/08/31", "2025-08-31"),
        ("2025-08-31", "2025-08-31"),
        ("20250831", "2025-08-31"),
    ],
)
def test_four_digit_dispensed_date_forms_normalize(
    source: str,
    expected: str,
) -> None:
    assert parse_dispensed_date(source, today=date(2025, 1, 1)) == expected
