import gzip
import hashlib
import json
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.db.reference_seed import (
    ReferenceSeedError,
    _write_rows,
    apply_reference_seed,
    decode_seed_value,
    encode_seed_value,
    validate_seed_artifacts,
)


def test_manifest_rejects_unknown_table(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"version":"v1","schema_head":"42","batch_size":500,'
        '"tables":[{"name":"users","file":"users.jsonl.gz","row_count":0,'
        '"sha256":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"key_fields":["id"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ReferenceSeedError, match="허용되지 않은 테이블"):
        validate_seed_artifacts(tmp_path)


def test_manifest_rejects_checksum_mismatch(tmp_path: Path) -> None:
    import gzip

    seed_path = tmp_path / "badges.jsonl.gz"
    with gzip.open(seed_path, "wt", encoding="utf-8") as stream:
        stream.write('{"name":"걷기 배지"}\n')
    (tmp_path / "manifest.json").write_text(
        '{"version":"v1","schema_head":"42","batch_size":500,'
        '"tables":[{"name":"badges","file":"badges.jsonl.gz","row_count":1,'
        '"sha256":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"key_fields":["name"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ReferenceSeedError, match="checksum"):
        validate_seed_artifacts(tmp_path)


def test_seed_codec_round_trips_supported_scalars() -> None:
    values = [
        Decimal("1.250"),
        datetime(2026, 9, 9, 12, 30),
        date(2026, 9, 9),
        None,
        "문자열",
        7,
        True,
    ]

    assert [decode_seed_value(encode_seed_value(value)) for value in values] == values


def _write_seed_dir(tmp_path: Path, tables: dict[str, tuple[tuple[str, ...], list[dict[str, object]]]]) -> Path:
    manifest_tables = []
    for table, (key_fields, rows) in tables.items():
        path = tmp_path / f"{table}.jsonl.gz"
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
                for row in rows:
                    stream.write(
                        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
                    )
        manifest_tables.append(
            {
                "name": table,
                "file": path.name,
                "row_count": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "key_fields": list(key_fields),
            }
        )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": "test",
                "schema_head": "42",
                "batch_size": 500,
                "tables": manifest_tables,
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


class MemoryUpsertDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, object]]] = {
            "common_code_groups": [
                {
                    "id": 9001,
                    "category": "OLD",
                    "group_code": "SEED_GROUP",
                    "group_name": "변경 전",
                    "description": None,
                    "is_active": 1,
                }
            ],
            "common_codes": [],
        }
        self.next_id = 10000

    async def seed_fetch_rows(self, table: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.tables.get(table, [])]

    async def seed_upsert_rows(
        self,
        table: str,
        rows: list[dict[str, object]],
        key_fields: tuple[str, ...],
        update_fields: tuple[str, ...],
        insert_if_missing: bool,
    ) -> None:
        target = self.tables.setdefault(table, [])
        for row in rows:
            found = next(
                (item for item in target if all(item.get(field) == row.get(field) for field in key_fields)),
                None,
            )
            if found is not None:
                found.update({field: row.get(field) for field in update_fields})
            elif insert_if_missing:
                inserted = dict(row)
                inserted.setdefault("id", self.next_id)
                self.next_id += 1
                target.append(inserted)


@pytest.mark.asyncio
async def test_apply_upserts_by_logical_key_and_remaps_parent_ids(tmp_path: Path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        {
            "common_code_groups": (
                ("group_code",),
                [
                    {
                        "id": 1,
                        "category": "CHL",
                        "group_code": "SEED_GROUP",
                        "group_name": "변경 후",
                        "description": "설명",
                        "is_active": 1,
                    }
                ],
            ),
            "common_codes": (
                ("group_id", "detail_code"),
                [
                    {
                        "id": 2,
                        "group_id": 1,
                        "detail_code": "ACTIVE",
                        "detail_name": "사용",
                        "description": None,
                        "sort_order": 1,
                        "is_active": 1,
                    }
                ],
            ),
        },
    )
    db = MemoryUpsertDb()

    first = await apply_reference_seed(db, seed_dir)
    second = await apply_reference_seed(db, seed_dir)

    assert first.total_created == 1
    assert second.total_created == 0
    assert db.tables["common_code_groups"][0]["id"] == 9001
    assert db.tables["common_code_groups"][0]["group_name"] == "변경 후"
    assert db.tables["common_codes"][0]["group_id"] == 9001


@pytest.mark.asyncio
async def test_apply_preserves_existing_smtp_password_and_skips_missing_setting(tmp_path: Path) -> None:
    seed_dir = _write_seed_dir(
        tmp_path,
        {
            "admin_settings": (
                ("setting_key",),
                [
                    {
                        "id": 1,
                        "setting_key": "SMTP",
                        "smtp_host": "new.smtp.example.com",
                        "smtp_port": 587,
                        "smtp_user": "new-user",
                        "smtp_password_enc": None,
                        "smtp_from_email": "new@example.com",
                        "updated_by_admin_id": None,
                    }
                ],
            )
        },
    )
    existing = MemoryUpsertDb()
    existing.tables["admin_settings"] = [
        {
            "id": 51,
            "setting_key": "SMTP",
            "smtp_host": "old.smtp.example.com",
            "smtp_port": 465,
            "smtp_user": "old-user",
            "smtp_password_enc": "KEEP_ME",
            "smtp_from_email": "old@example.com",
            "updated_by_admin_id": 7,
        }
    ]

    result = await apply_reference_seed(existing, seed_dir)

    assert result.tables["admin_settings"].updated == 1
    assert existing.tables["admin_settings"][0]["smtp_password_enc"] == "KEEP_ME"
    assert existing.tables["admin_settings"][0]["smtp_host"] == "new.smtp.example.com"
    assert existing.tables["admin_settings"][0]["updated_by_admin_id"] == 7

    missing = MemoryUpsertDb()
    missing.tables["admin_settings"] = []
    skipped = await apply_reference_seed(missing, seed_dir)
    assert skipped.tables["admin_settings"].skipped == 1
    assert missing.tables["admin_settings"] == []


