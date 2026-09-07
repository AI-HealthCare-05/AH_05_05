# Challenge Default Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `aerich upgrade` install curated production defaults for common code groups, common codes, badges, and challenges.

**Architecture:** Add stable badge image assets and one ordered Aerich data migration. The migration resolves foreign keys through natural keys, updates existing baseline rows, records only newly inserted natural keys in a helper table, and removes only those inserted rows on downgrade.

**Tech Stack:** Python 3.13, Aerich, Tortoise ORM, MySQL 8, SQL, static media assets

**Spec:** `docs/superpowers/specs/2026-09-07-challenge-default-seed-design.md`

## Global Constraints

- Exclude test, legacy inactive, and soft-deleted source rows listed in the spec.
- Do not hard-code common-code, badge, challenge, or administrator numeric IDs.
- Preserve existing rows with matching natural keys and update their baseline fields.
- Do not run automated tests.
- Do not create a Git commit.

---

### Task 1: Stable badge assets

**Files:**
- Create: `app/static/media/badges/water-badge.png`
- Create: `app/static/media/badges/stretching-badge.png`

**Interfaces:**
- Consumes: Existing uploaded image files referenced by the current Docker MySQL `badges.image_path` values.
- Produces: Stable relative paths consumed by the seed migration.

- [x] **Step 1: Copy the existing production badge images to stable names**

Copy `f8a781ebd41b423a973dae28ca5ff3e7.png` to `water-badge.png` and `a0b4184fa96b4ce9950d252bfcce5480.png` to `stretching-badge.png` without modifying the source files.

- [x] **Step 2: Verify the copied assets**

Run `file` and `shasum -a 256` for both source/destination pairs. Each destination must be a PNG and have the same hash as its source.

### Task 2: Aerich data migration

**Files:**
- Create: `app/core/db/migrations/models/36_*_seed_challenge_defaults.py`

**Interfaces:**
- Consumes: Tables created by migrations 21 and 32 and schema state from migration 35.
- Produces: Curated rows connected by resolved foreign keys.

- [x] **Step 1: Create a data-only migration with current model state**

Copy the `MODELS_STATE` value from migration 35 so future Aerich schema diffs retain the current `Badge.image_path` model state.

- [x] **Step 2: Create insertion tracking**

Create `_migration_36_challenge_default_seed` with `entity_type`, `key1`, and `key2` as its composite primary key. Before each insert, record natural keys only when the target row does not already exist.

- [x] **Step 3: Upsert common code groups**

Insert or update these natural keys: `P_REASON`, `N_REASON`, `CHL_TYPE`, `CHL_PERIOD`, `CHK_TYPE`, `CHK_FREQ`. Set their category, Korean names/descriptions, and `is_active=1`; leave administrator FKs unchanged for existing rows and `NULL` for inserted rows.

- [x] **Step 4: Upsert common codes**

Resolve each group by `group_code`, then insert or update the exact active detail codes from the spec. Update Korean name, description, sort order, and `is_active=1` without relying on numeric IDs.

- [x] **Step 5: Upsert badges**

Insert or update `물마시기 배지` and `스트레칭 배지` with stable image paths, descriptions, and `is_active=1`. Inserted rows use `NULL` administrator FKs; existing administrator audit fields remain unchanged.

- [x] **Step 6: Upsert the default challenge**

Resolve `T02`, `D7`, `SELF`, `DAILY`, and `스트레칭 배지` with scalar subqueries. Insert or update `스트레칭 챌린지` using the approved phrase, description, recruitment timestamps, display state, and delete state while preserving existing audit administrator FKs.

- [x] **Step 7: Implement FK-safe downgrade**

Delete tracked challenge rows, badge rows, common-code rows, and group rows in reverse dependency order. Delete a tracked group only when it has no remaining codes, then drop the tracking table. Existing pre-migration rows and their updated values remain.

### Task 3: Apply and verify

**Files:**
- Modify only through migration execution: Docker MySQL schema/data and the `aerich` version table.

**Interfaces:**
- Consumes: Migration 36 and stable image files.
- Produces: Docker MySQL at Aerich version 36 with complete baseline relations.

- [x] **Step 1: Format and lint the migration**

Run Ruff format and Ruff check on migration 36, then run `git diff --check` on the migration, assets, spec, and plan.

- [x] **Step 2: Apply the migration**

Run `uv run aerich upgrade`. Expected result: upgrade to migration 36 without duplicate-key or FK errors.

- [x] **Step 3: Verify database rows and relations**

Query all four tables by the approved natural keys. Confirm 6 groups, 20 active detail codes, 2 production badges, and 1 non-deleted default challenge; confirm the challenge joins to `T02`, `D7`, `SELF`, `DAILY`, and `스트레칭 배지`.

- [x] **Step 4: Verify idempotency properties statically**

Review the SQL natural-key predicates, `ON DUPLICATE KEY UPDATE` clauses, insertion tracking, and FK-safe downgrade order. Do not re-run an already-recorded Aerich migration or execute automated tests.
