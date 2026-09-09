"""Versioned reference-data seed artifact validation and application."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

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
