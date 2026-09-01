# Medication Safety v2 Approval and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `medication-safety-v2`의 유효한 5,190개 규칙을 검증 후 승인하고, 제외된 1,592행은 추정 없이 복원 가능 여부를 판정해 새 staging 세대로 발행한다.

**Architecture:** 승인 검사는 DB에 적재된 규칙·조건·출처를 규칙 단위로 검증하며 dry-run과 apply를 분리한다. 복원은 기존 staging parser에 결정론적 패턴만 추가하고 새 데이터셋 버전으로 재생성하며, 여전히 모호한 행은 품질 보고서에 남긴다.

**Tech Stack:** Python 3.13, Pydantic, Tortoise ORM, MySQL 8, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-01-reference-data-and-answer-fallback-observability-design.md`

## Global Constraints

- v1 규칙을 삭제하거나 상태 변경하지 않는다.
- v2 규칙은 검증 통과 건수가 `--expected-count`와 일치할 때만 한 트랜잭션으로 승인한다.
- 원본 단위·연령·기간을 임의로 추정하지 않는다.
- 복원 결과는 기존 v2 파일을 덮어쓰지 않는다.
- 승인·복원 결과는 SHA-256과 이유별 건수를 기록한다.

---

### Task 1: 안전 규칙 승인 검증 서비스

**Files:**
- Create: `ai_worker/services/medication_safety_approval_service.py`
- Create: `ai_worker/tests/services/test_medication_safety_approval_service.py`

**Interfaces:**
- Produces: `MedicationSafetyApprovalIssue`, `MedicationSafetyApprovalReport`, `validate_rule_for_approval(rule, conditions, sources)`

- [ ] **Step 1: Write failing invariant tests**

Create tests proving rejection for: malformed rule key, wrong dataset version, no source, missing numeric value, missing unit, `APPROVED` without `approved_at`. Add one valid daily-dose rule that passes.

```python
def test_numeric_condition_requires_value_and_unit() -> None:
    issue_codes = validate_rule_for_approval(
        build_rule(),
        [build_condition(value_min=Decimal("4000"), unit=None)],
        [build_source()],
        dataset_version="medication-safety-v2",
    )
    assert issue_codes == ["MISSING_CONDITION_UNIT"]
```

- [ ] **Step 2: Run and verify RED**

```bash
uv run --group ai --group app --group dev python -m pytest \
  ai_worker/tests/services/test_medication_safety_approval_service.py -q
```

Expected: FAIL because the approval service does not exist.

- [ ] **Step 3: Implement pure invariant validation**

The pure validator returns stable issue codes and never mutates ORM objects. Numeric kinds `AGE_DAYS`, `AGE_YEARS`, `DAILY_DOSE`, and `DURATION_DAYS` require a comparison value and unit. Text/presence conditions require `value_text`.

- [ ] **Step 4: Run tests and Ruff**

```bash
uv run --group dev ruff check ai_worker/services/medication_safety_approval_service.py ai_worker/tests/services/test_medication_safety_approval_service.py
uv run --group ai --group app --group dev python -m pytest ai_worker/tests/services/test_medication_safety_approval_service.py -q
```

- [ ] **Step 5: Commit Task 1**

```bash
git add ai_worker/services/medication_safety_approval_service.py ai_worker/tests/services/test_medication_safety_approval_service.py
git commit -m "[feature/199][임경수] 의약품 안전 규칙 승인 검증 추가"
```

### Task 2: dry-run 기본 승인 CLI와 감사 파일

**Files:**
- Create: `scripts/approve_medication_safety_rules.py`
- Create: `ai_worker/tests/scripts/test_approve_medication_safety_rules.py`
- Create: `app/tests/models/test_medication_safety_rule_approval.py`

**Interfaces:**
- Consumes: Task 1 validator
- Produces: `approve_dataset(dataset_version, reviewer, expected_count, apply, audit_path)`

- [ ] **Step 1: Write failing CLI and transaction tests**

Cover:

- no `--apply` means zero DB updates;
- expected count mismatch means zero DB updates;
- one invalid rule means zero DB updates;
- valid rules become `APPROVED` and receive the same `approved_at`;
- re-run reports `newly_approved_count=0`;
- audit JSON contains dataset version, reviewer, counts, issue counts, approved-key digest.

- [ ] **Step 2: Run and verify RED**

```bash
uv run --group ai --group app --group dev python -m pytest \
  ai_worker/tests/scripts/test_approve_medication_safety_rules.py \
  app/tests/models/test_medication_safety_rule_approval.py -q
```

Expected: FAIL because the CLI and approval transaction do not exist.

- [ ] **Step 3: Implement the CLI**

Use `prefetch_related("conditions", "sources")`, sort by `rule_key`, validate every rule, compare the valid count with `expected_count`, then update in one `in_transaction()` block only when `apply=True`. Write the audit file after the DB transaction succeeds; dry-run prints the same report but does not write an approval audit.

- [ ] **Step 4: Verify and commit**

```bash
uv run --group dev ruff check scripts/approve_medication_safety_rules.py ai_worker/tests/scripts/test_approve_medication_safety_rules.py app/tests/models/test_medication_safety_rule_approval.py
uv run --group ai --group app --group dev python -m pytest ai_worker/tests/scripts/test_approve_medication_safety_rules.py app/tests/models/test_medication_safety_rule_approval.py -q

