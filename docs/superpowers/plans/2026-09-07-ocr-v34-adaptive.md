# OCR v3.4 Adaptive Preprocessing Implementation Plan

**Goal:** Improve the frozen 309-field score by at least seven correct fields without extra runtime OCR/LLM calls or safety regressions.

**Architecture:** Retain the proven document geometry, source validation and coordinate contracts. Investigate image-only feature decisions at the corrected-image boundary; independently audit quality rejection before changing any gate. Keep experimental hypotheses outside application defaults, then implement only the best supported candidate as a new explicit version.

**Tech stack:** Existing Python, OpenCV, NumPy, Pillow, pytest; no new dependency.

**Spec:** `.context/compound-engineering/ce-optimize/ocr-v34-adaptive/spec.yaml` and the user's full implementation request.

## Global constraints and stop condition

- Work only in 906; preserve all existing dirty files and do not perform any Git mutation, DB migration or runtime configuration change.
- No parser, provider or LLM prompt changes. No raw OCR, source-image copies, patient fields or credential values in new outputs.
- Original images are known development data, not an independent test set. Group sample-08 and sample-11 together; report grouped and two-cohort results. Do not tune thresholds against individual image scores.
- Default remains v3.1.3 until >=2 percentage-point gain, <=200ms mean extra preprocessing, no new recapture errors, no >=2-row loss in any document, <=2pp regression in either cohort, and all tests pass.
- Stop after eligibility plus complete final verification, or six distinct experiments / three consecutive non-improving hypotheses / four hours. If no eligible candidate, retain best explicit version and explain limitations.

## Work packets and ownership

1. Main: measurement harness, checkpoint identity, experiment probes, application preprocessing, integration and final report.
2. Independent evaluator owner: new evaluator and its tests only. No application mutations; frozen truth values retained. A source reviewer may classify null fields as absent versus unreadable in a separate annotation file, never alter the 309 existing values to fit predictions.
3. Read-only pipeline and prior-learning auditors: findings only. Independent final reviewer after all implementation writes stop.

Dependency graph: audit + evaluator design + harness → hypothesis probes → best candidate tests/implementation → frozen comparison/robustness → independent QA → promotion decision/report.

## 1. Audit and freeze measurement

- [x] Trace validation, EXIF, document detection, conservative warp rollback, crop fallback, readability gate, illumination, deskew, white border and raw/preview matrices.
- [x] Run the OCR/config baseline; explicit candidate tests and the later 284-test OCR regression run also pass.
- [x] Add `scripts/benchmark_ocr_v34.py`: input/source code/harness/config identity, atomic checksum-wrapped per-image checkpoints, explicit in-flight OCR markers, stage call counts, safe structured whitelist. Reject corrupt or stale results; completed checkpoints must not initialize/call OCR again.
- [x] Independently test `scripts/evaluate_ocr_v34.py`: generic one-to-one sequence alignment, frozen readable field accuracy, false-positive penalties, exact rows and strict document success; no sample/version-specific matching rules.
- [x] Bind every report to truth and prediction checksums. Preserve old reports and measurements.

## 2. Distinct hypothesis probes

- [x] Collect only aggregate image features and existing gate reasons. Do not persist pixels or raw OCR.
- [x] Test resolution hypothesis: characterize connected-component text sizes at native resolution; bounded enlargement only for substantial small-text evidence, avoid continuous/dashed rules and extreme aspect ratios.
- [x] Test adaptive-photometric hypothesis: compare conservative brightness/contrast/color choices justified by image statistics, not a per-sample lookup.
- [x] Test shadow hypothesis. Keep blur/multiple-document safety; record common quality-gate weakness in deterministic rotation/perspective stress tests.
- [x] For each hypothesis, write identity/result checkpoint before another experiment; record negative results and why the next hypothesis differs. Only one external evaluation process at a time.

## 3. Minimal candidate and regression tests

- [x] Write failing behavior tests in `tests/ocr_v3/test_preprocess_adaptive.py` before adding `pipeline/adaptive.py` and profile integration in `preprocess.py`.
- [x] Verify chosen feature branches and conservative fallback; retain historical version output behavior.
- [x] Add tests for coordinates and privacy masks after resize/rotation/perspective, horizontal/dashed/table fixtures, small text, shadow, blur, low resolution, blank/corrupt input, extreme ratios and pixel/edge caps.
- [x] Expose new version in `app/core/config.py` and `.env.example` without changing default until promotion.

## 4. Final evidence and delivery

- [x] Freeze code and evaluator, compare 16 × existing three versions × final candidate under identical no-LLM conditions; run three alternating-order local timings per image/version after CPU work is quiescent.
- [x] Deterministic source variants: fixed +4-degree rotation, mild perspective, directional shadow, Gaussian blur and downscale; keep original/same-document group intact and persist transforms/hashes only. Both rotation signs are covered by synthetic deskew tests, not by the real-image OCR robustness experiment. Record this coverage limit explicitly.
- [x] Run all OCR/config tests, formatter/linter, diff check and independent read-only review. 305 OCR/config tests pass after promotion; historical migration expansion is 307 pass/2 unrelated failures. New adaptive module Mypy passes; 3 unchanged legacy NumPy typing diagnostics disclosed. Byte-exact default-only promotion audit verifies the measured algorithm was not altered.
- [x] Document overall/cohort/grouped field accuracy, precision/recall/F1, exact rows, strict document success, mean/median/p95 times, image-by-image changes, actual call totals, unresolved parser/provider bottlenecks and promotion decision.
- [x] Leave all modifications uncommitted; do not touch running services or `.env`.

## Completion

v3.4.1 was selected and promoted in code after passing predeclared primary/cohort/call/latency/coordinate/privacy/memory gates and an independent review. Config, low-level preprocessing, Service constructor and `.env.example` now agree. No runtime service or database migration was performed. Final report: `docs/ocr/ocr-v34-adaptive-20260907.md`. The source is a known development corpus; shared rotation/perspective gate failures remain a material limitation.

