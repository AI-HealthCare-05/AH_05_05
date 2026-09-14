# V16 Chat Evidence and Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve explicit question pairs through V16 retrieval and render concise, evidence-grounded medication and supplement answers.

**Architecture:** Chain 2 keeps explicit interaction targets and introduces a source-backed supplement function-goal path. Chain 3 verifies each interaction pair independently. Chain 4 receives server-owned display labels and applies a structural guard after LLM summarization.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, LangChain LCEL, OpenAI structured output, Qdrant, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-14-v16-chat-evidence-output-design.md`

## Global Constraints

- Keep `medication_knowledge_full_v16_te3large_3072_dot` and its metadata unchanged.
- Do not introduce unsupported medical claims, dosage values, or safety conclusions.
- Preserve explicit interaction targets ahead of active-intake expansion.
- Display labels are deterministic; LLM output supplies concise grounded prose only.
- Do not edit existing untracked V16 release or OCR temporary files.

---

### Task 1: Preserve explicit interaction pairs in Chain 2

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: `MedicationKnowledgeQueryPlan.entities`, `interaction_pairs`, `ActiveIntakeContext`.
- Produces: an execution plan whose explicit `interaction_pair_keys` are not replaced by active-intake pairs.

- [ ] **Step 1: Write failing tests**

```python
async def test_explicit_warfarin_vitamin_k_pair_is_not_replaced_by_active_intake() -> None:
    result = await use_case.execute(build_request("와파린과 비타민 K 영양제를 같이 먹어도 되나요?"))
    assert result.search_observation.query_plan.interaction_pair_keys == [warfarin_vitamin_k_key]
    assert result.route is MedicationChatRoute.INTERACTION
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k explicit_warfarin_vitamin_k -q`

- [ ] **Step 3: Implement the minimal planning guard**

```python
if query_plan.interaction_pairs:
    return planning
```

Place the guard before active-intake pair rebuilding. Keep active-intake expansion for entity-free personal questions.

- [ ] **Step 4: Re-run the focused test and relevant active-intake tests**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k 'warfarin_vitamin_k or active_intake' -q`

### Task 2: Add a supplement function-goal retrieval path

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/domain/medication_question_resolver.py` only if a reusable resolver predicate is required
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: source-backed supplement function chunks and a question without a product entity.
- Produces: `SUPPLEMENT_GUIDE` with retrieved evidence, rather than `CLARIFICATION`.

- [ ] **Step 1: Write a failing test**

```python
async def test_sleep_quality_function_goal_uses_grounded_supplement_evidence() -> None:
    result = await use_case.execute(build_request("수면의 질 개선과 관련된 건강기능식품 기능 정보가 있나요?"))
    assert result.route is MedicationChatRoute.SUPPLEMENT_GUIDE
    assert "제품명 또는 복용 목적" not in result.answer
    assert result.sources
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k sleep_quality_function_goal -q`

- [ ] **Step 3: Implement source-backed function-goal classification**

```python
if is_supplement_function_goal(question) and has_supplement_function_evidence(chunks):
    return MedicationChatRoute.SUPPLEMENT_GUIDE
```

The predicate identifies a functional outcome request, not a product recommendation. The answer lists only names present in retrieved supplement-function evidence.

- [ ] **Step 4: Re-run focused supplement tests**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k 'sleep_quality_function_goal or supplement' -q`

