# Evidence-Grounded Chat Safety and Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task. Each task uses TDD and ends in a separate commit.

**Goal:** Improve the medication and supplement chat so it reliably distinguishes evidence-grounded drug facts from safe general guidance, retains only same-session references, and adopts retrieval/LLM enhancements only when measured evaluation supports them.

**Architecture:** Keep the existing deterministic resolution → query-plan → approved-rule/RDBMS → Qdrant → draft → LLM rewrite → grounded-validator pipeline as the safety boundary. Add small, typed policy components around that pipeline: evaluation contracts, risk context, fallback guidance, session reference state, retrieval expansion, and experiment adapters. Retrieval and model features remain disabled unless their documented acceptance rule passes.

**Tech Stack:** Python 3.12, Pydantic v2, LangChain LCEL, FastAPI service layer, Qdrant, MySQL/Tortoise, pytest, LangSmith tracing.

**Spec:** User-approved feature/359 goal in this task conversation.

## Global Constraints

- Drug efficacy, indication, dose, medication change, contraindication, and interaction claims require a product guide, approved rule, or retrieved authoritative evidence.
- Risk flags use only `YES`, `NO`, or `UNKNOWN`; `UNKNOWN` is never treated as absence of risk.
- General lifestyle and supplement guidance must be framed as non-personalized information and name an official confirmation route when evidence is incomplete.
- Do not store hidden chain-of-thought. Store and trace only typed structured interpretation fields and reason codes.
- Session reference memory is keyed by the current chat session and must never read a different session.
- Each experiment records hypothesis, baseline, variables, metrics, status (`SUCCESS`, `PARTIAL`, or `FAIL`), and the reason for that status in `docs/experiments/`.
- New retrieval/model behavior is default-off until its documented acceptance rule passes. No new embedding run or external paid API call is part of this plan.
- LangGraph is assessed in an ADR only; it is not added as a dependency or runtime component.

---

### Task 1: Lock the evaluation contract and baseline

**Files:**
- Modify: `data/knowledge/evaluation/chat_representative_queries.yaml`
- Modify: `ai_worker/schemas/chat_evaluation.py`
- Modify: `ai_worker/evaluation/chat_evaluator.py`
- Test: `ai_worker/tests/evaluation/test_chat_representative_queries.py`, `ai_worker/tests/evaluation/test_chat_evaluator.py`
- Create: `docs/experiments/2026-09-09-chat-contract-baseline.md`

**Produces:** Every case declares required and forbidden answer evidence, and the evaluator can explicitly fail an answer that contains a forbidden phrase or omits a required evidence marker.

- [x] Write a failing evaluation test using a deterministic answer containing `안전합니다` for a no-evidence interaction case; expect an `ANSWER_POLICY` failure.
- [x] Add typed `required_answer_markers` and `forbidden_answer_markers` to the manifest contract and compare normalized answer text in `ChatEvaluator`.
- [x] Add the 20 user-approved representative questions with expected route, sources, evidence markers, forbidden markers, and success criteria.
- [x] Run focused evaluation tests and record the non-production baseline contract. Commit follows after full stage verification.

### Task 2: Add typed risk context and answer policy

**Files:**
- Create: `ai_worker/domain/chat_risk_policy.py`
- Modify: `ai_worker/schemas/medication_chat.py`, `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/domain/test_chat_risk_policy.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-risk-policy.md`

**Produces:** A `YES/NO/UNKNOWN` risk context and deterministic answer-scope decisions for drug, supplement, and lifestyle questions.

- [x] Write failing tests for pregnancy/surgery/anticoagulant flags, including missing data becoming `UNKNOWN`.
- [x] Implement a pure policy evaluator that blocks personal dose/recommendation framing whenever a relevant flag is `YES` or `UNKNOWN`.
- [x] Add a trace-safe policy summary to the draft and test that the safety validator receives the restricted draft.
- [x] Record policy coverage and commit.

### Task 3: Provide safe alternative guidance when evidence is insufficient

