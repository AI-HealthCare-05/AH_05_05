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


def _cards_with_unreadable_receipt_schedule() -> OcrResult:
    # Independent printed copies establish identity; merged digits are NOT doses.
    blocks = [_block("guide", "조제약&복약안내", 700, 50, 400, 40)]
    for i, (receipt, card) in enumerate(
        (
            ("가나다정", "가나다정(가상성분)"),
            ("라마바점", "라마바정(다른성분)"),
            ("사아자정", "사아자점(복합성분)"),
            ("차카타캡슐", "차카타캡슐(시험성분)"),
            ("파하나정", "파하나점(추가성분)"),
        )
    ):
        blocks.extend(
            (
                _block(f"receipt-{i}", receipt, 100 - i * 10, 950 + i * 50, 210, 40),
                _block(f"merged-{i}", "135", 510, 970 + i * 50, 140, 35),
                _block(f"card-{i}", card, 760 + (i % 2) * 900, 300 + (i // 2) * 380, 540, 45),
            )
        )
    return OcrResult(tuple(blocks))


def _table_with_partial_first_schedule(column=2, *, context=True, first_name="비)가나다정", competing=False):
    # A slanted header and the first name are close; only one first-row digit survives OCR.
    blocks = [
        _block("name-header", "약품명", 88, 248, 76, 32),
        _block("dose-header", "투약량", 1053, 305, 51, 21),
        _block("times-header", "횟수", 1112, 305, 34, 19),
        _block("days-header", "일수", 1155, 305, 36, 19),
        _block("first-name", first_name, 83, 271, 214, 36),
        _block("first-number", ("1", "3", "3")[column], (1060, 1145, 1195)[column], 332, 13, 13),
    ]
    if context:
        for index, (name, name_y, number_y) in enumerate((("라마바정5mg", 364, 426), ("사아자정", 479, 527))):
            blocks.append(_block(f"name-{index}", name, 64, name_y, 318, 40))
            for numeric_column, (value, x) in enumerate(zip(("1", "3", "3"), (1070, 1159, 1208), strict=True)):
                blocks.append(_block(f"number-{index}-{numeric_column}", value, x + index * 12, number_y, 16, 20))
    if competing:
        blocks.append(_block("competing-name", "다른약정", 90, 318, 180, 20))
    return OcrResult(tuple(blocks))


@pytest.mark.parametrize("column", [0, 1, 2])
def test_partial_first_row_keeps_grounded_name_and_only_observed_schedule(column):
    rows = materialize_medication_rows(build_ocr_layout(_table_with_partial_first_schedule(column)))
    assert [row.name for row in rows.medications] == ["가나다정", "라마바정5mg", "사아자정"]
    first = rows.medications[0]
    assert (first.dose_quantity, first.times_per_day, first.days) == (
        "1" if column == 0 else "",
        3 if column == 1 else None,
        3 if column == 2 else None,
    )
    assert first.issues
    assert first.fields.name.block_ids == ("first-name",)
    assert all((row.dose_quantity, row.times_per_day, row.days) == ("1", 3, 3) for row in rows.medications[1:])


@pytest.mark.parametrize("options", [{"context": False}, {"first_name": "합계"}, {"competing": True}])
def test_single_number_does_not_create_a_drug_without_unambiguous_table_context(options):
    rows = materialize_medication_rows(build_ocr_layout(_table_with_partial_first_schedule(**options)))
    assert all(row.fields.name.block_ids != ("first-name",) for row in rows.medications)


@pytest.mark.asyncio
async def test_partial_first_row_reaches_review_without_copying_neighbor_regimen():
    from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image

    class Provider:
        async def recognize(self, image):
            return _table_with_partial_first_schedule()

    result = await analyze_processed_image(Provider(), b"test-image")
    medications = result.project_review["medications"]
    assert len(medications) == 3
    assert medications[0]["name"] == "가나다정"
    assert medications[0]["days"] == 3
    assert "doseQuantity" not in medications[0] and "timesPerDay" not in medications[0]
    assert result.analysis_state == "COMPLETED_WITH_ISSUES"


def test_corroborated_card_and_receipt_names_survive_unreadable_numeric_columns():
    rows = materialize_medication_rows(build_ocr_layout(_cards_with_unreadable_receipt_schedule()))
    assert [row.name for row in rows.medications] == ["가나다정", "라마바정", "사아자정", "차카타캡슐", "파하나정"]
    assert all(row.dose_quantity == "" and row.times_per_day is None and row.days is None for row in rows.medications)
    assert all(row.issues for row in rows.medications)


def _receipt_vowel_variant(case="unique"):
    from dataclasses import replace

    blocks = list(_cards_with_unreadable_receipt_schedule().blocks)
    replacements = {"receipt-1": "라마비정", "card-2": "사아자정(복합성분)"}
    if case == "consonant":
        replacements["receipt-1"] = "라마사정"
    elif case == "few-anchors":
        replacements.pop("card-2")
    elif case == "two-variants":
        replacements["receipt-0"] = "가나디정"
    blocks = [replace(b, text=replacements.get(b.block_id, b.text)) for b in blocks]
    if case == "ambiguous":
        blocks.append(_block("competitor", "라마버정", 85, 1000, 210, 40))
    return OcrResult(tuple(blocks))


@pytest.mark.asyncio
async def test_single_vowel_disagreement_recovers_printed_card_name_with_required_review():
    from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image

    class Provider:
        async def recognize(self, image):
            return _receipt_vowel_variant()

    result = await analyze_processed_image(Provider(), b"test-image")
    medications = result.project_review["medications"]
    assert [row["name"] for row in medications] == ["가나다정", "라마바정", "사아자정", "차카타캡슐", "파하나정"]
    assert medications[1]["confidence"] == "low"
    assert all(not {"doseQuantity", "timesPerDay", "days"}.intersection(row) for row in medications)


@pytest.mark.parametrize("case", ["consonant", "few-anchors", "two-variants", "ambiguous"])
def test_vowel_disagreement_does_not_relax_ambiguous_or_uncorroborated_names(case):
    assert not materialize_medication_rows(build_ocr_layout(_receipt_vowel_variant(case))).medications


@pytest.mark.asyncio
async def test_corroborated_names_reach_review_without_guessing_merged_digits():
    from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image

    class Provider:
        async def recognize(self, image):
            return _cards_with_unreadable_receipt_schedule()

    result = await analyze_processed_image(Provider(), b"test-image")
    assert result.analysis_state == "COMPLETED_WITH_ISSUES"
    medications = result.project_review["medications"]
    assert [row["name"] for row in medications] == ["가나다정", "라마바정", "사아자정", "차카타캡슐", "파하나정"]
    assert all(not {"doseQuantity", "timesPerDay", "days"}.intersection(row) for row in medications)


@pytest.mark.parametrize(
    "case", ["no-guide", "no-cards", "duplicate-card", "different-drug", "no-receipt-lane", "branch-names"]
)
def test_name_recovery_does_not_accept_uncorroborated_or_conflicting_text(case):
    from dataclasses import replace

    original = _cards_with_unreadable_receipt_schedule()
    blocks = list(original.blocks)
    if case == "no-guide":
        blocks = [b for b in blocks if b.block_id != "guide"]
    elif case == "no-cards":
        blocks = [b for b in blocks if not b.block_id.startswith("card-")]
    elif case == "duplicate-card":
        card = next(b for b in blocks if b.block_id == "card-0")
        blocks.append(replace(card, block_id="duplicate"))
    elif case == "different-drug":
        blocks = [replace(b, text="다른약정(다른성분)") if b.block_id.startswith("card-") else b for b in blocks]
    elif case == "branch-names":
        branches = ["서울지점", "부산지점", "대구지점", "인천지점", "대전지점"]
        blocks = [
            replace(b, text=branches[int(b.block_id[-1])] + ("(성분)" if b.block_id.startswith("card-") else ""))
            if b.block_id.startswith(("receipt-", "card-"))
            else b
            for b in blocks
        ]
    else:
        blocks = [
            replace(b, bbox=tuple(Point(p.x + 2000, p.y) for p in b.bbox)) if b.block_id == "receipt-2" else b
            for b in blocks
        ]
    assert not materialize_medication_rows(build_ocr_layout(OcrResult(tuple(blocks)))).medications


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


@pytest.mark.parametrize("schedule", ["0.5정씩2회30밀분", "}정씩1회30일분"])
def test_inferred_guidance_keeps_name_when_schedule_is_corrupted(schedule: str) -> None:
    source = _guidance_with_repeated_page_title()
    source = OcrResult(
        (
            *source.blocks,
            _block("partial-name", "추가약정25mg", 183, 225, 90, 12),
            _block("partial-schedule", schedule, 464, 225, 74, 12),
        )
    )
    rows = materialize_medication_rows(build_ocr_layout(source))
    assert len(rows.medications) == 4
    partial = next(row for row in rows.medications if row.name == "추가약정25mg")
    assert (partial.dose_quantity, partial.times_per_day, partial.days) == ("", None, None)
    assert partial.fields.name.block_ids == ("partial-name",)
    assert partial.issues


@pytest.mark.parametrize("case", ["few-anchors", "competing-name", "outside-table"])
def test_damaged_guidance_requires_established_unambiguous_lanes(case: str) -> None:
    source = _guidance_with_repeated_page_title()
    blocks = list(source.blocks)
    if case == "few-anchors":
        blocks = [block for block in blocks if block.block_id not in {"name-3", "schedule-3"}]
    y = 600 if case == "outside-table" else 225
    blocks.extend(
        (
            _block("partial-name", "추가약정25mg", 183, y, 90, 12),
            _block("partial-schedule", "}정씩1회30일분", 464, y, 74, 12),
        )
    )
    if case == "competing-name":
        blocks.append(_block("competitor", "다른약정", 184, y, 80, 12))
    rows = materialize_medication_rows(build_ocr_layout(OcrResult(tuple(blocks))))
    assert all(row.name != "추가약정25mg" for row in rows.medications)


@pytest.mark.asyncio
async def test_damaged_combined_schedule_reaches_review_without_invented_numbers():
    from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image

    class Provider:
        async def recognize(self, image):
            source = _guidance_with_repeated_page_title()
            return OcrResult(
                (
                    *source.blocks,
                    _block("partial-name", "추가약정25mg", 183, 225, 90, 12),
                    _block("partial-schedule", "0.5정씩2회30밀분", 464, 225, 74, 12),
                )
            )

    result = await analyze_processed_image(Provider(), b"test-image")
    assert len(result.project_review["medications"]) == 4
    partial = next(row for row in result.project_review["medications"] if row["name"] == "추가약정25mg")
    assert not {"doseQuantity", "timesPerDay", "days"}.intersection(partial)
    assert result.analysis_state == "COMPLETED_WITH_ISSUES"


@pytest.mark.parametrize("schedule", ["충분한 물과 함께 복용", "30일 후 재진", "1정씩 복용하세요"])
def test_inferred_guidance_does_not_turn_instructions_into_partial_rows(schedule: str) -> None:
    source = _guidance_with_repeated_page_title()
    source = OcrResult(
        (
            *source.blocks,
            _block("partial-name", "백색정", 183, 225, 90, 12),
            _block("partial-schedule", schedule, 464, 225, 74, 12),
        )
    )
    rows = materialize_medication_rows(build_ocr_layout(source))
    assert len(rows.medications) == 3