@pytest.mark.asyncio
async def test_apply_accepts_empty_seed_table(tmp_path: Path) -> None:
    seed_dir = _write_seed_dir(tmp_path, {"interaction_entities": (("entity_kind", "normalized_name"), [])})

    class NoFetchDb(MemoryUpsertDb):
        async def seed_fetch_rows(self, table: str) -> list[dict[str, object]]:
            raise AssertionError(f"빈 시드 테이블을 조회하면 안 됩니다: {table}")

    result = await apply_reference_seed(NoFetchDb(), seed_dir)

    assert result.tables["interaction_entities"].unchanged == 0


@pytest.mark.asyncio
async def test_mysql_upsert_uses_row_alias_instead_of_deprecated_values_function() -> None:
    class CaptureDb:
        def __init__(self) -> None:
            self.query = ""

        async def execute_many(self, query: str, values: list[list[object]]) -> None:
            self.query = query

    db = CaptureDb()

    await _write_rows(
        db,  # type: ignore[arg-type]
        "badges",
        [{"name": "걷기", "description": "설명"}],
        ("name",),
        ("description",),
        True,
    )

    assert " AS new ON DUPLICATE KEY UPDATE " in db.query
    assert "VALUES(`description`)" not in db.query


def _challenge_seed(tmp_path: Path) -> Path:
    return _write_seed_dir(
        tmp_path,
        {
            "common_code_groups": (("group_code",), [{"id": 1, "group_code": "SEED_GROUP", "group_name": "공통"}]),
            "common_codes": (("group_id", "detail_code"), [{"id": 1, "group_id": 1, "detail_code": "DAILY"}]),
            "badges": (("name",), []),
            "challenges": (
                ("id",),
                [
                    {
                        "id": identifier,
                        "name": name,
                        "recruit_start_at": encode_seed_value(datetime(2026, 9, 1)),
                        "description": "시드 안내",
                        "challenge_period_id": 1,
                        "challenge_type_id": 1,
                        "check_frequency_id": 1,
                        "check_type_id": 1,
                        "reward_badge_id": None,
                    }
                    for identifier, name in [(2, "물 마시기"), (3, "매일 걷기")]
                ],
            ),
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing_name", "existing_start"),
    [("기존 사용자 챌린지", datetime(2026, 9, 1)), ("물 마시기", datetime(2026, 8, 1))],
)
async def test_conflicting_challenge_is_skipped_without_changing_history(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, existing_name: str, existing_start: datetime
) -> None:
    db = MemoryUpsertDb()
    original = {
        "id": 2,
        "name": existing_name,
        "recruit_start_at": existing_start,
        "description": "기존 설정 보존",
        "reward_badge_id": 71,
        "challenge_period_id": 82,
        "challenge_type_id": 83,
        "check_frequency_id": 84,
        "check_type_id": 85,
    }
    db.tables["challenges"] = [dict(original)]
    db.tables["user_challenges"] = [{"id": 91, "challenge_id": 2, "completed_count": 4}]
    db.tables["user_badges"] = [{"id": 92, "challenge_id": 2, "user_challenge_id": 91, "badge_id": 71}]
    history = deepcopy({key: db.tables[key] for key in ("user_challenges", "user_badges")})
    seed_dir = _challenge_seed(tmp_path)

    first = await apply_reference_seed(db, seed_dir)
    second = await apply_reference_seed(db, seed_dir)

    assert db.tables["challenges"][0] == original
    assert {key: db.tables[key] for key in history} == history
    assert [(row["id"], row["name"]) for row in db.tables["challenges"]] == [(2, existing_name), (3, "매일 걷기")]
    assert first.tables["challenges"].created == 1
    assert first.tables["challenges"].skipped == 1
    assert second.tables["challenges"].created == 0
    assert second.tables["challenges"].skipped == 1
    assert second.tables["challenges"].unchanged == 1
    assert any(record.levelname == "WARNING" and "2" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_empty_challenge_database_keeps_seed_ids_and_reapplication_is_idempotent(tmp_path: Path) -> None:
    db = MemoryUpsertDb()
    seed_dir = _challenge_seed(tmp_path)

    first = await apply_reference_seed(db, seed_dir)
    second = await apply_reference_seed(db, seed_dir)

    assert [(row["id"], row["name"]) for row in db.tables["challenges"]] == [(2, "물 마시기"), (3, "매일 걷기")]
    assert first.tables["challenges"].created == 2
    assert second.tables["challenges"].unchanged == 2
    assert second.tables["challenges"].created == 0
    assert second.tables["challenges"].skipped == 0


@pytest.mark.asyncio
async def test_matching_challenge_identity_still_updates_seed_fields(tmp_path: Path) -> None:
    db = MemoryUpsertDb()
    seed_dir = _challenge_seed(tmp_path)
    await apply_reference_seed(db, seed_dir)
    db.tables["challenges"][0]["description"] = "이전 안내"

    result = await apply_reference_seed(db, seed_dir)

    assert db.tables["challenges"][0]["description"] == "시드 안내"
    assert result.tables["challenges"].updated == 1
    assert result.tables["challenges"].skipped == 0