**Files:**
- Create: `ai_worker/domain/evidence_gap_guidance.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/domain/test_evidence_gap_guidance.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-evidence-gap-guidance.md`

**Produces:** A deterministic six-part alternative guide: verified fact boundary, general guide, unknown boundary, official route, clinician checklist, disclaimer.

- [x] Write failing tests ensuring a missing drug-interaction result never says the combination is safe.
- [x] Implement a source-kind-aware guidance builder and wire it only into no-evidence/restricted paths.
- [x] Test official-route and checklist rendering without invented product facts.
- [x] Record success/failure examples and commit.

### Task 4: Resolve same-session references through structured memory

**Files:**
- Create: `ai_worker/domain/chat_session_reference_memory.py`
- Modify: `app/services/chat.py`, `ai_worker/schemas/medication_chat.py`, `ai_worker/use_cases/answer_medication_question.py`
- Test: `app/tests/chat_apis/test_chat_session_history_api.py`, `ai_worker/tests/domain/test_chat_session_reference_memory.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-session-reference-memory.md`

**Produces:** The current session's last grounded product/ingredient/interaction entities become an explicit request field; `그 약` and `그중` resolve only from that field.

- [x] Write a failing test showing `그 약의 복용법` resolves to the preceding session’s confirmed entity.
- [x] Write a failing cross-session test showing another session’s entity cannot resolve the reference.
- [x] Implement deterministic extraction from persisted same-session messages and explicit injection into the core request.
- [x] Record reference precision and cross-session isolation result, then commit.

### Task 5: Add small-to-big parent context retrieval

**Files:**
- Create: `ai_worker/rag/retrievers/parent_context_resolver.py`
- Modify: `ai_worker/rag/retrievers/medication_knowledge_retriever.py`, `ai_worker/schemas/knowledge.py`
- Test: `ai_worker/tests/rag/retrievers/test_parent_context_resolver.py`, `ai_worker/tests/rag/retrievers/test_medication_knowledge_retriever.py`
- Create: `docs/experiments/2026-09-09-small-to-big-retrieval.md`

**Produces:** Child chunks are selected for recall, then their matching parent section is attached only when document, section, and entity contracts agree.

- [x] Write failing tests for child-to-parent expansion and for rejecting a parent from another document/entity.
- [x] Implement a pure parent-context resolver over retrieved chunks/metadata; do not change collection data or issue external embeddings.
- [x] Add retrieval diagnostics for child count, parent count, and rejected parent mismatches.
- [x] Compare fixture recall/context contamination against child-only behavior, record it, and commit. Live-collection comparison remains `PARTIAL` until the fixed evaluation set is rerun.

### Task 6: Retry retrieval once only for evidence coverage gaps

**Files:**
- Create: `ai_worker/rag/query_builders/coverage_gap_query_expander.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`, `ai_worker/schemas/knowledge.py`
- Test: `ai_worker/tests/rag/query_builders/test_coverage_gap_query_expander.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-coverage-retry.md`

**Produces:** One deterministic query expansion/sub-query retrieval only when requested evidence sections are missing; repeated retries are impossible.

- [x] Write failing tests for a missing `CAUTION` section that causes one retry and for complete coverage that causes none.
- [x] Implement the expansion from typed entities and missing sections; merge only additional authoritative chunks.
- [x] Trace retry cause, query count, and coverage before/after without persisting question contents by default.
- [x] Record latency and coverage change, then commit. Live P50/P95 comparison remains `PARTIAL` until the fixed evaluation set is rerun.

### Task 7: Use conditional structured LLM interpretation

**Files:**
- Create: `ai_worker/chains/conditional_question_interpretation_chain.py`
- Modify: `ai_worker/chains/medication_query_plan_chain.py`, `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/chains/test_conditional_question_interpretation_chain.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-conditional-llm-interpretation.md`

**Produces:** A Pydantic structured output parser invoked only for low-confidence, multi-entity, or same-session reference questions; its result augments but cannot invent catalog entities.

