# Reference Nutrition Data Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한국인 영양소 섭취기준 CSV 24건과 건강기능식품 XLSX 5,556건을 동일한 검증 계약과 트랜잭션 검증을 거쳐 MySQL에 적재한다.

**Architecture:** 형식별 Reader는 원시 행만 반환하고 기존 `validate_rows()`가 Numbers와 XLSX를 동일하게 검증한다. 적재기는 원본 키를 upsert한 뒤 같은 트랜잭션에서 대상 키 존재 여부를 재검증하며, CLI는 dry-run과 실제 적용을 명시적으로 분리한다.

**Tech Stack:** Python 3.13, Tortoise ORM, MySQL 8, openpyxl, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-01-reference-data-and-answer-fallback-observability-design.md`

## Global Constraints

- 기존 `.numbers` 지원을 제거하지 않는다.
- XLSX는 `read_only=True`, `data_only=True`로 읽는다.
- 영양소 기준은 정확히 24개 원본 키를 검증한다.
- 건강기능식품은 정확히 5,556개 원본 `food_code`를 검증한다.
- 전체 테이블을 truncate하거나 원본에 없는 기존 행을 삭제하지 않는다.
- 기존 검색 개선 미커밋 파일 4개는 수정하거나 커밋하지 않는다.

---

### Task 1: 영양소 섭취기준 dry-run과 적재 후 키 검증

**Files:**
- Modify: `scripts/import_nutrient_standards.py`
- Modify: `tests/scripts/test_import_nutrient_standards.py`
- Create: `app/tests/med_apis/test_nutrient_standard_importer.py`

**Interfaces:**
- Consumes: `parse_csv(path: Path) -> list[dict[str, object]]`
- Produces: `verify_stored_records(records, connection) -> None`, `_run_import(path, dry_run) -> tuple[list[dict[str, object]], ImportResult | None]`

- [ ] **Step 1: Write the failing parser/CLI tests**

```python
def test_default_source_contains_exactly_24_unique_targets() -> None:
    records = parse_csv(DEFAULT_PATH)
    keys = {(record["grp"], record["age"]) for record in records}
    assert len(records) == 24
    assert len(keys) == 24


def test_parse_args_supports_dry_run() -> None:
    args = parse_args(["--dry-run"])
    assert args.dry_run is True
    assert args.path == DEFAULT_PATH
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
uv run --group app --group dev python -m pytest \
  tests/scripts/test_import_nutrient_standards.py -q
```

Expected: FAIL because `parse_args()` and `--dry-run` do not exist.

- [ ] **Step 3: Implement argument parsing and dry-run**

Add:

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2025 한국인 영양소 섭취기준 CSV를 MySQL에 적재합니다.")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)
```

`dry_run=True`이면 `parse_csv()`까지만 실행하고 DB 초기화·upsert를 호출하지 않는다.

- [ ] **Step 4: Write the failing transaction verification test**

```python
class TestNutrientStandardImport(TestCase):
    async def test_upsert_verifies_every_source_key(self) -> None:
        records = [build_standard("성인", "19-29세"), build_standard("성인", "30-49세")]
        result = await upsert_records(records)
        assert result.total == 2
        assert await NutrientStandard.filter(grp="성인").count() == 2
```

- [ ] **Step 5: Run the DB test and verify RED**

Run:

```bash
uv run --group app --group dev python -m pytest \
  app/tests/med_apis/test_nutrient_standard_importer.py -q
```

Expected: FAIL because the new integration test fixture/helper is absent and stored-key verification is not exposed.

- [ ] **Step 6: Implement stored-key verification inside the transaction**

After bulk create/update, query every `(grp, age)` source key using the same transaction. Raise `RuntimeError` when any key is missing. Return created/updated counts only after verification succeeds.

- [ ] **Step 7: Run targeted tests and Ruff**

```bash
uv run --group dev ruff check \
  scripts/import_nutrient_standards.py \
  tests/scripts/test_import_nutrient_standards.py \
  app/tests/med_apis/test_nutrient_standard_importer.py

uv run --group app --group dev python -m pytest \
  tests/scripts/test_import_nutrient_standards.py \
  app/tests/med_apis/test_nutrient_standard_importer.py -q
```

- [ ] **Step 8: Commit Task 1**

```bash
git add \
  scripts/import_nutrient_standards.py \
  tests/scripts/test_import_nutrient_standards.py \
  app/tests/med_apis/test_nutrient_standard_importer.py
git commit -m "[feature/199][임경수] 영양소 섭취기준 적재 검증 보완"
```

### Task 2: 건강기능식품 XLSX Reader 추가

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `scripts/import_supplement_nutrients.py`
- Modify: `tests/scripts/test_import_supplement_nutrients.py`

**Interfaces:**
- Consumes: `validate_headers()`, `validate_rows()`
- Produces: `read_numbers_rows(path)`, `read_xlsx_rows(path)`, `parse_workbook(path)`

- [ ] **Step 1: Add the approved XLSX dependency**

Run:

```bash
uv add --group app "openpyxl>=3.1.5,<4"
```

Confirm `pyproject.toml` and `uv.lock` contain `openpyxl`.

- [ ] **Step 2: Write a failing XLSX parity test**

```python
def test_parse_xlsx_uses_the_same_row_contract(tmp_path: Path) -> None:
    path = tmp_path / "supplements.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(EXPECTED_HEADERS)
    sheet.append(valid_row())
    workbook.save(path)

    records = parse_workbook(path)

    assert len(records) == 1
    assert records[0]["food_code"] == "F101-TEST-001"
    assert records[0]["iron_mg"] == Decimal("15.00")
```