### Task 3: Verify pair-specific V16 evidence in Chain 3

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Test: `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Test: `ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py`

**Interfaces:**
- Consumes: `RetrievedKnowledgeChunk.metadata.interaction_pair_keys`, requested `MedicationInteractionQueryPair` values.
- Produces: `MedicationEvidenceCoverage.verified_interaction_pair_keys` and pair-local claims.

- [ ] **Step 1: Write failing tests**

```python
async def test_calcium_iron_direct_chunk_marks_requested_pair_verified() -> None:
    result = await use_case.execute(build_request("칼슘을 철분과 함께 먹으면 흡수에 영향이 있나요?"))
    assert calcium_iron_key in result.evidence_coverage.verified_interaction_pair_keys
    assert "**[칼슘-철분]**" in result.answer
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py -k calcium_iron_direct_chunk -q`

- [ ] **Step 3: Implement exact pair verification**

```python
verified_pair_keys = {
    pair.pair_key
    for pair in requested_pairs
    if any(pair.pair_key in chunk.metadata.interaction_pair_keys for chunk in interaction_chunks)
}
```

Pass only pair-matching chunks to evidence reasoning. Keep generic chunks retrievable but do not turn them into interaction claims.

- [ ] **Step 4: Re-run Chain 3 tests**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py -k 'calcium_iron or interaction' -q`

### Task 4: Enforce Chain 4 answer structure and concise subject sections

**Files:**
- Modify: `ai_worker/llm/prompts/medication_chat_prompt.py`
- Modify: `ai_worker/llm/generators/medication_answer_generator.py`
- Modify: `ai_worker/llm/assemblers/medication_answer_assembler.py`
- Modify: `ai_worker/llm/prompts/assets/medication_chat_prompt_v8.md`
- Test: `ai_worker/tests/llm/generators/test_medication_answer_generator.py`
- Test: `ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py`

**Interfaces:**
- Consumes: resolved display subject, draft section headings, requested question pairs, and generated `MedicationAnswerPayload`.
- Produces: pair-labelled, short-bullet markdown without raw internal section titles.

- [ ] **Step 1: Write failing tests**

```python
def test_generated_answer_restores_missing_question_pair_heading() -> None:
    answer = normalize_answer_layout(
        generated_answer="🔁 **질문 상호작용**\n- 흡수가 줄 수 있습니다.",
        required_pair_labels=["[펙소페나딘-자몽주스]"],
    )
    assert "**[펙소페나딘-자몽주스]**" in answer

def test_adverse_event_answer_uses_subject_and_adverse_event_section() -> None:
    answer = assemble_subject_sections(subject="독사조신", section="ADVERSE_EVENT", facts=["어지러움 사례가 보고되었습니다."])
    assert answer.startswith("**독사조신**")
    assert "🚨 **이상반응**" in answer
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `uv run pytest ai_worker/tests/llm/generators/test_medication_answer_generator.py ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py -k 'pair_heading or adverse_event_subject' -q`

- [ ] **Step 3: Implement the structural output contract**

```python
payload["display_subject"] = resolved_subject
payload["required_question_pair_labels"] = pair_labels
final_answer = enforce_answer_layout(generated_answer, display_subject, pair_labels)
```

`enforce_answer_layout` may add known labels and move existing grounded bullets. It must not synthesize a claim. The prompt requires one factual point per concise bullet and excludes `공공자료 추가 설명`.

- [ ] **Step 4: Re-run answer-generation tests**

Run: `uv run pytest ai_worker/tests/llm/generators/test_medication_answer_generator.py ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py -q`

### Task 5: Verify the integrated V16 cases

**Files:**
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Test: `ai_worker/tests/llm/prompts/test_medication_chat_prompt.py`

- [ ] **Step 1: Add integrated regression cases**

Cover doxazosin adverse-event summary, fexofenadine two-food pairs, warfarin–vitamin K, calcium–iron, and sleep-quality functional guidance.

- [ ] **Step 2: Run target tests**

Run: `uv run pytest ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/llm/generators/test_medication_answer_generator.py ai_worker/tests/llm/assemblers/test_medication_answer_assembler.py ai_worker/tests/llm/prompts/test_medication_chat_prompt.py -q`

- [ ] **Step 3: Run style checks**

Run: `uv run ruff format --check ai_worker && uv run ruff check ai_worker`

- [ ] **Step 4: Manually retest the five acceptance questions against V16**

Restart only the AI Worker/FastAPI service if source mounting requires it. Record route, source count, pair labels, and final sections.
