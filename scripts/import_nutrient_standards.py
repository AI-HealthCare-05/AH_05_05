from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
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
        await verify_stored_records(records, connection=connection)
    return ImportResult(total=len(records), created=len(to_create), updated=len(to_update))


async def verify_stored_records(
    records: list[dict[str, object]],
    *,
    connection: BaseDBAsyncClient | None = None,
) -> None:
    expected_keys = {(str(record["grp"]), record["age"]) for record in records}
    query = NutrientStandard.all()
    if connection is not None:
        query = query.using_db(connection)
    stored_keys = set(await query.values_list("grp", "age"))
    missing_keys = expected_keys.difference(stored_keys)
    if missing_keys:
        raise RuntimeError(f"영양소 섭취기준 원본 키가 DB에 모두 저장되지 않았습니다: missing={len(missing_keys)}")


async def _run_import(
    path: Path,
    *,
    dry_run: bool,
) -> tuple[list[dict[str, object]], ImportResult | None]:
    records = parse_csv(path)
    if dry_run:
        return records, None
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        return records, await upsert_records(records)
    finally:
        await Tortoise.close_connections()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2025 한국인 영양소 섭취기준 CSV를 MySQL에 적재합니다.")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records, result = asyncio.run(
            _run_import(
                args.path,
                dry_run=args.dry_run,
            )
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if result is None:
        print(f"total={len(records)} dry_run=true")
        return 0
    print(f"total={result.total} created={result.created} updated={result.updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
