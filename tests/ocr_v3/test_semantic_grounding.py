from __future__ import annotations

import importlib
import importlib.util
from dataclasses import replace
from datetime import date

import pytest

from app.services.medication_ocr_v3.domain import grounding as contracts
from app.services.medication_ocr_v3.domain.grounding import EvidenceBlock
from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline.deterministic_grounding import (
    canonicalize_deterministic_selection,
    materialize_deterministic_grounding,
)
from app.services.medication_ocr_v3.pipeline.evidence_catalog import build_evidence_catalog
from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox, build_ocr_layout
from app.services.medication_ocr_v3.pipeline.review_projection import build_project_review


def _block(block_id, text, x, y, width=70, height=12):
    return OcrBlock(
        block_id,
        text,
        0.99,
        (Point(x, y), Point(x + width, y), Point(x + width, y + height), Point(x, y + height)),
        False,
        (),
    )


def _table():
    return OcrResult(
        (
            _block("header-name", "약품명", 10, 10),
            _block("header-dose", "투약량", 200, 10, 40),
            _block("header-times", "횟수", 270, 10, 30),
            _block("header-days", "일수", 340, 10, 30),
            _block("name", "감마정", 10, 50),
            _block("dose", "1", 205, 50, 15),
            _block("times", "2", 275, 50, 15),
            _block("days", "5", 345, 50, 15),
        )
    )


def _fixture():
    ocr = _table()
    layout = build_ocr_layout(ocr)
    rows = materialize_medication_rows(layout)
    catalog = build_evidence_catalog(ocr, layout, rows)
    empty = contracts.GroundingSelection(dispensed_date_block_ids=[], medications=[])
    canonical = canonicalize_deterministic_selection(catalog, rows, empty, today=date(2026, 9, 7))
    baseline = materialize_deterministic_grounding(catalog, rows, canonical, today=date(2026, 9, 7))
    additional = tuple(
        EvidenceBlock(key, text, 0.98, AxisAlignedBBox(x, 70, x + 80, 82), "extra", ("row-0001",), fields)
        for key, text, x, fields in (
            ("full-name", "감마정100밀리그램", 10, ("name", "strength")),
            ("half", "0.5정", 205, ("doseQuantity",)),
            ("three", "3회", 275, ("timesPerDay",)),
            ("seven", "7일", 345, ("days",)),
        )
    )
    catalog = replace(
        catalog,
        blocks=(*catalog.blocks, *additional),
        rows=(replace(catalog.rows[0], block_ids=(*catalog.rows[0].block_ids, *(b.block_id for b in additional))),),
    )
    return catalog, rows, baseline


def _selection(**overrides):
    model = getattr(contracts, "SemanticGroundingSelection", None)
    assert model is not None, "five-field semantic selection contract is missing"
    fields = {
        "name": {"status": "supported", "text": "감마정100밀리그램", "blockIds": ["full-name"]},
        "strength": {"status": "supported", "text": "100밀리그램", "blockIds": ["full-name"]},
        "doseQuantity": {"status": "supported", "text": "0.5정", "blockIds": ["half"]},
        "timesPerDay": {"status": "supported", "text": "3회", "blockIds": ["three"]},
        "days": {"status": "supported", "text": "7일", "blockIds": ["seven"]},
    }
    fields.update(overrides)
    return model.model_validate({"dispensedDateBlockIds": [], "medications": [{"rowId": "row-0001", **fields}]})


def _materialize(catalog, rows, baseline, selection):
    module = "app.services.medication_ocr_v3.pipeline.semantic_grounding"
    assert importlib.util.find_spec(module) is not None, "semantic validation is missing"
    return importlib.import_module(module).materialize_semantic_review(catalog, rows, baseline, selection)


@pytest.mark.parametrize("quote", ["2.5mg", "120mg"])
def test_product_title_cannot_authorize_one_component_of_multiple_printed_strengths(quote):
    catalog, rows, baseline = _fixture()
    title = "감마정2.5mg 120mg"
    catalog = replace(
        catalog,
        blocks=tuple(replace(b, text=title) if b.block_id == "full-name" else b for b in catalog.blocks),
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(
            name={"status": "supported", "text": title, "blockIds": ["full-name"]},
            strength={"status": "supported", "text": quote, "blockIds": ["full-name"]},
        ),
    )
    assert build_project_review(reviewed, grounded)["medications"][0].get("strength") is None
    assert any(i.field == "strength" for i in grounded.issues)


