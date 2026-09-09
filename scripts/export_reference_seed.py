from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import io
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tortoise import Tortoise
from tortoise.transactions import in_transaction

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db.databases import TORTOISE_ORM  # noqa: E402
from app.core.db.reference_seed import (  # noqa: E402
    REFERENCE_TABLE_ORDER,
    SeedManifest,
    SeedTable,
    encode_seed_value,
)

SCHEMA_HEAD = "42_20260909180000_merge_challenge_schema_heads.py"


@dataclass(frozen=True)
class ExportSpec:
    columns: tuple[str, ...]
    key_fields: tuple[str, ...]
    joins: str = ""
    where: str = ""
    null_fields: tuple[str, ...] = ()


def _fields(value: str) -> tuple[str, ...]:
    return tuple(value.split())


NUTRIENT_STANDARD_COLUMNS = _fields(
    "id grp age carb_g_rni carb_g_ai carb_g_ul protein_g_rni protein_g_ai protein_g_ul "
    "fat_g_rni fat_g_ai fat_g_ul fiber_g_rni fiber_g_ai fiber_g_ul calcium_mg_rni "
    "calcium_mg_ai calcium_mg_ul iron_mg_rni iron_mg_ai iron_mg_ul phosphorus_mg_rni "
    "phosphorus_mg_ai phosphorus_mg_ul potassium_mg_rni potassium_mg_ai potassium_mg_ul "
    "sodium_mg_rni sodium_mg_ai sodium_mg_ul vitamin_a_ug_rae_rni vitamin_a_ug_rae_ai "
    "vitamin_a_ug_rae_ul thiamine_mg_rni thiamine_mg_ai thiamine_mg_ul riboflavin_mg_rni "
    "riboflavin_mg_ai riboflavin_mg_ul niacin_mg_rni niacin_mg_ai niacin_mg_ul "
    "vitamin_c_mg_rni vitamin_c_mg_ai vitamin_c_mg_ul vitamin_d_ug_rni vitamin_d_ug_ai "
    "vitamin_d_ug_ul"
)

