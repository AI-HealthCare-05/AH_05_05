# #315 Mutation-Time Future Goal Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile only future medication and supplement custom-challenge occurrences inside the transaction that changes their source schedule, while preserving all past goals and existing dose-driven progress.

**Architecture:** Add one schedule-only reconciler whose public boundary is `reconcile(*, user_id, source_kind, source_ids, changed_at, connection)`. Existing mutation services keep the shared `User`-first database serialization boundary, capture one `changed_at` only after their source/settings locks are held, persist the authoritative source change, then invoke the reconciler in the same transaction. The reconciler reloads post-mutation source rows through the existing window helpers, preserves every occurrence earlier than `changed_at`, and diffs only the future rows by `(target, scheduled_date, slot)`.

**Tech Stack:** Python 3.13, FastAPI service layer, Tortoise ORM transactions, pytest/pytest-asyncio, explicit in-memory SQLite under WSL.

**Spec:** `C:/dev/AH_05_05/.codex-work/315-personalized-design-draft.md` sections 3-6, with the later reviewed `User`-first lock order in `C:/dev/AH_05_05/.codex-work/315-api-review.md` and `C:/dev/AH_05_05/.codex-work/315-api-rereview.md` superseding the draft's stale settings-first paragraph.

## Global Constraints

- Reconciliation is eager at mutation time. GET recommendation/list/detail methods remain read-only and perform no reconciliation writes.
- `changed_at` is one timezone-aware KST instant captured after the mutation path holds its `User`, source, and settings locks; do not recalculate it per target.
- Preserve every existing occurrence with `scheduled_at < changed_at` byte-for-byte. Diff only occurrences with `scheduled_at >= changed_at`.
- A past key that a changed meal time would move into the future stays represented only by its original past occurrence; pass past `GoalKey` values as `preserved_keys` so no duplicate future row is created.
- Keep the participation hard boundary `joined_at <= scheduled_at < end_at` and each source's inclusive final calendar date through `plan_goals`.
- Medication source identity is `CareEpisode`; supplement source identity is `UserSupplementNutrient`. Reuse `custom_challenge_meal_times`, `medication_goal_windows`, and `supplement_goal_windows` from `app/services/custom_challenges.py` after prefetching their required relations.
- Every query is scoped by `participation.user_id == user_id`; source reloads additionally require `source.user_id == user_id`. Never accept ownership from request data.
- Lock order is `User` first. Existing-source schedule mutations then lock source, settings, active participation, target, and future occurrence rows. An idempotency participation lock in join may occur immediately after `User`; the common `User` lock prevents a cycle.
- Global meal-time changes reconcile all active medication and supplement targets for that user, including targets unrelated to the medication episode whose schedule form saved the times.
- A source with zero remaining planned goals loses only its future occurrences. Do not complete the participation, change status, create official challenge progress, or award/revoke a badge.
- Do not change API routes, DTO response shapes, frontend code, admin challenge behavior, dose save/undo services, visit challenges, badges, migrations, or migration model state.
- Run backend checks only in WSL with `/mnt/c/dev/AH_05_05/.venv/bin/python`, explicit in-memory SQLite, and `--noconftest`. Do not run the repository root MySQL fixture.

---

## File Structure

- Create `app/services/custom_challenge_schedule_reconciler.py`: own active-target selection, authoritative source-window reload, and future occurrence diffing.
- Create `app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py`: own an explicit-memory database fixture plus reconciler and mutation-hook regressions.
- Modify `app/services/medication_schedule.py`: hook episode schedule changes and global meal-time changes.
- Modify `app/services/medications.py`: make cancellation transactional and reconcile the cancelled episode.
- Modify `app/services/user_supplement_nutrients.py`: hook upsert/update/complete for one registration.
- Modify `app/services/settings.py`: add the shared `User` lock and reconcile every user target when any meal time changes.
- Modify `docs/superpowers/plans/2026-09-08-315-custom-challenge-api.md`: replace the deferred-interface paragraph with the implemented seam after all tests pass.

### Task 1: Future-only occurrence diff service

**Files:**
- Create: `app/services/custom_challenge_schedule_reconciler.py`
- Create: `app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py`

**Interfaces:**
- Consumes: `plan_goals`, `GoalKey`, and `PlannedGoal` from `app.services.custom_challenge_goal_planner`; `custom_challenge_meal_times`, `medication_goal_windows`, and `supplement_goal_windows` from `app.services.custom_challenges`.
- Produces:

