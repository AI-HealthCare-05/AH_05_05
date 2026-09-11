from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unicodedata import normalize

import pytest

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrErrorCode, OcrProviderError, OcrResult
from app.services.medication_ocr_v3.pipeline import analyze as analyze_module
from app.services.medication_ocr_v3.pipeline import grounding as grounding_module
from app.services.medication_ocr_v3.pipeline import medication_rows as medication_rows_module
from app.services.medication_ocr_v3.pipeline import ocr_layout as ocr_layout_module
from app.services.medication_ocr_v3.pipeline import review_projection as review_projection_module
from app.services.medication_ocr_v3.pipeline.analyze import (
    AnalyzePipelineCancellation,
    AnalyzePipelineFailure,
    analyze_processed_image,
)
from app.services.medication_ocr_v3.pipeline.deterministic_grounding import (
    canonicalize_deterministic_selection,
    materialize_deterministic_grounding,
    plan_deterministic_grounding,
)
from app.services.medication_ocr_v3.pipeline.evidence_catalog import build_evidence_catalog
from app.services.medication_ocr_v3.pipeline.grounding import (
    parse_dispensed_date,
    parse_strength,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows
from app.services.medication_ocr_v3.pipeline.ocr_layout import build_ocr_layout
from app.services.medication_ocr_v3.pipeline.review_projection import build_project_review


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


@pytest.mark.parametrize("scale", [1, 3])
def test_payment_filter_does_not_cross_receipt_and_guidance_column_gutter(scale):
    from app.services.medication_ocr_v3.pipeline import evidence_catalog as catalog_module

    # The receipt's amount header and fourth drug name share a baseline, but
    # repeated text above/below them establishes two distinct side-by-side panels.
    blocks = (
        _block("amount", "금액", 340, 747, 62, 18),
        _block("receipt-above", "영수증", 198, 650, 204, 20),
        _block("receipt-below", "품목", 198, 820, 204, 20),
        _block("guidance-above", "복약안내", 440, 650, 340, 20),
        _block("guidance-below", "식후 복용", 440, 820, 340, 20),
        _block("fourth-name", "파모티딘정20mg", 642, 747, 138, 24),
        _block("same-panel-value", "9600", 340, 769, 60, 18),
    )
    blocks = tuple(replace(b, bbox=tuple(Point(p.x * scale, p.y * scale) for p in b.bbox)) for b in blocks)
    layout = build_ocr_layout(OcrResult(blocks))
    sources, _ = catalog_module._unique_geometry_sources(blocks)
    _, sensitive, _ = catalog_module._line_indexes(layout, sources, frozenset({"fourth-name"}))
    assert "amount" in sensitive
    assert "same-panel-value" in sensitive
    assert "fourth-name" not in sensitive


def test_wide_receipt_columns_and_unproven_drug_text_remain_sensitive():
    from app.services.medication_ocr_v3.pipeline import evidence_catalog as catalog_module

    blocks = (
        _block("amount", "금액", 198, 747, 62, 18),
        _block("receipt-above", "항목", 198, 650, 62, 20),
        _block("receipt-below", "품목", 198, 820, 62, 20),
        _block("receipt-value", "9600", 340, 747, 60, 18),
        _block("value-above", "1200", 340, 650, 60, 20),
        _block("value-below", "4500", 340, 820, 60, 20),
        _block("drug-like", "파모티딘정20mg", 440, 747, 138, 24),
        _block("right-above", "내용", 440, 650, 138, 20),
        _block("right-below", "참고", 440, 820, 138, 20),
    )
    sources, _ = catalog_module._unique_geometry_sources(blocks)
    _, sensitive, _ = catalog_module._line_indexes(build_ocr_layout(OcrResult(blocks)), sources)
    assert "receipt-value" in sensitive
    assert "drug-like" in sensitive


@pytest.mark.parametrize("scale", [1, 3])
def test_dispensed_date_anchors_below_label_not_tall_next_visit_above(scale: int) -> None:
    source = OcrResult(
        (
            _block("next-visit", "2018-02-26", 594 * scale, 55 * scale, 100 * scale, 50 * scale),
            _block("label", "조제일자", 565 * scale, 80 * scale, 70 * scale, 20 * scale),
            _block("dispensed", "2018-02-19", 594 * scale, 118 * scale, 100 * scale, 20 * scale),
        )
    )
    layout = build_ocr_layout(source)
    rows = materialize_medication_rows(layout)
    catalog = build_evidence_catalog(source, layout, rows)
    plan = plan_deterministic_grounding(catalog, rows, today=date(2018, 2, 26))

    assert [block.block_id for block in catalog.date_candidates] == ["dispensed"]
    assert plan.selection.dispensed_date_block_ids == ["dispensed"]
    assert parse_dispensed_date(catalog.date_candidates[0].text, today=date(2018, 2, 26)) == "2018-02-19"


@pytest.mark.parametrize("x,y", [(190, 100), (120, 126), (190, 126)])
def test_dispensed_date_keeps_right_or_below_value_with_other_panel_date(x: int, y: int) -> None:
    source = OcrResult(
        (
            _block("receipt-date", "2018-02-26", 600, 100, 100, 20),
            _block("label", "조제일자", 100, 100, 70, 20),
            _block("dispensed", "2018-02-19", x, y, 100, 20),
        )
    )
    layout = build_ocr_layout(source)
    rows = materialize_medication_rows(layout)
    catalog = build_evidence_catalog(source, layout, rows)
    assert [block.block_id for block in catalog.date_candidates] == ["dispensed"]


@pytest.mark.parametrize(
    "suffix,x,y,expected",
    [
        ("일자", 136, 100, ["dispensed"]),
        ("일", 136, 100, ["dispensed"]),
        ("일자", 600, 100, []),
        ("일자", 136, 150, []),
    ],
)
def test_dispensed_date_accepts_only_adjacent_split_label(suffix: str, x: int, y: int, expected: list[str]) -> None:
    source = OcrResult(
        (
            _block("label-start", "조제", 100, 100, 35, 20),
            _block("label-end", suffix, x, y, 35, 20),
            _block("dispensed", "2018-02-19", 190, 100, 100, 20),
        )
    )
    layout = build_ocr_layout(source)
    catalog = build_evidence_catalog(source, layout, materialize_medication_rows(layout))
    assert [block.block_id for block in catalog.date_candidates] == expected


@pytest.mark.asyncio
async def test_pipeline_stage_lists_include_resolve_for_ocr_failure_and_cancellation() -> None:
    class FailingProvider:
        async def recognize(self, _image: bytes) -> OcrResult:
            raise OcrProviderError(OcrErrorCode.OCR_TIMEOUT, 504)

    failed = await analyze_processed_image(FailingProvider(), b"test-image")

    assert isinstance(failed, AnalyzePipelineFailure)
    assert [stage.name for stage in failed.stages] == ["ocr", "candidate", "resolve", "llm", "validate"]
    assert [stage.status for stage in failed.stages] == ["failed", "skipped", "skipped", "skipped", "skipped"]
    assert all(stage.code == "UPSTREAM_FAILED" for stage in failed.stages[1:])

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return OcrResult(())

    async def cancelled() -> bool:
        return True

    cancelled_result = await analyze_processed_image(Provider(), b"test-image", is_cancelled=cancelled)

    assert isinstance(cancelled_result, AnalyzePipelineCancellation)
    assert [stage.name for stage in cancelled_result.stages] == ["ocr", "candidate", "resolve", "llm", "validate"]
    assert [stage.status for stage in cancelled_result.stages] == [
        "succeeded",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert cancelled_result.stages[1].code == "REQUEST_CANCELLED"


@pytest.mark.asyncio
async def test_resolve_and_validate_stages_own_their_complete_local_work(monkeypatch) -> None:
    class Clock:
        value = 0.0

        def perf_counter(self) -> float:
            return self.value

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = Clock()
    original_plan = analyze_module.plan_deterministic_grounding
    original_project_review = analyze_module.build_project_review
    original_field_evidence = analyze_module._field_evidence

    def delayed_plan(*args: object, **kwargs: object) -> object:
        result = original_plan(*args, **kwargs)
        clock.advance(0.011)
        return result

    def delayed_project_review(*args: object, **kwargs: object) -> dict[str, object]:
        result = original_project_review(*args, **kwargs)
        clock.advance(0.013)
        return result

    def delayed_field_evidence(*args: object, **kwargs: object) -> dict[str, object]:
        result = original_field_evidence(*args, **kwargs)
        clock.advance(0.017)
        return result

    monkeypatch.setattr(analyze_module, "time", SimpleNamespace(perf_counter=clock.perf_counter))
    monkeypatch.setattr(analyze_module, "plan_deterministic_grounding", delayed_plan)
    monkeypatch.setattr(analyze_module, "build_project_review", delayed_project_review)
    monkeypatch.setattr(analyze_module, "_field_evidence", delayed_field_evidence)

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return _stacked_header_receipt()

    result = await analyze_processed_image(Provider(), b"test-image")

    assert [stage.name for stage in result.stages] == ["ocr", "candidate", "resolve", "llm", "validate"]
    elapsed_by_name = {stage.name: stage.elapsed_ms for stage in result.stages}
    assert elapsed_by_name["resolve"] == 11
    assert elapsed_by_name["validate"] == 30
    assert result.structure_elapsed_ms == 41


@pytest.mark.asyncio
async def test_cancellation_after_candidate_marks_every_remaining_stage():
    class Provider:
        async def recognize(self, _image):
            return _stacked_header_receipt()

    cancellations = iter((False, True))

    async def cancelled():
        return next(cancellations)

    result = await analyze_processed_image(Provider(), b"synthetic", is_cancelled=cancelled)
    assert isinstance(result, AnalyzePipelineCancellation)
    assert [stage.status for stage in result.stages] == ["succeeded", "succeeded", "skipped", "skipped", "skipped"]
    assert all(stage.code == "REQUEST_CANCELLED" for stage in result.stages[2:])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,failed_stage,code",
    [
        ("empty", "ocr", "NO_OCR_BLOCKS"),
        ("no-table", "candidate", "TABLE_NOT_FOUND"),
        ("rejected-table", "candidate", "AMBIGUOUS_MEDICATION_TABLE"),
    ],
)
async def test_unusable_output_fails_at_origin_and_does_not_run_downstream(monkeypatch, kind, failed_stage, code):
    source = _stacked_header_receipt()
    if kind == "empty":
        source = OcrResult(())
    elif kind == "no-table":
        source = OcrResult((_block("notice", "복약 안내입니다", 10, 10, 100),))
    else:
        source = OcrResult(
            (
                _block("h-name", "품목명", 10, 10, 50),
                _block("h-dose", "투약량", 250, 10, 40),
                _block("h-times", "횟수", 310, 10, 30),
                _block("h-days", "일수", 360, 10, 30),
                _block("name", "급여산정내역", 10, 40, 200),
                _block("dose", "1", 260, 40, 10),
                _block("times", "3", 320, 40, 10),
                _block("days", "5", 370, 40, 10),
            )
        )

    class Provider:
        async def recognize(self, _image):
            return source

    def forbidden(*args, **kwargs):
        raise AssertionError("downstream processing must not run after fatal extraction failure")

    monkeypatch.setattr(analyze_module, "plan_deterministic_grounding", forbidden)
    monkeypatch.setattr(analyze_module, "build_project_review", forbidden)
    result = await analyze_processed_image(Provider(), b"synthetic")
    stages = {stage.name: stage for stage in result.stages}
    assert stages[failed_stage].status == "failed"
    assert stages[failed_stage].code == code
    after_failure = False
    for stage in result.stages:
        if after_failure:
            assert (stage.status, stage.code, stage.elapsed_ms, stage.call_count) == (
                "skipped",
                "UPSTREAM_FAILED",
                0,
                0,
            )
        after_failure = after_failure or stage.name == failed_stage
    assert result.project_review["medications"] == []
    assert result.analysis_state == "FAILED"


@pytest.mark.parametrize(
    "name,accepted",
    [
        ("아목시실린클라불란산정625mg", True),
        ("아목시실린클라불란산정 625mg", True),
        ("트라넥삼산정500mg", True),
        ("엽산정1mg", True),
        ("산정", False),
        ("재산정", False),
        ("재산정625mg", False),
        ("•재산정625mg", False),
        ("비)재산정625mg", False),
        ("정산정625mg", False),
        ("산정내역", False),
        ("보험료산정", False),
        ("급여산정625mg", False),
        ("산정625mg", False),
    ],
)
def test_acid_tablet_strength_does_not_trigger_administrative_calculation_filter(name, accepted):
    source = OcrResult(
        (
            _block("h-name", "품목명", 10, 10, 50),
            _block("h-dose", "투약량", 250, 10, 40),
            _block("h-times", "횟수", 310, 10, 30),
            _block("h-days", "일수", 360, 10, 30),
            _block("name", name, 10, 40, 200),
            _block("dose", "1", 260, 40, 10),
            _block("times", "3", 320, 40, 10),
            _block("days", "5", 370, 40, 10),
        )
    )
    rows = materialize_medication_rows(build_ocr_layout(source))
    assert bool(rows.medications) is accepted
    if accepted:
        assert len(rows.medications) == 1
        assert rows.medications[0].times_per_day == 3


@pytest.mark.asyncio
async def test_validation_retains_partial_output_but_marks_issues():
    class Provider:
        async def recognize(self, _image):
            source = _stacked_header_receipt()
            return OcrResult(
                tuple(replace(b, confidence=0.4) if b.block_id == "receipt-name" else b for b in source.blocks)
            )

    result = await analyze_processed_image(Provider(), b"synthetic")
    assert len(result.project_review["medications"]) == 1
    assert result.project_review["medications"][0]["confidence"] == "low"
    stage = next(stage for stage in result.stages if stage.name == "validate")
    assert (stage.status, stage.code) == ("succeeded", "COMPLETED_WITH_ISSUES")


@pytest.mark.asyncio
async def test_validation_rejects_empty_projected_output_at_validate(monkeypatch):
    class Provider:
        async def recognize(self, _image):
            return _stacked_header_receipt()

    monkeypatch.setattr(
        analyze_module, "build_project_review", lambda *a: {"fields": {}, "medications": [], "lowConfidenceCount": 0}
    )
    result = await analyze_processed_image(Provider(), b"synthetic")
    stage = next(stage for stage in result.stages if stage.name == "validate")
    assert (stage.status, stage.code) == ("failed", "NO_VALID_MEDICATION_ROWS")
    assert result.analysis_state == "FAILED"


@pytest.mark.asyncio
async def test_deterministic_grounding_marks_the_skipped_llm_as_sufficient() -> None:
    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return _stacked_header_receipt()

    result = await analyze_processed_image(Provider(), b"test-image")

    assert result.project_review["medications"] == [
        {
            "tempId": "med-1",
            "name": "리토아틴정10밀리그램",
            "strength": "10mg",
            "doseQuantity": "1.00",
            "timesPerDay": 1,
            "days": 90,
            "confidence": "high",
        }
    ]
    assert result.stages[3].name == "llm"
    assert result.stages[3].status == "skipped"
    assert result.stages[3].code == "DETERMINISTIC_SUFFICIENT"


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


@pytest.mark.parametrize("prefix", ["*!", "!?/#$", "※→★", "✔️ 💊 ", "[]{}()", "！？＊", "__! ", "· + • !"])
def test_leading_symbols_do_not_change_medication_name_or_raw_evidence(prefix: str) -> None:
    printed_name = prefix + "리토아틴정10밀리그램"
    source = OcrResult(
        (
            _block("header-name", "약품명", 10, 10, 80),
            _block("header-dose", "투약량", 250, 10, 45),
            _block("header-times", "횟수", 320, 10, 35),
            _block("header-days", "일수", 390, 10, 35),
            _block("name", printed_name, 10, 40, 220),
            _block("dose", "1", 260, 40, 20),
            _block("times", "1", 330, 40, 20),
            _block("days", "90", 400, 40, 20),
        )
    )
    layout = build_ocr_layout(source)
    rows = materialize_medication_rows(layout)
    catalog = build_evidence_catalog(source, layout, rows)

    assert [row.name for row in rows.medications] == ["리토아틴정10밀리그램"]
    assert medication_rows_module._is_plausible_product_name(printed_name)
    assert ocr_layout_module._inline_name_key(printed_name) == "리토아틴정10밀리그램"
    assert build_project_review(rows)["medications"][0]["days"] == 90
    assert source.blocks[4].text == printed_name
    evidence = next(block for block in catalog.blocks if block.block_id == "name")
    assert evidence.text == " ".join(normalize("NFKC", printed_name).split())
    assert rows.medications[0].fields.name.block_ids == ("name",)


@pytest.mark.parametrize(
    ("printed_name", "expected"),
    [
        ("*!리토아틴정10밀", "리토아틴정10밀"),
        ("※5에프정", "5에프정"),
        ("→가나정10/20mg", "가나정10/20mg"),
        ("!가나크림0.1%", "가나크림0.1%"),
        ("!?!", ""),
    ],
)
def test_name_prefix_cleanup_preserves_printed_suffix_and_internal_characters(printed_name: str, expected: str) -> None:
    assert medication_rows_module._canonical_name_value(printed_name) == expected


def _stacked_header_receipt() -> OcrResult:
    # Real failing layout, with only medication evidence and synthetic context.
    entries = (
        ("main-header", "약품명", 141, 159, 57, 20),
        ("main-guidance", "복약안내", 325, 168, 60, 22),
        ("main-notice", "주의사항", 663, 175, 56, 21),
        ("clipped-name", "*!리토아틴정10밀", 93, 180, 143, 24),
        ("visit-label", "최근내방일:", 839, 509, 83, 17),
        ("visit-date", "2020-01-01", 921, 510, 87, 17),
        ("dose-upper", "1회", 1012, 511, 20, 16),
        ("times-upper", "일투여", 1032, 511, 30, 16),
        ("days-upper", "총투약", 1062, 511, 26, 16),
        ("dose-header", "투약량", 1009, 526, 28, 13),
        ("times-header", "횟수", 1036, 525, 23, 15),
        ("days-header", "일수", 1063, 525, 21, 15),
        ("receipt-name", "리토아틴정10밀리그램", 836, 533, 146, 18),
        ("receipt-dose", "1.00", 1003, 537, 33, 15),
        ("receipt-times", "1", 1042, 539, 11, 13),
        ("receipt-days", "90", 1058, 537, 21, 15),
    )
    return OcrResult(
        tuple(_block(block_id, text, x, y, width, height) for block_id, text, x, y, width, height in entries)
    )


@pytest.mark.parametrize("unrelated_y", [None, 510, 525, 537])
async def test_local_stacked_numeric_headers_recover_a_receipt_row(unrelated_y: int | None) -> None:
    source = _stacked_header_receipt()
    if unrelated_y is not None:
        source = replace(
            source, blocks=(*source.blocks, _block("unrelated", "별도 참고사항", 10, unrelated_y, 350, 24))
        )

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return source

    result = await analyze_processed_image(Provider(), b"synthetic-stacked-header-receipt")
    medications = result.project_review["medications"]

    assert len(medications) == 1
    assert medications[0]["name"] == "리토아틴정10밀리그램"
    assert medications[0]["doseQuantity"] == "1.00"
    assert medications[0]["timesPerDay"] == 1
    assert medications[0]["days"] == 90
    layout = build_ocr_layout(source)
    rows = materialize_medication_rows(layout)
    catalog = build_evidence_catalog(source, layout, rows)
    assert len(catalog.rows) == 1
    assert rows.medications[0].fields.name.block_ids == ("receipt-name",)
    assert rows.medications[0].fields.days.block_ids == ("receipt-days",)
    assert not {"clipped-name", "visit-label", "visit-date", "unrelated"}.intersection(
        block_id for row in catalog.rows for block_id in row.block_ids
    )
    assert rows.selected_table.header_inferred
    assert rows.selected_table.observed_header_coverage == 3


@pytest.mark.parametrize("missing_id", ["dose-upper", "times-upper", "days-upper", "days-header"])
def test_local_receipt_recovery_requires_complete_explicit_numeric_headers(missing_id: str) -> None:
    source = _stacked_header_receipt()
    source = replace(source, blocks=tuple(block for block in source.blocks if block.block_id != missing_id))

    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


@pytest.mark.parametrize(
    "extra",
    [
        _block("competing-dose", "2", 1005, 538, 20, 15),
        _block("invalid-competing-dose", "0", 1005, 538, 20, 15),
        _block("signed-competing-dose", "-1", 1005, 538, 20, 15),
        _block("garbled-competing-dose", "1O", 1005, 538, 20, 15),
        _block("competing-name", "다른정20밀리그램", 840, 538, 140, 17),
    ],
)
def test_local_receipt_recovery_does_not_guess_between_competing_values(extra: OcrBlock) -> None:
    source = _stacked_header_receipt()
    source = replace(source, blocks=(*source.blocks, extra))

    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


@pytest.mark.parametrize("name", ["청구금액", "보험부담금", "새봄병원", "리토아틴정10밀"])
def test_local_receipt_recovery_requires_a_complete_medication_name(name: str) -> None:
    source = _stacked_header_receipt()
    source = replace(
        source,
        blocks=tuple(
            replace(block, text=name) if block.block_id == "receipt-name" else block for block in source.blocks
        ),
    )

    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


def test_local_receipt_recovery_rejects_a_second_numeric_row() -> None:
    source = _stacked_header_receipt()
    source = replace(
        source,
        blocks=(
            *source.blocks,
            _block("second-name", "다른정20밀리그램", 836, 568, 146, 18),
            _block("second-dose", "2", 1003, 572, 33, 15),
            _block("second-times", "3", 1042, 574, 11, 13),
            _block("second-days", "30", 1058, 572, 21, 15),
        ),
    )
    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


def test_local_receipt_recovery_rejects_distant_headers() -> None:
    source = _stacked_header_receipt()
    source = replace(
        source,
        blocks=tuple(
            replace(block, bbox=tuple(replace(point, y=point.y - 200) for point in block.bbox))
            if block.block_id.endswith(("-header", "-upper"))
            else block
            for block in source.blocks
        ),
    )
    assert materialize_medication_rows(build_ocr_layout(source)).medications == ()


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
        "confidence": "high",
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


@pytest.mark.parametrize("include_products", [True, False])
async def test_product_names_win_over_ingredient_lines_aligned_with_schedule(include_products: bool) -> None:
    # Product/ingredient geometry from a guidance table, with no patient data.
    blocks = [
        _block("header-name", "약품명/성분", 567, 435, 201, 55),
        _block("header-dose", "투약량", 2239, 500, 107, 48),
        _block("header-times", "횟수", 2395, 500, 72, 48),
        _block("header-days", "일수", 2511, 500, 73, 48),
    ]
    products = [
        "오메크라정625밀리그램(아목시실린수화물·클라불란산칼륨(4:1))_(1정)",
        "글로덱시정300mg(덱시부프로펜)_(0.3g/1정)",
        "휴니즈레바미피드정_(0.1g/1정)",
    ]
    ingredients = ["클라불란산칼륨 0.125g", "덱시부프로펜 0.3g", "레바미피드 0.1g"]
    for index, (product, ingredient) in enumerate(zip(products, ingredients, strict=True)):
        top = 530 + index * (243 if include_products else 180)
        if include_products:
            blocks.append(_block(f"product-{index}", product, 571, top, 1626, 99))
        blocks.extend(
            (
                _block(f"manufacturer-{index}", "(주)제약회사", 575, top + 65, 300, 40),
                _block(f"ingredient-{index}", ingredient, 576, top + 115, 480, 55),
                _block(f"dose-{index}", "1", 2280, top + 116, 26, 43),
                _block(f"times-{index}", "3", 2420, top + 116, 26, 43),
                _block(f"days-{index}", "5", 2535, top + 116, 26, 43),
            )
        )

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return OcrResult(tuple(blocks))

    result = await analyze_processed_image(Provider(), b"synthetic-guidance-table")
    medications = result.project_review["medications"]

    assert [row["name"] for row in medications] == (
        ["오메크라정625밀리그램", "글로덱시정300mg", "휴니즈레바미피드정"] if include_products else ingredients
    )
    assert [(row["doseQuantity"], row["timesPerDay"], row["days"]) for row in medications] == [
        ("1", 3, 5),
        ("1", 3, 5),
        ("1", 3, 5),
    ]
    if include_products:
        # Keep the existing evidence-backed parser contract for both printed units.
        assert [row.get("strength") for row in medications] == ["625mg", "300mg 0.3g", "0.1g"]
    else:
        assert [row.get("strength") for row in medications] == ["0.125g", "0.3g", "0.1g"]


def test_main_guidance_rows_win_over_a_shorter_clipped_receipt_table() -> None:
    blocks = (
        _block("block-0001", "복약안내(투약량/횟수/일수)", 410, 80, 130),
        _block("block-0002", "아목클정375mg", 250, 85, 75),
        _block("block-0003", "1명씩3회7일분", 490, 90, 65),
        _block("block-0004", "록스파인정", 252, 125, 55),
        _block("block-0005", "1정씩3회7일분", 490, 125, 65),
        _block("block-0006", "스토엠정", 254, 155, 50),
        _block("block-0007", "1정씩3회7일분", 492, 155, 65),
        _block("block-0008", "알리코프정", 256, 185, 55),
        _block("block-0009", "1정씩3회7일분", 494, 185, 65),
        _block("block-0010", "에리텐캡슐", 258, 215, 58),
        _block("block-0011", "1협술학3회7일분", 496, 215, 70),
        _block("block-0012", "세페리손정", 260, 245, 58),
        _block("block-0013", "1정씩2회7일분", 498, 245, 65),
        _block("block-0014", "약품명", 5, 300, 45),
        _block("block-0015", "투약량", 125, 300, 45),
        _block("block-0016", "횟수", 180, 300, 35),
        _block("block-0017", "일수", 235, 300, 35),
        _block("block-0018", "목클정375mg", 5, 320, 70),
        _block("block-0019", "1", 130, 320, 10),
        _block("block-0020", "3", 190, 320, 10),
        _block("block-0021", "7", 245, 320, 10),
        _block("block-0022", "스파인정", 5, 340, 50),
        _block("block-0023", "1", 130, 340, 10),
        _block("block-0024", "3", 190, 340, 10),
        _block("block-0025", "7", 245, 340, 10),
        _block("block-0026", "에리덴캡슐", 5, 360, 60),
        _block("block-0027", "1", 130, 360, 10),
        _block("block-0028", "3", 190, 360, 10),
        _block("block-0029", "7", 245, 360, 10),
        _block("block-0030", "세페리손정", 5, 380, 60),
        _block("block-0031", "1", 130, 380, 10),
        _block("block-0032", "2", 190, 380, 10),
        _block("block-0033", "7", 245, 380, 10),
        _block("block-0034", "부담금", 3, 81, 54),
        _block("block-0035", "0원", 154, 82, 20),
        _block("block-0036", "총액", 5, 62, 30),
        _block("block-0037", "8600원", 135, 63, 37),
        _block("block-0038", "부담금", 4, 71, 52),
        _block("block-0039", "23390원", 130, 73, 42),
    )

    rows = materialize_medication_rows(build_ocr_layout(OcrResult(blocks)))

    assert [medication.name for medication in rows.medications] == [
        "아목클정375mg",
        "록스파인정",
        "스토엠정",
        "알리코프정",
        "에리텐캡슐",
        "세페리손정",
    ]
    assert rows.medications[0].dose_quantity == "1"
    assert rows.medications[4].dose_quantity == ""
    assert rows.medications[4].times_per_day == 3
    assert rows.medications[4].days == 7

    catalog = build_evidence_catalog(OcrResult(blocks), build_ocr_layout(OcrResult(blocks)), rows)
    plan = plan_deterministic_grounding(catalog, rows)
    canonical = canonicalize_deterministic_selection(catalog, rows, plan.selection)
    grounded = materialize_deterministic_grounding(catalog, rows, canonical)

    assert build_project_review(rows, grounded)["medications"][0]["strength"] == "375mg"


@pytest.mark.parametrize("duplicate_schedule", [None, "1정씩3회3일분"])
@pytest.mark.parametrize("photo_caption", [None, "사진"])
async def test_split_guidance_with_centered_headers_recovers_four_rows_from_sparse_receipt(
    duplicate_schedule: str | None,
    photo_caption: str | None,
) -> None:
    # Geometry follows the synthetic template: titles are centered, names left aligned.
    entries = [
        ("약품사진", 497, 208, 76),
        ("약품명", 725, 208, 61),
        ("복약안내(투약량", 911, 208, 140),
        ("/", 1054, 208, 14),
        ("횟수", 1069, 208, 40),
        ("/", 1113, 208, 10),
        ("일수)", 1125, 208, 49),
        ("주의사항", 1329, 208, 79),
    ]
    names = ["아세트아미노펜정", "세티리진정", "암브록솔염산염정", "모메타손 비강분무액"]
    for index, (name, width, times, days) in enumerate(
        zip(names, [160, 87, 137, 168], [3, 1, 3, 2], [3, 5, 5, 7], strict=True)
    ):
        y = 260 + index * 156
        entries.extend([(name, 630, y, width), ("1회", 889, y, 28)])
        if index < 3:
            entries.append((["500mg", "10mg", "30mg"][index], 632 + width, y, 53))
            entries.extend(
                [
                    ("1정", 921, y, 28),
                    ("/", 955, y, 10),
                    ("1일", 965, y, 29),
                    (f"{times}회", 998, y, 30),
                    ("/", 1032, y, 10),
                    (f"{days}일분", 1042, y, 49),
                ]
            )
        else:
            entries.extend(
                [
                    ("각", 921, y, 20),
                    ("비공", 945, y, 35),
                    ("1분무", 984, y, 48),
                    ("/", 1036, y, 10),
                    ("1일", 1050, y, 29),
                    ("2회", 1083, y, 30),
                    ("/", 1117, y, 10),
                    ("7일분", 1131, y, 49),
                ]
            )
        entries.append(("주의사항", 1199 if index == 3 else 1230, y, 85))
    entries.extend([("품목명", 130, 760, 45), ("투약량", 210, 760, 40), ("횟수", 280, 760, 30), ("일수", 330, 760, 30)])
    for index, (name, times, days) in enumerate(zip(names, [3, 1, 3, 2], [3, 5, 5, 7], strict=True)):
        y = 790 + index * 40
        entries.extend([(name, 20, y, 155), (str(days), 335, y, 10)])
        if index != 1:
            entries.append((str(times), 285, y, 10))
        if index in (0, 3):
            entries.append(("1" if index == 0 else "각 1분무", 220, y, 40))
    if duplicate_schedule is not None:
        entries.append((duplicate_schedule, 1280, 260, 70))
    if photo_caption is not None:
        entries.append((photo_caption, 640, 260, 20))
    blocks = tuple(_block(f"block-{index:04d}", *entry) for index, entry in enumerate(entries, start=1))

    rows = materialize_medication_rows(build_ocr_layout(OcrResult(blocks)))

    assert [row.name for row in rows.medications] == names
    assert [row.dose_quantity for row in rows.medications[:3]] == ["1", "1", "1"]
    assert [row.times_per_day for row in rows.medications] == [3, 1, 3, 2]
    assert [row.days for row in rows.medications] == [3, 5, 5, 7]
    assert rows.medications[3].fields.dose_quantity.source_text == "각 비공 1분무"

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return OcrResult(blocks)

    analyzed = await analyze_processed_image(Provider(), b"test-image")
    assert [med["name"] for med in analyzed.project_review["medications"]] == names
    assert [med["doseQuantity"] for med in analyzed.project_review["medications"]] == [
        "1정",
        "1정",
        "1정",
        "각비공1분무",
    ]


@pytest.mark.parametrize("gap, accepted", [(0, False), (9, False), (10, True), (19, True)])
def test_explicit_guidance_requires_a_visible_gap_before_a_caution(gap: int, accepted: bool) -> None:
    entries = [
        ("1회", 0, 20),
        ("1정", 25, 20),
        ("/", 50, 5),
        ("1일", 60, 20),
        ("3회", 85, 20),
        ("/", 110, 5),
        ("5일분", 120, 30),
        ("주의사항", 150 + gap, 60),
    ]
    blocks = tuple(
        _block(f"block-{index:04d}", text, x, 0, width) for index, (text, x, width) in enumerate(entries, start=1)
    )
    geometry, _ = ocr_layout_module._geometry_blocks(blocks)
    parsed = ocr_layout_module._guidance_instruction_cells(geometry)
    assert (parsed is not None) is accepted
    if parsed is not None:
        assert [cell.text for cell in parsed] == ["1정", "3회", "5일분"]


@pytest.mark.parametrize("complete_receipt", [True, False])
async def test_separatorless_guidance_preserves_capsule_tablet_and_liquid_units(complete_receipt: bool) -> None:
    names = ["오셀타미비르캡슐75mg", "아세트아미노펜정500mg", "레보드로프로피진시럽", "프로바이오틱스캡슐"]
    quantities = ["1캡슐씩", "1정씩", "10mL씩", "1캡슐씩"]
    entries = [
        ("약품사진", 500, 210, 80),
        ("약품명", 730, 210, 60),
        ("복약안내(투약량/횟수/일수)", 940, 210, 240),
        ("주의사항", 1330, 210, 80),
        ("품목명", 60, 750, 45),
        ("투약량", 205, 750, 45),
        ("횟수", 265, 750, 30),
        ("일수", 315, 750, 30),
    ]
    for i, (name, quantity, times, days) in enumerate(zip(names, quantities, [2, 3, 3, 2], [5, 3, 5, 5], strict=True)):
        y = 270 + i * 155
        entries.extend(
            [
                (name, 650, y, 190),
                ("1회", 900, y, 25),
                (quantity, 930, y, 60),
                ("1일", 995, y, 25),
                (f"{times}회", 1025, y, 30),
                (f"{days}일분", 1060, y, 45),
                ("주의사항", 1230, y, 60),
            ]
        )
        entries.extend(
            [(name, 35, 800 + i * 35, 150), (str(times), 275, 800 + i * 35, 10), (str(days), 325, 800 + i * 35, 10)]
        )
        if complete_receipt or i < 3:
            entries.append(("10" if i == 2 else "1", 225, 800 + i * 35, 20))
    blocks = tuple(_block(f"block-{i:04d}", *entry) for i, entry in enumerate(entries, start=1))

    class Provider:
        async def recognize(self, _image: bytes) -> OcrResult:
            return OcrResult(blocks)

    analyzed = await analyze_processed_image(Provider(), b"test-image")
    medications = analyzed.project_review["medications"]
    assert [med["name"] for med in medications] == names
    assert [med.get("doseQuantity") for med in medications] == ["1캡슐", "1정", "10mL", "1캡슐"]
    assert [med["timesPerDay"] for med in medications] == [2, 3, 3, 2]
    assert [med["days"] for med in medications] == [5, 3, 5, 5]


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
