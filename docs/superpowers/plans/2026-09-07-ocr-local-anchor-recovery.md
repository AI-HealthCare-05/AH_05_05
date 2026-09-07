# OCR Local Anchor Recovery Implementation Plan

> **For agentic workers:** Use test-first implementation with bounded read-only reviewers. The lead owns all writes and integrated verification in this existing local copy.

**Goal:** Ignore leading medication-name symbols and recover hospital/medication evidence despite incorrect global line grouping, without inventing clipped text or moving values between medications.

**Architecture:** Preserve immutable OCR blocks and the successful existing table path. Normalize name prefixes only in name consumers; use raw block geometry for label-local hospital extraction and a conservative local numeric-header fallback when the normal table path finds no candidate. Reuse the existing row, evidence, and semantic validation contracts.

**Tech Stack:** Python 3.13, existing OCR dataclasses and deterministic layout pipeline, pytest, Ruff.

**Spec:** Current conversation: the user approved the preceding local-anchor/row-recovery proposal and explicitly requested all leading special symbols be ignored while clipped names remain unreconstructed.

## Global Constraints

- Work only in `906/AH_05_05`; preserve all prior modified and untracked files.
- No branch changes, staging, commits, push, changes in the separate Git copy, or quality-threshold relaxation.
- Preserve raw OCR text, block IDs, coordinates and confidence as evidence.
- Strip leading non-alphanumeric decoration only; retain digits, letters, internal punctuation and the printed suffix. Never complete `10밀` by guessing.
- Do not send unfiltered document text to an LLM or write patient information into tests or reports.
- Keep ambiguity fail-closed. A row must own its name and schedule blocks; payment numbers and neighboring medications are not substitutes.
- Current scoped source baseline: HEAD `65822ad4a47e25b83e3d3c97d15a24226db1b057` plus pre-existing uncommitted changes. No baseline reset or stash is allowed.

## Task 1: Name-prefix normalization

**Files:** `pipeline/ocr_normalization.py`, `pipeline/medication_rows.py`, `pipeline/ocr_layout.py`, `tests/ocr_v3/test_internal_pipeline.py` under the current OCR package/project.

**Interfaces:** Add `strip_leading_name_symbols(text: str) -> str` to the existing normalization module; use it from canonical medication-name materialization and layout name matching, not from raw OCR ingestion or numeric fields.

- Add parameterized regression tests through the real pipeline for ASCII punctuation, mixed whitespace/symbols and Unicode symbol prefixes; expect the same clean printed medication name and unchanged schedule.
- Assert raw evidence still contains the original decorated name and original block ID.
- Check the contract with literal expectations:

```python
from app.services.medication_ocr_v3.pipeline.medication_rows import _canonical_name_value as canonical

assert canonical("*!리토아틴정10밀리그램") == "리토아틴정10밀리그램"
assert canonical("*!리토아틴정10밀") == "리토아틴정10밀"
assert canonical("※5에프정") == "5에프정"
assert canonical("※가나정10/20mg") == "가나정10/20mg"
```

- Observe failures before replacing the limited leading-symbol allowlist with a Unicode-aware leading non-alphanumeric removal. Do not change the complete-product-name grammar.
- Run the focused tests and existing internal/semantic pipeline tests.

## Task 2: Hospital label-local recovery

**Files:** `pipeline/hospital_name.py`, `tests/ocr_v3/test_hospital_name.py`.

**Interfaces:** Keep `extract_hospital_name(OcrResult, OcrLayoutResult) -> HospitalNameExtraction` unchanged. Reuse candidate parsing and return only original name-block evidence.

- Reproduce the supplied issuer geometry using synthetic names: issuer `[1578,369,1719,417]`, name `[1801,382,1958,438]`, doctor `[1957,382,2079,438]`, and the independent table header `[567,435,768,490]`.
- Require the hospital to survive label/value membership in different global lines and changes to an unrelated receipt column.
- Gather same-region original OCR neighbors from an explicit hospital label rather than enforcing same global line membership. Use the label's local position and nearby table boundaries; retain ordinary body/header exclusion for unlabelled names.
- Keep pharmacy/doctor/telephone exclusions, original confidence/bbox, and ambiguity behavior. Test conflicting hospital anchors and label-like text in the document body.
- Observe regression failure, implement the minimum recovery, then run the entire hospital test file.

## Task 3: Local medication-table recovery

**Files:** `pipeline/ocr_layout.py`, `tests/ocr_v3/test_internal_pipeline.py`; change downstream evidence code only if a verified contract gap requires it.

**Interfaces:** Keep `build_ocr_layout(OcrResult) -> OcrLayoutResult` unchanged. The fallback returns existing `TableCandidate`/`LayoutRow` types with original block evidence so materialization, evidence catalog and semantic validation remain authoritative.

- Use a privacy-free fixture with the supplied receipt geometry: stacked `1회/투약량`, `일투여/횟수`, `총투약/일수` headers at x≈1009–1088, y≈511–540, and a complete product name plus `1.00`, `1`, `90` at y≈533–552.
- Require one grounded medication with the complete printed receipt name, dose `1.00` or its existing canonical numeric equivalent, times `1`, days `90`; the distant clipped main-table name is not completed or used as replacement text.
- Demonstrate that global header/body grouping currently yields no candidate, then recover the bounded local header/row relationship from raw geometry. Reuse existing numeric-lane and name-row logic where its invariants fit.
- Test distant/absent headers, payment-only rows, conflicting nearby values, neighboring medications, and changes to unrelated columns. These must not create cross-row or fabricated evidence.
- Preserve the existing successful-table path. Region-local grouping is confined to recovery; no broad global-threshold retuning.

## Integrated Verification and Stop Condition

- Run focused new tests first, then the affected OCR internal, hospital, semantic, postprocess and service tests.
- Run Ruff/type checks using the existing project configuration on touched production/test files.
- Re-run the two user-supplied images with actual OCR where available. Record only quality state, safe hospital/drug results, stage status and aggregate counts; do not dump patient text.
- Inspect actual changes against the pre-work state and obtain an independent read-only review of the new behavior and safety boundaries. Fix in-scope blocking findings and rerun affected checks.
- Stop when leading decorations no longer reject a complete drug name, cross-line hospital evidence is recovered, the valid local receipt row is available downstream, and the negative/regression checks pass. Report any limitation rather than claiming clipped text was reconstructed.

No commit or push is part of this plan.

