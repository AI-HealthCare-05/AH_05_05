# Reference Data Aerich Upsert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the active rows from 19 reference tables as deterministic compressed seed data and upsert them during `aerich upgrade` without exporting the SMTP password.

**Architecture:** A deterministic exporter writes one gzip-compressed JSONL file per table plus a checksum manifest. A migration-safe loader validates every artifact before writing, resolves foreign keys by logical keys, and performs bounded batch create/update operations through the Aerich transaction connection. Migration 43 invokes seed version `v1` and preserves migration 42's model snapshot because this is a data-only migration.

**Tech Stack:** Python 3.13, Tortoise ORM database clients, Aerich, MySQL 8, JSONL, gzip, SHA-256, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-09-reference-data-aerich-upsert-design.md`

## Global Constraints

- Source data is the current Docker MySQL database at export time.
- Export only active rows: `is_active = true`; challenges additionally require `is_displayed = true AND is_deleted = false`; rule tables require `review_status = 'APPROVED'`.
- Child rows are exported only when every required parent is included.
- Never export or update `admin_settings.smtp_password_enc`.
- Normalize all `created_by_admin_id` and `updated_by_admin_id` values to `NULL`.
- Existing rows absent from the seed are never deleted.
- Batch size is 500 rows.
- Existing migration files and seed version `v1` are immutable after release.
- Only tests directly related to exporter, loader, and migration 43 are run.

---

### Task 1: Define and validate the seed artifact contract

**Files:**
- Create: `app/core/db/reference_seed.py`
- Create: `app/tests/models/test_reference_seed_loader.py`

**Interfaces:**
- Produces: `SeedManifest.load(seed_dir: Path) -> SeedManifest`
- Produces: `encode_seed_value(value: object) -> object`
- Produces: `decode_seed_value(value: object) -> object`
- Produces: `iter_seed_rows(path: Path) -> Iterator[dict[str, object]]`
- Produces: `validate_seed_artifacts(seed_dir: Path) -> SeedManifest`

- [ ] **Step 1: Write failing artifact-validation tests**

Add tests that build temporary `manifest.json` and `.jsonl.gz` files and assert:

```python
def test_manifest_rejects_unknown_table(tmp_path: Path) -> None:
    write_manifest(tmp_path, tables=[{"name": "users", "row_count": 0, "sha256": empty_gzip_sha()}])
    with pytest.raises(ReferenceSeedError, match="허용되지 않은 테이블"):
        validate_seed_artifacts(tmp_path)


def test_manifest_rejects_checksum_mismatch(tmp_path: Path) -> None:
    write_seed_file(tmp_path, "badges", [{"name": "걷기 배지"}])
    write_manifest(tmp_path, tables=[{"name": "badges", "row_count": 1, "sha256": "0" * 64}])
    with pytest.raises(ReferenceSeedError, match="checksum"):
        validate_seed_artifacts(tmp_path)


def test_seed_codec_round_trips_decimal_datetime_date_and_null() -> None:
    values = [Decimal("1.250"), datetime(2026, 9, 9, 12, 30), date(2026, 9, 9), None]
    assert [decode_seed_value(encode_seed_value(value)) for value in values] == values
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
uv run pytest -q app/tests/models/test_reference_seed_loader.py
```

Expected: collection or import failure because `app.core.db.reference_seed` does not exist.

- [ ] **Step 3: Implement the manifest and codec**

Define an immutable manifest model with these required fields:

```python
@dataclass(frozen=True)
class SeedTable:
    name: str
    file: str
    row_count: int
    sha256: str
    key_fields: tuple[str, ...]


@dataclass(frozen=True)
class SeedManifest:
    version: str
    schema_head: str
    batch_size: int
    tables: tuple[SeedTable, ...]
