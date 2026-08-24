from decimal import Decimal

import pytest

from scripts.import_supplement_nutrients import (
    EXPECTED_HEADERS,
    ImportValidationError,
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
