from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.models.interactions import MedicationProductGuide  # noqa: E402

CSV_FIELD_MAP = {
    "품목일련번호": "item_seq",
    "제품명": "product_name",
    "업체명": "manufacturer_name",
    "이 약의 효능은 무엇입니까?": "efficacy",
    "이 약은 어떻게 사용합니까?": "usage_instructions",
    "이 약을 사용하기 전에 반드시 알아야 할 내용은 무엇입니까?": ("pre_use_warning"),
    "이 약의 사용상 주의사항은 무엇입니까?": "precautions",
    "이 약을 사용하는 동안 주의해야 할 약 또는 음식은 무엇입니까?": ("drug_food_interactions"),
    "이 약은 어떤 이상반응이 나타날 수 있습니까?": "adverse_reactions",
    "이 약은 어떻게 보관해야 합니까?": "storage_instructions",
}


class ImportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MedicationProductGuideDataset:
    records: list[dict[str, str]]
    source_row_count: int
    unique_record_count: int
    duplicate_row_count: int


@dataclass(frozen=True)
class ImportResult:
    total: int
    created: int
    updated: int
    unchanged: int


def parse_csv(path: Path) -> MedicationProductGuideDataset:
    source_path = Path(path)
    if not source_path.is_file():
        raise ImportValidationError(f"e약은요 CSV를 찾을 수 없습니다: {source_path}")

    with source_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as source:
        reader = csv.DictReader(source)
        headers = set(reader.fieldnames or ())
        missing_headers = sorted(set(CSV_FIELD_MAP).difference(headers))
        if missing_headers:
            raise ImportValidationError("e약은요 CSV 필수 컬럼이 없습니다: " + ", ".join(missing_headers))

        records_by_item_seq: dict[str, dict[str, str]] = {}
        source_row_count = 0
        duplicate_row_count = 0
        for row_number, row in enumerate(reader, start=2):
            source_row_count += 1
            record = _normalize_row(row, row_number=row_number)
            item_seq = record["item_seq"]
            previous = records_by_item_seq.get(item_seq)
            if previous is None:
                records_by_item_seq[item_seq] = record
                continue
            if previous != record:
                different_fields = [
                    field_name for field_name in CSV_FIELD_MAP.values() if previous[field_name] != record[field_name]
                ]
                raise ImportValidationError(
                    f"품목일련번호 {item_seq}의 중복 행 내용이 충돌합니다: " + ", ".join(different_fields)
                )
            duplicate_row_count += 1

    records = list(records_by_item_seq.values())
    return MedicationProductGuideDataset(
        records=records,
        source_row_count=source_row_count,
        unique_record_count=len(records),
        duplicate_row_count=duplicate_row_count,
    )


async def upsert_records(
    records: list[dict[str, str]],
    *,
    batch_size: int = 500,
) -> ImportResult:
    if batch_size <= 0:
        raise ValueError("batch_size는 1 이상이어야 합니다.")

    existing_by_item_seq: dict[str, MedicationProductGuide] = {}
    item_sequences = [record["item_seq"] for record in records]
    async with in_transaction() as connection:
        for start in range(0, len(item_sequences), batch_size):
            batch = item_sequences[start : start + batch_size]
            existing = await MedicationProductGuide.filter(item_seq__in=batch).using_db(connection)
            existing_by_item_seq.update({guide.item_seq: guide for guide in existing})

        to_create: list[MedicationProductGuide] = []
        to_update: list[MedicationProductGuide] = []
        unchanged = 0
        for record in records:
            guide = existing_by_item_seq.get(record["item_seq"])
            if guide is None:
                to_create.append(MedicationProductGuide(**record))
                continue
            if all(getattr(guide, field_name) == record[field_name] for field_name in CSV_FIELD_MAP.values()):
                unchanged += 1
                continue
            for field_name in _UPDATE_FIELDS:
                setattr(guide, field_name, record[field_name])
            to_update.append(guide)

        if to_create:
            await MedicationProductGuide.bulk_create(
                to_create,
                batch_size=batch_size,
                using_db=connection,
            )
        if to_update:
            await MedicationProductGuide.bulk_update(
                to_update,
                fields=_UPDATE_FIELDS,
                batch_size=batch_size,
                using_db=connection,
            )

    return ImportResult(
        total=len(records),
        created=len(to_create),
        updated=len(to_update),
        unchanged=unchanged,
    )


def _normalize_row(
    row: dict[str, str | None],
    *,
    row_number: int,
) -> dict[str, str]:
    record = {field_name: (row.get(source_header) or "").strip() for source_header, field_name in CSV_FIELD_MAP.items()}
    missing = [source_header for source_header, field_name in CSV_FIELD_MAP.items() if not record[field_name]]
    if missing:
        raise ImportValidationError(f"행 {row_number}의 필수값이 비어 있습니다: " + ", ".join(missing))
    if re.fullmatch(r"[0-9]{1,20}", record["item_seq"]) is None:
        raise ImportValidationError(f"행 {row_number}의 품목일련번호 형식이 올바르지 않습니다.")
    for field_name in ("product_name", "manufacturer_name"):
        if len(record[field_name]) > 255:
            raise ImportValidationError(f"행 {row_number}의 {field_name}이 255자를 초과합니다.")
    return record


async def _run_import(
    *,
    path: Path,
    dry_run: bool,
    batch_size: int,
) -> tuple[MedicationProductGuideDataset, ImportResult | None]:
    dataset = parse_csv(path)
    if dry_run:
        return dataset, None

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        result = await upsert_records(
            dataset.records,
            batch_size=batch_size,
        )
        stored_count = await MedicationProductGuide.filter(
            item_seq__in=[record["item_seq"] for record in dataset.records]
        ).count()
        if stored_count != dataset.unique_record_count:
            raise RuntimeError(
                "의약품 제품 가이드 적재 건수가 검증 결과와 일치하지 않습니다: "
                f"expected={dataset.unique_record_count}, actual={stored_count}"
            )
        return dataset, result
    finally:
        await Tortoise.close_connections()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("식약처 e약은요 CSV의 사용자용 제품 가이드를 MySQL에 적재합니다."))
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=(PROJECT_ROOT / "data" / "knowledge" / "raw" / "public" / "mfds" / "drug_records" / "e약은요.csv"),
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.batch_size <= 0:
        parser.error("--batch-size는 1 이상이어야 합니다.")
    return args


def main() -> int:
    args = parse_args()
    try:
        dataset, result = asyncio.run(
            _run_import(
                path=args.path,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
            )
        )
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1

    payload: dict[str, object] = {
        "source_row_count": dataset.source_row_count,
        "unique_record_count": dataset.unique_record_count,
        "duplicate_row_count": dataset.duplicate_row_count,
        "dry_run": args.dry_run,
    }
    if result is not None:
        payload["database"] = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


_UPDATE_FIELDS = [field_name for field_name in CSV_FIELD_MAP.values() if field_name != "item_seq"]


if __name__ == "__main__":
    raise SystemExit(main())