```

Use explicit tagged JSON objects for non-JSON scalar types:

```python
{"$type": "decimal", "value": "1.250"}
{"$type": "datetime", "value": "2026-09-09T12:30:00"}
{"$type": "date", "value": "2026-09-09"}
```

Reject absolute paths, `..` path segments, duplicate table entries, unknown tables, negative row counts, invalid checksums, row-count mismatches, and malformed JSON objects. Read gzip streams line by line and calculate SHA-256 from the compressed file bytes before yielding any row.

- [ ] **Step 4: Run loader contract tests and Ruff**

```bash
uv run pytest -q app/tests/models/test_reference_seed_loader.py
uv run ruff format app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
uv run ruff check app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
```

Expected: all pass.

- [ ] **Step 5: Commit the artifact contract**

```bash
git add app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
git commit -m "feat: define reference seed artifact contract"
```

---

### Task 2: Export a deterministic active-data snapshot

**Files:**
- Create: `scripts/export_reference_seed.py`
- Create: `tests/scripts/test_export_reference_seed.py`

**Interfaces:**
- Consumes: `encode_seed_value` and the 19-table allowlist from Task 1
- Produces: `export_reference_seed(db: BaseDBAsyncClient, output_dir: Path, version: str) -> SeedManifest`
- Produces CLI: `uv run python scripts/export_reference_seed.py --output data/reference_seed/v1 --version v1`

- [ ] **Step 1: Write failing exporter filter tests**

Use a fake query client that returns active and inactive fixtures. Assert that the output:

```python
assert exported["common_code_groups"] == [active_group]
assert exported["common_codes"] == [active_code_in_active_group]
assert exported["badges"] == [active_badge]
assert exported["challenges"] == [displayed_not_deleted_challenge]
assert exported["custom_challenge_templates"] == [active_template]
assert exported["interaction_rules"] == [approved_interaction_rule]
assert exported["medication_safety_rules"] == [approved_safety_rule]
assert exported["admin_settings"][0]["smtp_password_enc"] is None
assert exported["admin_settings"][0]["updated_by_admin_id"] is None
```

Also assert children of excluded rules and rows referencing inactive code/badge parents are absent and counted in `manifest.json` under `excluded_rows`.

- [ ] **Step 2: Run the exporter tests and confirm RED**

```bash
uv run pytest -q tests/scripts/test_export_reference_seed.py
```

Expected: import failure because the exporter does not exist.

- [ ] **Step 3: Implement extraction queries and logical FK references**

Create one explicit select definition per table. Do not use `SELECT *`. Export FK references as nested logical keys, for example:

```json
{
  "pair_key": "DRUG:ASPIRIN|SUPPLEMENT:OMEGA3",
  "rule_dataset_version": "v1",
  "left_entity_ref": {"entity_kind": "DRUG", "normalized_name": "aspirin"},
  "right_entity_ref": {"entity_kind": "SUPPLEMENT", "normalized_name": "omega3"}
}
```

Use a repeatable-read, read-only transaction. Sort every table by its logical key. Write gzip with `gzip.GzipFile(filename="", mode="wb", mtime=0)` and UTF-8 JSON using `sort_keys=True` and compact separators. Write `manifest.json` only after every file and row count has been validated.

- [ ] **Step 4: Verify deterministic export and security rules**

Run the exporter twice against the same fake source and assert byte-identical files and manifests except `exported_at`, which must not participate in checksums. Search all generated fixture output for the source password token and assert it is absent.

- [ ] **Step 5: Run tests and Ruff**

```bash
uv run pytest -q tests/scripts/test_export_reference_seed.py app/tests/models/test_reference_seed_loader.py
uv run ruff format scripts/export_reference_seed.py tests/scripts/test_export_reference_seed.py
uv run ruff check scripts/export_reference_seed.py tests/scripts/test_export_reference_seed.py
```

Expected: all pass.

- [ ] **Step 6: Commit the exporter**

```bash
git add scripts/export_reference_seed.py tests/scripts/test_export_reference_seed.py
git commit -m "feat: export active reference seed data"
```

---

### Task 3: Implement dependency-aware batch upsert

**Files:**
- Modify: `app/core/db/reference_seed.py`
- Modify: `app/tests/models/test_reference_seed_loader.py`

**Interfaces:**
- Consumes: validated `SeedManifest` and JSONL row iterators from Task 1
- Produces: `apply_reference_seed(db: BaseDBAsyncClient, seed_dir: Path) -> SeedApplyResult`
- Produces: `SeedApplyResult.tables: dict[str, TableApplyResult]`

- [ ] **Step 1: Write failing upsert tests**

Create a disposable MySQL schema containing minimal versions of the 19 tables. Preinsert rows whose natural keys match the seed but whose PKs differ. Assert:

```python
first = await apply_reference_seed(db, seed_dir)
counts_after_first = await table_counts(db)
second = await apply_reference_seed(db, seed_dir)
assert await table_counts(db) == counts_after_first
assert second.total_created == 0
assert await scalar(db, "SELECT smtp_password_enc FROM admin_settings WHERE setting_key='SMTP'") == existing_secret
assert await scalar(db, "SELECT COUNT(*) FROM common_codes WHERE detail_code='INACTIVE'") == 0
```

Assert FK child rows point to the preexisting target DB parent IDs rather than source snapshot IDs. Add a challenge ID collision fixture with a different name and assert `ReferenceSeedConflictError` is raised before that row is updated.

- [ ] **Step 2: Run loader tests and confirm RED**

```bash
uv run pytest -q app/tests/models/test_reference_seed_loader.py -k upsert
```

Expected: failure because `apply_reference_seed` is not implemented.

- [ ] **Step 3: Implement table specifications**

Define `TableSeedSpec` entries with exact table name, writable columns, logical key fields, FK resolver functions, and update exclusions. Use this fixed dependency order:

```python
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
```

For each 500-row batch, query existing logical keys, split into create/update/unchanged groups, resolve parent IDs through cached logical-key maps, and use parameterized `execute_many`. Never interpolate seed values into SQL. For `nutrient_standard` and nullable source keys, normalize `None` to a sentinel only in Python key comparison, never in stored data.

- [ ] **Step 4: Add all-or-nothing preflight validation**

Before the first write, scan all files and verify checksums, row counts, required columns, duplicate logical keys, all logical FK references, and challenge ID fingerprints. Store no full-table row list; maintain only key sets and FK maps. Raise a table/key-specific error without including SMTP values or long medical text.

- [ ] **Step 5: Run loader tests twice and Ruff**

```bash
uv run pytest -q app/tests/models/test_reference_seed_loader.py
uv run pytest -q app/tests/models/test_reference_seed_loader.py
uv run ruff format app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
uv run ruff check app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
```

Expected: both runs pass with identical counts.

- [ ] **Step 6: Commit the loader**

```bash
git add app/core/db/reference_seed.py app/tests/models/test_reference_seed_loader.py
git commit -m "feat: upsert versioned reference seed data"
```

---

### Task 4: Export and review seed version v1

**Files:**
- Create: `data/reference_seed/v1/manifest.json`
- Create: `data/reference_seed/v1/*.jsonl.gz`

**Interfaces:**
- Consumes: exporter CLI from Task 2
- Produces: immutable seed version `v1`

- [ ] **Step 1: Export from the local Docker MySQL source**

```bash
uv run python scripts/export_reference_seed.py --output data/reference_seed/v1 --version v1
```

Expected: 19 gzip files plus `manifest.json`; output reports included and excluded counts without row contents.

- [ ] **Step 2: Validate the generated artifacts independently**

```bash
uv run python -c "from pathlib import Path; from app.core.db.reference_seed import validate_seed_artifacts; print(validate_seed_artifacts(Path('data/reference_seed/v1')))"
```

Expected: version `v1`, schema head `42_20260909180000_merge_challenge_schema_heads.py`, 19 validated tables.

- [ ] **Step 3: Review filters and secrets**

Check manifest counts against direct SQL counts for active rows. Decompress and search only for forbidden field names and known password ciphertext digest, without printing secrets. Confirm every child table count equals a join restricted to included parents.

- [ ] **Step 4: Commit immutable v1 artifacts**

```bash
git add data/reference_seed/v1
git commit -m "data: add active reference seed v1"
```

---

### Task 5: Add Aerich data migration 43

**Files:**
- Create: `app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py`
- Create: `app/tests/models/test_reference_seed_aerich.py`

**Interfaces:**
- Consumes: `apply_reference_seed(db, PROJECT_ROOT / 'data/reference_seed/v1')`
- Produces: Aerich head `43_20260909193000_upsert_reference_seed_v1.py`

- [ ] **Step 1: Write the failing migration contract test**

Assert the migration:

```python
async def test_reference_seed_migration_applies_v1_and_has_safe_downgrade() -> None:
    migration = import_module("app.core.db.migrations.models.43_20260909193000_upsert_reference_seed_v1")
    assert await migration.downgrade(None) == "SELECT 1;"
    assert decompress_dict(migration.MODELS_STATE) == decompress_dict(
        import_module("app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads").MODELS_STATE
    )
```

The MySQL test must apply migration 43 to a disposable database, assert manifest row counts, execute `apply_reference_seed` a second time, assert all counts are unchanged, and confirm Aerich has no remaining heads.

- [ ] **Step 2: Run the migration test and confirm RED**

```bash
uv run pytest -q app/tests/models/test_reference_seed_aerich.py
```

Expected: import failure because migration 43 does not exist.

- [ ] **Step 3: Implement migration 43**

Use a data-only migration:

```python
from importlib import import_module
from pathlib import Path

from app.core.db.reference_seed import apply_reference_seed

RUN_IN_TRANSACTION = True


async def upgrade(db):
    seed_dir = Path(__file__).resolve().parents[5] / "data" / "reference_seed" / "v1"
    await apply_reference_seed(db, seed_dir)
    return "SELECT 1;"


async def downgrade(db):
    return "SELECT 1;"


MODELS_STATE = import_module(
    "app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads"
).MODELS_STATE
```

- [ ] **Step 4: Run the real migration and idempotency tests**

```bash
uv run pytest -q app/tests/models/test_reference_seed_aerich.py app/tests/models/test_reference_seed_loader.py
```

Expected: all pass; second apply reports zero creates and unchanged table counts.

- [ ] **Step 5: Run formatting and static checks**

```bash
uv run ruff format app/core/db/reference_seed.py scripts/export_reference_seed.py app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py app/tests/models/test_reference_seed_loader.py app/tests/models/test_reference_seed_aerich.py tests/scripts/test_export_reference_seed.py
uv run ruff check app/core/db/reference_seed.py scripts/export_reference_seed.py app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py app/tests/models/test_reference_seed_loader.py app/tests/models/test_reference_seed_aerich.py tests/scripts/test_export_reference_seed.py
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit migration 43**

```bash
git add app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py app/tests/models/test_reference_seed_aerich.py
git commit -m "feat: upsert reference data during aerich upgrade"
```

---

### Task 6: End-to-end verification and handoff

**Files:**
- Modify only if a directly related verification reveals a defect.

**Interfaces:**
- Verifies all interfaces produced by Tasks 1–5.

- [ ] **Step 1: Verify a clean database upgrade**

Create a disposable MySQL database, apply the full Aerich chain through migration 43, and assert `aerich heads` is empty. Never point the test at the development database.

- [ ] **Step 2: Verify active-only content and FK integrity**

Run SQL assertions for inactive flags, non-approved rules, orphan rows, manifest counts, and `smtp_password_enc IS NULL` on newly inserted settings. Confirm existing encrypted SMTP passwords survive an upsert.

- [ ] **Step 3: Run the focused regression suite**

```bash
uv run pytest -q app/tests/models/test_reference_seed_loader.py app/tests/models/test_reference_seed_aerich.py tests/scripts/test_export_reference_seed.py tests/scripts/test_import_medication_product_guides.py tests/scripts/test_import_supplement_nutrients.py tests/scripts/test_import_nutrient_standards.py app/tests/models/test_medication_safety_staging_import.py
```

Expected: all pass.

- [ ] **Step 4: Run final quality checks**

```bash
uv run ruff format --check app/core/db/reference_seed.py scripts/export_reference_seed.py app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py app/tests/models/test_reference_seed_loader.py app/tests/models/test_reference_seed_aerich.py tests/scripts/test_export_reference_seed.py
uv run ruff check app/core/db/reference_seed.py scripts/export_reference_seed.py app/core/db/migrations/models/43_20260909193000_upsert_reference_seed_v1.py app/tests/models/test_reference_seed_loader.py app/tests/models/test_reference_seed_aerich.py tests/scripts/test_export_reference_seed.py
git diff --check
git status --short
```

Expected: no formatting, lint, or whitespace errors; only intended files remain changed.
