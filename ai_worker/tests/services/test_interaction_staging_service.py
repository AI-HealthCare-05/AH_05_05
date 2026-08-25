import csv
import json
from pathlib import Path

import pytest

from ai_worker.schemas.interaction import InteractionRuleCandidate
from ai_worker.services.interaction_staging_service import (
    InteractionStagingService,
)

FIELDNAMES = [
    "DUR일련번호",
    "DUR유형",
    "DUR성분코드",
    "DUR성분명",
    "금기내용",
    "병용금기DUR성분코드",
    "병용금기DUR성분명",
    "상태",
]


def write_csv(
    path: Path,
    rows: list[dict[str, str]],
    *,
    fieldnames: list[str] | None = None,
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames or FIELDNAMES,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_row(
    record_id: str,
    *,
    left_code: str = "D000353",
    left_name: str = "파록세틴",
    right_code: str = "D000139",
    right_name: str = "셀레길린염산염",
    effect: str = "세로토닌성증후군",
    status: str = "정상",
) -> dict[str, str]:
    return {
        "DUR일련번호": record_id,
        "DUR유형": "병용금기",
        "DUR성분코드": left_code,
        "DUR성분명": left_name,
        "금기내용": effect,
        "병용금기DUR성분코드": right_code,
        "병용금기DUR성분명": right_name,
        "상태": status,
    }


def build_service(tmp_path: Path) -> InteractionStagingService:
    return InteractionStagingService(
        source_id="mfds_drug_records",
        document_id="mfds-dur-contraindication",
    )


def test_build_merges_reverse_pairs_and_preserves_source_rows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "DUR병용금기.csv"
    output_root = tmp_path / "processed"
    write_csv(
        input_path,
        [
            build_row("23"),
            build_row(
                "24",
                left_code="D000139",
                left_name="셀레길린염산염",
                right_code="D000353",
                right_name="파록세틴",
                effect="고혈압·고열 위험",
            ),
            build_row("25", status="삭제"),
            build_row("26", right_name=""),
        ],
    )

    result = build_service(tmp_path).build(
        input_path=input_path,
        output_root=output_root,
        dataset_version="interaction-pilot-v1",
    )

    assert result.input_row_count == 4
    assert result.accepted_row_count == 2
    assert result.candidate_count == 1
    assert result.duplicate_merged_count == 1
    assert result.skipped_reason_counts == {
        "INACTIVE_STATUS": 1,
        "MISSING_REQUIRED_VALUE": 1,
    }
    assert [
        (
            row.source_line_number,
            row.record_id,
            row.reason,
        )
        for row in result.skipped_rows
    ] == [
        (4, "25", "INACTIVE_STATUS"),
        (5, "26", "MISSING_REQUIRED_VALUE"),
    ]

    candidate_lines = (
        output_root / result.candidates_path
    ).read_text(encoding="utf-8").splitlines()
    assert len(candidate_lines) == 1
    candidate = InteractionRuleCandidate.model_validate_json(
        candidate_lines[0]
    )
    assert candidate.effect_summaries == [
        "세로토닌성증후군",
        "고혈압·고열 위험",
    ]
    assert [source.record_id for source in candidate.source_records] == [
        "23",
        "24",
    ]
    assert candidate.review_status.value == "PENDING"

    quality_report = json.loads(
        (output_root / result.quality_report_path).read_text(
            encoding="utf-8"
        )
    )
    assert quality_report["candidate_count"] == 1
    assert quality_report["ready_for_rdb_import"] is False


def test_build_rejects_missing_required_csv_column(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "DUR병용금기.csv"
    output_root = tmp_path / "processed"
    write_csv(
        input_path,
        [build_row("23")],
        fieldnames=[
            field
            for field in FIELDNAMES
            if field != "병용금기DUR성분명"
        ],
    )

    with pytest.raises(ValueError, match="필수 컬럼"):
        build_service(tmp_path).build(
            input_path=input_path,
            output_root=output_root,
            dataset_version="interaction-pilot-v1",
        )

    assert not output_root.exists()


def test_build_is_deterministic(tmp_path: Path) -> None:
    input_path = tmp_path / "DUR병용금기.csv"
    output_root = tmp_path / "processed"
    write_csv(
        input_path,
        [
            build_row("29"),
            build_row(
                "31",
                left_code="D000747",
                left_name="에르고타민",
                right_code="D000650",
                right_name="수마트립탄",
                effect="혈압상승 및 맥각독성 위험",
            ),
        ],
    )
    service = build_service(tmp_path)

    service.build(
        input_path=input_path,
        output_root=output_root,
        dataset_version="interaction-pilot-v1",
    )
    first = (
        output_root / "records" / "interaction_rule_candidates.jsonl"
    ).read_text(encoding="utf-8")
    service.build(
        input_path=input_path,
        output_root=output_root,
        dataset_version="interaction-pilot-v1",
    )
    second = (
        output_root / "records" / "interaction_rule_candidates.jsonl"
    ).read_text(encoding="utf-8")

    assert first == second


def test_build_skips_unclosed_quote_without_swallowing_later_rows(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "DUR병용금기.csv"
    output_root = tmp_path / "processed"
    write_csv(
        input_path,
        [
            build_row("1492", effect="닫히지 않은 따옴표"),
            build_row("1500"),
        ],
    )
    malformed = input_path.read_text(encoding="utf-8-sig").replace(
        "닫히지 않은 따옴표",
        '"닫히지 않은 따옴표',
        1,
    )
    input_path.write_text(malformed, encoding="utf-8-sig")

    result = build_service(tmp_path).build(
        input_path=input_path,
        output_root=output_root,
        dataset_version="interaction-pilot-v1",
    )

    assert result.input_row_count == 2
    assert result.accepted_row_count == 1
    assert result.candidate_count == 1
    assert result.skipped_reason_counts == {
        "MALFORMED_CSV_ROW": 1,
    }
    assert result.skipped_rows[0].source_line_number == 2
    assert result.skipped_rows[0].record_id == "1492"
