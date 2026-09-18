from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.services.medication_ocr_v3.domain.grounding import (
    EvidenceBlock,
    EvidenceCatalog,
    EvidenceRow,
    GroundingSelection,
    MedicationBlockSelection,
    SemanticGroundingSelection,
)
from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline import analyze as analyze_module
from app.services.medication_ocr_v3.pipeline import deterministic_grounding as deterministic_module
from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image
from app.services.medication_ocr_v3.pipeline.deterministic_grounding import (
    canonicalize_deterministic_selection,
    plan_deterministic_grounding,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationFields,
    MedicationRow,
    MedicationRowsResult,
)
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox


def _bbox(x: float, y: float, width: float = 60, height: float = 12) -> AxisAlignedBBox:
    return AxisAlignedBBox(x, y, x + width, y + height)


def _ambiguous_fixture() -> tuple[EvidenceCatalog, MedicationRowsResult]:
    row_id = "row-0001"
    blocks = (
        EvidenceBlock("name", "감마정", 0.99, _bbox(10, 40), "line-name", (row_id,), ("name",)),
        EvidenceBlock("strength-a", "10mg", 0.99, _bbox(80, 40), "line-strength-a", (row_id,), ("strength",)),
        EvidenceBlock("strength-b", "20mg", 0.99, _bbox(80, 55), "line-strength-b", (row_id,), ("strength",)),
        EvidenceBlock("date-a", "2026-09-01", 0.99, _bbox(10, 10), "line-date-a", (), ("dispensedDate",)),
        EvidenceBlock("date-b", "2026-09-02", 0.99, _bbox(10, 25), "line-date-b", (), ("dispensedDate",)),
    )
    field = MedicationField("감마정", "감마정", ("name",), _bbox(10, 40), 0.99, ())
    fields = MedicationFields(
        name=field,
        dose_quantity=MedicationField("1", "1", (), _bbox(150, 40), 0.99, ()),
        times_per_day=MedicationField(1, "1", (), _bbox(180, 40), 0.99, ()),
        days=MedicationField(5, "5", (), _bbox(210, 40), 0.99, ()),
    )
    row = MedicationRow("감마정", "1", 1, 5, 0.99, _bbox(10, 40, 220), fields, ())
    rows = MedicationRowsResult(None, (row,), ())
    catalog = EvidenceCatalog(
        blocks=blocks,
        date_candidates=(blocks[3], blocks[4]),
        rows=(EvidenceRow(row_id, _bbox(10, 40, 220), ("name", "strength-a", "strength-b")),),
    )
    return catalog, rows


def _receipt() -> OcrResult:
    def block(block_id: str, text: str, x: float, y: float, width: float, height: float = 16) -> OcrBlock:
        return OcrBlock(
            block_id,
            text,
            0.99,
            (Point(x, y), Point(x + width, y), Point(x + width, y + height), Point(x, y + height)),
            False,
            (),
        )

    return OcrResult(
        (
            block("header-name", "약품명", 10, 10, 50),
            block("header-dose", "투약량", 200, 10, 45),
            block("header-times", "횟수", 270, 10, 30),
            block("header-days", "일수", 340, 10, 30),
            block("name", "감마정10mg", 10, 50, 100),
            block("dose", "1", 205, 50, 15),
            block("times", "2", 275, 50, 15),
            block("days", "5", 345, 50, 15),
        )
    )


def test_prepared_plan_reuses_exactly_the_same_canonical_result_for_ambiguous_invalid_llm_input() -> None:
    catalog, rows = _ambiguous_fixture()
    llm_selection = GroundingSelection(
        dispensed_date_block_ids=["unknown-date"],
        medications=[
            MedicationBlockSelection(row_id="row-0001", strength_block_ids=["unknown-strength"]),
            MedicationBlockSelection(row_id="row-9999", strength_block_ids=["unknown-row-strength"]),
        ],
    )
    today = date(2026, 9, 18)
    plan = plan_deterministic_grounding(catalog, rows, today=today)

    fresh = canonicalize_deterministic_selection(catalog, rows, llm_selection, today=today)
    reused = canonicalize_deterministic_selection(
        catalog,
        rows,
        llm_selection,
        today=today,
        prepared_plan=plan,
    )

    assert reused == fresh
    assert fresh.ambiguity_required
    assert {issue.field for issue in fresh.issues} >= {"dispensedDate", "strength"}


@pytest.mark.parametrize("mismatch", ["catalog", "rows", "today"])
def test_prepared_plan_rebuilds_when_request_snapshot_or_today_does_not_match(monkeypatch, mismatch: str) -> None:
    catalog, rows = _ambiguous_fixture()
    llm_selection = GroundingSelection(dispensed_date_block_ids=[], medications=[])
    base_today = date(2026, 9, 18)
    if mismatch == "catalog":
        source_catalog = replace(catalog, date_candidates=(catalog.date_candidates[0],))
        target_catalog = catalog
        target_rows = rows
        target_today = base_today
    elif mismatch == "rows":
        source_catalog = catalog
        target_catalog = catalog
        target_rows = replace(rows, medications=tuple(rows.medications))
        target_today = base_today
    else:
        source_catalog = catalog
        target_catalog = catalog
        target_rows = rows
        target_today = date(2026, 9, 19)

    prepared = plan_deterministic_grounding(source_catalog, rows, today=base_today)
    expected = canonicalize_deterministic_selection(
        target_catalog,
        target_rows,
        llm_selection,
        today=target_today,
    )
    original = deterministic_module.plan_deterministic_grounding
    calls = 0

    def spy(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(deterministic_module, "plan_deterministic_grounding", spy)
    actual = canonicalize_deterministic_selection(
        target_catalog,
        target_rows,
        llm_selection,
        today=target_today,
        prepared_plan=prepared,
    )

    assert actual == expected
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic", [False, True])
async def test_analyze_builds_one_request_local_plan_on_legacy_and_semantic_paths(monkeypatch, semantic: bool) -> None:
    original = deterministic_module.plan_deterministic_grounding
    calls = 0

    def spy(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(analyze_module, "plan_deterministic_grounding", spy)
    monkeypatch.setattr(deterministic_module, "plan_deterministic_grounding", spy)

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return _receipt()

    class SemanticStructurer:
        review_mode = "semantic"

        async def select(self, _catalog):
            return SemanticGroundingSelection(dispensed_date_block_ids=[], medications=[])

    result = await analyze_processed_image(Provider(), b"receipt", SemanticStructurer() if semantic else None)

    assert result.project_review["medications"]
    assert calls == 1
