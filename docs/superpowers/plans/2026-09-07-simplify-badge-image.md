# Simplify Badge Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the two active/inactive badge images with one badge image while preserving challenge badge selection behavior.

**Architecture:** Rename the persisted `badges.on_image_path` value to `image_path`, remove `off_image_path`, and propagate the new field through Tortoise models, API DTOs, upload handling, participant award snapshots, and admin screens. Existing `user_badges.badge_image_path` remains a historical snapshot.

**Tech Stack:** FastAPI, Tortoise ORM, Aerich, MySQL, vanilla JavaScript, HTML/CSS

**Spec:** Approved conversation design for the badge-management schema change.

## Global Constraints

- Keep challenge reward badge selection and search popup behavior unchanged.
- Do not commit changes.
- Do not run automated tests per user request.

---

### Task 1: Domain and API contract

**Files:**
- Modify: `app/models/challenges.py`
- Modify: `app/dtos/challenges.py`
- Modify: `app/apis/v1/admin_challenge_router.py`
- Modify: `app/services/challenge_participation.py`

- [x] Rename the model and API fields to `image_path`.
- [x] Accept and store one uploaded image.
- [x] Preserve awarded badge snapshots using `badge.image_path`.

### Task 2: Database migration

**Files:**
- Create: `app/core/db/migrations/models/35_*_simplify_badge_images.py`

- [x] Generate an Aerich migration that renames `on_image_path` and removes `off_image_path`.
- [x] Apply the migration to Docker MySQL.

### Task 3: Admin screens

**Files:**
- Modify: `app/static/templates/badge-management.html`
- Modify: `app/static/js/badge-management.js`

- [x] Replace the dual image controls with one image control.
- [x] Add badge ID, badge name, and use-status search controls.
- [x] Keep challenge badge selection and popup behavior intact.

### Task 4: Static verification

- [x] Search production sources for obsolete fields.
- [x] Run formatting and diff checks without executing tests.
