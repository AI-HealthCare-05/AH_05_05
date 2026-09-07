from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline import ocr_layout as layout
from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image


@pytest.mark.parametrize(
    "text, expected",
    [
        ("약 품 명 / 성 분", ("name", False)),
        ("１회량", ("dose", False)),
        ("약품멍", ("name", True)),
        ("복약랑", ("dose", True)),
        ("일수", ("days", False)),
        ("참고사항", None),
        ("투약", None),
    ],
)
def test_header_match_normalizes_only_the_current_input(monkeypatch, text, expected) -> None:
    normalize = layout._normalized_header_text
    calls = []

    def counted(value: str) -> str:
        calls.append(value)
        return normalize(value)

    monkeypatch.setattr(layout, "_normalized_header_text", counted)
    result = layout._header_match(text)

    assert ((result.key, result.fuzzy) if result else None) == expected
    assert calls == [text], "static header aliases must not be normalized again per OCR token"


def _geometry(entries):
    blocks = tuple(
        OcrBlock(
            block_id=f"block-{index:04d}",
            text="참고",
            confidence=0.99,
            bbox=(Point(x, y), Point(x + 10, y), Point(x + 10, y + height), Point(x, y + height)),
            line_break=False,
            issues=(),
        )
        for index, (x, y, height) in enumerate(entries, start=1)
    )
    return layout._geometry_blocks(blocks)[0]


def test_line_grouping_recomputes_statistics_only_when_group_changes(monkeypatch) -> None:
    geometry = _geometry([(column * 20, row * 40, 10) for row in range(20) for column in range(5)])
    real_median = layout.median
    calls = 0

    def counted(values):
        nonlocal calls
        calls += 1
        return real_median(values)

    monkeypatch.setattr(layout, "median", counted)
    groups = layout._cluster_lines(geometry)

    assert len(groups) == 20
    assert [[block.source.block_id for block in group.blocks] for group in groups] == [
        [f"block-{row * 5 + column + 1:04d}" for column in range(5)] for row in range(20)
    ]
    assert calls <= 2 * len(geometry), "unchanged groups must reuse their exact median statistics"


def test_line_grouping_preserves_mixed_height_membership_and_original_bounds() -> None:
    geometry = _geometry([(0, 0, 10), (20, 4, 10), (0, 30, 10), (20, 32, 20), (0, 85, 10)])
    groups = layout._cluster_lines(geometry)

    assert [[block.source.block_id for block in group.blocks] for group in groups] == [
        ["block-0001", "block-0002"],
        ["block-0003", "block-0004"],
        ["block-0005"],
    ]
    assert [(group.bbox.y_min, group.bbox.y_max) for group in groups] == [(0, 14), (30, 52), (85, 95)]


def _labeled_guidance(slope=0.28, *, mixed=True, wrong_days=False, competing=False, header=True):
    entries = [("약품명" if header else "상품", 20, 20, 50)]
    for row, (name, dose, times, days) in enumerate(
        [
            ("가나정", "1.00", "2", "5"),
            ("다라캡슐", "2", "3", "7"),
            ("마바시럽", "10mL", "1", "9"),
        ]
    ):
        y = 60 + row * 65
        entries.extend([(name, 20, y, 150), ("1회투약량", 240, y, 60), (dose, 305, y, 40)])
        for label, value, x in [("1일투여횟수", times, 385), ("총투약일수", days, 525)]:
            if wrong_days and row == 1 and label == "총투약일수":
                label = "종투약일수"
            if mixed and row % 2 == 0:
                entries.extend([(label, x, y, 90), (value, x + 95, y, 15)])
            else:
                entries.append((label + value, x, y, 110))
        entries.append(("1일 3회 주의사항", 320, y + 28, 160))
    if competing:
        entries.append(("4", 308, 60, 15))
    return OcrResult(
        tuple(
            OcrBlock(
                block_id=f"block-{index:04d}",
                text=text,
                confidence=0.99,
                bbox=tuple(
                    Point(px, py + slope * px) for px, py in [(x, y), (x + width, y), (x + width, y + 12), (x, y + 12)]
                ),
                line_break=False,
                issues=(),
            )
            for index, (text, x, y, width) in enumerate(entries, start=1)
        )
    )


