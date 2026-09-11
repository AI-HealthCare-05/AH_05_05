# v11 Card Template Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development, with the user's local-copy/no-commit rules overriding branch and commit steps.

**Goal:** Render arbitrary registered users' intake reports with the approved v11-guarded card layout and evidence-locked contents.

**Architecture:** The server binds registered medication IDs to unambiguous guide IDs, constructs typed evidence, and asks AI for a validated card plan. The same accepted cards generate the public structured response and email Markdown. Nutrient values remain server-owned. Legacy responses retain their existing renderer.

**Tech Stack:** Python/Pydantic/LangChain, FastAPI, React/TypeScript, pytest, Playwright.

**Spec:** Approved in-chat request to match `output/intake-report-versions/mobile-v11-guarded.html`, followed by explicit implementation approval; this document captures that design.

## Global constraints

- No fixture medication names/counts or demographic values in production code.
- Keep every registered medication identity; no ambiguous or substring-based clinical pair inference.
- Preserve efficacy/caution/contraindication categories and source conditions; absent evidence is unknown, never safe.
- No DB changes, server start/restart, email sends, Git write operations, or unrelated edits.
- Preserve emailToken and derive reportMarkdown from the same accepted presentation.

## Task 1: Evidence catalog and generation (backend owner)

Files: new `ai_worker/schemas/intake_report_cards.py`, `ai_worker/reports/v11_cards.py`, `ai_worker/llm/generators/intake_report_cards_generator.py`, `ai_worker/tests/reports/test_v11_cards.py`.

- [x] Test arbitrary IDs, wrong owner/category, omitted/duplicate required facts, mutation of safety statements and unknown sources; run RED before implementation.
- [x] Produce `IntakeReportCards` and `OpenAIIntakeReportCardsGenerator.generate(draft=...)`; AI selects evidence IDs, safe spacing changes may be accepted only with non-whitespace equality.
- [x] Render the accepted structured cards to email Markdown; raise generation errors after bounded repair, never publish a failed plan.
- [x] Run isolated tests and Ruff. Review before accepting; final integration remains pending below.

## Task 2: Public API integration (lead owner)

Files: `ai_worker/schemas/intake_report.py`, `ai_worker/use_cases/generate_intake_report.py`, `ai_worker/services/intake_report_core_service.py`, `app/dtos/intake_reports.py`, existing schema/use-case/service tests.

- [x] Add failing identity-binding test: `assert generator.draft.guide_item_bindings == {901: 93821}` for arbitrary product names.
- [x] Bind each registration to its successful unambiguous lookup; duplicate names keep distinct registration IDs.
- [x] Add optional cards to outcome/result/DTO and derive `presentation_version='ai-report-v11'` only when cards exist; otherwise retain v2.
- [x] Factory uses new generator; verify API aliases, exact Markdown propagation, and legacy/email regressions.

## Task 3: Card UI (frontend owner, independent after contract)

Files: new `frontend/src/pages/reports/V11ReportBody.tsx`, optional CSS, entity types, route in IntakeReportBody, new `frontend/tests/e2e/311-v11-report-cards.spec.ts`.

- [x] Failing browser checks for core labels, one nutrient display, source links, dynamic products and mobile overflow.
- [x] Build hero, anchor chips, interactions, per-nutrient overlaps, lifestyle, nutrients, medication core/details, supplements and collapsed provenance.
- [x] Render only the structured body, no duplicate Markdown/table. Escape text and restrict links to http/https.
- [x] Run typecheck, existing report/email browser tests, 320/390/desktop checks and inspect screenshots.

## Task 4: Integration verification

- [x] Independent read-only review of changed contract, renderer and generator, resolve blocking issues.
- [x] Fresh targeted pytest and browser tests, Ruff/typecheck, diff check, rendered visual inspection.
- [x] Report measured outcome and any runtime limitation honestly; no commit/push.

## Progress / resumable checkpoint

Identity: v11-card-template / registered-ID-evidence-lock / 2026-09-11. Resume from unchecked tasks after reading current files and confirming owners; completed tests must be rerun if their source changes.

Original owners: task 1 v11_structured_backend, task 2 lead, task 3 v11_structured_frontend. All implementation ownership has returned to the lead. Subsequent Claude Code packets supplied scoped implementation drafts, read-only reviews, and test execution; the lead integrated and verified the combined state.
Preflight: task 1 produces IntakeReportCards consumed by tasks 2/3; contract is explicitly exchanged before implementation. Task 2 binds input IDs consumed by task 1. Task 3 uses existing nutrient totals unchanged. All tasks agree on no fixture data and legacy/email preservation.

### Integration checkpoint

- Final targeted backend checks: 122 passed (97 evidence/schema/use-case/service/assembler/repository tests, 25 API/email tests). This includes 74 v11-specific regressions. No unused RAG dependency for evidence-locked cards; legacy generators retain retrieval.
- Source-pair correction: report citations use additive paired title/nullable URL metadata, preserving legacy arrays. Repository/assembler and medication-question compatibility: 77 passed.
- Frontend production build/typecheck passed; offline real-mode browser regression: 7 passed (email 3, v11 4), including signed-snapshot email flow and safe one-pass entity display; 6 original mock-only entry tests skipped, not claimed passed. No HTTP server started.
- Backend now uses bounded per-medication requests (concurrency 3), a separate interaction/lifestyle batch, a 90-second aggregate deadline, and per-request caching of strictly validated text. Public cards and Markdown retain canonical non-whitespace characters, including when safely projecting near-match spacing.
- Long-text repair now targets only failing fields with lossless bounded chunks. Both chunk screening and the final whole-field projection retain original characters; the existing whole-field 3-character alignment budget cannot multiply across chunks. Full canonical equality, protected-token spacing, coverage, and aggregate validation remain mandatory. Repair calls consume the existing attempt/time budget.
- Actual read-only DB/model generation accepted in run 10: COMPLETED, `ai-report-v11`, no fallback, 20.4 seconds, 5 medication cards, 5 guidance cards, 4 lifestyle cards, 2 nutrient overlaps. Original artifacts: `output/intake-report-workspace/v11-run10` under the 810final root. Earlier failed runs remain preserved as diagnostic evidence.
- App/email presentation parity: both decode clinical entities exactly once while treating markup as text. The accepted run 10 cards were re-rendered without DB/model/SMTP calls after fixing email double-escaping. `v11-run10/rendered/provenance.json` records the accepted response hash, rendering-source hash, and unchanged-card identity.
- Actual-data visual checks: app 320/390/1280 px and email 320/900 px, no horizontal overflow or page errors; all five medication identities/core texts, four nutrient bars, and complete email core/detail/guidance/overlap/lifestyle text checked. Screenshots visually inspected under `output/intake-report-workspace/v11-real-ui`; `checks.json` records the measurements.
- Final Ruff and `git diff --check` passed; the index is empty. No commit/push. Pre-existing and task changes remain uncommitted.
- Runtime activation still requires a later authorized server/email-worker restart. Existing processes have not been restarted. No DB writes, email sends, commits, or pushes during this implementation.
