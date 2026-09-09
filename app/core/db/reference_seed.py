"""Versioned reference-data seed artifact validation and application."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

REFERENCE_TABLE_ORDER = (
    "medication_product_guides",
    "supplement_nutrients",
    "nutrient_standard",
    "common_code_groups",
    "common_codes",
    "admin_settings",
    "interaction_entities",
    "interaction_entity_aliases",
    "interaction_entity_identifiers",
    "supplement_interaction_entities",
    "interaction_rules",
    "interaction_rule_sources",
    "interaction_rule_evidence_chunks",
    "medication_safety_rules",
    "medication_safety_rule_conditions",
    "medication_safety_rule_sources",
    "badges",
    "custom_challenge_templates",
    "challenges",
)
REFERENCE_TABLES = frozenset(REFERENCE_TABLE_ORDER)


class ReferenceSeedError(ValueError):
    """Raised when a reference seed artifact is invalid."""


class ReferenceSeedConflictError(ReferenceSeedError):
    """Raised when applying a seed would overwrite an unrelated record."""


@dataclass(frozen=True)
class SeedTable:
    name: str
    file: str
    row_count: int
    sha256: str
    key_fields: tuple[str, ...]
    excluded_rows: int = 0


@dataclass(frozen=True)
class SeedManifest:
    version: str
    schema_head: str
    batch_size: int
    tables: tuple[SeedTable, ...]

    @classmethod
    def load(cls, seed_dir: Path) -> SeedManifest:
        try:
            payload = json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReferenceSeedError("manifest.json을 읽을 수 없습니다.") from exc
        if not isinstance(payload, dict):
            raise ReferenceSeedError("manifest 형식이 올바르지 않습니다.")
        try:
            raw_tables = payload["tables"]
            if not isinstance(raw_tables, list):
                raise TypeError
            tables = tuple(_parse_seed_table(item) for item in raw_tables)
            manifest = cls(
                version=str(payload["version"]),
                schema_head=str(payload["schema_head"]),
                batch_size=int(payload["batch_size"]),
                tables=tables,
            )
        except ReferenceSeedError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ReferenceSeedError("manifest 필수 항목이 올바르지 않습니다.") from exc
        if manifest.batch_size <= 0:
            raise ReferenceSeedError("batch_size는 1 이상이어야 합니다.")
        names = [table.name for table in tables]
        if len(names) != len(set(names)):
            raise ReferenceSeedError("manifest에 중복 테이블이 있습니다.")
        return manifest


@dataclass(frozen=True)
class ForeignKeySpec:
    field: str
    parent_table: str
    nullable: bool = False


@dataclass(frozen=True)
class TableSeedSpec:
    key_fields: tuple[str, ...]
    foreign_keys: tuple[ForeignKeySpec, ...] = ()
    update_exclusions: frozenset[str] = field(default_factory=frozenset)
    insert_if_missing: bool = True


@dataclass(frozen=True)
class TableApplyResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class SeedApplyResult:
    tables: dict[str, TableApplyResult]

    @property
    def total_created(self) -> int:
        return sum(result.created for result in self.tables.values())

    @property
    def total_updated(self) -> int:
        return sum(result.updated for result in self.tables.values())


class ReferenceSeedDb(Protocol):
    async def execute_query_dict(self, query: str) -> list[dict[str, Any]]: ...

    async def execute_many(self, query: str, values: list[list[object]]) -> None: ...


_AUDIT_EXCLUSIONS = frozenset({"created_by_admin_id", "updated_by_admin_id"})
TABLE_SEED_SPECS: dict[str, TableSeedSpec] = {
    "medication_product_guides": TableSeedSpec(("item_seq",)),
    "supplement_nutrients": TableSeedSpec(("food_code",)),
    "nutrient_standard": TableSeedSpec(("grp", "age")),
    "common_code_groups": TableSeedSpec(("group_code",), update_exclusions=_AUDIT_EXCLUSIONS),
    "common_codes": TableSeedSpec(
        ("group_id", "detail_code"),
        (ForeignKeySpec("group_id", "common_code_groups"),),
        _AUDIT_EXCLUSIONS,
    ),
    # A missing row deliberately falls back to .env. An incomplete SMTP row cannot
    # be inserted because its encrypted password and actor FK are both NOT NULL.
    "admin_settings": TableSeedSpec(
        ("setting_key",),
        update_exclusions=frozenset({"smtp_password_enc", "updated_by_admin_id"}),
        insert_if_missing=False,
    ),
    "interaction_entities": TableSeedSpec(("entity_kind", "normalized_name")),
    "interaction_entity_aliases": TableSeedSpec(
        ("interaction_entity_id", "normalized_alias"),
        (ForeignKeySpec("interaction_entity_id", "interaction_entities"),),
    ),
    "interaction_entity_identifiers": TableSeedSpec(
        ("source_id", "source_code"),
        (ForeignKeySpec("interaction_entity_id", "interaction_entities"),),
    ),
    "supplement_interaction_entities": TableSeedSpec(
        ("supplement_nutrient_id", "interaction_entity_id"),
        (
            ForeignKeySpec("supplement_nutrient_id", "supplement_nutrients"),
            ForeignKeySpec("interaction_entity_id", "interaction_entities"),
        ),
    ),
    "interaction_rules": TableSeedSpec(
        ("pair_key", "rule_dataset_version"),
        (
            ForeignKeySpec("left_entity_id", "interaction_entities"),
            ForeignKeySpec("right_entity_id", "interaction_entities"),
        ),
    ),
    "interaction_rule_sources": TableSeedSpec(
        ("interaction_rule_id", "source_id", "document_id", "record_id"),
        (ForeignKeySpec("interaction_rule_id", "interaction_rules"),),
    ),
    "interaction_rule_evidence_chunks": TableSeedSpec(
        ("interaction_rule_source_id", "dataset_version", "vector_chunk_id"),
        (ForeignKeySpec("interaction_rule_source_id", "interaction_rule_sources"),),
    ),
    "medication_safety_rules": TableSeedSpec(
        ("rule_key", "rule_dataset_version"),
        (ForeignKeySpec("interaction_entity_id", "interaction_entities"),),
    ),
    "medication_safety_rule_conditions": TableSeedSpec(
        ("medication_safety_rule_id", "condition_group_no", "condition_order"),
        (ForeignKeySpec("medication_safety_rule_id", "medication_safety_rules"),),
    ),
    "medication_safety_rule_sources": TableSeedSpec(
        ("medication_safety_rule_id", "source_id", "document_id", "record_id"),
        (ForeignKeySpec("medication_safety_rule_id", "medication_safety_rules"),),
    ),
    "badges": TableSeedSpec(
        ("name",),
        (ForeignKeySpec("type", "common_codes", nullable=True),),
        _AUDIT_EXCLUSIONS,
    ),
    "custom_challenge_templates": TableSeedSpec(
        ("name",),
        (
            ForeignKeySpec("check_type_id", "common_codes"),
            ForeignKeySpec("challenge_type", "common_codes", nullable=True),
            ForeignKeySpec("reward_badge_id", "badges", nullable=True),
        ),
        _AUDIT_EXCLUSIONS,
    ),
    "challenges": TableSeedSpec(
        ("id",),
        (
            ForeignKeySpec("challenge_period_id", "common_codes"),
            ForeignKeySpec("challenge_type_id", "common_codes"),
            ForeignKeySpec("check_frequency_id", "common_codes"),
            ForeignKeySpec("check_type_id", "common_codes"),
            ForeignKeySpec("reward_badge_id", "badges", nullable=True),
        ),
        _AUDIT_EXCLUSIONS,
    ),
}


def _parse_seed_table(payload: object) -> SeedTable:
    if not isinstance(payload, dict):
        raise TypeError
    name = str(payload["name"])
    if name not in REFERENCE_TABLES:
        raise ReferenceSeedError(f"허용되지 않은 테이블입니다: {name}")
    file_name = str(payload["file"])
    pure_path = PurePosixPath(file_name)
    if pure_path.is_absolute() or ".." in pure_path.parts or len(pure_path.parts) != 1:
        raise ReferenceSeedError(f"안전하지 않은 시드 파일 경로입니다: {file_name}")
    row_count = int(payload["row_count"])
    excluded_rows = int(payload.get("excluded_rows", 0))
    if row_count < 0 or excluded_rows < 0:
        raise ReferenceSeedError("행 수는 음수일 수 없습니다.")
    checksum = str(payload["sha256"]).lower()
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise ReferenceSeedError("sha256 checksum 형식이 올바르지 않습니다.")
    key_fields = tuple(str(field) for field in payload["key_fields"])
    if not key_fields or any(not field for field in key_fields):
        raise ReferenceSeedError("논리 키가 비어 있습니다.")
    return SeedTable(name, file_name, row_count, checksum, key_fields, excluded_rows)


def encode_seed_value(value: object) -> object:
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ReferenceSeedError(f"지원하지 않는 시드 값 형식입니다: {type(value).__name__}")


def decode_seed_value(value: object) -> object:
    if not isinstance(value, dict) or "$type" not in value:
        return value
    kind = value.get("$type")
    raw = value.get("value")
    if not isinstance(raw, str):
        raise ReferenceSeedError("태그된 시드 값이 올바르지 않습니다.")
    try:
        if kind == "decimal":
            return Decimal(raw)
        if kind == "datetime":
            return datetime.fromisoformat(raw)
        if kind == "date":
            return date.fromisoformat(raw)
    except ValueError as exc:
        raise ReferenceSeedError(f"{kind} 시드 값이 올바르지 않습니다.") from exc
    raise ReferenceSeedError(f"알 수 없는 시드 값 형식입니다: {kind}")


def _decode_row(value: object) -> object:
    if isinstance(value, list):
        return [_decode_row(item) for item in value]
    if isinstance(value, dict):
        if "$type" in value:
            return decode_seed_value(value)
        return {str(key): _decode_row(item) for key, item in value.items()}
    return value


def iter_seed_rows(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ReferenceSeedError(f"{path.name}:{line_no} 행은 JSON 객체여야 합니다.")
                yield _decode_row(payload)  # type: ignore[misc]
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceSeedError(f"시드 파일을 읽을 수 없습니다: {path.name}") from exc


def validate_seed_artifacts(seed_dir: Path) -> SeedManifest:
    manifest = SeedManifest.load(seed_dir)
    for table in manifest.tables:
        path = seed_dir / table.file
        try:
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ReferenceSeedError(f"시드 파일이 없습니다: {table.file}") from exc
        if checksum != table.sha256:
            raise ReferenceSeedError(f"checksum이 일치하지 않습니다: {table.file}")
        row_count = sum(1 for _ in iter_seed_rows(path))
        if row_count != table.row_count:
            raise ReferenceSeedError(f"행 수가 일치하지 않습니다: {table.file}")
    return manifest


def _normalized_key(row: dict[str, object], fields: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(("__REFERENCE_SEED_NULL__" if row.get(name) is None else row.get(name)) for name in fields)


def _load_and_preflight_rows(
    seed_dir: Path,
    manifest: SeedManifest,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, set[object]]]:
    rows_by_table: dict[str, list[dict[str, object]]] = {}
    source_ids: dict[str, set[object]] = {}
    for table in manifest.tables:
        spec = TABLE_SEED_SPECS[table.name]
        if table.key_fields != spec.key_fields:
            raise ReferenceSeedError(f"논리 키가 계약과 다릅니다: {table.name}")
        rows = list(iter_seed_rows(seed_dir / table.file))
        rows_by_table[table.name] = rows
        source_ids[table.name] = _validate_table_rows(table.name, rows, spec)

    _validate_foreign_key_references(rows_by_table, source_ids)
    return rows_by_table, source_ids


def _validate_table_rows(
    table_name: str,
    rows: list[dict[str, object]],
    spec: TableSeedSpec,
) -> set[object]:
    seen: set[tuple[object, ...]] = set()
    ids: set[object] = set()
    required = {"id", *spec.key_fields, *(fk.field for fk in spec.foreign_keys)}
    for row in rows:
        missing = sorted(required.difference(row))
        if missing:
            raise ReferenceSeedError(f"필수 컬럼이 없습니다: {table_name}.{missing[0]}")
        key = _normalized_key(row, spec.key_fields)
        if key in seen:
            raise ReferenceSeedError(f"중복 논리 키가 있습니다: {table_name}")
        seen.add(key)
        source_id = row["id"]
        if source_id in ids:
            raise ReferenceSeedError(f"중복 원본 ID가 있습니다: {table_name}")
        ids.add(source_id)
    return ids


def _validate_foreign_key_references(
    rows_by_table: dict[str, list[dict[str, object]]],
    source_ids: dict[str, set[object]],
) -> None:
    for table_name, rows in rows_by_table.items():
        for fk in TABLE_SEED_SPECS[table_name].foreign_keys:
            if fk.parent_table not in rows_by_table:
                raise ReferenceSeedError(f"부모 테이블 시드가 없습니다: {table_name}.{fk.field}")
            invalid = next(
                (
                    row
                    for row in rows
                    if not (row[fk.field] is None and fk.nullable) and row[fk.field] not in source_ids[fk.parent_table]
                ),
                None,
            )
            if invalid is not None:
                raise ReferenceSeedError(f"부모 참조가 없습니다: {table_name}.{fk.field}")


async def _fetch_target_rows(
    db: ReferenceSeedDb,
    table: str,
    columns: tuple[str, ...],
) -> list[dict[str, object]]:
    hook = getattr(db, "seed_fetch_rows", None)
    if hook is not None:
        return await hook(table)
    selected = ", ".join(f"`{column}`" for column in columns)
    return await db.execute_query_dict(f"SELECT {selected} FROM `{table}`")


async def _write_rows(
    db: ReferenceSeedDb,
    table: str,
    rows: list[dict[str, object]],
    key_fields: tuple[str, ...],
    update_fields: tuple[str, ...],
    insert_if_missing: bool,
) -> None:
    if not rows:
        return
    hook = getattr(db, "seed_upsert_rows", None)
    if hook is not None:
        await hook(table, rows, key_fields, update_fields, insert_if_missing)
        return
    if not insert_if_missing:
        set_clause = ", ".join(f"`{field}` = %s" for field in update_fields)
        where_clause = " AND ".join(f"`{field}` <=> %s" for field in key_fields)
        values = [[row.get(field) for field in (*update_fields, *key_fields)] for row in rows]
        await db.execute_many(f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}", values)
        return
    columns = tuple(rows[0])
    placeholders = ", ".join("%s" for _ in columns)
    column_sql = ", ".join(f"`{column}`" for column in columns)
    if update_fields:
        update_sql = ", ".join(f"`{field}` = VALUES(`{field}`)" for field in update_fields)
    else:
        update_sql = f"`{key_fields[0]}` = `{key_fields[0]}`"
    values = [[row.get(column) for column in columns] for row in rows]
    await db.execute_many(
        f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {update_sql}",
        values,
    )


def _remap_foreign_keys(
    table: str,
    row: dict[str, object],
    id_maps: dict[str, dict[object, object]],
) -> dict[str, object]:
    remapped = dict(row)
    for fk in TABLE_SEED_SPECS[table].foreign_keys:
        source_id = row[fk.field]
        if source_id is None and fk.nullable:
            continue
        try:
            remapped[fk.field] = id_maps[fk.parent_table][source_id]
        except KeyError as exc:
            raise ReferenceSeedError(f"대상 부모 ID를 찾을 수 없습니다: {table}.{fk.field}") from exc
    return remapped


async def _preflight_challenge_collisions(
    db: ReferenceSeedDb,
    rows: list[dict[str, object]],
) -> None:
    if not rows:
        return
    existing = await _fetch_target_rows(db, "challenges", ("id", "name", "recruit_start_at"))
    existing_by_id = {row["id"]: row for row in existing}
    for row in rows:
        target = existing_by_id.get(row["id"])
        if target is None:
            continue
        if target.get("name") != row.get("name") or target.get("recruit_start_at") != row.get("recruit_start_at"):
            raise ReferenceSeedConflictError(f"챌린지 ID 충돌이 발생했습니다: {row['id']}")


async def apply_reference_seed(
    db: ReferenceSeedDb,
    seed_dir: Path,
) -> SeedApplyResult:
    manifest = validate_seed_artifacts(seed_dir)
    rows_by_table, _ = _load_and_preflight_rows(seed_dir, manifest)
    await _preflight_challenge_collisions(db, rows_by_table.get("challenges", []))

    id_maps: dict[str, dict[object, object]] = {}
    results: dict[str, TableApplyResult] = {}
    for table in REFERENCE_TABLE_ORDER:
        if table not in rows_by_table:
            continue
        result, id_map = await _apply_table(
            db,
            table,
            rows_by_table[table],
            id_maps,
            manifest.batch_size,
        )
        results[table] = result
        id_maps[table] = id_map
    return SeedApplyResult(results)


async def _apply_table(
    db: ReferenceSeedDb,
    table: str,
    source_rows: list[dict[str, object]],
    id_maps: dict[str, dict[object, object]],
    batch_size: int,
) -> tuple[TableApplyResult, dict[object, object]]:
    if not source_rows:
        return TableApplyResult(), {}
    spec = TABLE_SEED_SPECS[table]
    remapped_rows = [_remap_foreign_keys(table, row, id_maps) for row in source_rows]
    all_columns = tuple(dict.fromkeys(column for row in remapped_rows for column in row))
    target_rows = await _fetch_target_rows(db, table, all_columns)
    existing_by_key = {_normalized_key(row, spec.key_fields): row for row in target_rows}
    update_fields = tuple(
        column
        for column in all_columns
        if column not in {"id", "created_at", *spec.key_fields, *spec.update_exclusions}
    )
    rows_to_write, result = _classify_rows(table, remapped_rows, existing_by_key, spec, update_fields)
    for start in range(0, len(rows_to_write), batch_size):
        await _write_rows(
            db,
            table,
            rows_to_write[start : start + batch_size],
            spec.key_fields,
            update_fields,
            spec.insert_if_missing,
        )
    refreshed = await _fetch_target_rows(db, table, ("id", *spec.key_fields))
    target_by_key = {_normalized_key(row, spec.key_fields): row["id"] for row in refreshed}
    id_map = {
        source["id"]: target_by_key[_normalized_key(remapped, spec.key_fields)]
        for source, remapped in zip(source_rows, remapped_rows, strict=True)
        if _normalized_key(remapped, spec.key_fields) in target_by_key
    }
    return result, id_map


def _classify_rows(
    table: str,
    rows: list[dict[str, object]],
    existing_by_key: dict[tuple[object, ...], dict[str, object]],
    spec: TableSeedSpec,
    update_fields: tuple[str, ...],
) -> tuple[list[dict[str, object]], TableApplyResult]:
    rows_to_write: list[dict[str, object]] = []
    created = updated = unchanged = skipped = 0
    for row in rows:
        existing = existing_by_key.get(_normalized_key(row, spec.key_fields))
        if existing is None and not spec.insert_if_missing:
            skipped += 1
            continue
        if existing is not None and all(existing.get(field) == row.get(field) for field in update_fields):
            unchanged += 1
            continue
        writable = {
            column: value
            for column, value in row.items()
            if (column != "id" or "id" in spec.key_fields) and column not in spec.update_exclusions
        }
        if existing is None:
            created += 1
            if table != "challenges":
                writable.pop("id", None)
        else:
            updated += 1
        rows_to_write.append(writable)
    return rows_to_write, TableApplyResult(created, updated, unchanged, skipped)
