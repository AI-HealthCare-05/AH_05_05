import csv
from pathlib import Path

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.interactions import MedicationProductGuide
from scripts.import_medication_product_guides import (
    CSV_FIELD_MAP,
    ImportValidationError,
    parse_csv,
    upsert_records,
)


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


def build_row(
    item_seq: str = "197900277",
    *,
    efficacy: str = "두통과 치통의 통증 완화",
) -> dict[str, str]:
    return {
        "품목일련번호": item_seq,
        "제품명": "게보린정",
        "업체명": "삼진제약(주)",
        "이 약의 효능은 무엇입니까?": efficacy,
        "이 약은 어떻게 사용합니까?": "정해진 용법에 따라 복용합니다.",
        "이 약을 사용하기 전에 반드시 알아야 할 내용은 무엇입니까?": ("복용 전 전문가와 상의하십시오."),
        "이 약의 사용상 주의사항은 무엇입니까?": "과량 복용하지 마십시오.",
        "이 약을 사용하는 동안 주의해야 할 약 또는 음식은 무엇입니까?": ("다른 해열진통제와 함께 복용하지 마십시오."),
        "이 약은 어떤 이상반응이 나타날 수 있습니까?": "발진이 나타날 수 있습니다.",
        "이 약은 어떻게 보관해야 합니까?": "실온에서 보관하십시오.",
        "공개일자": "2020-12-24",
        "낱알이미지": "https://example.com/first.png",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [*CSV_FIELD_MAP, "공개일자", "낱알이미지", ""]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_parse_csv_keeps_requested_fields_and_merges_safe_duplicates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "e약은요.csv"
    first = build_row()
    duplicate = build_row()
    duplicate["낱알이미지"] = "https://example.com/second.png"
    write_csv(path, [first, duplicate, build_row("202000001")])

    dataset = parse_csv(path)

    assert dataset.source_row_count == 3
    assert dataset.unique_record_count == 2
    assert dataset.duplicate_row_count == 1
    assert dataset.records[0] == {
        "item_seq": "197900277",
        "product_name": "게보린정",
        "manufacturer_name": "삼진제약(주)",
        "efficacy": "두통과 치통의 통증 완화",
        "usage_instructions": "정해진 용법에 따라 복용합니다.",
        "pre_use_warning": "복용 전 전문가와 상의하십시오.",
        "precautions": "과량 복용하지 마십시오.",
        "drug_food_interactions": ("다른 해열진통제와 함께 복용하지 마십시오."),
        "adverse_reactions": "발진이 나타날 수 있습니다.",
        "storage_instructions": "실온에서 보관하십시오.",
    }


def test_parse_csv_rejects_conflicting_duplicate_product(
    tmp_path: Path,
) -> None:
    path = tmp_path / "e약은요.csv"
    write_csv(
        path,
        [
            build_row(),
            build_row(efficacy="서로 다른 효능 설명"),
        ],
    )

    with pytest.raises(
        ImportValidationError,
        match=r"197900277.*중복.*충돌",
    ):
        parse_csv(path)


def test_parse_csv_rejects_missing_required_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "e약은요.csv"
    row = build_row()
    row.pop("이 약은 어떻게 보관해야 합니까?")
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(ImportValidationError, match="필수 컬럼"):
        parse_csv(path)


@pytest.mark.asyncio
async def test_upsert_records_is_idempotent_and_updates_changed_content(
    initialized_db: None,
) -> None:
    records = parse_csv_from_rows([build_row(), build_row("202000001")])

    first = await upsert_records(records)
    second = await upsert_records(records)
    changed = [dict(records[0]), dict(records[1])]
    changed[0]["efficacy"] = "변경된 공공데이터 효능"
    third = await upsert_records(changed)

    assert (first.created, first.updated, first.unchanged) == (2, 0, 0)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 2)
    assert (third.created, third.updated, third.unchanged) == (0, 1, 1)
    assert await MedicationProductGuide.all().count() == 2
    guide = await MedicationProductGuide.get(item_seq="197900277")
    assert guide.efficacy == "변경된 공공데이터 효능"


def parse_csv_from_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for row in rows:
        parsed.append({field_name: row[source_header] for source_header, field_name in CSV_FIELD_MAP.items()})
    return parsed
