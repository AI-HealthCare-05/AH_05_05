# Automatic Blocked Document Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically recover usable consumer reports, automatically exclude irrecoverably garbled PDFs, and produce a concise manual-review document for only the remaining unsafe research PDFs.

**Architecture:** Extend the supplement parser with a verified consumer-report header variant. Add an explicit recovery classification layer that prevents irrecoverable text from being treated as a failed index candidate, while retaining layout-unsafe research papers in a generated manual-review report.

**Tech Stack:** Python 3.13, Pydantic, pytest, Ruff, existing PDF preprocessing pipeline.

**Spec:** `docs/superpowers/specs/2026-09-07-automatic-blocked-document-recovery-design.md`

## Global Constraints

- Do not infer missing medical content.
- Do not index text classified as unrecoverable or reading-order unsafe.
- Reuse the existing manifest, quality report, and review-document conventions.
- Do not modify unrelated uncommitted work.

---

### Task 1: Consumer-report header recovery

**Files:**
- Modify: `ai_worker/rag/parsers/supplement_code_parser.py`
- Test: `ai_worker/tests/rag/parsers/test_supplement_code_parser.py`

**Interfaces:**
- Consumes: `list[KnowledgePage]` for `food_safety_korea_supplement_ingredients`.
- Produces: `KnowledgeSection` entries for ingredient, function, daily intake, and caution.

- [ ] Write a failing test with the literal header `기능성 원료명(인정번호)` and the four consumer fields.
- [ ] Run the test and confirm no ingredient section is produced before the parser change.
- [ ] Add the field pattern and preserve extraction order.
- [ ] Re-run the focused parser test.

### Task 2: Automatic exclusion and manual-review reporting

**Files:**
- Create: `ai_worker/services/knowledge_blocked_document_recovery_service.py`
- Modify: `ai_worker/services/knowledge_corpus_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_blocked_document_recovery_service.py`

**Interfaces:**
- Consumes: `KnowledgeDocumentPreprocessingReport` and source-document paths.
- Produces: recovery classification and `review/REQUIRES_MANUAL_REVIEW.md`.

- [ ] Write a failing test that classifies a garbled `p1-*` document as automatic exclusion and a reading-order-unsafe research report as manual review.
- [ ] Run the focused test and confirm the recovery service is absent.
- [ ] Implement deterministic classification and manual-review Markdown rendering.
- [ ] Integrate generated reports into corpus preprocessing output.
- [ ] Re-run focused tests.

### Task 3: Full dry-run and regression verification

**Files:**
- Create: `data/knowledge/processed/ocr-tesseract-bulk-dry-run-v7/` generated outputs
- Test: `ai_worker/tests/services/test_knowledge_corpus_preprocessing_service.py`

- [ ] Run the full corpus preprocessing script with `o200k_base` and the existing OCR artifact selection.
- [ ] Check classification totals and ensure only layout-unsafe research documents require manual review.
- [ ] Run Ruff, AI-worker tests, and `git diff --check`.