@pytest.mark.parametrize("slope, mixed", [(0.28, True), (-0.23, False), (0.0, True)])
async def test_explicit_labeled_guidance_recovers_rows_without_changing_evidence_coordinates(slope, mixed) -> None:
    ocr = _labeled_guidance(slope, mixed=mixed)

    class Provider:
        async def recognize(self, _image):
            return ocr

    result = await analyze_processed_image(Provider(), b"synthetic-guidance")
    medications = result.project_review["medications"]

    assert [row["name"] for row in medications] == ["가나정", "다라캡슐", "마바시럽"]
    assert [row["doseQuantity"] for row in medications] == ["1.00", "2", "10mL"]
    assert [row["timesPerDay"] for row in medications] == [2, 3, 1]
    assert [row["days"] for row in medications] == [5, 7, 9]
    source_by_id = {block.block_id: block for block in ocr.blocks}
    header_box = result.layout.table_candidates[0].header_columns[0].bbox
    header_points = ocr.blocks[0].bbox
    assert (header_box.x_min, header_box.y_min, header_box.x_max, header_box.y_max) == (
        min(point.x for point in header_points),
        min(point.y for point in header_points),
        max(point.x for point in header_points),
        max(point.y for point in header_points),
    )
    for row in result.medication_rows.medications:
        for field in row.fields.as_tuple():
            points = [point for block_id in field.block_ids for point in source_by_id[block_id].bbox]
            assert (field.bbox.x_min, field.bbox.y_min, field.bbox.x_max, field.bbox.y_max) == (
                min(point.x for point in points),
                min(point.y for point in points),
                max(point.x for point in points),
                max(point.y for point in points),
            )


@pytest.mark.parametrize("kwargs", [{"header": False}, {"competing": True}])
def test_labeled_guidance_rejects_missing_header_or_competing_numeric_values(kwargs) -> None:
    assert layout.build_ocr_layout(_labeled_guidance(**kwargs)).table_candidates == ()


def test_labeled_guidance_does_not_guess_a_misrecognized_duration_label() -> None:
    from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows

    rows = materialize_medication_rows(layout.build_ocr_layout(_labeled_guidance(wrong_days=True))).medications
    assert [row.name for row in rows] == ["가나정", "마바시럽"]
    assert [row.days for row in rows] == [5, 9]


@pytest.mark.parametrize("mode", ["remote-panel", "remote-header", "duplicate-name"])
def test_labeled_guidance_rejects_cross_panel_and_duplicate_name_ambiguity(mode) -> None:
    blocks = []
    for block in _labeled_guidance(slope=0).blocks:
        if (mode == "remote-panel" and block.bbox[0].y >= 120) or (
            mode == "remote-header" and block.block_id != "block-0001"
        ):
            block = replace(block, bbox=tuple(Point(point.x, point.y + 10000) for point in block.bbox))
        if mode == "duplicate-name" and block.text == "다라캡슐":
            block = replace(block, text="가나정(다른 설명)")
        blocks.append(block)
    assert layout.build_ocr_layout(OcrResult(tuple(blocks))).table_candidates == ()


@pytest.mark.parametrize("mode", ["steep", "inconsistent-slopes", "suffix-conflict", "times-conflict", "two-names"])
def test_labeled_guidance_rejects_unproven_label_or_name_alignment(mode) -> None:
    blocks = list(_labeled_guidance(slope=0.75 if mode == "steep" else 0).blocks)
    if mode == "inconsistent-slopes":
        index = next(index for index, block in enumerate(blocks) if block.text == "1회투약량")
        source = blocks[index]
        blocks[index] = replace(source, bbox=tuple(Point(point.x, point.y + 0.2 * point.x) for point in source.bbox))
    elif mode == "suffix-conflict":
        index = next(index for index, block in enumerate(blocks) if block.text == "1회투약량")
        blocks[index] = replace(blocks[index], text="1회투약량1")
    elif mode in {"times-conflict", "two-names"}:
        source = next(block for block in blocks if block.text == ("2" if mode == "times-conflict" else "가나정"))
        blocks.append(replace(source, block_id="block-9999", text="4" if mode == "times-conflict" else "사아정"))
    assert layout.build_ocr_layout(OcrResult(tuple(blocks))).table_candidates == ()

