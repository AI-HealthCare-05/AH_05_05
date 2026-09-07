# AI Worker Boundary Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve current medication chat behavior while separating PDF repair, retrieval policy, and chat orchestration responsibilities.

**Architecture:** Keep the three public entry points unchanged. Extract pure or near-pure collaborators behind typed internal contracts; the existing classes remain thin facades that preserve ordering, diagnostics, and error handling.

**Tech Stack:** Python 3.13, Pydantic v2, LangChain Core LCEL, Qdrant async client, Tortoise repositories, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-08-ai-worker-boundary-refactor-design.md`

## Global Constraints

- Do not change Qdrant collection, MySQL schema, Aerich migration, API DTO, prompt text, score constants, or safety rules.
- Preserve dirty user files and stage only files owned by each task.
- Keep `KnowledgeSplitter.split`, `MedicationKnowledgeRetriever.search_with_diagnostics`, and `AnswerMedicationQuestionUseCase.execute` callable with their current signatures.
- Test before production extraction; compare existing observable results rather than only call counts.

---

### Task 1: Extract verified-document chunk repairers

**Files:**
- Create: `ai_worker/rag/splitters/repairers/__init__.py`
- Create: `ai_worker/rag/splitters/repairers/protocol.py`
- Create: `ai_worker/rag/splitters/repairers/registry.py`
- Create: `ai_worker/rag/splitters/repairers/*.py` grouped by reviewed research document family
- Modify: `ai_worker/rag/splitters/knowledge_splitter.py`
- Modify: `ai_worker/tests/rag/splitters/test_knowledge_splitter.py`
- Create: `ai_worker/tests/rag/splitters/repairers/test_registry.py`

**Interfaces:**
- Consumes: `list[KnowledgeChunk]` produced by `KnowledgeSplitter`.
- Produces: `DocumentChunkRepairer.apply(chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]`.
- Public preservation: `KnowledgeSplitter._repair_verified_document_chunks()` delegates to the registry and retains chunk-index rebuild behavior.

- [ ] **Step 1: Write failing registry tests**

```python
def test_registry_returns_original_chunks_when_document_has_no_repairer() -> None:
    chunks = [_chunk(document_id="unreviewed", content="원문")]

    assert DocumentChunkRepairRegistry().repair(chunks) == chunks


def test_registry_applies_verified_repairer_then_rebuilds_chunk_indexes() -> None:
    chunks = [_chunk(document_id=KNOWN_DOCUMENT_ID, content="before")]

    repaired = DocumentChunkRepairRegistry().repair(chunks)

    assert repaired[0].content == "after"
    assert repaired[0].metadata.chunk_index == 0
```

- [ ] **Step 2: Run the focused test and confirm the missing registry causes the failure**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/splitters/repairers/test_registry.py -q`

- [ ] **Step 3: Introduce the repair protocol and registry**

```python
class DocumentChunkRepairer(Protocol):
    document_id: str

    def apply(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]: ...


class DocumentChunkRepairRegistry:
    def repair(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        if not chunks:
            return chunks
        repairer = self._repairers.get(chunks[0].metadata.document_id)
        return chunks if repairer is None else repairer.apply(chunks)
```

- [ ] **Step 4: Move existing document-specific methods without changing their algorithms**

Move each existing verified document repair method and its private helpers into a repairer module. Keep generic heading recognition, token splitting, table grouping, and chunk building in `knowledge_splitter.py`.

- [ ] **Step 5: Run focused tests and existing splitter regression tests**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/splitters -q`

- [ ] **Step 6: Commit only Task 1 files**

```bash
git add ai_worker/rag/splitters ai_worker/tests/rag/splitters
git commit -m "[feature/263][임경수] 문서별 청킹 복원 규칙 분리"
```

### Task 2: Separate retrieval candidate, policy, and diagnostics stages

**Files:**
- Create: `ai_worker/rag/retrievers/candidate_retrieval.py`
- Create: `ai_worker/rag/retrievers/medication_knowledge_eligibility.py`
- Create: `ai_worker/rag/retrievers/medication_knowledge_ranking.py`
- Create: `ai_worker/rag/retrievers/medication_knowledge_diagnostics.py`
- Modify: `ai_worker/rag/retrievers/medication_knowledge_retriever.py`
- Modify: `ai_worker/tests/rag/retrievers/test_medication_knowledge_retriever.py`
- Create: `ai_worker/tests/rag/retrievers/test_medication_knowledge_ranking.py`

**Interfaces:**
- Consumes: `MedicationSearchExecutionPlan` and `RetrievedKnowledgeChunk` candidates.
- Produces: unchanged `KnowledgeRetrievalResult` and `KnowledgeRetrievalDiagnostics`.
- Public preservation: `MedicationKnowledgeRetriever.search_with_diagnostics()` remains the only integration entry point.

- [ ] **Step 1: Write failing policy equivalence tests**

```python
def test_ranking_policy_preserves_exact_entity_bonus() -> None:
    score = MedicationKnowledgeRankingPolicy().score(
        result=_result(score=0.70, ingredient_names=["마그네슘"]),
        plan=_plan(entity_names=["마그네슘"]),
    )

    assert score[0] == 0.82
```

- [ ] **Step 2: Run focused tests and confirm imports are absent**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/retrievers/test_medication_knowledge_ranking.py -q`

- [ ] **Step 3: Extract collaborators with unchanged constants and predicates**

`CandidateRetriever` owns concurrent query embedding and tier calls. `EligibilityPolicy` owns score/entity/pair acceptance. `RankingPolicy` owns the current tuple score. `DiagnosticsBuilder` owns candidate observation serialization. The facade calls them in the existing order.

- [ ] **Step 4: Add facade regression assertions**

Extend existing tests to compare selected chunk IDs, `attempted_search_tiers`, `selected_search_tier`, rejection counts, and diagnostics adjusted scores for dense and hybrid fixtures.

- [ ] **Step 5: Run Retriever tests**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/retrievers/test_medication_knowledge_retriever.py ai_worker/tests/rag/vectorstores -q`

- [ ] **Step 6: Commit only Task 2 files**

```bash
git add ai_worker/rag/retrievers ai_worker/tests/rag/retrievers ai_worker/tests/rag/vectorstores
git commit -m "[feature/263][임경수] 의약품 검색 정책과 진단 단계 분리"
```

### Task 3: Make the medication chat pipeline stages explicit

**Files:**
- Create: `ai_worker/use_cases/medication_chat_pipeline.py`
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `ai_worker/tests/use_cases/test_medication_chat_pipeline.py`

**Interfaces:**
- Consumes: `MedicationChatRequest`, active context, query plan, repositories, and retrieval result.
- Produces: internal `PreparedMedicationQuestion`, `MedicationEvidenceBundle`, and `MedicationChatDraft` objects.
- Public preservation: `AnswerMedicationQuestionUseCase.execute(request, limit, progress_callback)` returns the unchanged `MedicationChatResult`.

- [ ] **Step 1: Write failing stage-order tests**

```python
async def test_pipeline_runs_safety_validation_after_llm_rewrite() -> None:
    events: list[str] = []
    use_case = _use_case(events=events)

    await use_case.execute(_request())

    assert events.index("llm.generate") < events.index("safety.validate")
```

- [ ] **Step 2: Run the focused test and confirm the stage module is absent**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/use_cases/test_medication_chat_pipeline.py -q`

- [ ] **Step 3: Extract immutable pipeline outputs and stages**

Use frozen dataclasses for stage handoff. Keep trace span names, progress notifications, all early clarification/no-evidence return conditions, and exception-to-fallback behavior in the same relative order.

- [ ] **Step 4: Keep the Use Case as a thin orchestrator**

`execute()` loads context, invokes stages in order, and owns the final `GroundedClaimValidator.validate()` call. It must not alter route or source construction behavior.

- [ ] **Step 5: Run Use Case, generator, safety, and chain tests**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/use_cases/test_medication_chat_pipeline.py ai_worker/tests/llm/generators/test_medication_answer_generator.py ai_worker/tests/safety/test_grounded_claim_validator.py ai_worker/tests/chains -q`

- [ ] **Step 6: Commit only Task 3 files**

```bash
git add ai_worker/use_cases ai_worker/tests/use_cases ai_worker/tests/llm ai_worker/tests/safety ai_worker/tests/chains
git commit -m "[feature/263][임경수] 약영양제 채팅 처리 단계 분리"
```

### Task 4: Final behavior-preservation verification

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-ai-worker-boundary-refactor-design.md`
- Modify: `docs/superpowers/plans/2026-09-08-ai-worker-boundary-refactor.md`

- [ ] **Step 1: Run AI Worker full lint and tests**

Run: `uv run --group dev ruff check ai_worker && uv run --group ai --group dev python -m pytest ai_worker/tests -q`

- [ ] **Step 2: Run whitespace and migration-state checks**

Run: `git diff --check && uv run --group app aerich heads`

- [ ] **Step 3: Record actual verification outcomes and commit the plan documents**

```bash
git add docs/superpowers/specs/2026-09-08-ai-worker-boundary-refactor-design.md docs/superpowers/plans/2026-09-08-ai-worker-boundary-refactor.md
git commit -m "[feature/263][임경수] AI Worker 리팩터링 검증 기록"
```

### Deferred experiment branches

이 작업은 `feature/263`의 단일 PR에 포함하지 않는다. 리팩터링 PR이 merge된 뒤 최신 `main`에서 아래 실험 브랜치를 새로 만든다.

- `feature/<number>-reranker-evaluation`: Candidate Retrieval·Eligibility·Ranking 기준선을 바탕으로 reranker만 평가한다.
- `feature/<number>-chat-history-memory`: 세션 이력 조회와 메모리 안전 한계만 독립적으로 평가한다.

## 구현·검증 결과

- 청킹: 문서 ID별 복원 규칙 등록을 `repairers` registry로 분리하고, 기존 `KnowledgeSplitter`의 청크 재생성과 공개 진입점을 유지했다.
- 검색: 후보 조회 I/O, 적합성 판정, 정렬·다양성 선택, 진단 조립을 별도 컴포넌트로 분리했다. 기존 유사도 기준·metadata boost·단계적 검색 순서는 변경하지 않았다.
- 채팅: 질문 준비, 근거 묶음, 결정론적 초안을 불변 단계 객체로 전달하도록 정리했다. LLM 정제 뒤 `GroundedClaimValidator`를 실행하는 안전성 순서는 유지했다.
- 2026-09-08 검증: `ruff check ai_worker`, `pytest ai_worker/tests -q` → **917 passed, 1 skipped**. `aerich heads` → **No available heads**. `git diff --check` 통과.