def test_semantic_payload_exposes_all_five_fields_without_changing_legacy_payload():
    catalog, _, _ = _fixture()
    payload = getattr(catalog, "to_semantic_payload", None)
    assert callable(payload), "full-row semantic payload is missing"
    exposed = {b["blockId"] for b in payload()["rows"][0]["blocks"]}
    assert {"name", "dose", "times", "days", "full-name", "half", "three", "seven"} <= exposed
    legacy = catalog.to_llm_payload()
    assert {b["blockId"] for b in legacy["rows"][0]["blocks"]} == {"full-name"}


def test_supported_five_field_review_reaches_public_projection_and_provenance():
    catalog, rows, baseline = _fixture()
    reviewed, grounded = _materialize(catalog, rows, baseline, _selection())
    medication = build_project_review(reviewed, grounded)["medications"][0]
    assert {key: medication[key] for key in ("name", "strength", "doseQuantity", "timesPerDay", "days")} == {
        "name": "감마정100밀리그램",
        "strength": "100mg",
        "doseQuantity": "0.5정",
        "timesPerDay": 3,
        "days": 7,
    }
    assert reviewed.medications[0].fields.name.block_ids == ("full-name",)
    assert reviewed.medications[0].fields.days.block_ids == ("seven",)
    assert grounded.medications[0].strength.block_ids == ("full-name",)
    assert not grounded.issues


@pytest.mark.parametrize(
    "field,text,ids",
    [
        ("strength", "50밀리그램", ["full-name"]),
        ("strength", "100밀리그램", ["unknown"]),
        ("strength", "100밀리그램", ["full-name", "full-name"]),
        ("doseQuantity", "5정", ["half"]),
        ("name", "다른약정", ["full-name"]),
        ("days", "7", ["seven", "unknown"]),
        ("timesPerDay", "7일", ["seven"]),
    ],
)
def test_invalid_review_never_replaces_the_corresponding_fallback(field, text, ids):
    catalog, rows, baseline = _fixture()
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(
            **{
                field: {"status": "supported", "text": text, "blockIds": ids},
            }
        ),
    )
    medication = build_project_review(reviewed, grounded)["medications"][0]
    expected = {"name": "감마정", "strength": None, "doseQuantity": "1", "timesPerDay": 2, "days": 5}
    assert medication.get(field) == expected[field]
    assert any(issue.field == field for issue in grounded.issues)


def test_cross_row_evidence_is_rejected_even_when_text_matches():
    catalog, rows, baseline = _fixture()
    catalog = replace(
        catalog, blocks=tuple(replace(b, row_ids=("row-0002",)) if b.block_id == "seven" else b for b in catalog.blocks)
    )
    reviewed, grounded = _materialize(catalog, rows, baseline, _selection())
    assert build_project_review(reviewed, grounded)["medications"][0]["days"] == 5
    assert any(i.code.value == "CROSS_ROW_BLOCK_ID" for i in grounded.issues)


@pytest.mark.parametrize("status", ["uncertain", "absent"])
def test_unresolved_review_preserves_fallback_and_marks_conflict(status):
    catalog, rows, baseline = _fixture()
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(
            days={
                "status": status,
                "text": None,
                "blockIds": [],
            }
        ),
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["days"] == 5
    assert any(i.field == "days" and i.code.value == "AMBIGUOUS_FIELD_VALUE" for i in grounded.issues)
    assert build_project_review(reviewed, grounded)["medications"][0]["confidence"] == "low"


def test_missing_review_row_is_not_silently_reported_as_success():
    catalog, rows, baseline = _fixture()
    selection = _selection().model_copy(update={"medications": []})
    reviewed, grounded = _materialize(catalog, rows, baseline, selection)
    assert build_project_review(reviewed, grounded)["medications"][0]["name"] == "감마정"
    assert any(i.code.value == "INCOMPLETE_SEMANTIC_REVIEW" for i in grounded.issues)
    assert build_project_review(reviewed, grounded)["medications"][0]["confidence"] == "low"