EXPORT_SPECS: dict[str, ExportSpec] = {
    "medication_product_guides": ExportSpec(
        _fields(
            "id item_seq product_name manufacturer_name efficacy usage_instructions pre_use_warning precautions "
            "drug_food_interactions adverse_reactions storage_instructions created_at updated_at item_image_url"
        ),
        ("item_seq",),
    ),
    "supplement_nutrients": ExportSpec(
        _fields(
            "id food_code name basis_qty energy_kcal water_g protein_g fat_g ash_g carb_g sugar_g fiber_g "
            "calcium_mg iron_mg phosphorus_mg potassium_mg sodium_mg vitamin_a_ug_rae retinol_ug "
            "beta_carotene_ug thiamine_mg riboflavin_mg niacin_mg vitamin_c_mg vitamin_d_ug cholesterol_mg "
            "sat_fat_g trans_fat_g serving_desc serving_size daily_freq target"
        ),
        ("food_code",),
    ),
    "nutrient_standard": ExportSpec(NUTRIENT_STANDARD_COLUMNS, ("grp", "age")),
    "common_code_groups": ExportSpec(
        _fields(
            "id category group_code group_name description is_active created_at updated_at "
            "created_by_admin_id updated_by_admin_id"
        ),
        ("group_code",),
        where="t.`is_active` = 1",
        null_fields=("created_by_admin_id", "updated_by_admin_id"),
    ),
    "common_codes": ExportSpec(
        _fields(
            "id detail_code detail_name description sort_order is_active created_at updated_at "
            "created_by_admin_id group_id updated_by_admin_id"
        ),
        ("group_id", "detail_code"),
        joins="JOIN `common_code_groups` AS parent_group ON parent_group.`id` = t.`group_id`",
        where="t.`is_active` = 1 AND parent_group.`is_active` = 1",
        null_fields=("created_by_admin_id", "updated_by_admin_id"),
    ),
    "admin_settings": ExportSpec(
        _fields(
            "id setting_key smtp_host smtp_port smtp_user smtp_password_enc smtp_from_email created_at updated_at "
            "updated_by_admin_id"
        ),
        ("setting_key",),
        null_fields=("smtp_password_enc", "updated_by_admin_id"),
    ),
    "interaction_entities": ExportSpec(
        _fields("id entity_kind canonical_name normalized_name created_at updated_at"),
        ("entity_kind", "normalized_name"),
    ),
    "interaction_entity_aliases": ExportSpec(
        _fields("id alias_type alias normalized_alias is_preferred created_at interaction_entity_id"),
        ("interaction_entity_id", "normalized_alias"),
    ),
    "interaction_entity_identifiers": ExportSpec(
        _fields("id source_id source_code created_at interaction_entity_id"),
        ("source_id", "source_code"),
    ),
    "supplement_interaction_entities": ExportSpec(
        _fields("id amount unit source_field match_method created_at interaction_entity_id supplement_nutrient_id"),
        ("supplement_nutrient_id", "interaction_entity_id"),
    ),
    "interaction_rules": ExportSpec(
        _fields(
            "id pair_key pair_type risk_level review_status rule_dataset_version extraction_method approved_at "
            "created_at updated_at left_entity_id right_entity_id"
        ),
        ("pair_key", "rule_dataset_version"),
        where="t.`review_status` = 'APPROVED'",
    ),
    "interaction_rule_sources": ExportSpec(
        _fields(
            "id source_id document_id record_id raw_effect_text source_published_at source_url created_at "
            "interaction_rule_id"
        ),
        ("interaction_rule_id", "source_id", "document_id", "record_id"),
        joins="JOIN `interaction_rules` AS parent_rule ON parent_rule.`id` = t.`interaction_rule_id`",
        where="parent_rule.`review_status` = 'APPROVED'",
    ),
    "interaction_rule_evidence_chunks": ExportSpec(
        _fields("id dataset_key dataset_version vector_chunk_id created_at interaction_rule_source_id"),
        ("interaction_rule_source_id", "dataset_version", "vector_chunk_id"),
        joins=(
            "JOIN `interaction_rule_sources` AS parent_source "
            "ON parent_source.`id` = t.`interaction_rule_source_id` "
            "JOIN `interaction_rules` AS parent_rule ON parent_rule.`id` = parent_source.`interaction_rule_id`"
        ),
        where="parent_rule.`review_status` = 'APPROVED'",
    ),
    "medication_safety_rules": ExportSpec(
        _fields(
            "id rule_key rule_type risk_level guidance_text review_status rule_dataset_version extraction_method "
            "approved_at created_at updated_at interaction_entity_id"
        ),
        ("rule_key", "rule_dataset_version"),
        where="t.`review_status` = 'APPROVED'",
    ),
    "medication_safety_rule_conditions": ExportSpec(
        _fields(
            "id condition_group_no condition_order condition_kind comparison_operator value_min value_max value_text "
            "unit created_at medication_safety_rule_id"
        ),
        ("medication_safety_rule_id", "condition_group_no", "condition_order"),
        joins=("JOIN `medication_safety_rules` AS parent_rule ON parent_rule.`id` = t.`medication_safety_rule_id`"),
        where="parent_rule.`review_status` = 'APPROVED'",
    ),
    "medication_safety_rule_sources": ExportSpec(
        _fields(
            "id source_id document_id record_id raw_effect_text source_published_at source_url created_at "
            "medication_safety_rule_id"
        ),
        ("medication_safety_rule_id", "source_id", "document_id", "record_id"),
        joins=("JOIN `medication_safety_rules` AS parent_rule ON parent_rule.`id` = t.`medication_safety_rule_id`"),
        where="parent_rule.`review_status` = 'APPROVED'",
    ),
    "badges": ExportSpec(
        _fields(
            "id name description image_path is_active created_at updated_at created_by_admin_id "
            "updated_by_admin_id type"
        ),
        ("name",),
        joins=(
            "LEFT JOIN `common_codes` AS badge_type ON badge_type.`id` = t.`type` "
            "LEFT JOIN `common_code_groups` AS badge_group ON badge_group.`id` = badge_type.`group_id`"
        ),
        where=(
            "t.`is_active` = 1 AND (t.`type` IS NULL OR (badge_type.`is_active` = 1 AND badge_group.`is_active` = 1))"
        ),
        null_fields=("created_by_admin_id", "updated_by_admin_id"),
    ),
    "custom_challenge_templates": ExportSpec(
        _fields(
            "id name is_active check_type_id created_by_admin_id updated_by_admin_id created_at updated_at "
            "challenge_type reward_badge_id"
        ),
        ("name",),
        joins=(
            "JOIN `common_codes` AS check_code ON check_code.`id` = t.`check_type_id` "
            "JOIN `common_code_groups` AS check_group ON check_group.`id` = check_code.`group_id` "
            "LEFT JOIN `common_codes` AS challenge_code ON challenge_code.`id` = t.`challenge_type` "
            "LEFT JOIN `common_code_groups` AS challenge_group ON challenge_group.`id` = challenge_code.`group_id` "
            "LEFT JOIN `badges` AS reward_badge ON reward_badge.`id` = t.`reward_badge_id`"
        ),
        where=(
            "t.`is_active` = 1 "
            "AND check_code.`is_active` = 1 AND check_group.`is_active` = 1 "
            "AND (t.`challenge_type` IS NULL OR "
            "(challenge_code.`is_active` = 1 AND challenge_group.`is_active` = 1)) "
            "AND (t.`reward_badge_id` IS NULL OR reward_badge.`is_active` = 1)"
        ),
        null_fields=("created_by_admin_id", "updated_by_admin_id"),
    ),
    "challenges": ExportSpec(
        _fields(
            "id name phrase description recruit_start_at recruit_end_at is_displayed is_deleted deleted_at "
            "created_at updated_at challenge_period_id challenge_type_id check_frequency_id check_type_id "
            "created_by_admin_id reward_badge_id updated_by_admin_id"
        ),
        ("id",),
        joins=(
            "JOIN `common_codes` AS period_code ON period_code.`id` = t.`challenge_period_id` "
            "JOIN `common_codes` AS type_code ON type_code.`id` = t.`challenge_type_id` "
            "JOIN `common_codes` AS frequency_code ON frequency_code.`id` = t.`check_frequency_id` "
            "JOIN `common_codes` AS check_code ON check_code.`id` = t.`check_type_id` "
            "JOIN `common_code_groups` AS period_group ON period_group.`id` = period_code.`group_id` "
            "JOIN `common_code_groups` AS type_group ON type_group.`id` = type_code.`group_id` "
            "JOIN `common_code_groups` AS frequency_group ON frequency_group.`id` = frequency_code.`group_id` "
            "JOIN `common_code_groups` AS check_group ON check_group.`id` = check_code.`group_id` "
            "LEFT JOIN `badges` AS reward_badge ON reward_badge.`id` = t.`reward_badge_id`"
        ),
        where=(
            "t.`is_displayed` = 1 AND t.`is_deleted` = 0 "
            "AND period_code.`is_active` = 1 AND type_code.`is_active` = 1 "
            "AND frequency_code.`is_active` = 1 AND check_code.`is_active` = 1 "
            "AND period_group.`is_active` = 1 AND type_group.`is_active` = 1 "
            "AND frequency_group.`is_active` = 1 AND check_group.`is_active` = 1 "
            "AND (t.`reward_badge_id` IS NULL OR reward_badge.`is_active` = 1)"
        ),
        null_fields=("created_by_admin_id", "updated_by_admin_id"),
    ),
}


