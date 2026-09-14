# Pair-Scoped Interaction Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve every explicit interaction pair and restrict Chain 3 claims to pair-scoped evidence chunks.

**Architecture:** Keep the existing `N choose 2` planner and add regression coverage. Extend the reviewed annotation manifest with document-specific split boundaries, then split annotated pharmacy-review documents before metadata assignment. Strengthen the Chain 3 prompt so it cannot transform another interaction in the same source into a claim for the requested pair.

**Tech Stack:** Python 3.14, Pydantic, pytest, LangChain LCEL, Qdrant metadata contracts, YAML manifests.

**Spec:** `docs/superpowers/specs/2026-09-13-pair-scoped-interaction-evidence-design.md`

## Global Constraints

- Preserve existing user changes outside this feature.
- Assign an interaction pair key only when both entities and the reviewed evidence phrase occur in the same split chunk.
- Do not create a Qdrant collection or call embedding APIs.
- Use tests before production changes.

---

### Task 1: Preserve explicit pair combinations

**Files:**
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: `AnswerMedicationQuestionUseCase._interaction_pairs_for_entities`
- Produces: regression proof that A-B, A-C, B-C remain in `MedicationKnowledgeQueryPlan`.

- [x] **Step 1: Confirm the focused pair count and search-stimulus assertion**

The existing regression already verifies the three explicit pairs and their three pair-specific alternate queries; no planner change was needed.

```python
assert {(pair.left_name, pair.right_name) for pair in query_plan.interaction_pairs} == {
    ("마그네슘", "아연"),
    ("마그네슘", "칼슘"),
    ("아연", "칼슘"),
}
```

- [x] **Step 2: Run the focused test and verify pair preservation**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k explicit_interaction_pairs -q`

- [x] **Step 3: Keep the planner unchanged because all pairs are preserved**

- [x] **Step 4: Run the focused test again**

- [x] **Step 5: Run the affected use-case suite**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -q`

### Task 2: Add reviewed document split boundaries

**Files:**
- Modify: `ai_worker/rag/metadata/interaction_annotation_registry.py`
- Modify: `ai_worker/rag/splitters/knowledge_splitter.py`
- Modify: `data/knowledge/manifests/interaction_annotations.yaml`
- Test: `ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py`
- Test: `ai_worker/tests/rag/splitters/test_knowledge_splitter.py`

**Interfaces:**
- Consumes: reviewed YAML document annotation and source page content.
- Produces: ordered document-local boundaries used before pair metadata is assigned.

- [x] **Step 1: Write a failing registry test for document boundaries**

```python
assert registry.section_boundaries("reviewed-warfarin") == ["1. 차", "2. 캐모마일"]
```

- [x] **Step 2: Write a failing splitter test**

```python
chunks = splitter.split([page])
vitamin_k_chunk = next(chunk for chunk in chunks if "비타민 K" in chunk.content)
chamomile_chunk = next(chunk for chunk in chunks if "캐모마일" in chunk.content)
assert pair_key in vitamin_k_chunk.metadata.interaction_pair_keys
assert pair_key not in chamomile_chunk.metadata.interaction_pair_keys
```

- [x] **Step 3: Run both tests and verify RED**

Run: `uv run pytest ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py -q`

- [x] **Step 4: Add the manifest boundary model and registry accessor**

- [x] **Step 5: Split only documents with reviewed boundaries before chunk metadata extraction**

- [x] **Step 6: Add the vitamin K evidence phrase and document boundaries to the reviewed manifest**

- [x] **Step 7: Run both tests and verify GREEN**

### Task 3: Strengthen Chain 3 pair scope

**Files:**
- Modify: `ai_worker/llm/prompts/assets/medication_chat_prompt_v7.md`
- Test: `ai_worker/tests/llm/prompts/test_medication_chat_prompt.py`
- Test: `ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py`

**Interfaces:**
- Consumes: `EvidenceReasoningInput` with pair-scoped evidence items.
- Produces: prompt contract prohibiting independent third-entity interactions.

- [x] **Step 1: Add a failing prompt-contract test**

```python
assert "제3 성분의 독립 상호작용" in prompt_document.compiled_system
```

- [x] **Step 2: Retain the existing pair-key/evidence-ID fixture coverage**

The runtime schema already rejects a claim, action, or conflict evidence ID whose pair key differs from the requested pair. The new prompt contract covers third-entity prose within an otherwise valid source chunk.

- [x] **Step 3: Run focused tests and verify RED**

Run: `uv run pytest ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py -q`

- [x] **Step 4: Add the pair-scope constraint to the Evidence Reasoning system prompt**

- [x] **Step 5: Run focused tests and verify GREEN**

### Task 4: Full verification

**Files:**
- Verify only

- [x] **Step 1: Run format and targeted suites**

Run: `uv run ruff format --check ai_worker/rag/metadata/interaction_annotation_registry.py ai_worker/rag/splitters/knowledge_splitter.py ai_worker/chains/interaction_evidence_reasoning_chain.py ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py`

- [x] **Step 2: Run all affected tests**

Run: `uv run pytest ai_worker/tests/rag/metadata/test_interaction_annotation_registry.py ai_worker/tests/rag/splitters/test_knowledge_splitter.py ai_worker/tests/chains/test_interaction_evidence_reasoning_chain.py ai_worker/tests/llm/prompts/test_medication_chat_prompt.py ai_worker/tests/use_cases/test_answer_medication_question.py -q`

- [x] **Step 3: Confirm no Qdrant collection or embedding API call was made**

- [x] **Step 4: Report the collection release as a separate approval-required action**