```python
class CustomChallengeScheduleReconciler:
    async def reconcile(
        self,
        *,
        user_id: int,
        source_kind: CustomChallengeType,
        source_ids: Collection[int] | None,
        changed_at: datetime,
        connection: BaseDBAsyncClient,
    ) -> None: ...
```

`source_ids=None` means all active targets of `source_kind` owned by `user_id`; a collection means only those source snapshots after canonicalizing to a sorted unique tuple. An empty collection is a no-op. Only `MEDICATION` and `SUPPLEMENT` are accepted; `VISIT` raises `ValueError` because visit policy remains outside this slice.

The caller must already be inside the source mutation transaction and hold that user's `User` row plus any directly mutated source/settings rows. The reconciler does not open a transaction or reacquire `User`; it continues the shared order with participation, target, and occurrence locks.

- [ ] **Step 1: Add the explicit-memory fixture and failing future-diff tests**

  Initialize Tortoise exactly as the existing custom-challenge API suite does:

```python
@pytest_asyncio.fixture(autouse=True)
async def initialized_db() -> None:
    sqlite3.register_adapter(time, lambda value: value.isoformat())
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
```

  Add these real-database tests with fixed aware KST instants. Direct reconciler calls must occur inside `in_transaction()` after the test locks the user's `User`, affected source, and settings rows, matching the production precondition:

  - `test_reconcile_updates_inserts_and_deletes_only_future_occurrences`: join a medication participation, retain one past row, mutate the authoritative episode slots/windows, call `reconcile` inside a transaction, and assert a surviving future key keeps its occurrence ID with a new `scheduled_at`, removed future keys disappear, new future keys appear, and the past row is unchanged.
  - `test_reconcile_does_not_recreate_past_key_moved_after_changed_at`: create today's 08:00 occurrence, set `changed_at` to 09:00, move that slot's meal time to 10:00, and assert the original 08:00 row remains the only row for that `(target, date, slot)`.
  - `test_reconcile_is_owner_scoped_and_zero_future_does_not_complete_or_award`: include another user's target, complete/end the selected user's source, reconcile only the selected user, and assert only that user's future rows are removed while both participation statuses remain unchanged and `UserBadge`/official `ChallengeProgress` counts do not increase.

- [ ] **Step 2: Run the three tests and verify RED**

  Run:

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  -k "updates_inserts or moved_after or owner_scoped" -q
```

  Expected: collection/import failure for missing `CustomChallengeScheduleReconciler`, not a fixture or schema error.

- [ ] **Step 3: Implement active target and authoritative source loading**

  In `custom_challenge_schedule_reconciler.py`, validate the boundary and load rows on the supplied transaction:

```python
class CustomChallengeScheduleReconciler:
    async def reconcile(self, *, user_id, source_kind, source_ids, changed_at, connection) -> None:
        if source_kind not in {CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT}:
            raise ValueError("only medication and supplement schedules can be reconciled")
        selected_ids = None if source_ids is None else tuple(sorted(set(source_ids)))
        if selected_ids == ():
            return

        participations = await (
            CustomChallengeParticipation.filter(
                user_id=user_id,
                challenge_type=source_kind,
                status=ChallengeParticipationStatus.ACTIVE,
            )
            .using_db(connection)
            .select_for_update()
            .order_by("id")
        )
        participation_ids = [participation.id for participation in participations]
        targets_query = CustomChallengeTarget.filter(participation_id__in=participation_ids)
        if selected_ids is not None:
            targets_query = targets_query.filter(source_id_snapshot__in=selected_ids)
        targets = await (
            targets_query.using_db(connection)
            .select_for_update()
            .prefetch_related("participation")
            .order_by("participation_id", "id")
        )
