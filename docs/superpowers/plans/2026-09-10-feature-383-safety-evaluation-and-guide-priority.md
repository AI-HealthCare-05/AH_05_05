# Feature 383 Safety, Evaluation Seed, and Evidence Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Prevent disclaimer-driven safety false positives, make active-intake evaluation reproducible, preserve source-backed pair evidence, and ensure product-name drug-food questions consult official guides before research RAG.

**Architecture:** The final-answer validator removes only the canonical MEDICAL_DISCLAIMER from the policy scan, while preserving the original answer and still blocking direct medication-change commands. A non-production evaluation seed uses existing schema and explicit --apply opt-in to create a dedicated user, confirmed episode, active intake, typed mappings, and checked prerequisites. Pair annotations remain document- and chunk-scoped; source co-occurrence never becomes clinical evidence. Product-name provenance travels from question resolution into the immutable query plan even when interaction search converts a product to its ingredient.

**Tech Stack:** Python 3.13, Pydantic v2, Tortoise ORM, Pytest, Ruff, YAML, Qdrant release tooling.

**Spec:** docs/superpowers/specs/2026-09-09-therapeutic-class-and-pair-evidence-design.md and the approved Feature 383 objective.

## Global Constraints

- No RDBMS schema change or Aerich migration is permitted.
- No Qdrant collection, OpenAI embedding call, or active-collection change occurs in this branch without a new, explicit approval naming the collection and embedding count.
- Only APPROVED interaction rules and therapeutic classifications can determine a deterministic interaction answer.
- A chunk receives interaction_pair_keys only when its reviewed source text explicitly establishes and contains both annotated entities.
- The seed is evaluation-only, idempotent, dry-run by default, and never runs automatically against a shared database.
- Preserve unrelated user-created HTML, OCR, Vite, output, and temporary files.

---

## File Structure

| File | Responsibility |
| --- | --- |
| ai_worker/safety/grounded_claim_validator.py | Exclude the canonical disclaimer from unsafe-command pattern matching only. |
| ai_worker/tests/safety/test_grounded_claim_validator.py | Direct validator regressions. |
| ai_worker/tests/use_cases/test_answer_medication_question.py | End-to-end answer and product-guide regressions. |
| scripts/seed_chat_evaluation_account.py | Idempotent explicit-apply evaluation-account seeder. |
| ai_worker/tests/scripts/test_seed_chat_evaluation_account.py | Seeder contract and repeatability tests. |
| data/knowledge/manifests/interaction_annotations.yaml | Reviewed direct-pair annotations only. |
| ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py | Source and chunk eligibility tests. |
| ai_worker/schemas/medication_search.py | Query-plan product lookup candidate contract. |
| ai_worker/domain/medication_question_resolver.py | Retain original product provenance after ingredient substitution. |
| ai_worker/rag/query_builders/medication_knowledge_query_builder.py | Populate stable guide candidates from typed entities. |
| ai_worker/use_cases/answer_medication_question.py | Query guide candidates before RAG for product-name drug-food questions. |
| ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py | Product-alias query-plan regression. |
| docs/experiments/2026-09-10-direct-pair-evidence-readiness.md | Source readiness and collection gate. |

## Task 1: Prevent canonical-disclaimer safety false positives

**Files:**
- Modify: ai_worker/safety/grounded_claim_validator.py
- Modify: ai_worker/tests/safety/test_grounded_claim_validator.py
- Modify: ai_worker/tests/use_cases/test_answer_medication_question.py

**Interfaces:**
- Produce RuleBasedGroundedClaimValidator._answer_for_policy_scan(answer: str) -> str.
- diagnose() uses the sanitized value only for medication-change, diagnosis, and treatment patterns. Disclaimer detection still sees the original normalized answer.

- [ ] **Step 1: Write two failing direct-validator tests**

~~~python
async def test_validator_ignores_canonical_disclaimer_when_scanning_for_medication_change() -> None:
    answer = "타이레놀은 통증과 발열 완화에 사용됩니다. 주의사항을 확인하세요.\n\n" + MEDICAL_DISCLAIMER
    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1), result=build_result(answer)
    )
    assert result.safety_status == SafetyStatus.SAFE
    assert result.answer == answer

async def test_validator_blocks_direct_instruction_even_when_canonical_disclaimer_is_present() -> None:
    result = await RuleBasedGroundedClaimValidator().validate(
        context=ActiveIntakeContext(user_id=1),
        result=build_result("오늘부터 약 복용을 중단하세요.\n\n" + MEDICAL_DISCLAIMER),
    )
    assert result.safety_status == SafetyStatus.BLOCKED
    assert result.safety_reason_codes == ["MEDICATION_CHANGE_INSTRUCTION"]
~~~

- [x] **Step 2: Run the focused test and inspect the baseline behavior**

Run: uv run --group ai --group app pytest ai_worker/tests/safety/test_grounded_claim_validator.py -q

