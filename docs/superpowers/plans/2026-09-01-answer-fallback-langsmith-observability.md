# Answer Fallback LangSmith Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `OpenAIMedicationAnswerGenerator`의 재작성 성공·생략·초안 fallback·실패를 명시적 결과 계약으로 반환하고 LangSmith `llm.generate` span에서 원인 코드를 확인할 수 있게 한다.

**Architecture:** 생성 결과와 관측값을 `MedicationAnswerGenerationOutcome`으로 묶어 호출자에게 반환한다. Grounding 검사는 boolean 대신 안정적인 enum 이유를 반환하고, use case는 원문 대신 상태·이유·SHA-256만 LangSmith에 기록한다.

**Tech Stack:** Python 3.13, Pydantic 2, LangChain OpenAI, LangSmith, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-01-reference-data-and-answer-fallback-observability-design.md`

## Global Constraints

- API가 반환하는 `MedicationChatResult` JSON 계약은 변경하지 않는다.
- 질문·초안·생성 답변 원문은 커스텀 span 출력에 넣지 않는다.
- OpenAI 오류는 기존처럼 `ChatAnswerGenerationError`로 전달한다.
- LangSmith 오류는 비즈니스 답변을 중단하지 않는다.
- fallback 이유는 enum으로 제한한다.

---

### Task 1: 생성 결과와 fallback 이유 스키마

**Files:**
- Modify: `ai_worker/schemas/medication_chat.py`
- Modify: `ai_worker/tests/schemas/test_medication_chat_schema.py`

**Interfaces:**
- Produces: `MedicationAnswerRewriteStatus`, `MedicationAnswerFallbackReason`, `MedicationAnswerGenerationObservation`, `MedicationAnswerGenerationOutcome`

- [ ] **Step 1: Write failing schema tests**

```python
def test_generation_outcome_keeps_observation_out_of_chat_result() -> None:
    outcome = MedicationAnswerGenerationOutcome(
        result=build_result(),
        observation=MedicationAnswerGenerationObservation(
            status=MedicationAnswerRewriteStatus.DRAFT_FALLBACK,
            fallback_used=True,
            fallback_reason=MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT,
            draft_answer_hash="a" * 64,
            generated_answer_hash="b" * 64,
        ),
    )
    assert "observation" not in outcome.result.model_dump()
    assert outcome.observation.fallback_used is True
```

Add validation tests: hash must be 64 lowercase hex; `REWRITTEN` cannot have fallback reason; `DRAFT_FALLBACK` requires one.

- [ ] **Step 2: Verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/schemas/test_medication_chat_schema.py -q
```

Expected: FAIL because the generation outcome types do not exist.

- [ ] **Step 3: Implement minimal enums and Pydantic models**

Use the exact statuses and reason codes from the spec. Keep observations outside `MedicationChatResult` so HTTP response serialization remains unchanged.

- [ ] **Step 4: Verify and commit**

```bash
uv run --group dev ruff check ai_worker/schemas/medication_chat.py ai_worker/tests/schemas/test_medication_chat_schema.py
uv run --group ai --group dev python -m pytest ai_worker/tests/schemas/test_medication_chat_schema.py -q

git add ai_worker/schemas/medication_chat.py ai_worker/tests/schemas/test_medication_chat_schema.py
git commit -m "[feature/199][임경수] 답변 재작성 관측 결과 계약 추가"
```

### Task 2: Generator가 명시적 outcome을 반환

**Files:**
- Modify: `ai_worker/domain/interfaces.py`
- Modify: `ai_worker/llm/generators/medication_answer_generator.py`
- Modify: `ai_worker/tests/llm/generators/test_medication_answer_generator.py`

**Interfaces:**
- Consumes: Task 1 outcome models
- Produces: `MedicationAnswerGenerator.generate(...) -> MedicationAnswerGenerationOutcome`

- [ ] **Step 1: Change existing tests to assert outcomes first**

Add or update tests for:

- successful rewrite → `REWRITTEN`, no fallback;
- no sources → `SKIPPED/NO_GROUNDED_SOURCES`;
- clarification → `SKIPPED/CLARIFICATION_REQUIRED`;
- generated dosage absent from draft → `DRAFT_FALLBACK/GENERATED_DOSAGE_NOT_IN_DRAFT`;
- generated safety assertion absent from draft → `DRAFT_FALLBACK/UNSUPPORTED_SAFETY_ASSERTION`;
- both grounding checks fail → safety assertion reason wins;
- OpenAI error → `ChatAnswerGenerationError.reason_code == CLIENT_ERROR`.

