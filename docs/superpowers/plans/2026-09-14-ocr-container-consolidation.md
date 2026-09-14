# OCR container consolidation implementation plan

**Goal:** Remove the standalone `ocr-worker` and `ocr-images` Compose services while retaining asynchronous OCR, queue retries, original/processed previews and RAM-only image retention.

**Architecture:** The FastAPI container supervises one API process, one ARQ OCR process and an image-only Redis bound to `127.0.0.1:6380`. The existing Redis broker, email worker, alarm worker and AI worker remain unchanged. Container count decreases by two; no claim of equivalent RAM savings is made.

**Spec:** User-approved direction in this task: reduce containers for AWS Docker deployment; preserve OCR behavior and do not persist images. The concrete design was announced before implementation.

**Tech stack:** Python 3.13, FastAPI/Uvicorn, ARQ, Redis, Docker Compose, Supervisor.

## Constraints

- Image Redis: RDB/AOF disabled, noeviction, bounded maxmemory, loopback only, tmpfs working directory, swap/core dumps disabled at container level.
- Keep DB records, queue identities, retries and TTL (at most 60 minutes) unchanged.
- Default API worker count and OCR parallel jobs are one. Existing service command overrides must still work.
- PID 1 must manage child shutdown/restart and report persistent startup failures. Healthcheck must not report healthy with a dead OCR worker.
- No live database reset, OCR/provider calls, automatic volume pruning or production deployment during tests.
- Local copy rules apply; no unrelated changes or implicit Git publication.

## Work packets

### U1: Combined runtime (runtime agent)

Own `app/Dockerfile`, `app/runtime/*`, `ai_worker/tests/runtime/test_combined_ocr_runtime.py`.

- [ ] Write and observe failing runtime tests before implementation.
- [ ] Implement `uv run --no-sync python -m app.runtime.combined` and healthcheck module.
- [ ] Exercise supervisor startup/configuration, failures and termination; retain reusable workers' command overrides.

### U2: Deployment and resource bounds (lead)

Own local/production Compose, core config, OCR worker limits, `.env.example`, existing Compose tests and this document/runbook.

- [ ] Update Compose contract test: neither removed service exists; API uses loopback image Redis, tmpfs, no swap, managed startup, shutdown grace, healthcheck and dependencies.
- [ ] Observe old Compose fails that contract; then edit both variants.
- [ ] Configure bounded OCR concurrency default one and test invalid values.
- [ ] Update deployment instructions: rebuild image before rollout; drain old OCR queue and previews; remove only obsolete containers after verified cutover; preserve all volumes.

### U3: Integration and independent review (lead + read-only reviewer)

- [ ] Run targeted tests and full AI tests plus lint/format.
- [ ] Build the actual app image and launch an isolated combined-runtime smoke test using fake OCR provider/network-safe test inputs, not patient data.
- [ ] Verify RAM-only original/processed image roundtrip, TTL, no external Redis port, worker liveness and SIGTERM/failure behavior.
- [ ] Review combined diff independently; fix blockers and rerun affected checks.

## Checkpoints and stop condition

Source/config edits are checkpoint one; passing isolated build/runtime tests checkpoint two. Resume from Git diff and this contract, not old running container assumptions. Finish only with two fewer declared services in both Compose variants, preserved queue/preview contracts and measured runtime verification. Disclose that deployment restarts invalidate existing RAM-only previews; never migrate those images to disk to hide the limitation.
