from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from scripts.import_supplement_nutrients import (
    EXPECTED_HEADERS,
    ImportValidationError,
    parse_args,
    parse_workbook,
    validate_headers,
    validate_rows,
)


def valid_row(code: str = "F101-TEST-001", name: str = "테스트 철분") -> list[object]:
    return [
        code,
        name,
        "500mg",
        "0",
        None,
        "0.00",
        "0.00",
        None,
        "0.00",
        None,
        None,
        None,
        "15.00",
        None,
        None,
        "0",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "1캡슐",
        "500mg",
        "1회",
        None,
    ]


def test_headers_are_exact_and_row_values_preserve_zero_and_null() -> None:
    assert len(EXPECTED_HEADERS) == 31
    validate_headers(EXPECTED_HEADERS, row_number=2)
    with pytest.raises(ImportValidationError, match="header"):
        validate_headers([*EXPECTED_HEADERS[:-1], "잘못된 컬럼"], row_number=2)

    record = validate_rows([valid_row()], first_row_number=3)[0]

    assert record["energy_kcal"] == 0
    assert record["sodium_mg"] == 0
    assert record["water_g"] is None
    assert record["protein_g"] == Decimal("0.00")
    assert record["iron_mg"] == Decimal("15.00")


def test_duplicate_code_and_field_overflow_report_source_rows_and_columns() -> None:
    with pytest.raises(ImportValidationError, match=r"F101-TEST-001.*3.*4"):
        validate_rows([valid_row(), valid_row()], first_row_number=3)

    too_long = valid_row()
    too_long[1] = "가" * 101
    with pytest.raises(ImportValidationError, match=r"row 3.*식품명"):
        validate_rows([too_long], first_row_number=3)

    overflow = valid_row()
    overflow[12] = "1000.00"
    with pytest.raises(ImportValidationError, match=r"row 3.*철\(mg\)"):
        validate_rows([overflow], first_row_number=3)


def test_parse_workbook_reads_xlsx_with_leading_blank_rows(tmp_path: Path) -> None:
    path = tmp_path / "supplements.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append([])
    worksheet.append(EXPECTED_HEADERS)
    worksheet.append(valid_row())
    workbook.save(path)

    records = parse_workbook(path)

    assert len(records) == 1
    assert records[0]["food_code"] == "F101-TEST-001"
    assert records[0]["iron_mg"] == Decimal("15.00")


def test_parse_workbook_maps_wide_mfds_xlsx_without_guessing_serving_unit(tmp_path: Path) -> None:
    path = tmp_path / "mfds-supplements.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    headers = [
        "식품코드",
        "식품명",
        "데이터구분명",
        "영양성분제공단위량",
        "에너지(kcal)",
        "수분(g)",
        "단백질(g)",
        "지방(g)",
        "회분(g)",
        "탄수화물(g)",
        "당류(g)",
        "식이섬유(g)",
        "칼슘(mg)",
        "철(mg)",
        "인(mg)",
        "칼륨(mg)",
        "나트륨(mg)",
        "비타민A(μg RAE)",
        "레티놀(μg)",
        "베타카로틴(μg)",
        "티아민(mg)",
        "리보플라빈(mg)",
        "니아신(mg)",
        "비타민 C(mg)",
        "비타민 D(μg)",
        "콜레스테롤(mg)",
        "포화지방산(g)",
        "트랜스지방산(g)",
        "1회분량중량/부피",
        "1일섭취횟수",
        "섭취대상명",
    ]
    values = valid_row()
    values.pop(27)
    values.insert(2, "건강기능식품")
    worksheet.append(headers)
    worksheet.append(values)
    workbook.save(path)

    records = parse_workbook(path)

    assert records[0]["serving_desc"] == "500mg"
    assert records[0]["serving_size"] == "500mg"
    assert "데이터구분명" not in records[0]


def test_parse_workbook_rejects_unsupported_file_type(tmp_path: Path) -> None:
    path = tmp_path / "supplements.csv"
    path.write_text("unsupported", encoding="utf-8")

    with pytest.raises(ImportValidationError, match="unsupported workbook type"):
        parse_workbook(path)


def test_parse_args_supports_dry_run_and_expected_count(tmp_path: Path) -> None:
    path = tmp_path / "supplements.xlsx"

    args = parse_args([str(path), "--dry-run", "--expected-count", "5556"])

    assert args.path == path
    assert args.dry_run is True
    assert args.expected_count == 5556
