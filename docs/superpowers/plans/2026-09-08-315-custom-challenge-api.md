# #315 Medication and Supplement Custom Challenge API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated medication and supplement custom-challenge recommendations, one-participation join, and read-only progress APIs over the approved three-table storage model.

**Architecture:** `Config` supplies the deployment-specific template-ID-to-enum mapping; a focused service owns source eligibility, transactional joins, idempotency, duplicate detection, and dose-derived read models. The existing pure goal planner remains the only calendar-boundary implementation. The existing `/api/v1/user` challenge router exposes DTOs without changing administrator APIs.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, Tortoise ORM, pytest/pytest-asyncio, in-memory SQLite under WSL.

**Spec:** `C:/dev/AH_05_05/.codex-work/315-erd-additions.dbml` (authoritative 21-column storage contract) and `C:/dev/AH_05_05/.codex-work/315-personalized-design-draft.md` (medication/supplement behavior only).

## Global Constraints

- Do not edit the backoffice `CustomChallengeTemplate` schema, service, routes, or UI.
- Do not edit historical migrations or run a live database migration.
- Do not implement VISIT completion, badges, final-result freezing, or read-time reconciliation.
- `MEDICATION` joins accept exactly one care-episode ID and one independent idempotency key; `SUPPLEMENT` joins accept one canonical non-empty set of registration IDs.
- Generate occurrences only when `joined_at <= scheduled_at < end_at`; `end_at` is midnight after seven Asia/Seoul calendar dates, and inclusive source end dates may shorten goals.
- Reads calculate completion only from existing `MedicationDose` and `SupplementDose` rows matching an occurrence; dose writes and undo APIs remain unchanged.
- Run backend checks only in WSL with an explicit in-memory SQLite test harness and `--noconftest`.

---

## File Structure

- Modify `app/models/enums.py`: host the immutable `CustomChallengeType` enum in the shared enum module.
- Modify `app/models/custom_challenges.py`: import/re-export the shared enum without changing storage fields.
- Modify `app/core/config.py`: add the deployment-provided template ID mapping with an empty default.
- Modify `.env.example`, `envs/example.local.env`, `envs/example.prod.env`: document JSON mapping syntax without hard-coded database IDs.
- Create `app/dtos/custom_challenges.py`: define camelCase request/response contracts and forbid unknown join fields.
- Create `app/services/custom_challenges.py`: implement eligibility, join, idempotency, active-duplicate protection, and dose-derived response projection.
- Modify `app/core/exceptions.py`: add stable `AppError` subclasses for unsupported/inactive templates, invalid targets, idempotency conflict, duplicate active participation, and missing owned participation.
- Modify `app/apis/v1/challenge_router.py`: add four authenticated routes beneath the existing `/user` router.
- Create `app/tests/custom_challenge_apis/test_custom_challenge_api.py`: own the isolated SQLite API, transaction, and lock-order contract tests. SQLite does not prove MySQL concurrency behavior.
- Do not modify `app/services/custom_challenge_goal_planner.py`, `app/models/custom_challenges.py` fields, migration 40, or their existing tests except the enum import-only adjustment above.

### Task 1: Configuration and API contracts

