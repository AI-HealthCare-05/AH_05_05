from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from numbers_parser import Document
from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.supplement_nutrients import SupplementNutrient  # noqa: E402

EXPECTED_HEADERS = [
    "식품코드",
    "식품명",
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
    "비타민 A(μg RAE)",
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
    "1회분량",
    "1회분량중량/부피",
    "1일섭취횟수",
    "섭취대상",
]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: Literal["string", "integer", "decimal"]
    required: bool
    max_length: int | None = None
    max_digits: int | None = None
    decimal_places: int | None = None


FIELD_SPECS = [
    FieldSpec("food_code", "string", True, max_length=20),
    FieldSpec("name", "string", True, max_length=100),
    FieldSpec("basis_qty", "string", True, max_length=10),
    FieldSpec("energy_kcal", "integer", True),
    FieldSpec("water_g", "decimal", False, max_digits=10, decimal_places=3),
    FieldSpec("protein_g", "decimal", True, max_digits=5, decimal_places=2),
    FieldSpec("fat_g", "decimal", False, max_digits=5, decimal_places=2),
    FieldSpec("ash_g", "decimal", False, max_digits=10, decimal_places=3),
    FieldSpec("carb_g", "decimal", True, max_digits=6, decimal_places=2),
    FieldSpec("sugar_g", "decimal", False, max_digits=5, decimal_places=2),
    FieldSpec("fiber_g", "decimal", False, max_digits=7, decimal_places=1),
    FieldSpec("calcium_mg", "integer", False),
    FieldSpec("iron_mg", "decimal", False, max_digits=5, decimal_places=2),
    FieldSpec("phosphorus_mg", "integer", False),
    FieldSpec("potassium_mg", "integer", False),
    FieldSpec("sodium_mg", "integer", False),
    FieldSpec("vitamin_a_ug_rae", "integer", False),
    FieldSpec("retinol_ug", "integer", False),
    FieldSpec("beta_carotene_ug", "integer", False),
    FieldSpec("thiamine_mg", "decimal", False, max_digits=6, decimal_places=3),
    FieldSpec("riboflavin_mg", "decimal", False, max_digits=6, decimal_places=3),
    FieldSpec("niacin_mg", "decimal", False, max_digits=6, decimal_places=3),
    FieldSpec("vitamin_c_mg", "decimal", False, max_digits=7, decimal_places=2),
    FieldSpec("vitamin_d_ug", "decimal", False, max_digits=7, decimal_places=2),
    FieldSpec("cholesterol_mg", "decimal", False, max_digits=6, decimal_places=2),
    FieldSpec("sat_fat_g", "decimal", False, max_digits=4, decimal_places=2),
    FieldSpec("trans_fat_g", "decimal", False, max_digits=4, decimal_places=2),
    FieldSpec("serving_desc", "string", True, max_length=10),
    FieldSpec("serving_size", "string", True, max_length=10),
    FieldSpec("daily_freq", "string", True, max_length=5),
    FieldSpec("target", "string", False, max_length=10),
]

SOURCE_FIELDS = [spec.name for spec in FIELD_SPECS]


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    total: int
    created: int
    updated: int
    failed: int = 0


def validate_headers(headers: list[object], *, row_number: int) -> None:
    normalized = [str(value).strip() if value is not None else None for value in headers]
    if normalized != EXPECTED_HEADERS:
        raise ImportValidationError(f"header mismatch at row {row_number}")


def _decimal_digit_counts(value: Decimal) -> tuple[int, int]:
    sign, digits, exponent = value.as_tuple()
    del sign
    decimal_places = max(-exponent, 0)
    integer_places = max(len(digits) + exponent, 0)
    return max(integer_places + decimal_places, 1), decimal_places