git add scripts/approve_medication_safety_rules.py ai_worker/tests/scripts/test_approve_medication_safety_rules.py app/tests/models/test_medication_safety_rule_approval.py
git commit -m "[feature/199][임경수] 안전 규칙 v2 승인과 감사 기록 추가"
```

### Task 3: 개월 단위 연령 복원

**Files:**
- Modify: `ai_worker/services/medication_safety_staging_service.py`
- Modify: `ai_worker/tests/services/test_medication_safety_staging_service.py`

**Interfaces:**
- Produces: `_parse_age_condition()` support for `개월`

- [ ] **Step 1: Write failing month-boundary tests**

```python
@pytest.mark.parametrize(("source", "days", "operator"), [
    ("3개월미만", Decimal("90"), SafetyComparisonOperator.LT),
    ("6개월이상", Decimal("180"), SafetyComparisonOperator.GTE),
])
def test_parse_age_condition_converts_explicit_months_to_days(source, days, operator) -> None:
    condition = _parse_age_condition(source)
    assert condition.condition_kind == SafetyConditionKind.AGE_DAYS
    assert condition.value_min == days
    assert condition.unit == "day"
    assert condition.comparison_operator == operator
```

- [ ] **Step 2: Verify RED**

Run the two new tests. Expected: existing parser raises `UNSUPPORTED_AGE_MONTH_UNIT`.

- [ ] **Step 3: Implement exact integer month conversion**

Only integer month expressions matching the existing anchored age pattern are accepted. Convert one month to 30 days and preserve the unmodified source criterion in `raw_effect_text`; do not accept decimal months or free-form prose.

- [ ] **Step 4: Verify and commit**

```bash
uv run --group dev ruff check ai_worker/services/medication_safety_staging_service.py ai_worker/tests/services/test_medication_safety_staging_service.py
uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_medication_safety_staging_service.py -q

git add ai_worker/services/medication_safety_staging_service.py ai_worker/tests/services/test_medication_safety_staging_service.py
git commit -m "[feature/199][임경수] DUR 개월 연령 조건 복원"
```

### Task 4: 명시적 용량·기간 표현 복원과 격리 유지

**Files:**
- Modify: `ai_worker/services/medication_safety_staging_service.py`
- Modify: `ai_worker/tests/services/test_medication_safety_staging_service.py`

**Interfaces:**
- Produces: strict parsing helpers that return a condition or `_SkipRowError`

- [ ] **Step 1: Profile skipped examples into deterministic fixtures**

Create fixtures from the v2 quality report for all 46 ambiguous dose, 16 unsupported dose, one duration, and representative missing-unit rows. Do not alter production code in this step.

- [ ] **Step 2: Write failing tests only for unambiguous patterns**

For each accepted new pattern assert exact decimal value, normalized unit, operator, and source text. Add negative tests proving unitless rows and multi-interpretation expressions remain skipped.

- [ ] **Step 3: Verify RED**

Run only the new tests and confirm each fails with the existing skip reason.

- [ ] **Step 4: Implement anchored parsers**

Every accepted parser must use `fullmatch`, a closed unit map, and explicit operator mapping. No substring unit inference and no product-form-based unit inference are allowed.

- [ ] **Step 5: Generate a new staging version**

Use `medication-safety-v3` so v2 remains immutable. Compare input, accepted, candidate, duplicate, and every skipped reason with v2.

- [ ] **Step 6: Verify and commit**

```bash
uv run --group dev ruff check ai_worker/services/medication_safety_staging_service.py ai_worker/tests/services/test_medication_safety_staging_service.py
uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_medication_safety_staging_service.py -q

git add ai_worker/services/medication_safety_staging_service.py ai_worker/tests/services/test_medication_safety_staging_service.py
git commit -m "[feature/199][임경수] 의약품 안전자료 결정론적 복원 보완"
```

### Task 5: 로컬 v2 승인과 v3 복원 검증

**Files:**
- Generated, ignored staging/audit outputs only

- [ ] **Step 1: v2 approval dry-run**

```bash
uv run --group ai --group app python -m scripts.approve_medication_safety_rules \
  --dataset-version medication-safety-v2 \
  --reviewer feature-199-local \
  --expected-count 5190
```

Expected: valid 5,190, invalid 0, DB updates 0.

- [ ] **Step 2: Apply v2 approval**

Run the same command with `--apply`. Query DB and verify v2 `APPROVED=5190`, `PENDING=0`; v1 remains unchanged.

- [ ] **Step 3: Build v3 staging**

Run `scripts.build_medication_safety_staging` with the same seven source files and `--dataset-version medication-safety-v3`. Do not import or approve v3 during this task.

- [ ] **Step 4: Write the comparison summary**

Report v2/v3 accepted candidates and all skipped-reason deltas. Confirm every original input row is either a candidate source or a skipped row with an explicit reason.