**Files:**
- Modify: `app/models/enums.py`
- Modify: `app/models/custom_challenges.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Modify: `envs/example.local.env`
- Modify: `envs/example.prod.env`
- Create: `app/dtos/custom_challenges.py`
- Modify: `app/core/exceptions.py`
- Test: `app/tests/custom_challenge_apis/test_custom_challenge_api.py`

**Interfaces:**
- Consumes: existing `CustomChallengeParticipation`, `CustomChallengeTarget`, `CustomChallengeOccurrence`, `ChallengeParticipationStatus`, and `CamelModel`.
- Produces: `Config.CUSTOM_CHALLENGE_TEMPLATE_TYPES: dict[int, CustomChallengeType]`; `CustomChallengeJoinRequest(target_ids: list[int], idempotency_key: str)`; recommendation and participation response DTOs; domain-specific `AppError` classes.

- [ ] **Step 1: Write failing configuration and validation tests**

  Add tests that instantiate `Config(_env_file=None)` and assert the mapping defaults to `{}`, parses JSON such as `{"41":"MEDICATION","42":"SUPPLEMENT"}` into positive integer keys and enum values, rejects duplicate enum assignments and non-positive IDs, and rejects an empty/duplicate `targetIds` join body.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run from WSL:

  ```bash
  cd /mnt/c/dev/AH_05_05/.codex-work/feature-315-custom
  uv run pytest --noconftest app/tests/custom_challenge_apis/test_custom_challenge_api.py -q
  ```

  Expected: collection/import failure because the custom challenge DTOs and config field do not exist.

- [ ] **Step 3: Implement the minimal configuration and DTO layer**

  Move the enum definition to `app.models.enums` and retain the import in `app.models.custom_challenges` so existing direct-module imports remain valid. Add the typed mapping field with `default_factory=dict` and a validator for positive IDs and one template per type. Define camelCase DTOs with literal `action="NONE"`, offset-aware datetimes, local dates, targets, occurrences, counts, and a two-decimal progress percentage.

- [ ] **Step 4: Add stable domain errors**

  Add `AppError` subclasses with distinct codes for template unavailable, unsupported VISIT type, invalid/ineligible target selection, idempotency-key reuse with a different request, already-active participation, and missing owned participation. Use 404 to hide unowned resources, 409 for idempotency/active conflicts, and 422 for invalid target cardinality or eligibility.

- [ ] **Step 5: Re-run focused tests and verify GREEN**

  Run the command from Step 2 and require zero failures before Task 2.

### Task 2: Recommendation and join service

**Files:**
- Create: `app/services/custom_challenges.py`
- Test: `app/tests/custom_challenge_apis/test_custom_challenge_api.py`

**Interfaces:**
- Consumes: `GoalWindow`, `PlannedGoal`, `plan_goals`, and `seven_day_end` from `app.services.custom_challenge_goal_planner`.
- Produces: `CustomChallengeService.recommendations(user)`, `CustomChallengeService.join(user, template_id, request)`, `CustomChallengeService.list(user)`, and `CustomChallengeService.get(user, participation_id)`.
- Future schedule work may consume source-window helpers from this service, but no reconciliation hook is added in this task.

- [ ] **Step 1: Write failing recommendation tests**

  Cover an empty config, inactive/unmapped templates, confirmed and scheduled ACTIVE care episodes, unowned/cancelled/unscheduled medication sources, ACTIVE standard and manual supplement registrations, inclusive source end dates, and sources with no future goal after the exact join timestamp. Assert that no GET creates settings, targets, occurrences, or participations.

- [ ] **Step 2: Verify recommendation tests fail for missing behavior**

  Run the focused SQLite command and confirm failures name the missing service/route behavior.

- [ ] **Step 3: Implement source window normalization and recommendations**

  Read `UserSettings` without `get_or_create`, falling back to the existing 08:00/13:00/19:00/22:00 defaults. For medication, require owned ACTIVE episodes with start date/start slot and scheduled non-PRN medication slots; do not add the AI-report-only `confirmed_at`/`confirmation_hash` constraint because valid manually scheduled episodes need not carry it. Union duplicate medication windows by episode/date/slot through the planner. For supplements, use registration IDs, include standard and manual ACTIVE registrations, and preserve registration identity for same-slot goals. Return only active mapped medication/supplement templates and eligible targets; never infer type from template name or check type. `existingParticipationId` is a per-target membership hint: select the most recently joined active participation of the same challenge type containing that source, independent of the currently mapped template. For overlapping supplement sets it does not predict whether a proposed set is a duplicate; only the exact canonical target-set rule in join does that.

- [ ] **Step 4: Write failing join/idempotency/lock-order tests**

  Assert medication cardinality is exactly one, supplement IDs are non-empty and unique, duplicate request IDs fail validation, every source is owned/ACTIVE/eligible, zero-goal joins roll back, same key plus same logical request returns the original participation, same key plus any different template/type/target set returns an idempotency conflict, and a different key cannot create a duplicate active medication target or exact supplement target set even after a server template mapping replacement. Add a supplement mutation regression proving every source-touching path enters the shared `User -> source -> settings` order; a new-source path enters `User -> settings -> insert` because no source row exists yet.

- [ ] **Step 5: Verify join tests fail for missing behavior**

  Run the focused SQLite command and inspect that the failures are assertions against observable rows/responses rather than test setup errors.

- [ ] **Step 6: Implement transactional join**

  Canonicalize target IDs before entering the transaction and reject duplicates instead of silently deduplicating them. Inside the transaction, lock `User` first, then check/lock an existing idempotency participation and return it when the stored request matches. Otherwise lock the template, requested source rows in ascending ID order, lock/create `UserSettings`, revalidate source eligibility, lock active participation rows for the duplicate check, and finally create participation/target/occurrence rows. Align existing supplement mutation paths to the same `User`-first serialization boundary before they touch source/settings rows. Compare active rows by challenge type plus canonical target set rather than by template ID, because template mappings are replaceable server configuration. Compare existing participation template, stored challenge type, and canonical source IDs before returning an idempotent retry. Translate the `(user,idempotency_key)` race after rollback by reloading and comparing the committed request. Do not add a process-local mutex: SQLite's no-op row locks can verify deterministic service behavior and lock-call order, but only the database constraints and shared production lock order provide cross-process MySQL serialization; this SQLite suite does not claim to prove MySQL concurrency.

- [ ] **Step 7: Re-run focused tests and verify GREEN**

  Run the focused SQLite command and require that all recommendation, rollback, idempotency, ownership, duplicate-active, and lock-order cases pass.

### Task 3: Read-only progress projection and authenticated routes

**Files:**
- Modify: `app/apis/v1/challenge_router.py`
- Modify: `app/services/custom_challenges.py`
- Test: `app/tests/custom_challenge_apis/test_custom_challenge_api.py`

**Interfaces:**
- Consumes: service methods from Task 2 and `get_request_user`.
- Produces: `GET /api/v1/user/custom-challenge-recommendations`; `POST /api/v1/user/custom-challenge-recommendations/{template_id}/participations`; `GET /api/v1/user/custom-challenge-participations`; `GET /api/v1/user/custom-challenge-participations/{participation_id}`.

- [ ] **Step 1: Write failing route and progress tests**

  Assert unauthenticated requests return 401; authenticated users cannot read another user's participation; list/detail return identical counts; unscheduled dose rows do not count; matching medication and supplement doses count once; existing dose deletion/undo reduces the next GET count; target count never changes on reads; actual end date equals the last occurrence date rather than the hard window; and repeated GETs do not mutate any custom challenge table.

- [ ] **Step 2: Verify route/progress tests fail**

  Run the focused SQLite command and confirm route 404/import failures or missing computed fields.

- [ ] **Step 3: Implement dose-derived response projection**

  Load owned participations, targets, and occurrences in deterministic order. Build medication completion keys from `(care_episode_id, dose_date, slot)` additionally filtered by participation user, and supplement keys from `(registration_id, dose_date, slot)` through an owned registration. Mark only exact occurrence keys complete, calculate counts and a clamped two-decimal rate, and calculate `actual_end_date` from the final occurrence. Do not write status, progress, occurrences, or awards during reads.

- [ ] **Step 4: Register the four authenticated endpoints**

  Extend the existing `challenge_router` only; use `Annotated[User, Depends(get_request_user)]`, positive path constraints, 201 for join, and the Task 1 response models. Leave `app/apis/v1/__init__.py` unchanged because this router is already included.

- [ ] **Step 5: Re-run focused tests and verify GREEN**

  Run the focused SQLite command and require zero failures.

### Task 4: Regression verification and commit

**Files:**
- Verify all files listed above.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: a reviewable backend-only feature commit and a stable service/window interface for later mutation-time reconciliation.

- [ ] **Step 1: Run static checks in WSL**

  ```bash
  cd /mnt/c/dev/AH_05_05/.codex-work/feature-315-custom
  uv run ruff check app/core/config.py app/core/exceptions.py app/dtos/custom_challenges.py app/apis/v1/challenge_router.py app/services/custom_challenges.py app/tests/custom_challenge_apis/test_custom_challenge_api.py
  uv run mypy app/core/config.py app/dtos/custom_challenges.py app/services/custom_challenges.py app/apis/v1/challenge_router.py
  ```

  Require exit code 0. If this repository does not expose a configured mypy command, report that exact tool failure and run the repository's configured type-check command instead; do not claim type-check success without output.

- [ ] **Step 2: Run isolated backend regression tests**

  ```bash
  uv run pytest --noconftest app/tests/custom_challenge_apis/test_custom_challenge_api.py app/tests/services/test_custom_challenge_goal_planner.py app/tests/models/test_custom_challenge_models.py -q
  ```

  Require zero failures and confirm the command uses SQLite rather than the repository MySQL fixture.

- [ ] **Step 3: Review the diff against exclusions**

  Confirm no frontend, administrator challenge code, dose writer, follow-up visit, badge, historical migration, or migration-model-state file changed. Confirm every GET path is free of create/update/delete calls.

- [ ] **Step 4: Commit the backend API slice**

  ```bash
  git add app/models/enums.py app/models/custom_challenges.py app/core/config.py app/core/exceptions.py app/dtos/custom_challenges.py app/services/custom_challenges.py app/apis/v1/challenge_router.py app/tests/custom_challenge_apis/test_custom_challenge_api.py .env.example envs/example.local.env envs/example.prod.env docs/superpowers/plans/2026-09-08-315-custom-challenge-api.md
  git commit -m "feature/315[신동훈]맞춤 챌린지 사용자 API 추가"
  ```

  Do not stage the pre-existing untracked storage or goal-planner plan files.

## Implemented Future-Reconciliation Interface

`app/services/custom_challenge_schedule_reconciler.py` now exports this transaction-boundary method:

```python
async def reconcile(
    *,
    user_id: int,
    source_kind: CustomChallengeType,
    source_ids: Collection[int] | None,
    changed_at: datetime,
    connection: BaseDBAsyncClient,
) -> None: ...
```

`source_ids=None` means every active target of `source_kind` owned by `user_id`; a collection selects only matching immutable source snapshots, and an empty collection is a no-op. `source_kind` must be an actual `CustomChallengeType.MEDICATION` or `CustomChallengeType.SUPPLEMENT` enum member; raw strings and `VISIT` are rejected. The caller must already be inside the source mutation transaction, hold the user's `User` row as the common first lock, hold any directly mutated source/settings rows, and capture one timezone-aware `changed_at` after those contested locks. The reconciler then locks active participations, targets, and occurrences, preserving every row with `scheduled_at < changed_at` and diffing only future rows.

The authoritative live source must still be attached through the target's nullable foreign key and its ID must equal `source_id_snapshot`. A null foreign key after source deletion produces an empty future window; reconciliation never looks up or reattaches a newly reused database ID from the snapshot alone. Missing, inactive, completed, cancelled, or cross-account sources likewise produce no future goals. Removing all remaining goals does not change participation status or create progress/badge rows.

The stable normalization seam exported by `app/services/custom_challenges.py` remains `custom_challenge_meal_times(settings)`, `medication_goal_windows(episode)`, and `supplement_goal_windows(registration)`. The caller must prefetch medication/slot or supplement/slot relations before invoking the latter two functions. These helpers return planner inputs only and perform no writes.

Medication schedule edits/cancellation, supplement upsert/update/completion, and global meal-time edits invoke reconciliation inside their mutation transaction. Recommendation/list/detail GETs remain read-only. Medication and supplement dose writers still perform no custom-challenge writes; their existing dose rows drive progress projection on subsequent reads. Visit completion, badges, and final-result freezing remain deferred.