```

  Batch-load only owned ACTIVE sources from the same connection. Use `prefetch_related("medications__slots")` for care episodes and `prefetch_related("slots")` for supplement registrations. Missing, deleted, cancelled, completed, or cross-account sources map to an empty window list; never load them by snapshot ID without the user filter. Read `UserSettings` on the supplied connection and pass it through `custom_challenge_meal_times` without creating settings.

- [ ] **Step 4: Implement the per-target future diff**

  Normalize database datetimes to KST before comparison. For each locked target, lock all its occurrences in deterministic ID order and split them once:

```python
past = [row for row in occurrences if aware(row.scheduled_at) < changed_at]
future = [row for row in occurrences if aware(row.scheduled_at) >= changed_at]
preserved_keys: set[GoalKey] = {
    (target.source_id_snapshot, row.scheduled_date, row.slot) for row in past
}
desired = plan_goals(
    windows=windows_by_source.get(target.source_id_snapshot, []),
    meal_times=meal_times,
    joined_at=aware(target.participation.joined_at),
    end_at=aware(target.participation.end_at),
    not_before=changed_at,
    preserved_keys=preserved_keys,
)
```

  Diff by `(scheduled_date, slot)`: update only `scheduled_at` for keys present in both sets whose time changed, delete future row IDs absent from the desired set, and bulk-create desired keys absent from future rows. Never save or delete an item from `past`; never touch participation status, targets, doses, challenge progress, or badges.

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  -k "updates_inserts or moved_after or owner_scoped" -q
```

  Expected: all selected tests pass with no warnings or writes outside the in-memory database.

- [ ] **Step 6: Commit the independently reviewable reconciler**

```bash
git add app/services/custom_challenge_schedule_reconciler.py app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py
git commit -m "feature/315[신동훈]맞춤 챌린지 미래 목표 재계산 추가"
```

### Task 2: Medication schedule and cancellation hooks

**Files:**
- Modify: `app/services/medication_schedule.py`
- Modify: `app/services/medications.py`
- Modify: `app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py`

**Interfaces:**
- Consumes: `CustomChallengeScheduleReconciler.reconcile(...)` from Task 1.
- Produces: unchanged public signatures `MedicationScheduleService.save(user, record_id, request)` and `MedicationService.cancel(user, record_id)`; both commit source changes and future-goal diffs atomically.

- [ ] **Step 1: Write failing medication mutation tests**

  Add:

  - `test_medication_schedule_save_reconciles_changed_episode_when_meal_times_unchanged`: join two episode participations, change slots on one through the real `MedicationScheduleService.save`, and assert only that episode's future keys change.
  - `test_medication_schedule_global_time_change_reconciles_all_user_medication_and_supplement_targets`: join two medication episodes and one supplement registration for one user plus equivalent targets for another user; save one episode with a changed meal time and assert every future occurrence for the saving user uses the new time while the other user's rows stay unchanged.
  - `test_medication_schedule_uses_one_changed_at_after_locks`: inject a fixed `mutation_time_provider`, put one occurrence just before and another at the boundary, save the schedule, and assert the former is unchanged while the latter is eligible for diffing. Assert every reconciled participation uses that same boundary outcome.
  - `test_medication_schedule_and_cancel_reject_unowned_episode_without_occurrence_writes`: invoke both mutations as another user and assert their existing 404/403 contracts plus unchanged source and occurrence rows.
  - `test_medication_cancel_removes_only_future_goals`: cancel an owned episode through `MedicationService.cancel`, assert past goals remain and future goals disappear, and assert the custom participation remains ACTIVE with no `UserBadge` created.

- [ ] **Step 2: Run the five medication tests and verify RED**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  -k "medication_schedule or medication_cancel" -q
```

  Expected: persisted source schedules change but future occurrence assertions fail; cancellation leaves future occurrences.

- [ ] **Step 3: Hook `MedicationScheduleService.save`**

  Add optional constructor dependencies without changing route/API callers:

```python
def __init__(
    self,
    reconciler: CustomChallengeScheduleReconciler | None = None,
    mutation_time_provider: Callable[[], datetime] | None = None,
) -> None:
    self._reconciler = reconciler or CustomChallengeScheduleReconciler()
    self._mutation_time_provider = mutation_time_provider or (lambda: datetime.now(config.TIMEZONE))
```

  Preserve `User -> CareEpisode -> UserSettings` ordering. Replace transactional `UserSettings.get_or_create` with `select_for_update().first()` plus same-transaction creation. After all three locks and request ownership/cardinality validation, compute `previous_meal_times = custom_challenge_meal_times(settings)` and capture `changed_at = self._mutation_time_provider()` once. Persist settings, episode, and medication slots and sync alarms as today. Then:

```python
if previous_meal_times != meal_times:
    for source_kind in (CustomChallengeType.MEDICATION, CustomChallengeType.SUPPLEMENT):
        await self._reconciler.reconcile(
            user_id=user.id,
            source_kind=source_kind,
            source_ids=None,
            changed_at=changed_at,
            connection=connection,
        )
