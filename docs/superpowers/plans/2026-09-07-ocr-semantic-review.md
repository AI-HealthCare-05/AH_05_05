# OCR Semantic Review Implementation Plan

> **For agentic workers:** Use ce-work for scoped local execution. The lead owns all core writes and authoritative verification; read-only mapping and independent QA may run as subagents. User local-copy/no-Git rules override generic branch/commit steps.

**Goal:** Make the LLM review all five medication fields against OCR evidence and prove its incremental accuracy with a same-OCR control.

**Architecture:** Preserve the legacy ID-only contract for measurement. Add a strict semantic selection and bounded context catalog; validate selections into existing grounded and row objects before public projection.

**Tech Stack:** Python 3.13, Pydantic, existing OpenAI Responses client, CLOVA General OCR, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-07-ocr-semantic-review-design.md`

## Global Constraints

- Local copy `906/AH_05_05`; no commits, push, branches, live service restart, API/DB migrations, or unrelated rewrites.
- Preserve existing dirty files. Lead owns integration and all shared contracts.
- Never persist patient details, OCR raw text, provider payloads, or image crops in benchmark artifacts.
- Accuracy first; measure latency but do not optimize it at the expense of measured correctness.

## Task 1: Evidence and strict semantic contract

Files: `domain/grounding.py`, `pipeline/evidence_catalog.py`, new `pipeline/semantic_grounding.py`, new `tests/ocr_v3/test_semantic_grounding.py` within medication_ocr_v3.

Interfaces: `EvidenceCatalog.to_semantic_payload() -> dict`; `SemanticGroundingSelection` containing each row's five field selections (status, exact text, block IDs); `materialize_semantic_review(catalog, medication_rows, baseline, selection) -> tuple[MedicationRowsResult, GroundedResult]`.

- [x] Add failing tests for full-row input, supported five-field correction, numeric-token boundary, unknown/cross-row/duplicate evidence, absent/uncertain fallback and issue propagation. Use synthetic medication rows with literal expected outputs, e.g. `assert review['medications'][0]['strength'] == '68.1mg'` and `assert 'CROSS_ROW_BLOCK_ID' in codes`.
- [x] Run `uv run pytest tests/ocr_v3/test_semantic_grounding.py -q` and record the expected missing behavior before implementation.
- [x] Add semantic payload without changing `to_llm_payload()` legacy behavior. Retain original field hints and supply safe contextual strengths.
- [x] Implement evidence validation using existing normalization/parsing and geometry helpers; output existing row/grounded dataclasses so downstream code stays compatible.
- [x] Rerun focused tests, then existing internal pipeline tests.

## Task 2: Provider and analysis integration

Depends on Task 1. Files: `providers/openai_grounded.py`, new `prompts/medication_semantic_review_v1.md`, `pipeline/analyze.py`, provider and pipeline tests.

Interfaces: provider `review_mode` chooses legacy or semantic; `select(catalog)` returns the corresponding strict selection. Pipeline uses full semantic catalog for semantic mode and the unchanged ambiguity-only path for legacy mode. Diagnostics identify actual prompt/schema and corrected/rejected fields.

- [x] Add failing integration tests through `analyze_processed_image` with real layout/catalog/projection and a fake external responder. Assert all five final fields and actual evidence IDs, not just calls.
- [x] Verify timeout/refusal/malformed/partial results preserve fallback and report issues; cancellation still prevents external calls.
- [x] Implement prompt and provider schema selection, one provider call per input, full-row review even without legacy ambiguity, and grounded projection integration.
- [x] Run `uv run pytest tests/ocr_v3 tests/ocr/test_openai_grounded_provider.py app/tests/test_ocr_config.py -q` plus worker/service tests covering touched boundaries.

## Task 3: Same-OCR evaluation and promotion gate

Depends on Task 2. Files: new `scripts/benchmark_ocr_semantic_review.py`, benchmark tests, `docs/ocr/ocr-semantic-review-20260907.md`.

- [x] Reuse `benchmark_ocr_postprocess` checkpoint/hash/adjudication helpers and `evaluate_ocr_v34.score_sample` with frozen corrected gold.
- [x] Add failing tests for restored/harmed field accounting, absent/unknown field exclusions, and stale/corrupt checkpoint rejection.
- [x] Obtain OCR once per document in memory; compare no-LLM, legacy, semantic on precisely that object. Alternate LLM arm order and record actual timings, calls, hashes and safe scores. Keep service timing distinct from replay timing.
- [x] Run `test.jpg` first; then all 16 common cases with fixed gold. Resume only validated completed units. Investigate any newly wrong answer before promotion.
- [x] Compare exact field counts, false positives, missed fields, and row results. Promote semantic default only with improved accuracy and no increased FP; otherwise preserve legacy default and clearly report unmet criteria.

## Task 4: Independent verification and delivery

Depends on Tasks 1–3. Read-only verifier checks privacy, failure paths, evidence identity, tests and measured claims. Lead integrates fixes, reruns affected tests, Ruff check/format, and `git diff --check`.

- [x] Reconcile every blocking finding with direct source/test evidence.
- [x] Document actual results, tested scope, exclusions, timing boundaries, and any remaining extraction limitations.
- [x] Deliver important paths, fresh verification and uncommitted status. Stop after acceptance checks; do not start Git shipping or additional unrelated improvements.

