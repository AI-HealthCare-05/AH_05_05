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
- Create `app/tests/custom_challenge_apis/test_custom_challenge_api.py`: own the isolated SQLite API and concurrency contract tests.
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

  Read `UserSettings` without `get_or_create`, falling back to the existing 08:00/13:00/19:00/22:00 defaults. For medication, require owned ACTIVE episodes with start date/start slot and scheduled non-PRN medication slots; do not add the AI-report-only `confirmed_at`/`confirmation_hash` constraint because valid manually scheduled episodes need not carry it. Union duplicate medication windows by episode/date/slot through the planner. For supplements, use registration IDs, include standard and manual ACTIVE registrations, and preserve registration identity for same-slot goals. Return only active mapped medication/supplement templates and eligible targets; never infer type from template name or check type.

- [ ] **Step 4: Write failing join/idempotency/concurrency tests**

  Assert medication cardinality is exactly one, supplement IDs are non-empty and unique, every source is owned/ACTIVE/eligible, zero-goal joins roll back, same key plus same logical request returns the original participation, same key plus any different template/type/target set returns an idempotency conflict, a different key cannot create a duplicate active medication target or exact supplement target set, and two concurrent different-key joins leave exactly one active participation.

- [ ] **Step 5: Verify join tests fail for missing behavior**

  Run the focused SQLite command and inspect that the failures are assertions against observable rows/responses rather than test setup errors.

- [ ] **Step 6: Implement transactional join**

  Canonicalize target IDs before entering the transaction. Recheck idempotency inside the transaction; follow the existing medication mutation order by locking `User`, requested source rows in ascending ID order, then locking/creating `UserSettings`, and finally locking participation rows. Revalidate eligibility and check active duplicates using a locking read. Create one participation, one target per source, and planner-produced occurrences atomically. Compare existing participation template/type/canonical source IDs before returning an idempotent retry. Translate the `(user,idempotency_key)` race after rollback by reloading and comparing the committed request. The SQLite concurrency test verifies service behavior with SQLite's no-op row locks plus the process-local guard; cross-process MySQL serialization still depends on the shared `User`/source row lock order and must not be claimed as proven by SQLite.

- [ ] **Step 7: Re-run focused tests and verify GREEN**

  Run the focused SQLite command and require that all recommendation, rollback, idempotency, ownership, and concurrent-join cases pass.

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

## Deferred Follow-up Interface

After this API slice is reviewed, a separate task may add `CustomChallengeScheduleReconciler.reconcile(*, user_id, source_kind, source_ids, changed_at, connection)`. It must reuse the same source-window normalization, preserve occurrences with `scheduled_at < changed_at`, and be invoked only inside schedule/settings/cancel/supplement mutation transactions. This plan intentionally adds no such hooks.

The stable normalization seam exported by `app/services/custom_challenges.py` is `custom_challenge_meal_times(settings)`, `medication_goal_windows(episode)`, and `supplement_goal_windows(registration)`. The caller must prefetch medication/slot or supplement/slot relations before invoking the latter two functions. These helpers return planner inputs only and perform no writes.