else:
    await self._reconciler.reconcile(
        user_id=user.id,
        source_kind=CustomChallengeType.MEDICATION,
        source_ids=(episode.id,),
        changed_at=changed_at,
        connection=connection,
    )
```

- [ ] **Step 4: Make `MedicationService.cancel` atomic and owner-safe**

  Add the same optional reconciler/time-provider constructor. Replace the current read-then-save with one transaction: lock `User`, lock `CareEpisode` by ID, preserve the existing not-found versus foreign-owner error behavior, lock/read `UserSettings` without creating it, then capture `changed_at`. If already cancelled, return. Otherwise save CANCELLED and call `reconcile` for `(episode.id,)` before commit. Do not modify `save_dose` or add challenge writes there.

- [ ] **Step 5: Run medication tests plus existing #315 suite**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  app/tests/custom_challenge_apis/test_custom_challenge_api.py \
  app/tests/services/test_custom_challenge_goal_planner.py -q
```

  Expected: all tests pass. SQLite verifies results and deterministic service call behavior only; do not describe it as MySQL deadlock proof.

- [ ] **Step 6: Commit medication hooks**

```bash
git add app/services/medication_schedule.py app/services/medications.py app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py
git commit -m "feature/315[신동훈]복약 일정 변경 미래 목표 연동"
```

### Task 3: Supplement and global settings hooks

**Files:**
- Modify: `app/services/user_supplement_nutrients.py`
- Modify: `app/services/settings.py`
- Modify: `app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py`

**Interfaces:**
- Consumes: `CustomChallengeScheduleReconciler.reconcile(...)` from Task 1.
- Produces: unchanged public supplement and settings method signatures; schedule changes and their future occurrence diffs share one transaction.

- [ ] **Step 1: Write failing supplement/settings mutation tests**

  Add:

  - `test_supplement_update_reconciles_only_selected_registration`: join a multi-registration participation, change one registration's dates/slots through real `update`, and assert its future keys change while sibling and other-user targets do not.
  - `test_supplement_upsert_reconciles_existing_registration`: join a standard registration, upsert new dates/slots for the same product, assert the registration ID is reused and future goals reflect the post-lock persisted rows.
  - `test_supplement_complete_with_no_remaining_goals_preserves_history_without_award`: complete a joined registration, assert past rows remain, future rows are removed, participation stays ACTIVE, and no official progress/badge row appears.
  - `test_supplement_update_rejects_foreign_registration_without_occurrence_writes`: preserve the existing 404 ownership behavior and verify neither owner's goals change.
  - `test_notify_meal_time_change_reconciles_all_user_medication_and_supplement_targets`: PATCH behavior through real `NotifySettingsService.update` with multiple source types and assert all and only that user's future timestamps change.
  - `test_notify_toggle_only_update_does_not_change_occurrences`: update notification consent/toggles without time fields and assert occurrence IDs/timestamps are identical.

- [ ] **Step 2: Run the six tests and verify RED**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  -k "supplement or notify" -q
```

  Expected: source/settings writes succeed but future occurrences remain on their old schedule.

- [ ] **Step 3: Hook supplement upsert/update/complete after existing locks**

  Extend `UserSupplementNutrientService.__init__` with optional `reconciler` and `mutation_time_provider` while retaining the optional repository argument. In `_write_upsert`, `update`, and `complete`, capture `changed_at` only after the existing `User -> registration -> settings` locks. Persist the source and slots, sync alarms, then call:

```python
await self._reconciler.reconcile(
    user_id=user_id,
    source_kind=CustomChallengeType.SUPPLEMENT,
    source_ids=(registration.id,),
    changed_at=changed_at,
    connection=connection,
)
```

  For `update` use `user.id`; for `complete` call the same reconciliation even when the row was already COMPLETED so an earlier interrupted/legacy state can converge without changing participation status. `create_manual` creates a brand-new source ID that cannot already be a target, so it receives no challenge hook. Keep its existing lock order and alarm behavior unchanged.

- [ ] **Step 4: Put `NotifySettingsService.update` behind the shared User lock**

  Add optional reconciler/time-provider constructor arguments. At transaction entry lock `User` before `UserSettings`, preserving same-transaction settings creation. Capture `changed_at` after the settings lock. Keep existing field merge, ordering validation, consent write, and alarm/follow-up-visit alarm behavior. Only when `time_update_fields` is non-empty, invoke `reconcile` once for MEDICATION/all sources and once for SUPPLEMENT/all sources using the same `changed_at`. Toggle-only requests must not query or write custom-challenge occurrences.

- [ ] **Step 5: Run Task 3 and all reconciliation tests**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py -q
```

  Expected: all reconciler, medication, supplement, ownership, boundary, and settings tests pass.