def _convert_value(value: object, spec: FieldSpec, *, row_number: int, header: str) -> object:
    if value is None or (isinstance(value, str) and not value.strip()):
        if spec.required:
            raise ImportValidationError(f"row {row_number}, column {header}: value is required")
        return None

    if spec.kind == "string":
        normalized = str(value).strip()
        if spec.max_length is not None and len(normalized) > spec.max_length:
            raise ImportValidationError(
                f"row {row_number}, column {header}: length {len(normalized)} exceeds {spec.max_length}"
            )
        return normalized

    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ImportValidationError(f"row {row_number}, column {header}: invalid number {value!r}") from exc
    if not number.is_finite():
        raise ImportValidationError(f"row {row_number}, column {header}: number must be finite")

    if spec.kind == "integer":
        if number != number.to_integral_value():
            raise ImportValidationError(f"row {row_number}, column {header}: integer required")
        return int(number)

    total_digits, decimal_places = _decimal_digit_counts(number)
    if total_digits > spec.max_digits or decimal_places > spec.decimal_places:
        raise ImportValidationError(
            f"row {row_number}, column {header}: {number} exceeds decimal({spec.max_digits},{spec.decimal_places})"
        )
    return number


def validate_rows(rows: list[list[object]], *, first_row_number: int) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    code_rows: dict[str, int] = {}
    for index, row in enumerate(rows):
        row_number = first_row_number + index
        if not any(value is not None and (not isinstance(value, str) or value.strip()) for value in row):
            continue
        if len(row) != len(FIELD_SPECS):
            raise ImportValidationError(
                f"row {row_number}: expected {len(FIELD_SPECS)} columns, received {len(row)}"
            )
        record = {
            spec.name: _convert_value(value, spec, row_number=row_number, header=header)
            for value, spec, header in zip(row, FIELD_SPECS, EXPECTED_HEADERS, strict=True)
        }
        food_code = str(record["food_code"])
        if food_code in code_rows:
            raise ImportValidationError(
                f"duplicate food code {food_code} at rows {code_rows[food_code]} and {row_number}"
            )
        code_rows[food_code] = row_number
        records.append(record)
    return records


def parse_numbers(path: str | Path) -> list[dict[str, object]]:
    document = Document(str(path))
    rows = document.sheets[0].tables[0].rows(values_only=True)
    header_index = next(
        (index for index, row in enumerate(rows) if any(value is not None and str(value).strip() for value in row)),
        None,
    )
    if header_index is None:
        raise ImportValidationError("header row not found")
    validate_headers(rows[header_index], row_number=header_index + 1)
    return validate_rows(rows[header_index + 1 :], first_row_number=header_index + 2)


async def upsert_records(records: list[dict[str, object]], *, batch_size: int = 500) -> ImportResult:
    codes = [str(record["food_code"]) for record in records]
    async with in_transaction() as connection:
        existing = await SupplementNutrient.filter(food_code__in=codes).using_db(connection)
        existing_by_code = {product.food_code: product for product in existing}
        to_create: list[SupplementNutrient] = []
        to_update: list[SupplementNutrient] = []
        for record in records:
            product = existing_by_code.get(str(record["food_code"]))
            if product is None:
                to_create.append(SupplementNutrient(**record))
                continue
            for field_name in SOURCE_FIELDS:
                setattr(product, field_name, record[field_name])
            to_update.append(product)
        if to_create:
            await SupplementNutrient.bulk_create(to_create, batch_size=batch_size, using_db=connection)
        if to_update:
            await SupplementNutrient.bulk_update(
                to_update,
                fields=SOURCE_FIELDS,
                batch_size=batch_size,
                using_db=connection,
            )
    return ImportResult(total=len(records), created=len(to_create), updated=len(to_update))


async def _run_import(path: Path) -> ImportResult:
    records = parse_numbers(path)
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await upsert_records(records)
    finally:
        await Tortoise.close_connections()


def main() -> int:
    parser = argparse.ArgumentParser(description="건강기능식품 영양성분 Numbers 파일을 MySQL에 적재합니다.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(_run_import(args.path))
    except Exception as exc:
        print("total=0 created=0 updated=0 failed=1", file=sys.stdout)
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"total={result.total} created={result.created} updated={result.updated} failed={result.failed}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
