from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.supplement_nutrients import NutrientStandard  # noqa: E402

DEFAULT_PATH = PROJECT_ROOT / "data" / "nutrient_standards.csv"
NUTRIENT_PREFIXES = (
    "carb_g",
    "protein_g",
    "fat_g",
    "fiber_g",
    "calcium_mg",
    "iron_mg",
    "phosphorus_mg",
    "potassium_mg",
    "sodium_mg",
    "vitamin_a_ug_rae",
    "thiamine_mg",
    "riboflavin_mg",
    "niacin_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
)
NUTRIENT_FIELDS = tuple(
    f"{prefix}_{standard_type}" for prefix in NUTRIENT_PREFIXES for standard_type in ("rni", "ai", "ul")
)
EXPECTED_HEADERS = ("grp", "age", *NUTRIENT_FIELDS)


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    total: int
    created: int
    updated: int


def _parse_decimal(value: str, *, row_number: int, field_name: str) -> Decimal | None:
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    try:
        number = Decimal(normalized)
    except InvalidOperation as exc:
        raise ImportValidationError(f"row {row_number}, column {field_name}: invalid number {value!r}") from exc
    if not number.is_finite():
        raise ImportValidationError(f"row {row_number}, column {field_name}: number must be finite")

    _, digits, exponent = number.as_tuple()
    decimal_places = max(-exponent, 0)
    integer_places = max(len(digits) + exponent, 0)
    if max(integer_places + decimal_places, 1) > 10 or decimal_places > 3:
        raise ImportValidationError(f"row {row_number}, column {field_name}: value exceeds decimal(10,3)")
    return number


def parse_csv(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADERS:
            raise ImportValidationError("header mismatch")

        records: list[dict[str, object]] = []
        seen: dict[tuple[str, str | None], int] = {}
        for row_number, row in enumerate(reader, start=2):
            grp = (row["grp"] or "").strip()
            age = (row["age"] or "").strip() or None
            if not grp:
                raise ImportValidationError(f"row {row_number}, column grp: value is required")
            if len(grp) > 10 or (age is not None and len(age) > 20):
                raise ImportValidationError(f"row {row_number}: group or age length exceeded")

            key = (grp, age)
            if key in seen:
                raise ImportValidationError(f"duplicate target rows {seen[key]} and {row_number}")
            seen[key] = row_number

            record: dict[str, object] = {"grp": grp, "age": age}
            record.update(
                {
                    field_name: _parse_decimal(row[field_name] or "", row_number=row_number, field_name=field_name)
                    for field_name in NUTRIENT_FIELDS
                }
            )
            records.append(record)
    return records


async def upsert_records(records: list[dict[str, object]]) -> ImportResult:
    async with in_transaction() as connection:
        existing = await NutrientStandard.all().using_db(connection)
        existing_by_key = {(item.grp, item.age): item for item in existing}
        to_create: list[NutrientStandard] = []
        to_update: list[NutrientStandard] = []

        for record in records:
            key = (str(record["grp"]), record["age"])
            standard = existing_by_key.get(key)
            if standard is None:
                to_create.append(NutrientStandard(**record))
                continue
            for field_name in EXPECTED_HEADERS:
                setattr(standard, field_name, record[field_name])
            to_update.append(standard)

        if to_create:
            await NutrientStandard.bulk_create(to_create, using_db=connection)
        if to_update:
            await NutrientStandard.bulk_update(
                to_update,
                fields=list(EXPECTED_HEADERS),
                using_db=connection,
            )
    return ImportResult(total=len(records), created=len(to_create), updated=len(to_update))


async def _run_import(path: Path) -> ImportResult:
    records = parse_csv(path)
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return await upsert_records(records)
    finally:
        await Tortoise.close_connections()


def main() -> int:
    parser = argparse.ArgumentParser(description="2025 한국인 영양소 섭취기준 CSV를 MySQL에 적재합니다.")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        result = asyncio.run(_run_import(args.path))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"total={result.total} created={result.created} updated={result.updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