- [ ] **Step 2: Run and verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/llm/generators/test_medication_answer_generator.py -q
```

Expected: FAIL because `generate()` still returns `MedicationChatResult` and `_is_grounded_rewrite()` only returns boolean.

- [ ] **Step 3: Implement reason-returning grounding checks**

Replace `_is_grounded_rewrite()` with:

```python
@classmethod
def _grounding_failure_reason(cls, *, draft_answer: str, generated_answer: str) -> MedicationAnswerFallbackReason | None:
    if cls._contains_unsupported_safety_assertion(draft_answer, generated_answer):
        return MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION
    if cls._contains_new_dosage(draft_answer, generated_answer):
        return MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT
    return None
```

Hash normalized UTF-8 text with SHA-256. For skipped LLM calls, `generated_answer_hash` is `None`.

- [ ] **Step 4: Add safe error reason code**

Extend `ChatAnswerGenerationError` with a constructor accepting `reason_code: str`, defaulting to `CLIENT_ERROR` for this generator. Do not expose the caught provider exception text.

- [ ] **Step 5: Verify and commit**

```bash
uv run --group dev ruff check ai_worker/domain/interfaces.py ai_worker/domain/errors.py ai_worker/llm/generators/medication_answer_generator.py ai_worker/tests/llm/generators/test_medication_answer_generator.py
uv run --group ai --group dev python -m pytest ai_worker/tests/llm/generators/test_medication_answer_generator.py -q

git add ai_worker/domain/interfaces.py ai_worker/domain/errors.py ai_worker/llm/generators/medication_answer_generator.py ai_worker/tests/llm/generators/test_medication_answer_generator.py
git commit -m "[feature/199][임경수] OpenAI 초안 fallback 원인 구조화"
```

### Task 3: Use case와 테스트 doubles를 새 계약으로 전환

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`

**Interfaces:**
- Consumes: `MedicationAnswerGenerationOutcome`
- Produces: unchanged final `MedicationChatResult`

- [ ] **Step 1: Write failing use-case trace tests**

Assert `llm.generate` outputs for rewritten, fallback, skipped, and provider-error paths. Required keys:

```python
assert llm_outputs == {
    "rewrite_status": "DRAFT_FALLBACK",
    "fallback_used": True,
    "fallback_reason": "GENERATED_DOSAGE_NOT_IN_DRAFT",
    "draft_answer_hash": "a" * 64,
    "generated_answer_hash": "b" * 64,
    "route": "MEDICATION_GUIDE",
    "source_count": 1,
}
```

Also assert the serialized span output does not contain the question, draft answer, or generated answer.

- [ ] **Step 2: Verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/use_cases/test_answer_medication_question.py -q
```

Expected: FAIL because the use case reads `MedicationChatResult` directly and emits only route/source count.

- [ ] **Step 3: Implement outcome unpacking and span output**

The use case receives `outcome`, compacts `outcome.result.answer`, records `outcome.observation`, and continues safety validation with the result. Catch `ChatAnswerGenerationError`, call `llm_span.end()` with `rewrite_status=FAILED`, `fallback_reason=error.reason_code`, then re-raise.

- [ ] **Step 4: Update all fakes without changing behavior**

`ai_worker/tests/use_cases/test_answer_medication_question.py`의 fake generator는 각 테스트 시나리오에 맞는 `REWRITTEN` 또는 `SKIPPED` outcome을 반환한다. 기존 응답·안전성 assertion은 약화하지 않는다.

- [ ] **Step 5: Verify and commit**

```bash
uv run --group dev ruff check ai_worker/use_cases/answer_medication_question.py ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests app/tests
uv run --group ai --group app --group dev python -m pytest ai_worker/tests/use_cases/test_answer_medication_question.py app/tests/chat_apis -q

git add ai_worker/use_cases/answer_medication_question.py ai_worker/tests/use_cases/test_answer_medication_question.py
git commit -m "[feature/199][임경수] LangSmith에 답변 fallback 원인 기록"
```

### Task 4: 전체 회귀 및 LangSmith 실제 검증

**Files:**
- No planned production file changes

- [ ] **Step 1: Run focused suites**

```bash
uv run --group ai --group app --group dev python -m pytest \
  ai_worker/tests/llm/generators/test_medication_answer_generator.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py \
  ai_worker/tests/observability \
  app/tests/chat_apis -q
```

- [ ] **Step 2: Run full lint and tests**

```bash
uv run --group dev ruff check ai_worker app scripts tests
uv run --group ai --group app --group dev python -m pytest ai_worker/tests app/tests tests -q
git diff --check
```

- [ ] **Step 3: Verify a real fallback trace**

With development LangSmith configuration enabled, run the generator integration fixture that introduces a dosage not present in the deterministic draft. Confirm `llm.generate` shows `DRAFT_FALLBACK` and `GENERATED_DOSAGE_NOT_IN_DRAFT` while the final answer remains the safe draft.

- [ ] **Step 4: Verify a normal rewrite trace**

Submit a standard grounded question and confirm `REWRITTEN`, `fallback_used=false`, both hashes present, and no answer text in custom span outputs.