- [ ] **Step 6: Commit supplement/settings hooks**

```bash
git add app/services/user_supplement_nutrients.py app/services/settings.py app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py
git commit -m "feature/315[신동훈]영양제와 알림 시간 미래 목표 연동"
```

### Task 4: Contract documentation and final verification

**Files:**
- Modify: `docs/superpowers/plans/2026-09-08-315-custom-challenge-api.md`
- Verify only: all production and test files from Tasks 1-3

**Interfaces:**
- Consumes: completed mutation-time reconciler and hooks.
- Produces: one reviewed backend schedule-reconciliation slice with no API/schema/frontend changes.

- [ ] **Step 1: Replace the old deferred-interface note**

  Document the exact `CustomChallengeScheduleReconciler.reconcile` signature, `None == all owned active targets of that type`, the caller-held `User`-first lock precondition, post-lock single `changed_at`, and the three exported source-window helpers. State explicitly that GETs and dose writers still do no custom-challenge writes.

- [ ] **Step 2: Run focused static checks in WSL**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m ruff check \
  app/services/custom_challenge_schedule_reconciler.py \
  app/services/medication_schedule.py app/services/medications.py \
  app/services/user_supplement_nutrients.py app/services/settings.py \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py

MYPY_CACHE_DIR=/tmp/feature315-reconcile-mypy \
/mnt/c/dev/AH_05_05/.venv/bin/python -m mypy --follow-imports=skip \
  app/services/custom_challenge_schedule_reconciler.py \
  app/services/medication_schedule.py app/services/medications.py \
  app/services/user_supplement_nutrients.py app/services/settings.py
```

  Expected: Ruff reports `All checks passed!`; mypy reports no issues in the five source files.

- [ ] **Step 3: Run the complete bounded backend regression**

```bash
/mnt/c/dev/AH_05_05/.venv/bin/python -m pytest --noconftest \
  app/tests/custom_challenge_apis/test_custom_challenge_schedule_reconciliation.py \
  app/tests/custom_challenge_apis/test_custom_challenge_api.py \
  app/tests/services/test_custom_challenge_goal_planner.py \
  app/tests/models/test_custom_challenge_models.py \
  app/tests/models/test_custom_challenge_migration.py -q
```

  Require zero failures. Confirm the tests initialize `sqlite://:memory:` themselves and never load `app/tests/conftest.py`.

- [ ] **Step 4: Audit scope and transaction boundaries**

  Run:

```bash
git diff --check
git diff --name-only
rg -n "reconcile\(" app/services
rg -n "CustomChallengeOccurrence|CustomChallengeParticipation|UserBadge" app/services/medication_schedule.py app/services/medications.py app/services/user_supplement_nutrients.py app/services/settings.py
```

  Confirm hooks occur only inside existing/new source mutation transactions; `save_dose` and `SupplementDoseService.save` contain no hook; recommendations/list/detail contain no mutation-time reconciliation; no route, DTO, migration, frontend, visit, badge, or admin file changed.

- [ ] **Step 5: Commit documentation after verification**

```bash
git add docs/superpowers/plans/2026-09-08-315-custom-challenge-api.md
git commit -m "docs/315[신동훈]미래 목표 재계산 계약 반영"
```

## Self-Review

- Spec coverage: medication schedule edits, medication cancellation, supplement upsert/update/complete, and global meal-time edits all call the reconciler in their source transaction. Reads, doses, visits, badges, and frontend remain untouched.
- Boundary coverage: exact `changed_at`, KST awareness, hard `end_at`, inclusive source end, past preservation, past-key suppression after a forward time move, update/delete/insert future diff, zero remaining goals, account ownership, and all-user global times each have an explicit test.
- Lock coverage: the implementation uses the reviewed `User`-first boundary and documents the early join idempotency-participation lock instead of repeating the old shorthand.
- Placeholder scan: no task depends on an undefined helper or unspecified policy. Supplement overlap remains the existing exact canonical-set join contract and is unrelated to occurrence reconciliation.
