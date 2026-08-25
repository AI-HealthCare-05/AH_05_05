# Knowledge Qdrant Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전처리된 약·영양제 `KnowledgeChunk`를 새 불변 Qdrant 컬렉션에 적재하고, 정답이 표시된 질문 세트로 검색 정확도와 P95를 평가한다.

**Architecture:** 기존 `GuidelineMetadata` 기반 저장소는 그대로 두고 `KnowledgeChunk` 전용 loader, Qdrant store, indexer, evaluator를 추가한다. 인덱싱과 평가는 CLI에서 명시적으로 실행하며, 평가를 통과하기 전에는 기존 Chat Core 설정이나 컬렉션을 변경하지 않는다.

**Tech Stack:** Python 3.13, Pydantic v2, qdrant-client, langchain-openai, PyYAML, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-25-knowledge-qdrant-pilot-design.md`

## Global Constraints

- 기존 `public_guidelines_small_v1`과 `QdrantGuidelineStore`를 변경하지 않는다.
- 인덱싱에는 `KnowledgeChunk.embedding_text`를 사용하고 인용에는 `content`를 사용한다.
- 동일 이름의 release 컬렉션을 자동 덮어쓰기 또는 자동 삭제하지 않는다.
- 검색 필터에는 `dataset_version`을 항상 포함한다.
- 실제 OpenAI/Qdrant 통합 실행은 CI 기본 테스트에서 제외한다.
- 모든 production behavior는 실패하는 테스트를 먼저 확인한 뒤 구현한다.

---

### Task 1: Knowledge release 로더

**Files:**
- Create: `ai_worker/rag/loaders/knowledge_chunk_loader.py`
- Test: `ai_worker/tests/rag/loaders/test_knowledge_chunk_loader.py`

**Interfaces:**
- Consumes: `KnowledgeChunk.model_validate_json(line)`, `Path`
- Produces: `KnowledgeChunkLoader.load(directory: Path, expected_dataset_version: str) -> list[KnowledgeChunk]`

- [ ] **Step 1: Write failing loader tests**

```python
def test_load_reads_sorted_jsonl_and_validates_release(tmp_path: Path) -> None:
    chunks = KnowledgeChunkLoader().load(
        tmp_path,
        expected_dataset_version="knowledge-pilot-v1",
    )
    assert [chunk.chunk_id for chunk in chunks] == ["a" * 64, "b" * 64]

def test_load_rejects_duplicate_chunk_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="중복"):
        KnowledgeChunkLoader().load(tmp_path, "knowledge-pilot-v1")

