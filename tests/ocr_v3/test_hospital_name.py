import pytest

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline import review_projection
from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image
from app.services.medication_ocr_v3.pipeline.hospital_name import extract_hospital_name
from app.services.medication_ocr_v3.pipeline.medication_rows import materialize_medication_rows
from app.services.medication_ocr_v3.pipeline.ocr_layout import (
    AxisAlignedBBox,
    OcrLayoutResult,
    OcrLine,
    build_ocr_layout,
)


def _block(
    block_id: str, text: str, x: float, y: float, width: float, confidence: float = 0.99, *, height: float = 10
) -> OcrBlock:
    return OcrBlock(
        block_id=block_id,
        text=text,
        confidence=confidence,
        bbox=(
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
        ),
        line_break=False,
        issues=(),
    )


def _extract(*blocks: OcrBlock):
    result = OcrResult(tuple(blocks))
    return extract_hospital_name(result, build_ocr_layout(result))


@pytest.mark.parametrize("scale", [1, 3])
def test_hospital_fallback_separates_receipt_panel_with_misaligned_label(scale: int) -> None:
    # Separate receipt/hospital panels; the hospital label is on another OCR row.
    extracted = _extract(
        _block("fee", "보험자부담금(2)", 10 * scale, 100 * scale, 80 * scale, height=10 * scale),
        _block("amount", "4,100", 100 * scale, 100 * scale, 30 * scale, height=10 * scale),
        _block("hospital", "김귀완내과", 330 * scale, 100 * scale, 70 * scale, height=10 * scale),
        _block("label", "병원정보", 250 * scale, 122 * scale, 70 * scale, height=10 * scale),
        _block("header", "약품명", 10 * scale, 220 * scale, 45 * scale, height=10 * scale),
    )

    assert extracted.value == "김귀완내과"
    assert extracted.block_ids == ("hospital",)


def test_hospital_name_joins_adjacent_ocr_blocks_after_label() -> None:
    extracted = _extract(
        _block("block-0001", "병원정보", 10, 10, 45),
        _block("block-0002", "송도센트럴", 65, 10, 60, 0.96),
        _block("block-0003", "이비인후과의원", 127, 10, 80, 0.94),
        _block("block-0004", "약품명", 10, 80, 45),
    )

    assert extracted is not None
    assert extracted.value == "송도센트럴이비인후과의원"
    assert extracted.block_ids == ("block-0002", "block-0003")
    assert extracted.confidence == 0.94
    assert extracted.issues == ()


def test_hospital_name_accepts_an_unlabelled_department_name_in_header() -> None:
    extracted = _extract(
        _block("block-0001", "서울정형외과", 10, 10, 80, 0.91),
        _block("block-0002", "약품명", 10, 80, 45),
    )

    assert extracted is not None
    assert extracted.value == "서울정형외과"
    assert extracted.block_ids == ("block-0001",)


def test_hospital_name_stops_at_department_before_a_trailing_person_name() -> None:
    extracted = _extract(
        _block("block-0001", "·병원정보", 10, 30, 55, 0.75),
        _block("block-0002", ":", 70, 30, 5, 0.95),
        _block("block-0003", "송도센트럴이비인후과고일주)", 80, 27, 155, 0.96),
        _block("block-0004", "Tel.", 245, 30, 25, 0.99),
        _block("block-0005", "0328319972", 275, 30, 65, 0.99),
        _block("block-0006", "약품명", 10, 80, 45),
    )

    assert extracted.value == "송도센트럴이비인후과"
    assert extracted.block_ids == ("block-0003",)
    assert extracted.confidence == 0.96
    review = review_projection.build_project_review(
        materialize_medication_rows(build_ocr_layout(OcrResult(tuple()))),
        hospital_name=extracted,
    )
    assert review["fields"]["hospitalName"]["confidence"] == "high"
    assert review["lowConfidenceCount"] == 0


@pytest.mark.parametrize("title", ["조제약&복약안내", "복약안내문"])
def test_document_title_does_not_hide_hospital_header(title: str) -> None:
    extracted = _extract(
        _block("title", title, 600, 100, 300),
        _block("label", "병원정보:", 600, 210, 100),
        _block("hospital", "가경수피부과", 705, 210, 150),
        _block("table", "약품명", 700, 300, 80),
        _block("body", "다른내과", 700, 350, 100),
    )
    assert extracted.value == "가경수피부과"
    assert extracted.block_ids == ("hospital",)