- [x] Write failing tests proving high-confidence single-entity questions do not call the LLM chain.
- [x] Write failing tests proving model-proposed unknown entities are discarded.
- [x] Implement a typed request/response model and a policy gate; record only version, confidence, reason codes, and normalized output.
- [x] Compare rule-only vs conditional mode against the contract fixture and commit only the default-off experiment adapter if the live metric is unavailable. Live model comparison remains `PARTIAL`.

### Task 8: Evaluate new supplement registration safety deterministically

**Files:**
- Create: `ai_worker/domain/supplement_registration_safety.py`
- Modify: `ai_worker/domain/interfaces.py`, `ai_worker/schemas/medication_chat.py`
- Test: `ai_worker/tests/domain/test_supplement_registration_safety.py`
- Create: `docs/experiments/2026-09-09-supplement-registration-safety.md`

**Produces:** Deterministic duplicate ingredient, computable-total, approved-rule, and risk decisions; missing amount/unit/ingredient yields `UNKNOWN`.

- [x] Write failing cases for duplicate ingredients, an approved interaction rule, and incomplete unit/amount data.
- [x] Implement a pure evaluator that exposes decision factors and leaves natural-language explanation to the existing answer generator.
- [x] Ensure no LLM output can change the decision state in tests.
- [x] Record rule coverage and commit.

### Task 9: Build fatigue conversational triage policy

**Files:**
- Create: `ai_worker/domain/fatigue_conversation_policy.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/domain/test_fatigue_conversation_policy.py`, `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `docs/experiments/2026-09-09-fatigue-triage.md`

**Produces:** A question-first route for fatigue queries that asks about emergency signs, current medication/supplements, and lifestyle context without diagnosing or recommending a product.

- [x] Write failing tests for `요즘 피곤해` and a red-flag fatigue statement.
- [x] Implement a deterministic question set and emergency assistance copy boundary.
- [x] Verify that the response contains no diagnosis, dose, or product recommendation.
- [x] Record behavior and commit.

### Task 10: Add default-off reranker A/B evaluation

**Files:**
- Create: `ai_worker/evaluation/reranker_ab_evaluator.py`
- Create: `ai_worker/rag/rerankers/candidate_reranker.py`
- Modify: `ai_worker/schemas/medication_search_evaluation.py`
- Test: `ai_worker/tests/evaluation/test_reranker_ab_evaluator.py`, `ai_worker/tests/rag/rerankers/test_candidate_reranker.py`
- Create: `docs/experiments/2026-09-09-reranker-ab.md`

**Produces:** An offline reranker evaluator limited to cases whose gold document is in Top 30 but outside Top 5, with an explicit adoption decision.

- [x] Write failing tests for eligibility filtering and metric computation (`Hit@5`, `MRR`, wrong-target mixing, P95).
- [x] Implement a deterministic score adapter/test reranker interface; keep runtime reranking disabled.
- [x] Define success as non-decreasing safety metrics and source precision with an improvement in Hit@5 or MRR, under the documented P95 budget.
- [x] Record result; enable no runtime path unless the success rule is met; commit.

### Task 11: Decide LangGraph need with an ADR

**Files:**
- Create: `docs/adr/2026-09-09-langgraph-decision.md`
- Test: none; the ADR is a decision record backed by preceding experiment evidence.

**Produces:** A `defer`, `limited adoption`, or `adopt` decision for registration safety, fatigue interview, one retry, and human intervention flows.

- [x] Compare each flow’s state, branching, resumability, and operator-intervention needs with the existing typed use-case pipeline.
- [x] Document that current one-retry retrieval and deterministic safety checks do not justify a graph runtime.
- [x] Specify the exact threshold for reconsidering a graph: resumable multi-stage registration review or managed human intervention with persisted state.
- [x] Commit the ADR without adding LangGraph dependency or code.

## Completion Checklist

- [x] Every task has focused RED → GREEN test evidence.
- [x] Every task has a separate experiment/decision record and commit.
- [x] Full AI Worker suite and Ruff checks pass after the final task.
- [x] No untracked OCR, Vite, `output/`, `tmp/`, or `:memory:.ses` artifact is committed.