@pytest.mark.parametrize("membership", ["missing", "duplicate"])
def test_unresolvable_catalog_membership_keeps_grounded_fallback_and_flags_review(membership):
    catalog, rows, baseline = _fixture()
    baseline = replace(
        baseline,
        medications=(
            replace(baseline.medications[0], strength=replace(baseline.medications[0].strength, value="100mg")),
        ),
    )
    catalog = replace(catalog, rows=() if membership == "missing" else (*catalog.rows, *catalog.rows))
    reviewed, grounded = _materialize(catalog, rows, baseline, _selection())
    assert build_project_review(reviewed, grounded)["medications"][0]["strength"] == "100mg"
    assert any(i.code.value == "INCOMPLETE_SEMANTIC_REVIEW" for i in grounded.issues)


@pytest.mark.parametrize("text", ["0정", "-1정", "복용", "1/0정"])
def test_nonpositive_or_unparseable_printed_dose_cannot_erase_valid_fallback(text):
    catalog, rows, baseline = _fixture()
    catalog = replace(
        catalog, blocks=tuple(replace(b, text=text) if b.block_id == "half" else b for b in catalog.blocks)
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(
            doseQuantity={
                "status": "supported",
                "text": text,
                "blockIds": ["half"],
            }
        ),
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["doseQuantity"] == "1"
    assert any(i.field == "doseQuantity" for i in grounded.issues)


def test_strength_excerpt_cannot_discard_a_concentration_denominator():
    catalog, rows, baseline = _fixture()
    catalog = replace(
        catalog,
        blocks=tuple(
            replace(b, text="감마정100밀리그램/5mL") if b.block_id == "full-name" else b for b in catalog.blocks
        ),
    )
    reviewed, grounded = _materialize(catalog, rows, baseline, _selection())
    assert "strength" not in build_project_review(reviewed, grounded)["medications"][0]
    assert any(i.field == "strength" for i in grounded.issues)


def test_name_excerpt_cannot_cut_inside_the_product_name():
    catalog, rows, baseline = _fixture()
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(name={"status": "supported", "text": "감마", "blockIds": ["full-name"]}),
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["name"] == "감마정"
    assert any(i.field == "name" for i in grounded.issues)


def test_dose_excerpt_cannot_discard_its_printed_unit():
    catalog, rows, baseline = _fixture()
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(doseQuantity={"status": "supported", "text": "0.5", "blockIds": ["half"]}),
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["doseQuantity"] == "1"
    assert any(i.field == "doseQuantity" for i in grounded.issues)


def test_superfluous_cited_strength_block_is_not_claimed_as_support():
    catalog, rows, baseline = _fixture()
    extra = EvidenceBlock(
        "unrelated", "999mg", 0.11, AxisAlignedBBox(10, 100, 80, 112), "extra2", ("row-0001",), ("strength",)
    )
    catalog = replace(
        catalog,
        blocks=(*catalog.blocks, extra),
        rows=(replace(catalog.rows[0], block_ids=(*catalog.rows[0].block_ids, "unrelated")),),
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(strength={"status": "supported", "text": "100밀리그램", "blockIds": ["full-name", "unrelated"]}),
    )
    assert "strength" not in build_project_review(reviewed, grounded)["medications"][0]
    assert any(i.field == "strength" for i in grounded.issues)


@pytest.mark.parametrize("second_amount,expected", [("120mg", None), ("2.5mg", "2.5mg")])
def test_standalone_ingredient_amount_cannot_stand_for_a_multicomponent_product(second_amount, expected):
    catalog, rows, baseline = _fixture()
    ingredients = tuple(
        EvidenceBlock(key, amount, 0.99, AxisAlignedBBox(10, y, 80, y + 12), key, ("row-0001",), ("strength",))
        for key, amount, y in (("component-a", "2.5mg", 100), ("component-b", second_amount, 130))
    )
    catalog = replace(
        catalog,
        blocks=tuple(replace(b, allowed_fields=("name",)) if b.block_id == "full-name" else b for b in catalog.blocks)
        + ingredients,
        rows=(replace(catalog.rows[0], block_ids=(*catalog.rows[0].block_ids, *(b.block_id for b in ingredients))),),
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(strength={"status": "supported", "text": "2.5mg", "blockIds": ["component-a"]}),
    )
    assert build_project_review(reviewed, grounded)["medications"][0].get("strength") == expected
    if expected is None:
        assert any(i.field == "strength" and i.code.value == "AMBIGUOUS_FIELD_VALUE" for i in grounded.issues)


def test_next_short_title_blocks_previous_long_title_strength_association():
    from app.services.medication_ocr_v3.pipeline.semantic_catalog import _preceding_title, _Title

    titles = [
        _Title("long", "row-0001", AxisAlignedBBox(10, 10, 270, 30)),
        _Title("short", "row-0002", AxisAlignedBBox(10, 60, 80, 80)),
    ]
    assert _preceding_title(AxisAlignedBBox(140, 85, 200, 100), titles) is None


@pytest.mark.parametrize("raw,fragment,selectable", [("33", "3", False), ("15", "5", False), ("15", "15", True)])
def test_merged_numeric_ocr_block_cannot_replace_a_layout_split_field(raw, fragment, selectable):
    from app.services.medication_ocr_v3.pipeline.semantic_catalog import build_semantic_evidence_catalog

    ocr = OcrResult(tuple(replace(b, text=raw) if b.block_id == "days" else b for b in _table().blocks))
    layout = build_ocr_layout(ocr)
    rows = materialize_medication_rows(layout)
    medication = rows.medications[0]
    field = replace(medication.fields.days, value=int(fragment), source_text=raw)
    table = rows.selected_table
    table_row = table.rows[0]
    table = replace(
        table,
        rows=(
            replace(
                table_row,
                cells=tuple(
                    replace(cell, parsed_text=fragment) if cell is not None and cell.block_ids == ("days",) else cell
                    for cell in table_row.cells
                ),
            ),
        ),
    )
    rows = replace(
        rows,
        selected_table=table,
        medications=(replace(medication, days=int(fragment), fields=replace(medication.fields, days=field)),),
    )
    original = build_evidence_catalog(ocr, layout, rows)
    semantic = build_semantic_evidence_catalog(ocr, layout, rows, original)
    block = next(b for b in semantic.blocks if b.block_id == "days")
    assert ("days" in block.allowed_fields) is selectable
    assert next(b for b in original.blocks if b.block_id == "days").allowed_fields == ("days",)
    if not selectable:
        assert block.allowed_fields == ()


@pytest.mark.parametrize("form", ["one-block", "split-blocks"])
def test_multicomponent_amounts_cannot_bypass_review_through_ocr_token_grouping(form):
    catalog, rows, baseline = _fixture()
    parts = (
        [("amounts", "2.5mg 120mg", 10, 100)]
        if form == "one-block"
        else [
            ("amount-a", "2.5", 10, 100),
            ("unit-a", "mg", 50, 100),
            ("amount-b", "120", 10, 130),
            ("unit-b", "mg", 50, 130),
        ]
    )
    evidence = tuple(
        EvidenceBlock(key, text, 0.99, AxisAlignedBBox(x, y, x + 30, y + 12), str(y), ("row-0001",), ("strength",))
        for key, text, x, y in parts
    )
    catalog = replace(
        catalog,
        blocks=tuple(replace(b, allowed_fields=("name",)) if b.block_id == "full-name" else b for b in catalog.blocks)
        + evidence,
        rows=(replace(catalog.rows[0], block_ids=(*catalog.rows[0].block_ids, *(b.block_id for b in evidence))),),
    )
    ids = ["amounts"] if form == "one-block" else ["amount-a", "unit-a"]
    reviewed, grounded = _materialize(
        catalog, rows, baseline, _selection(strength={"status": "supported", "text": "2.5mg", "blockIds": ids})
    )
    assert build_project_review(reviewed, grounded)["medications"][0].get("strength") is None
    assert any(i.field == "strength" and i.code.value == "AMBIGUOUS_FIELD_VALUE" for i in grounded.issues)


@pytest.mark.parametrize("expression", ["10mg/mL", "100밀리그램/5mL"])
def test_full_concentration_quote_cannot_lose_its_denominator_during_parsing(expression):
    catalog, rows, baseline = _fixture()
    catalog = replace(
        catalog, blocks=tuple(replace(b, text=expression) if b.block_id == "full-name" else b for b in catalog.blocks)
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(strength={"status": "supported", "text": expression, "blockIds": ["full-name"]}),
    )
    assert build_project_review(reviewed, grounded)["medications"][0].get("strength") is None
    assert any(i.field == "strength" for i in grounded.issues)


@pytest.mark.parametrize("field_hints", [False, True])
def test_separate_numeric_cells_cannot_be_concatenated_into_a_new_duration(field_hints):
    catalog, rows, baseline = _fixture()
    catalog = replace(
        catalog,
        blocks=tuple(
            replace(
                b,
                allowed_fields=("doseQuantity", "timesPerDay", "days"),
                field_hints=b.allowed_fields if field_hints else (),
            )
            if b.block_id in {"times", "days"}
            else b
            for b in catalog.blocks
        ),
    )
    reviewed, grounded = _materialize(
        catalog, rows, baseline, _selection(days={"status": "supported", "text": "25", "blockIds": ["times", "days"]})
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["days"] == 5
    assert any(i.field == "days" for i in grounded.issues)


def test_single_duration_expression_split_into_number_and_unit_remains_selectable():
    catalog, rows, baseline = _fixture()
    unit = EvidenceBlock("day-unit", "일", 0.99, AxisAlignedBBox(380, 70, 395, 82), "extra", ("row-0001",), ("days",))
    catalog = replace(
        catalog,
        blocks=tuple(
            replace(b, text="7", bbox=AxisAlignedBBox(345, 70, 375, 82)) if b.block_id == "seven" else b
            for b in catalog.blocks
        )
        + (unit,),
        rows=(replace(catalog.rows[0], block_ids=(*catalog.rows[0].block_ids, "day-unit")),),
    )
    reviewed, grounded = _materialize(
        catalog,
        rows,
        baseline,
        _selection(days={"status": "supported", "text": "7일", "blockIds": ["seven", "day-unit"]}),
    )
    assert build_project_review(reviewed, grounded)["medications"][0]["days"] == 7
    assert grounded.medications[0].days.block_ids == ("seven", "day-unit")
    assert not any(i.field == "days" for i in grounded.issues)


@pytest.mark.parametrize("unknown_title", [False, True])
def test_printed_product_heading_owns_following_strength_in_duplicate_guidance_region(unknown_title):
    ocr = OcrResult(
        (
            _block("header-name", "약품명", 500, 10),
            _block("header-dose", "투약량", 780, 10, 40),
            _block("header-times", "횟수", 850, 10, 30),
            _block("header-days", "일수", 920, 10, 30),
            _block("name-1", "소로펜정", 500, 50),
            _block("dose-1", "1", 785, 50, 15),
            _block("times-1", "2", 855, 50, 15),
            _block("days-1", "5", 925, 50, 15),
            _block("name-2", "써스펜8시간이알서방정650...", 500, 90, 260),
            _block("dose-2", "1", 785, 90, 15),
            _block("times-2", "2", 855, 90, 15),
            _block("days-2", "5", 925, 90, 15),
            _block("title-1", "소로펜정(록소프로펜나트륨...", 10, 150, 260),
            _block("ingredient-1", "록소프로펜나트륨", 10, 180, 130),
            _block("strength-1", "68.1mg", 145, 180, 60),
            _block("title-2", "베타실제제품정" if unknown_title else "써스펜8시간이알서방정650...", 10, 200, 260),
            _block("ingredient-2", "아세트아미노펜", 10, 220, 120),
            _block("strength-2", "650mg", 135, 220, 60),
            _block("bare-person", "홍길동", 10, 190, 80),
            _block("bare-person-strength", "500mg", 95, 190, 60),
            _block("patient", "환자 성명 홍길동", 10, 300, 160),
            _block("sensitive-dose", "999mg", 175, 300, 50),
        )
    )
    layout = build_ocr_layout(ocr)
    rows = materialize_medication_rows(layout)
    original = build_evidence_catalog(ocr, layout, rows)
    module = "app.services.medication_ocr_v3.pipeline.semantic_catalog"
    assert importlib.util.find_spec(module) is not None, "semantic row-context association is missing"
    catalog = importlib.import_module(module).build_semantic_evidence_catalog(ocr, layout, rows, original)
    blocks = {b.block_id: b for b in catalog.blocks}
    assert blocks["strength-1"].row_ids == ("row-0001",)
    if unknown_title:
        assert "strength-2" not in blocks or blocks["strength-2"].row_ids != ("row-0001",)
    else:
        assert blocks["strength-2"].row_ids == ("row-0002",)
    assert blocks["title-1"].row_ids == ("row-0001",)
    assert "patient" not in blocks
    assert "sensitive-dose" not in blocks
    assert "bare-person" not in blocks
    assert len([row for row in catalog.rows if "strength-1" in row.block_ids]) == 1


@pytest.mark.asyncio
async def test_pipeline_reviews_all_fields_even_without_legacy_ambiguity_and_projects_changed_evidence():
    from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image

    ocr = _table()
    ocr = OcrResult(tuple(replace(b, text="감마정100밀리그램") if b.block_id == "name" else b for b in ocr.blocks))

    class Provider:
        async def recognize(self, _image):
            return ocr

    class Reviewer:
        review_mode = "semantic"

        async def select(self, catalog):
            exposed = {b["blockId"] for b in catalog.to_semantic_payload()["rows"][0]["blocks"]}
            assert {"name", "dose", "times", "days"} <= exposed
            return contracts.SemanticGroundingSelection.model_validate(
                {
                    "dispensedDateBlockIds": [],
                    "medications": [
                        {
                            "rowId": "row-0001",
                            "name": {"status": "supported", "text": "감마정100밀리그램", "blockIds": ["name"]},
                            "strength": {"status": "supported", "text": "100밀리그램", "blockIds": ["name"]},
                            "doseQuantity": {"status": "supported", "text": "2", "blockIds": ["times"]},
                            "timesPerDay": {"status": "supported", "text": "1", "blockIds": ["dose"]},
                            "days": {"status": "supported", "text": "5", "blockIds": ["days"]},
                        }
                    ],
                }
            )

    result = await analyze_processed_image(Provider(), b"synthetic", Reviewer())
    assert isinstance(result, AnalyzePipelineResult)
    med = result.project_review["medications"][0]
    assert med["name"] == "감마정100밀리그램"
    assert med["strength"] == "100mg"
    assert med["doseQuantity"] == "2"
    assert med["timesPerDay"] == 1
    assert med["days"] == 5
    assert result.diagnostics["fieldEvidence"]["medications"][0]["timesPerDay"]["blockIds"] == ["dose"]
    assert next(stage for stage in result.stages if stage.name == "llm").call_count == 1
    assert result.diagnostics["llm"]["mode"] == "semantic"
    assert not result.grounded.issues


@pytest.mark.asyncio
async def test_semantic_provider_failure_keeps_deterministic_result_with_explicit_issue():
    from app.services.medication_ocr_v3.pipeline.analyze import analyze_processed_image
    from app.services.medication_ocr_v3.providers.openai_grounded import LlmErrorCode, LlmProviderError

    class Provider:
        async def recognize(self, _image):
            return _table()

    class Reviewer:
        review_mode = "semantic"

        async def select(self, _catalog):
            raise LlmProviderError(LlmErrorCode.LLM_TIMEOUT, 504)

    result = await analyze_processed_image(Provider(), b"synthetic", Reviewer())
    med = result.project_review["medications"][0]
    assert (med["name"], med["doseQuantity"], med["timesPerDay"], med["days"]) == ("감마정", "1", 2, 5)
    assert any(issue["code"] == "LLM_TIMEOUT" for issue in result.issues)
    assert result.analysis_state == "COMPLETED_WITH_ISSUES"
