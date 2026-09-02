# Dashboard Chat Response Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show real chatbot response counts and average five-star satisfaction on the admin dashboard.

**Architecture:** Extend `ChatSession` with an optional validated score, aggregate terminal assistant messages and rated sessions in the existing dashboard service, and expose the result through the existing summary DTO. The static dashboard consumes the new response and renders counts plus a fractional five-star rating.

**Tech Stack:** Python 3.13, Tortoise ORM, Aerich, FastAPI/Pydantic, vanilla JavaScript, HTML/CSS, pytest, Node test runner

**Spec:** `docs/superpowers/specs/2026-09-02-dashboard-chat-response-stats-design.md`

## Global Constraints

- Work in `/Users/admin/PycharmProjects/FinalProject`.
- Do not commit changes.
- Scores are nullable integers in the inclusive range 1 through 5.
- Dashboard counts include only terminal `ASSISTANT` messages in the selected period.
- Dashboard satisfaction includes only rated sessions created in the selected period.

---

### Task 1: Chat session score schema

**Files:**
- Modify: `tests/models/test_model_metadata.py`
- Modify: `app/models/chat.py`
- Create: `app/core/db/migrations/models/<next>_add_chat_session_score.py`

**Interfaces:**
- Produces: `ChatSession.score: int | None` with 1..5 validation and the description `채팅 별점`.

- [x] Add a model metadata test that requires a nullable integer score, both boundary validators, and the database description.
- [x] Run the test and confirm it fails because `score` does not exist.
- [x] Add the minimal model field and generate the Aerich migration.
- [x] Run the model test and migration tests.

### Task 2: Dashboard chatbot aggregation contract

**Files:**
- Modify: `app/tests/admin_apis/test_admin_dashboard_api.py`
- Modify: `app/dtos/admin_dashboard.py`
- Modify: `app/services/admin_dashboard.py`

**Interfaces:**
- Produces: `DashboardSummaryResponse.chat_responses: ChatResponseStats`.
- `ChatResponseStats` fields: `total`, `completed`, `failed`, `average_score`.

- [x] Add API tests with real chat sessions/messages for role, status, selected-period, and nullable-score behavior.
- [x] Run the focused API tests and confirm `chatResponses` is missing.
- [x] Add the DTO and service aggregation using `completed_at` for responses and session `created_at` for ratings.
- [x] Run the focused API tests and existing dashboard API suite.

### Task 3: Five-star dashboard rendering

**Files:**
- Modify: `app/tests/static_ui/dashboard.test.mjs`
- Modify: `app/static/templates/dashboard.html`
- Modify: `app/static/js/dashboard.js`
- Modify: `app/static/css/styles.css`

**Interfaces:**
- Produces: `formatChatSatisfaction(value)` returning display text and star fill percentage.
- Consumes: API `chatResponses` camel-case payload.

- [x] Add JS/HTML tests for real data slots, fractional star fill, and the no-rating state.
- [x] Run the focused Node test and confirm the formatter/data slots are missing.
- [x] Replace fixed values and the automatic-resolution block with API-backed counts and accessible stars.
- [x] Run the focused Node test and confirm the dashboard/brand suites pass; record unrelated pre-existing failures from the full static UI run.

### Task 4: Verification and database migration

**Files:**
- Verify all modified source, test, and migration files.

**Interfaces:**
- Consumes: Tasks 1 through 3.

- [x] Run Ruff formatting and lint checks for changed Python files.
- [x] Run focused model, dashboard API, migration, and static UI tests.
- [x] Run the relevant full test suites.
- [x] Apply the Aerich migration to the configured Docker MySQL database and confirm the column metadata.