def _select_query(table: str, spec: ExportSpec) -> str:
    columns = ", ".join(f"t.`{column}`" for column in spec.columns)
    query = f"SELECT /* {table} */ {columns} FROM `{table}` AS t"
    if spec.joins:
        query += f" {spec.joins}"
    if spec.where:
        query += f" WHERE {spec.where}"
    order = ", ".join(f"t.`{column}`" for column in spec.key_fields)
    return f"{query} ORDER BY {order}"


def _count_query(table: str) -> str:
    return f"SELECT /* {table} */ COUNT(*) AS source_count FROM `{table}`"


def _encode(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return encode_seed_value(value)


def _write_gzip_rows(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text_stream:
                for row in rows:
                    text_stream.write(
                        json.dumps(_encode(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    )
                    text_stream.write("\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def export_reference_seed(
    db: Any,
    output_dir: Path,
    version: str,
    *,
    schema_head: str = SCHEMA_HEAD,
    batch_size: int = 500,
) -> SeedManifest:
    if batch_size <= 0:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    tables: list[SeedTable] = []
    for table in REFERENCE_TABLE_ORDER:
        spec = EXPORT_SPECS[table]
        rows = await db.execute_query_dict(_select_query(table, spec))
        source_count_rows = await db.execute_query_dict(_count_query(table))
        source_count = int(source_count_rows[0]["source_count"])
        for row in rows:
            for field in spec.null_fields:
                row[field] = None
        file_name = f"{table}.jsonl.gz"
        checksum = _write_gzip_rows(output_dir / file_name, rows)
        tables.append(
            SeedTable(
                name=table,
                file=file_name,
                row_count=len(rows),
                sha256=checksum,
                key_fields=spec.key_fields,
                excluded_rows=max(0, source_count - len(rows)),
            )
        )
    manifest = SeedManifest(version, schema_head, batch_size, tuple(tables))
    manifest_payload = {
        "version": manifest.version,
        "schema_head": manifest.schema_head,
        "batch_size": manifest.batch_size,
        "tables": [asdict(table) for table in manifest.tables],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="활성 기준정보를 Aerich 시드 파일로 내보냅니다.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> SeedManifest:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        async with in_transaction() as db:
            await db.execute_script("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ; SET TRANSACTION READ ONLY;")
            return await export_reference_seed(
                db,
                args.output,
                args.version,
                batch_size=args.batch_size,
            )
    finally:
        await Tortoise.close_connections()


def main() -> None:
    args = parse_args()
    manifest = asyncio.run(_run(args))
    for table in manifest.tables:
        print(f"{table.name}: included={table.row_count}, excluded={table.excluded_rows}")


if __name__ == "__main__":
    main()
