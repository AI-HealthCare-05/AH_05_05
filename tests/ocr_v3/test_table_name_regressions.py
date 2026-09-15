from __future__ import annotations

import pytest

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows
from app.services.medication_ocr_v3.pipeline.ocr_layout import build_ocr_layout


def _block(block_id: str, text: str, x: float, y: float, width: float, height: float = 10) -> OcrBlock:
    return OcrBlock(
        block_id=block_id,
        text=text,
        confidence=0.99,
        bbox=(
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
        ),
        line_break=False,
        issues=(),
    )


def _single_receipt_with_local_numeric_headers() -> OcrResult:
    entries = (
        ("main-name-header", "약품명", 141, 159, 57, 20),
        ("main-guidance", "복약안내", 325, 168, 60, 22),
        ("main-name", "*!리토아틴정10밀", 93, 180, 143, 24),
        ("upper-dose", "회", 1020, 514, 12, 12),
        ("upper-times", "일투여", 1032, 514, 28, 12),
        ("upper-days", "총투약", 1059, 514, 28, 12),
        ("lower-dose", "약량", 1017, 526, 20, 12),
        ("lower-times", "횟수", 1039, 526, 18, 14),
        ("lower-days", "일수", 1064, 526, 20, 14),
        ("receipt-name", "리토아틴정10밀리그램", 836, 534, 144, 17),
        ("receipt-dose", "1.00", 1003, 537, 33, 15),
        ("receipt-times", "1", 1043, 540, 11, 12),
        ("receipt-days", "90", 1059, 538, 20, 14),
    )
    return OcrResult(tuple(_block(*entry) for entry in entries))


def _guidance_with_following_description_line() -> OcrResult:
    entries = (
        ("photo-header", "약품사진", 215, 106, 40, 12),
        ("name-header", "약품명", 296, 107, 30, 12),
        ("guidance-header", "복약안내(투약량/횟수/일수)", 411, 107, 99, 10),
        ("caution-header", "주의사항", 583, 106, 47, 13),
        ("name-1", "아나프록스정", 255, 120, 54, 11),
        ("schedule-1", "1정씩3회3일분", 477, 119, 50, 10),
        ("name-2", "오구멘틴정", 255, 152, 46, 11),
        ("schedule-2", "1정씩3회3일분", 477, 152, 50, 9),
        ("description-1", "백색이거나", 255, 163, 37, 9),
        ("description-2", "거의", 292, 163, 16, 9),
        ("description-3", "백색", 309, 163, 16, 9),
        ("description-4", "타원페니실린계", 325, 163, 54, 9),
        ("name-3", "한미알마계이트정", 255, 184, 72, 12),
        ("schedule-3", "1정씩3회3일분", 477, 184, 50, 9),
    )
    return OcrResult(tuple(_block(*entry) for entry in entries))


def _guidance_with_repeated_page_title() -> OcrResult:
    entries = (
        ("page-title", "복약안내", 282, 91, 80, 21),
        ("name-header", "약품명", 220, 186, 37, 14),
        ("merged-guidance-header", "복약안내(투막밥/횟수/필수)", 362, 185, 123, 14),
        ("caution-header", "주의사항", 583, 183, 47, 16),
        ("name-1", "테올란비서방캡슐10...", 183, 204, 107, 14),
        ("schedule-1", "1캡슐씩2회3일분", 464, 203, 74, 12),
        ("name-2", "오논캅셀", 182, 247, 44, 14),
        ("schedule-2", "1캡슐씩2회3일분", 465, 245, 74, 13),
        ("name-3", "타리온정10mg", 181, 291, 74, 14),
        ("schedule-3", "1정씩2회3일분", 466, 289, 66, 13),
    )
    return OcrResult(tuple(_block(*entry) for entry in entries))


def test_single_receipt_row_accepts_split_local_numeric_headers_with_main_name_match() -> None:
    rows = materialize_medication_rows(build_ocr_layout(_single_receipt_with_local_numeric_headers()))

    assert [
        (medication.name, medication.dose_quantity, medication.times_per_day, medication.days)
        for medication in rows.medications
    ] == [
        ("리토아틴정10밀리그램", "1.00", 1, 90),
    ]


@pytest.mark.parametrize("missing", ["main-name", "upper-dose", "upper-times", "upper-days"])
def test_weak_receipt_header_requires_corroboration_and_complete_numeric_headers(missing: str) -> None:
    source = _single_receipt_with_local_numeric_headers()
    source = OcrResult(tuple(block for block in source.blocks if block.block_id != missing))

    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


def test_weak_receipt_header_rejects_competing_main_names() -> None:
    source = _single_receipt_with_local_numeric_headers()
    source = OcrResult((*source.blocks, _block("other-main-name", "리토아틴정10밀", 93, 260, 143, 24)))

    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


def test_guidance_name_excludes_following_description_line() -> None:
    rows = materialize_medication_rows(build_ocr_layout(_guidance_with_following_description_line()))

    assert [medication.name for medication in rows.medications] == [
        "아나프록스정",
        "오구멘틴정",
        "한미알마계이트정",
    ]
    assert rows.medications[1].fields.name.block_ids == ("name-2",)


def test_guidance_repeated_page_title_does_not_block_three_rows() -> None:
    rows = materialize_medication_rows(build_ocr_layout(_guidance_with_repeated_page_title()))

    assert [medication.name for medication in rows.medications] == [
        "테올란비서방캡슐10...",
        "오논캅셀",
        "타리온정10mg",
    ]
    assert [
        (medication.dose_quantity, medication.times_per_day, medication.days) for medication in rows.medications
    ] == [
        ("1", 2, 3),
        ("1", 2, 3),
        ("1", 2, 3),
    ]
