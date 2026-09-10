# Therapeutic-class registered-intake retrieval and verified pair-evidence plan

**Goal:** Restrict registered-intake therapeutic-class questions to source-backed active medicines, add direct vitamin D–calcium evidence metadata from an official source, and prove RDB rule plus Qdrant pair-evidence retrieval end to end.

**Spec:** [2026-09-09-therapeutic-class-and-pair-evidence-design.md](../specs/2026-09-09-therapeutic-class-and-pair-evidence-design.md)

## Task 1 — Test and add reviewed therapeutic-class storage

- [ ] Add failing model/repository tests for approved class selection, alias matching, and unclassified active medicines.
- [ ] Add `TherapeuticClass`, `TherapeuticClassAlias`, and `InteractionEntityTherapeuticClass` Tortoise models plus an Aerich migration.
- [ ] Add a versioned source-backed seed manifest and importer. Initial warfarin classification must cite the reviewed existing source text; no classification code constants.
- [ ] Add repository resolution through explicit medication mappings first, then read-only canonical/alias name resolution.
- [ ] Run focused repository/model tests; commit the data-model unit separately.

## Task 2 — Select class-matched active intake in the chat use case

- [ ] Write a failing use-case test: only active warfarin, not an unrelated active medicine, becomes a pair candidate for an active-intake coagulation question.
- [ ] Add a `TherapeuticClassRepository` dependency to the use case and wire the DB implementation in `MedicationChatCoreService`.
- [ ] Preserve existing non-class active-intake behavior and add aggregate `therapeutic_class.resolve` trace metadata.
- [ ] Run focused use-case/service tests; commit the runtime selection unit separately.

## Task 3 — Annotate official vitamin D–calcium direct evidence

- [ ] Write a failing metadata/indexing test against the MFDS vitamin D document.
- [ ] Add a document-specific `SUPPLEMENT_SUPPLEMENT` annotation in `interaction_annotations.yaml`.
- [ ] Prove a chunk gains the exact pair key only if both entity groups appear. Add a regression that magnesium–zinc remains unannotated without a direct reviewed document.
- [ ] Run metadata/preprocessing tests; commit annotation and guards separately.

## Task 4 — End-to-end retrieval contract

- [ ] Add E2E tests for `active intake → therapeutic class → approved rule → exact pair evidence`.
- [ ] Verify a `PENDING` class assignment or rule never appears in the deterministic result.
- [ ] Verify no class match produces safe evidence-gap guidance, not a broad all-medicine search.
- [ ] Run affected tests, full AI worker test suite, relevant app tests, Ruff, and `git diff --check`.
- [ ] Commit the E2E test/report unit.

## Post-implementation gate

Before creating any new collection, inspect the preprocessed release manifest and request separate approval specifying OpenAI embedding count and the immutable Qdrant collection name. Run the vitamin D–calcium and magnesium–zinc evaluation cases against that release; do not activate it unless the direct evidence outcome improves without false pair evidence.