Observed: both cases already pass. The exact canonical disclaimer uses the noun-list construction `복용 시작·중단·용량 변경은 … 상의하세요`, while the direct-instruction pattern only matches an action followed by an imperative such as `중단하세요`. The historical `MEDICATION_CHANGE_INSTRUCTION` Trace therefore cannot have been caused by this exact constant; it must be investigated as a separate generated or source-derived sentence. The explicit sanitizer is retained as a regression boundary if the disclaimer wording changes.

- [ ] **Step 3: Add minimal policy scan sanitization**

~~~python
@staticmethod
def _answer_for_policy_scan(answer: str) -> str:
    return answer.replace(MEDICAL_DISCLAIMER, "")
~~~

Call the helper after spacing normalization and before every policy regex. Do not strip official warnings or any noncanonical answer text. Matched-fragment hashing remains based on an actual answer fragment.

- [ ] **Step 4: Add a use-case regression**

Use build_use_case with build_guide(), LongAnswerGenerator, and RuleBasedGroundedClaimValidator. Ask "타이레놀은 어디에 좋고 먹을 때 뭘 조심해야 해?", assert MEDICATION_GUIDE and SAFE, and assert efficacy plus caution text remain in the answer.

- [ ] **Step 5: Verify and commit**

Run:
~~~bash
uv run --group ai --group app pytest ai_worker/tests/safety/test_grounded_claim_validator.py ai_worker/tests/use_cases/test_answer_medication_question.py -q
uv run ruff check ai_worker/safety/grounded_claim_validator.py ai_worker/tests/safety/test_grounded_claim_validator.py ai_worker/tests/use_cases/test_answer_medication_question.py
git diff --check
git add -- ai_worker/safety/grounded_claim_validator.py ai_worker/tests/safety/test_grounded_claim_validator.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "[feature/383][임경수] 면책문구 안전성 과차단 수정"
~~~

## Task 2: Add a dedicated idempotent active-intake evaluation seed

**Files:**
- Create: scripts/seed_chat_evaluation_account.py
- Create: ai_worker/tests/scripts/test_seed_chat_evaluation_account.py

**Interfaces:**
- Produce EvaluationSeedPlan, a pure data model identifying ketorolac, aspirin, warfarin, vitamin K, ANTICOAGULANT, and approved evidence prerequisites.
- Produce async seed_evaluation_account(plan: EvaluationSeedPlan, *, apply: bool) -> EvaluationSeedResult.
- CLI requires --email and --password only with --apply. Omission of --apply produces a no-write dry-run report.

- [ ] **Step 1: Write failing seed tests**

Test the plan exposes exactly ketorolac, aspirin, warfarin, vitamin K, an ANTICOAGULANT class, and APPROVED-only prerequisite rules. Test dry-run performs no write. Test applying the same plan twice produces one user, one confirmed active episode, three medications, and one vitamin K registration.

- [ ] **Step 2: Verify RED**

Run: uv run --group ai --group app pytest ai_worker/tests/scripts/test_seed_chat_evaluation_account.py -q

Expected: module and seed interface are missing.

- [ ] **Step 3: Implement the non-production seed**

1. Use --email and --password only for the local evaluation user; never commit credentials.
2. Default dry-run resolves and reports existing canonical entities, vitamin K catalog item, mappings, class assignment, and rules without writes.
3. --apply creates or reuses user, confirmed active CareEpisode, three medication rows, and active vitamin K registration.
4. Existing InteractionEntity, SupplementNutrient, MedicationInteractionEntity, APPROVED InteractionEntityTherapeuticClass, and APPROVED InteractionRule are prerequisites. Abort with missing identifiers instead of creating an unreviewed rule or calling it APPROVED.
5. Print the active interaction-rule and therapeutic-class dataset versions so the evaluator can set matching local environment values.

- [ ] **Step 4: Add SQLite E2E coverage**

Seed reviewed source records, a PENDING control rule, active intake, mappings, and therapeutic class data. Use DbActiveIntakeContextProvider, DbTherapeuticClassRepository, and DbInteractionRuleRepository to prove that warfarin is selected with vitamin K and only APPROVED rules are returned.

- [ ] **Step 5: Verify and commit**

Run:
~~~bash
uv run --group ai --group app pytest ai_worker/tests/scripts/test_seed_chat_evaluation_account.py ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/repositories/test_therapeutic_class_repository.py ai_worker/tests/repositories/test_interaction_rule_repository.py -q
uv run ruff check scripts/seed_chat_evaluation_account.py ai_worker/tests/scripts/test_seed_chat_evaluation_account.py
git diff --check
git add -- scripts/seed_chat_evaluation_account.py ai_worker/tests/scripts/test_seed_chat_evaluation_account.py
git commit -m "[feature/383][임경수] 활성 복약정보 평가 시드 추가"
~~~

## Task 3: Verify direct pair evidence metadata without co-occurrence expansion

**Files:**
- Modify: data/knowledge/manifests/interaction_annotations.yaml only if a reviewed direct source exists.
- Modify: ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py
- Modify: ai_worker/tests/rag/splitters/test_knowledge_splitter.py if chunk propagation requires coverage.
- Create: docs/experiments/2026-09-10-direct-pair-evidence-readiness.md