- [ ] **Step 3: Run the XLSX test and verify RED**

```bash
uv run --group app --group dev python -m pytest \
  tests/scripts/test_import_supplement_nutrients.py::test_parse_xlsx_uses_the_same_row_contract -q
```

Expected: FAIL because `parse_workbook()` is not implemented.

- [ ] **Step 4: Implement format-specific readers**

Implement:

```python
def read_xlsx_rows(path: Path) -> list[list[object]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def parse_workbook(path: str | Path) -> list[dict[str, object]]:
    source = Path(path)
    if source.suffix.casefold() == ".numbers":
        rows = read_numbers_rows(source)
    elif source.suffix.casefold() == ".xlsx":
        rows = read_xlsx_rows(source)
    else:
        raise ImportValidationError(f"unsupported workbook type: {source.suffix}")
    header_index = find_header_index(rows)
    validate_headers(rows[header_index], row_number=header_index + 1)
    return validate_rows(rows[header_index + 1 :], first_row_number=header_index + 2)
```

Keep `parse_numbers()` as a compatibility wrapper around `parse_workbook()`.

- [ ] **Step 5: Add corruption tests**

Cover wrong header, duplicate `food_code`, blank workbook, unsupported suffix, and a decimal overflow. Each test must assert the source row and column in the exception.

- [ ] **Step 6: Run tests and Ruff**

```bash
uv run --group dev ruff check \
  scripts/import_supplement_nutrients.py \
  tests/scripts/test_import_supplement_nutrients.py

uv run --group app --group dev python -m pytest \
  tests/scripts/test_import_supplement_nutrients.py -q
```

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  pyproject.toml uv.lock \
  scripts/import_supplement_nutrients.py \
  tests/scripts/test_import_supplement_nutrients.py
git commit -m "[feature/199][임경수] 건강기능식품 XLSX 적재 지원"
```

### Task 3: 건강기능식품 upsert 후 원본 키 검증

**Files:**
- Modify: `scripts/import_supplement_nutrients.py`
- Modify: `app/tests/med_apis/test_supplement_importer.py`

**Interfaces:**
- Consumes: `parse_workbook(path)`
- Produces: `verify_stored_food_codes(records, connection) -> None`, CLI `--dry-run`, `--expected-count`

- [ ] **Step 1: Write failing expected-count and DB-key tests**

```python
def test_validate_expected_count_rejects_partial_workbook() -> None:
    with pytest.raises(ImportValidationError, match="expected 5556"):
        validate_expected_count([{"food_code": "F1"}], expected_count=5556)


class TestSupplementNutrientUpsert(TestCase):
    async def test_upsert_verifies_all_source_food_codes(self) -> None:
        records = validate_rows([valid_row("F1"), valid_row("F2")], first_row_number=2)
        result = await upsert_records(records, batch_size=1)
        assert result.total == 2
```

- [ ] **Step 2: Verify RED**

```bash
uv run --group app --group dev python -m pytest \
  tests/scripts/test_import_supplement_nutrients.py \
  app/tests/med_apis/test_supplement_importer.py -q
```

Expected: FAIL because expected-count and post-upsert key validation are absent.

- [ ] **Step 3: Implement expected-count and transaction verification**

Add CLI options `--dry-run` and `--expected-count` with default `None`. For the production XLSX command pass `--expected-count 5556`. Verify all source `food_code` values exist before the transaction exits.

- [ ] **Step 4: Verify GREEN and commit**

```bash
uv run --group dev ruff check scripts/import_supplement_nutrients.py tests/scripts/test_import_supplement_nutrients.py app/tests/med_apis/test_supplement_importer.py
uv run --group app --group dev python -m pytest tests/scripts/test_import_supplement_nutrients.py app/tests/med_apis/test_supplement_importer.py -q

git add scripts/import_supplement_nutrients.py tests/scripts/test_import_supplement_nutrients.py app/tests/med_apis/test_supplement_importer.py
git commit -m "[feature/199][임경수] 건강기능식품 적재 건수 검증 추가"
```

### Task 4: 로컬 MySQL 적재 및 증거 수집

**Files:**
- No production code changes

**Interfaces:**
- Consumes: the import CLIs from Tasks 1–3
- Produces: verified local DB counts

- [ ] **Step 1: Dry-run both sources**

```bash
uv run --group app python -m scripts.import_nutrient_standards --dry-run

uv run --group app python -m scripts.import_supplement_nutrients \
  "data/knowledge/raw/public/mfds/supplement_products/건강기능식품DB_20260623_5556건.xlsx" \
  --expected-count 5556 \
  --dry-run
```

Expected: 24 and 5,556 validated records, DB write count zero.

- [ ] **Step 2: Apply both imports**

```bash
uv run --group app python -m scripts.import_nutrient_standards

uv run --group app python -m scripts.import_supplement_nutrients \
  "data/knowledge/raw/public/mfds/supplement_products/건강기능식품DB_20260623_5556건.xlsx" \
  --expected-count 5556
```

- [ ] **Step 3: Re-run to prove idempotency**

Run the same two apply commands again. Expected: `created=0`, all source records reported as updated or unchanged according to the importer contract.

- [ ] **Step 4: Query DB counts**

Verify `nutrient_standard=24` and all 5,556 source `food_code` values exist in `supplement_nutrients`.