@pytest.mark.parametrize("suffix", ["(홍길동)", "（홍길동）", "(홍길동"])
def test_hospital_name_removes_parenthesized_doctor_after_department(suffix: str) -> None:
    extracted = _extract(
        _block("label", "병원정보:", 600, 210, 100),
        _block("hospital", "가경수피부과" + suffix, 705, 210, 240),
        _block("tel", "Tel.", 950, 210, 40),
        _block("table", "약품명", 700, 300, 80),
    )
    assert extracted.value == "가경수피부과"


def test_hospital_name_does_not_read_below_standalone_guidance_table_header() -> None:
    assert (
        _extract(
            _block("table", "복약안내", 700, 300, 80),
            _block("body", "다른내과", 700, 350, 100),
        ).value
        is None
    )


def test_hospital_name_keeps_institution_suffix_after_department() -> None:
    extracted = _extract(
        _block("block-0001", "병원정보", 10, 10, 50),
        _block("block-0002", "서울정형외과의원", 70, 10, 100, 0.95),
        _block("block-0003", "약품명", 10, 80, 45),
    )

    assert extracted.value == "서울정형외과의원"


def test_hospital_name_excludes_pharmacy_and_medication_description() -> None:
    extracted = _extract(
        _block("block-0001", "발행기관", 10, 10, 45),
        _block("block-0002", "한도가까운약국", 65, 10, 85),
        _block("block-0003", "[비염 치료제]", 10, 35, 80),
        _block("block-0004", "약품명", 10, 80, 45),
    )

    assert extracted is not None
    assert extracted.value is None
    assert extracted.block_ids == ()


def test_issuing_hospital_stops_before_unlabelled_doctor_and_other_columns() -> None:
    extracted = _extract(
        _block("label", "발행기관", 10, 10, 45),
        _block("hospital", "한도병원", 65, 10, 55, 0.99),
        _block("doctor", "홍길동", 125, 10, 35),
        _block("pharmacy", "한도가까운약국", 250, 10, 100),
        _block("header", "약품명", 10, 80, 45),
    )
    assert extracted.value == "한도병원"
    assert extracted.block_ids == ("hospital",)
    assert extracted.confidence == 0.99


def test_issuing_hospital_excludes_lower_line_number_sorted_before_name() -> None:
    # Geometry from the angled reference; unrelated values are synthetic.
    extracted = _extract(
        _block("label", "발행기관", 231, 139, 62, height=23),
        _block("hospital", "한도병원", 302, 137, 77, height=27),
        _block("doctor", "홍길동", 377, 139, 58, height=27),
        _block("number", "12345678", 298, 162, 93, height=23),
        _block("receipt", "1234567890", 963, 139, 139, height=25),
        _block("receipt-1", "영", 1146, 152, 19, height=18),
        _block("receipt-2", "수", 1184, 150, 20, height=23),
        _block("receipt-3", "증", 1223, 150, 19, height=23),
        _block("receipt-4", "값", 1261, 150, 21, height=23),
        _block("receipt-5", "12345", 1290, 154, 90, height=21),
        _block("receipt-6", "금액", 1405, 152, 108, height=18),
        _block("header", "약품명", 10, 220, 45),
    )
    assert extracted.value == "한도병원"
    assert extracted.block_ids == ("hospital",)


@pytest.mark.parametrize("receipt_text", ["1234567890", "다른병원"])
@pytest.mark.parametrize("merged_header_top", [350, 382])
def test_hospital_anchor_recovers_name_across_global_lines(receipt_text: str, merged_header_top: int) -> None:
    # Preserve the failing reference's geometry; all non-hospital text is synthetic.
    result = OcrResult(
        (
            _block("label", "발행기관", 1578, 369, 141, height=48),
            _block("receipt", receipt_text, 3000, 317, 507, height=100),
            _block("left", "교부번호", 329, merged_header_top, 180, height=115),
            _block("hospital", "이지의원", 1801, 382, 157, 0.97, height=56),
            _block("doctor", "홍길동", 1957, 382, 122, height=56),
            _block("phone", "032-000-0000", 1801, 433, 327, height=57),
            _block("header", "약품명", 567, 435, 201, height=55),
            _block("right", "000", 3370, 382, 128, height=115),
        )
    )
    layout = OcrLayoutResult(
        lines=(
            OcrLine("line-4", ("label", "receipt"), f"발행기관 {receipt_text}", AxisAlignedBBox(1578, 317, 3507, 417)),
            OcrLine(
                "line-5",
                ("left", "header", "hospital", "doctor", "phone", "right"),
                "교부번호 약품명 이지의원 홍길동 032-000-0000 000",
                AxisAlignedBBox(329, merged_header_top, 3498, 497),
            ),
        ),
        table_candidates=(),
        issues=(),
    )

    extracted = extract_hospital_name(result, layout)

    assert extracted.value == "이지의원"
    assert extracted.block_ids == ("hospital",)
    assert extracted.confidence == 0.97
    assert extracted.bbox == AxisAlignedBBox(1801, 382, 1958, 438)