**Interfaces:**
- Consume document-scoped KnowledgeInteractionAnnotationRegistry entries.
- Produce an interaction pair key only when a chunk contains both reviewed aliases and the document is a direct relationship source.

- [ ] **Step 1: Write readiness tests**

1. The existing vitamin D-calcium MFDS annotation applies only to chunks containing both terms.
2. Vitamin-D-only and calcium-only chunks do not receive the pair key.
3. Magnesium-zinc stays unannotated until a reviewed direct relationship source is identified.

- [ ] **Step 2: Run RED/green according to source evidence**

Run: uv run --group ai pytest ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py -q

If no reviewed magnesium-zinc source is in the corpus, keep the negative test and document the missing-source decision. Do not add a pair key. If a direct source is found, add only its document ID and aliases required by the direct relation text, then rerun all tests.

- [ ] **Step 3: Record collection readiness**

Create docs/experiments/2026-09-10-direct-pair-evidence-readiness.md listing source document IDs, chunk eligibility, negative cases, baseline collection, and the no-embedding/no-activation gate.

- [ ] **Step 4: Verify and commit**

Run:
~~~bash
uv run --group ai pytest ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py ai_worker/tests/scripts/test_index_knowledge_release.py -q
uv run ruff check ai_worker/rag/metadata/interaction_annotation_registry.py ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py
git diff --check
git add -- data/knowledge/manifests/interaction_annotations.yaml ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py docs/experiments/2026-09-10-direct-pair-evidence-readiness.md
git commit -m "[feature/383][임경수] 직접 상호작용 근거 메타데이터 검증"
~~~

Stage only changed files; do not force-add an annotation manifest change when no reviewed magnesium-zinc source exists.

## Task 4: Preserve product provenance for drug-food official-guide priority

**Files:**
- Modify: ai_worker/schemas/medication_search.py
- Modify: ai_worker/domain/medication_question_resolver.py
- Modify: ai_worker/rag/query_builders/medication_knowledge_query_builder.py
- Modify: ai_worker/use_cases/answer_medication_question.py
- Modify: ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py
- Modify: ai_worker/tests/use_cases/test_answer_medication_question.py

**Interfaces:**
- Add medication_product_lookup_names: list[str] to MedicationKnowledgeQueryPlan.
- Preserve selected product/brand candidates before interaction resolution replaces a product with its trailing ingredient.
- _find_guide() uses these candidates only for a DRUG_FOOD interaction, then retains RAG behavior when no guide is found.

- [ ] **Step 1: Write failing query-plan test**

Create a typed catalog where the alias "타이레놀" resolves to product "타이레놀정500밀리그람(아세트아미노펜)" and "술" resolves to alcohol. Assert the interaction plan has drug entity "아세트아미노펜" plus medication_product_lookup_names containing the original product name.

- [ ] **Step 2: Write failing use-case tests**

1. "타이레놀과 술을 같이 먹어도 돼?" calls the guide repository with the resolved product first and preserves public RAG evidence.
2. Ingredient-only "아세트아미노펜과 술..." has no invented product candidate and uses RAG.
3. Product-name query with no guide result remains on RAG rather than returning an empty answer.

- [ ] **Step 3: Verify RED**

Run: uv run --group ai --group app pytest ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py ai_worker/tests/use_cases/test_answer_medication_question.py -q

Expected: current interaction substitution leaves an ingredient-only entity and does not persist a usable product guide candidate.

- [ ] **Step 4: Implement minimal provenance propagation**

Derive candidates from typed catalog output, never a Tylenol constant. Deduplicate in stable case-insensitive order and include the field in the existing query-plan hash. For DRUG_FOOD interaction, check resolved product candidates before existing generic request/context candidates. Keep non-interaction medication-guide behavior unchanged.

- [ ] **Step 5: Verify and commit**

Run:
~~~bash
uv run --group ai --group app pytest ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/safety/test_grounded_claim_validator.py -q
uv run ruff check ai_worker/schemas/medication_search.py ai_worker/domain/medication_question_resolver.py ai_worker/rag/query_builders/medication_knowledge_query_builder.py ai_worker/use_cases/answer_medication_question.py ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py ai_worker/tests/use_cases/test_answer_medication_question.py
git diff --check
git add -- ai_worker/schemas/medication_search.py ai_worker/domain/medication_question_resolver.py ai_worker/rag/query_builders/medication_knowledge_query_builder.py ai_worker/use_cases/answer_medication_question.py ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "[feature/383][임경수] 약-음식 제품 가이드 우선 조회 보완"
~~~

## Final verification and release gate

- [ ] Run all ai_worker tests, relevant provider/repository app tests, Ruff, and git diff --check.
- [ ] Inspect git status and stage only the planned feature files; do not stage user-generated HTML, OCR, Vite, output, or temporary files.
- [ ] Confirm no Aerich migration and no Qdrant/OpenAI external operation happened.
- [ ] Before collection creation, report the changed chunk count and request a separate approval naming the collection and OpenAI embedding count.