def test_load_rejects_mixed_dataset_or_ineligible_chunk(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dataset_version|인덱싱"):
        KnowledgeChunkLoader().load(tmp_path, "knowledge-pilot-v1")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_knowledge_chunk_loader.py -q
```

Expected: import failure because `knowledge_chunk_loader.py` does not exist.

- [ ] **Step 3: Implement strict JSONL loading**

Implementation requirements:

```python
class KnowledgeChunkLoader:
    def load(
        self,
        directory: Path,
        expected_dataset_version: str,
    ) -> list[KnowledgeChunk]:
        ...
```

Read `*.jsonl` in sorted path order, include file and line in validation errors, reject empty releases, duplicate chunk IDs, mixed versions, version mismatch, and `index_eligible=false`.

- [ ] **Step 4: Run loader tests and verify GREEN**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_knowledge_chunk_loader.py -q
```

Expected: all loader tests pass.

### Task 2: Knowledge 검색 스키마와 Qdrant 저장소

**Files:**
- Modify: `ai_worker/schemas/knowledge.py`
- Create: `ai_worker/rag/vectorstores/qdrant_knowledge_store.py`
- Test: `ai_worker/tests/rag/vectorstores/test_qdrant_knowledge_store.py`

**Interfaces:**
- Produces: `KnowledgeSearchFilter`, `KnowledgeSearchQuery`, `RetrievedKnowledgeChunk`
- Produces: `QdrantKnowledgeStore.create_release_collection()`, `upsert_chunks()`, `count_points()`, `search()`

- [ ] **Step 1: Write failing schema and in-memory Qdrant tests**

```python
async def test_create_release_collection_rejects_existing_collection() -> None:
    await store.create_release_collection()
    with pytest.raises(ValueError, match="이미 존재"):
        await store.create_release_collection()

async def test_search_always_filters_dataset_and_optional_ingredient() -> None:
    results = await store.search(
        [1.0, 0.0, 0.0],
        KnowledgeSearchQuery(
            query="비타민 B6 주의사항",
            dataset_version="knowledge-pilot-v1",
            ingredient_names=["비타민 B6"],
            limit=5,
        ),
    )
    assert [item.metadata.document_id for item in results] == ["vitamin-b6"]
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/vectorstores/test_qdrant_knowledge_store.py -q
```

Expected: missing schemas/store import failure.

- [ ] **Step 3: Implement schemas and immutable store**

Required public contracts:

```python
class KnowledgeSearchQuery(BaseModel):
    query: str
    dataset_version: str
    document_types: list[KnowledgeDocumentType] = []
    drug_names: list[str] = []
    ingredient_names: list[str] = []
    interaction_type: str | None = None
    special_populations: list[str] = []
    section_types: list[KnowledgeSectionType] = []
    limit: int = 5

class RetrievedKnowledgeChunk(KnowledgeChunk):
    point_id: str
    similarity_score: float
```

Store behavior:

```python
await store.create_release_collection()
await store.upsert_chunks(chunks, vectors)
count = await store.count_points()
results = await store.search(query_vector, search_query)
```

Use UUID5 of `chunk_id`, cosine distance, full payload, array-aware `MatchAny` filters, and exact dataset filter.

- [ ] **Step 4: Run store tests and verify GREEN**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/vectorstores/test_qdrant_knowledge_store.py -q
```

Expected: all store tests pass.

### Task 3: 배치 Knowledge 인덱서

**Files:**
- Create: `ai_worker/rag/indexers/knowledge_indexer.py`
- Test: `ai_worker/tests/rag/indexers/test_knowledge_indexer.py`

**Interfaces:**
- Consumes: `EmbeddingProvider`, `QdrantKnowledgeStore`, `list[KnowledgeChunk]`
- Produces: `KnowledgeIndexResult(dataset_version, collection_name, indexed_chunk_count)`

- [ ] **Step 1: Write failing batching and integrity tests**

```python
async def test_index_release_embeds_embedding_text_in_batches() -> None:
    result = await indexer.index_release(chunks)
    assert embedding_provider.batches == [["embed-1", "embed-2"], ["embed-3"]]
    assert result.indexed_chunk_count == 3

async def test_index_release_rejects_point_count_mismatch() -> None:
    with pytest.raises(ValueError, match="저장 건수"):
        await indexer.index_release(chunks)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/indexers/test_knowledge_indexer.py -q
```

Expected: missing indexer import failure.

- [ ] **Step 3: Implement minimal batch indexer**

```python
class KnowledgeIndexer:
    async def index_release(
        self,
        chunks: list[KnowledgeChunk],
    ) -> KnowledgeIndexResult:
        ...
```

Validate one dataset version, create a fresh collection once, embed and upsert in configured batches, and compare exact final point count with input count.

- [ ] **Step 4: Run indexer tests and verify GREEN**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/indexers/test_knowledge_indexer.py -q
```

Expected: all indexer tests pass.

### Task 4: 검색 평가 스키마와 평가기

**Files:**
- Create: `ai_worker/schemas/knowledge_evaluation.py`
- Create: `ai_worker/rag/evaluators/__init__.py`
- Create: `ai_worker/rag/evaluators/knowledge_retrieval_evaluator.py`
- Test: `ai_worker/tests/rag/evaluators/__init__.py`
- Test: `ai_worker/tests/rag/evaluators/test_knowledge_retrieval_evaluator.py`

**Interfaces:**
- Consumes: evaluation cases, `EmbeddingProvider`, `QdrantKnowledgeStore`, monotonic timer
- Produces: `KnowledgeEvaluationReport` with per-query results and aggregate metrics

- [ ] **Step 1: Write failing metric tests with hand-derived values**

```python
async def test_evaluate_computes_hit_mrr_precision_duplicates_and_p95() -> None:
    report = await evaluator.evaluate(cases)
    assert report.hit_at_5 == 0.5
    assert report.mrr == 0.25
    assert report.citation_accuracy == 0.5
    assert report.duplicate_retrieval_rate == 0.25
    assert report.search_p95_ms == 40.0

async def test_evaluate_counts_wrong_entity_mixing() -> None:
    report = await evaluator.evaluate([vitamin_b6_case])
    assert report.wrong_entity_mixing_count == 1
    assert report.passed is False
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/evaluators/test_knowledge_retrieval_evaluator.py -q
```

Expected: missing evaluator/schema import failure.

- [ ] **Step 3: Implement deterministic metrics**

Use nearest-rank percentile for P95: sort durations and choose `ceil(0.95 * n) - 1`. Hit and reciprocal rank use expected document IDs. Citation accuracy is relevant retrieved results divided by all retrieved results. Duplicate detection uses `content_hash`. Wrong entity mixing counts retrieved chunks carrying non-expected entities when expected entity lists are provided.

- [ ] **Step 4: Run evaluator tests and verify GREEN**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/rag/evaluators/test_knowledge_retrieval_evaluator.py -q
```

Expected: all evaluator tests pass.

### Task 5: 인덱싱·평가 CLI와 파일럿 질문 계약

**Files:**
- Create: `scripts/index_knowledge_release.py`
- Create: `scripts/evaluate_knowledge_retrieval.py`
- Create: `data/knowledge/evaluation/pilot_queries.yaml`
- Test: `ai_worker/tests/scripts/test_index_knowledge_release.py`
- Test: `ai_worker/tests/scripts/test_evaluate_knowledge_retrieval.py`

**Interfaces:**
- Produces CLI: `python -m scripts.index_knowledge_release`
- Produces CLI: `python -m scripts.evaluate_knowledge_retrieval`
- Produces JSON report at an explicit `--output` path

- [ ] **Step 1: Write failing CLI orchestration tests**

```python
async def test_index_cli_loads_release_and_closes_client(monkeypatch) -> None:
    exit_code = await run_cli(args)
    assert exit_code == 0
    assert fake_client.closed is True

async def test_evaluate_cli_returns_nonzero_when_quality_gate_fails(monkeypatch) -> None:
    exit_code = await run_cli(args)
    assert exit_code == 2
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/scripts/test_index_knowledge_release.py ai_worker/tests/scripts/test_evaluate_knowledge_retrieval.py -q
```

Expected: missing script import failure.

- [ ] **Step 3: Implement CLI wiring and YAML loader**

Index CLI must accept `--chunks-dir`, `--dataset-version`, `--collection`, `--embedding-batch-size`, and `--upsert-batch-size`. Evaluation CLI must accept `--evaluation-file`, `--dataset-version`, `--collection`, and `--output`. Both use `Config`, `OpenAIEmbeddingProvider`, and `AsyncQdrantClient`; both always close the client in `finally`.

The tracked `pilot_queries.yaml` contains only verified questions whose expected document IDs exist in current pilot JSONL. It must not contain copied source passages.

- [ ] **Step 4: Run CLI tests and verify GREEN**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests/scripts/test_index_knowledge_release.py ai_worker/tests/scripts/test_evaluate_knowledge_retrieval.py -q
```

Expected: all CLI tests pass.

### Task 6: 문서화와 전체 검증

**Files:**
- Modify: `data/knowledge/README.md`
- Modify: `data/knowledge/CHUNKING_STRATEGY.md`
- Modify: `.env.example` only if a non-destructive pilot default is required

**Interfaces:**
- Documents exact index/evaluation commands and collection safety policy.

- [ ] **Step 1: Run focused tests**

```bash
uv run --group ai --group dev python -m pytest \
  ai_worker/tests/rag/loaders/test_knowledge_chunk_loader.py \
  ai_worker/tests/rag/vectorstores/test_qdrant_knowledge_store.py \
  ai_worker/tests/rag/indexers/test_knowledge_indexer.py \
  ai_worker/tests/rag/evaluators/test_knowledge_retrieval_evaluator.py \
  ai_worker/tests/scripts/test_index_knowledge_release.py \
  ai_worker/tests/scripts/test_evaluate_knowledge_retrieval.py -q
```

- [ ] **Step 2: Run formatting and lint**

```bash
uv run --group dev ruff format ai_worker scripts
uv run --group dev ruff check ai_worker scripts
```

- [ ] **Step 3: Run complete AI Worker tests**

```bash
uv run --group ai --group dev python -m pytest ai_worker/tests -q
```

- [ ] **Step 4: Verify Git diff safety**

```bash
git diff --check
git status --short
```

Confirm no raw PDFs, processed JSONL, Qdrant volume, API key, or generated evaluation report is tracked.