def test_hospital_anchor_does_not_recover_a_label_below_the_table() -> None:
    extracted = _extract(
        _block("header", "약품명", 10, 80, 45),
        _block("label", "발행기관", 10, 110, 45, height=20),
        _block("hospital", "새봄의원", 65, 116, 55, height=20),
    )

    assert extracted.value is None
    assert extracted.block_ids == ()


@pytest.mark.parametrize("name", ["한도병원", "새봄의원", "서울내과의원"])
def test_issuing_hospital_accepts_label_and_value_in_one_block(name: str) -> None:
    extracted = _extract(
        _block("value", f"발행기관 {name} 홍길동", 10, 10, 180),
        _block("header", "약품명", 10, 80, 45),
    )
    assert extracted.value == name
    assert extracted.block_ids == ("value",)


def test_issuing_hospital_joins_split_name_without_doctor_evidence() -> None:
    extracted = _extract(
        _block("label", "발행기관", 10, 10, 45),
        _block("name", "한도", 65, 10, 25),
        _block("suffix", "병원", 92, 10, 25),
        _block("doctor", "홍길동", 125, 10, 35, 0.4),
        _block("header", "약품명", 10, 80, 45),
    )
    assert extracted.value == "한도병원"
    assert extracted.block_ids == ("name", "suffix")
    assert extracted.confidence == 0.99


@pytest.mark.parametrize("value", ["홍길동", "80401114", "한도가까운약국", "한도가까운약국 서울병원"])
def test_issuer_is_not_automatically_a_hospital(value: str) -> None:
    assert (
        _extract(
            _block("value", f"발행기관 {value}", 10, 10, 200),
            _block("header", "약품명", 10, 80, 45),
        ).value
        is None
    )


def test_hospital_name_omits_conflicting_equally_ranked_candidates() -> None:
    extracted = _extract(
        _block("block-0001", "병원명", 10, 10, 40),
        _block("block-0002", "서울병원", 60, 10, 55),
        _block("block-0003", "의료기관", 10, 30, 45),
        _block("block-0004", "새봄의원", 65, 30, 55),
        _block("block-0005", "약품명", 10, 80, 45),
    )

    assert extracted is not None
    assert extracted.value is None
    assert extracted.block_ids == ("block-0002", "block-0004")
    assert tuple(issue.value for issue in extracted.issues) == ("AMBIGUOUS_HOSPITAL_NAME",)


@pytest.mark.asyncio
async def test_pipeline_projects_hospital_name_and_diagnostic_evidence() -> None:
    result = OcrResult(
        (
            _block("title", "조제약&복약안내", 10, -40, 160),
            _block("block-0001", "병원정보", 10, 10, 45),
            _block("block-0002", "송도센트럴이비인후과의원", 65, 10, 140, 0.93),
            _block("block-0003", "약품명", 10, 80, 45),
        )
    )

    class Provider:
        async def recognize(self, _processed_jpeg: bytes) -> OcrResult:
            return result

        async def aclose(self) -> None:
            return None

    analyzed = await analyze_processed_image(Provider(), b"processed")

    assert isinstance(analyzed, AnalyzePipelineResult)
    assert analyzed.project_review is not None
    assert analyzed.project_review["fields"]["hospitalName"] == {
        "value": "송도센트럴이비인후과의원",
        "confidence": "high",
    }
    assert analyzed.diagnostics is not None
    assert analyzed.diagnostics["fieldEvidence"]["hospitalName"] == {
        "blockIds": ["block-0002"],
        "bbox": {
            "coordinateSpace": "processed",
            "xMin": 65,
            "yMin": 10,
            "xMax": 205,
            "yMax": 20,
        },
        "confidence": "high",
        "issues": [],
    }


def test_review_omits_missing_hospital_name() -> None:
    result = OcrResult((_block("block-0001", "한도가까운약국", 10, 10, 90),))
    layout = build_ocr_layout(result)
    rows = materialize_medication_rows(layout)
    extracted = extract_hospital_name(result, layout)

    review = review_projection.build_project_review(rows, hospital_name=extracted)

    assert review["fields"] == {}
