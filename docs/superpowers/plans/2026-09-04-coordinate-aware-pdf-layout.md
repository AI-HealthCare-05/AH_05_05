# Coordinate-Aware PDF Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 연구·허가 PDF의 표 셀 소속과 다단 읽기 순서를 좌표로 복원하고, 구조 안전성을 검증하지 못한 문서를 Qdrant 인덱싱 전에 차단한다.

**Architecture:** `pdfplumber` 좌표 추출을 독립 모듈에 격리하고 `KnowledgePdfLoader`가 구조화 블록을 만드는 방식으로 기존 pypdf 경로를 확장한다. Splitter는 표 블록을 행 경계로 별도 청킹하며, pilot service가 표·읽기 순서 검증 오류를 자동 `BLOCKED` 상태로 승격한다.

**Tech Stack:** Python 3.13, Pydantic, pypdf, pdfplumber, LangChain text splitters, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-04-coordinate-aware-pdf-layout-design.md`

## Global Constraints

- 기존 `KnowledgePage.content` 입력과 pypdf 기반 추출은 하위 호환을 유지한다.
- 좌표 기반 추출은 우선 `RESEARCH_ARTICLE`, `REGULATORY_DRUG_LABEL`에만 적용한다.
- 표 행을 둘로 자르지 않고 표 청크 overlap은 항상 0이다.
- 검증하지 못한 표나 다단 순서를 추측하여 Qdrant 근거로 사용하지 않는다.
- 대표 문서 4개만 재전처리하고 전체 PDF 처리·임베딩·Qdrant 생성은 하지 않는다.
- 사용자·팀원의 기존 미커밋 파일과 OCR 산출물은 수정하거나 삭제하지 않는다.

---

### Task 1: 구조화 페이지·표 스키마

**Files:**
- Modify: `ai_worker/schemas/knowledge.py`
- Test: `ai_worker/tests/schemas/test_knowledge_schema.py`

**Interfaces:**
- Consumes: 기존 `KnowledgeMetadata`, `KnowledgePage`, `KnowledgeChunkMetadata`
- Produces: `KnowledgeContentKind`, `KnowledgeBoundingBox`, `KnowledgeTableRow`, `KnowledgePageBlock`, `KnowledgePage.blocks`, `KnowledgeChunkMetadata.content_kind`

- [ ] **Step 1: Write the failing schema tests**

```python
def test_page_accepts_ordered_text_and_table_blocks(metadata):
    page = KnowledgePage(
        content="제목\n성분=철분 | 결과=감소",
        metadata=metadata,
        page_number=1,
        blocks=[
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TEXT,
                order=0,
                bbox=KnowledgeBoundingBox(x0=0, top=0, x1=500, bottom=40),
                content="제목",
            ),
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TABLE,
                order=1,
                bbox=KnowledgeBoundingBox(x0=0, top=50, x1=500, bottom=200),
                content="성분=철분 | 결과=감소",
                headers=["성분", "결과"],
                rows=[KnowledgeTableRow(cells=["철분", "감소"])],
                column_count=2,
            ),
        ],
    )
    assert page.blocks[1].column_count == 2


def test_legacy_page_without_blocks_remains_valid(metadata):
    assert KnowledgePage(content="본문", metadata=metadata, page_number=1).blocks == []
```

- [ ] **Step 2: Run the schema tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/schemas/test_knowledge_schema.py -q`

Expected: import or validation failure because the structured block types do not exist.

- [ ] **Step 3: Implement the schema types**

Add a `TEXT`/`TABLE` enum, a PDF coordinate model that permits negative CropBox coordinates while validating `x1 >= x0` and `bottom >= top`, table rows, and page blocks. Add `blocks: list[KnowledgePageBlock] = Field(default_factory=list)` and `content_kind: KnowledgeContentKind = KnowledgeContentKind.TEXT`.

- [ ] **Step 4: Run schema tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/schemas/test_knowledge_schema.py -q`

Expected: PASS.

### Task 2: 좌표 추출·표 행 복원기

**Files:**
- Create: `ai_worker/rag/loaders/pdf_layout_extractor.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py`

**Interfaces:**
- Consumes: `pdfplumber.Page`, `KnowledgeBoundingBox`, `KnowledgePageBlock`
- Produces: `PdfLayoutExtraction(blocks, warnings)`, `PdfLayoutExtractor.extract(page) -> PdfLayoutExtraction`

- [ ] **Step 1: Write failing tests with a fake coordinate page**

```python
def test_extract_separates_table_words_and_serializes_rows():
    extraction = PdfLayoutExtractor().extract(fake_page_with_two_column_table())
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == ["Ingredient", "Result"]
    assert table.rows[0].cells == ["Iron", "Reduced absorption"]
    assert table.content == "Ingredient=Iron | Result=Reduced absorption"
    assert "Iron" not in next(block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT)


def test_extract_marks_mismatched_table_row_unsafe():
    extraction = PdfLayoutExtractor().extract(fake_page_with_missing_cell())
    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE in extraction.warnings
```

- [ ] **Step 2: Run extractor tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py -q`

Expected: module import failure.

- [ ] **Step 3: Add pdfplumber dependency**

Run: `uv add --group ai pdfplumber`

Expected: `pyproject.toml` and `uv.lock` contain `pdfplumber` and its transitive dependencies.

- [ ] **Step 4: Implement coordinate primitives and table serialization**

Implement word-to-bbox checks, table region exclusion, row/column normalization, explicit `header=value` serialization, and `TABLE_STRUCTURE_UNSAFE` warnings for column-count or source-token loss. Do not forward-fill ordinary empty cells; only expand `same as ...` references with the previous row context in a separate `참조 행` suffix.

- [ ] **Step 5: Run extractor tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py -q`

Expected: PASS.

### Task 3: 다단 읽기 순서와 보존 검사

**Files:**
- Modify: `ai_worker/rag/loaders/pdf_layout_extractor.py`
- Test: `ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py`

**Interfaces:**
- Consumes: 표 밖 `extract_words()` 결과와 페이지 width/height
- Produces: `TEXT` blocks ordered as top full-width, left column, right column, bottom full-width; `READING_ORDER_UNSAFE` warning

- [ ] **Step 1: Write failing multi-column tests**

```python
def test_orders_spanning_title_before_left_and_right_columns():
    extraction = PdfLayoutExtractor().extract(fake_two_column_page())
    assert [block.content for block in extraction.blocks] == [
        "Article title",
        "Left one\nLeft two",
        "Right one\nRight two",
        "Page footer",
    ]


def test_marks_duplicate_word_assignment_unsafe():
    extraction = PdfLayoutExtractor().extract(fake_page_with_duplicate_word_assignment())
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in extraction.warnings
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py -q`

Expected: order assertion and warning assertion fail.

- [ ] **Step 3: Implement deterministic reading order**

Cluster words into lines by vertical tolerance, classify full-width versus left/right blocks using the page midpoint and horizontal coverage, then sort by the approved order. Compare stable source word identifiers with assigned identifiers; any missing or duplicate identifier emits `READING_ORDER_UNSAFE`.

- [ ] **Step 4: Run extractor tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_pdf_layout_extractor.py -q`

Expected: PASS.

### Task 4: KnowledgePdfLoader 통합과 fallback

**Files:**
- Modify: `ai_worker/rag/loaders/knowledge_pdf_loader.py`
- Test: `ai_worker/tests/rag/loaders/test_knowledge_pdf_loader.py`

**Interfaces:**
- Consumes: `PdfLayoutExtractor.extract(pdfplumber_page)`
- Produces: `KnowledgePage` with ordered `blocks`, combined `content`, and extraction warnings

- [ ] **Step 1: Write failing loader integration tests**

Add tests proving research/regulatory documents use the coordinate extractor, ordinary document types retain pypdf behavior, block content is joined in order, and a coordinate extraction exception falls back to pypdf while recording `READING_ORDER_UNSAFE`.

- [ ] **Step 2: Run loader tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_knowledge_pdf_loader.py -q`

Expected: coordinate extractor assertions fail.

- [ ] **Step 3: Implement loader integration**

Inject an optional `PdfLayoutExtractor`, open pypdf and pdfplumber documents for the same path, combine block content with blank lines, merge warnings without duplicates, and close the pdfplumber document in all paths.

- [ ] **Step 4: Run loader tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/loaders/test_knowledge_pdf_loader.py -q`

Expected: PASS.

### Task 5: 표 전용 청킹

**Files:**
- Modify: `ai_worker/rag/splitters/knowledge_splitter.py`
- Test: `ai_worker/tests/rag/splitters/test_knowledge_splitter.py`

**Interfaces:**
- Consumes: `KnowledgePage.blocks`
- Produces: `KnowledgeChunk` with `metadata.content_kind`; table chunks preserve full rows and use no overlap

- [ ] **Step 1: Write failing table chunk tests**

```python
def test_split_keeps_table_rows_whole_and_marks_content_kind():
    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page_with_text_and_table_blocks()])
    table_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
    assert table_chunks
    assert all("Ingredient=" in chunk.content for chunk in table_chunks)
    assert all("Result=" in chunk.content for chunk in table_chunks)
```

Also add a test that a single row over `hard_max_tokens` remains a single table chunk so the quality layer can block it instead of silently splitting the row.

- [ ] **Step 2: Run splitter tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/splitters/test_knowledge_splitter.py -q`

Expected: no table chunks or missing content kind.

- [ ] **Step 3: Implement block-aware splitting**

Use the legacy section path when `blocks` is empty. For block pages, feed `TEXT` content through the existing section logic and build `TABLE` chunks by grouping complete serialized rows up to the policy hard max. Set overlap to zero and never split a row.

- [ ] **Step 4: Run splitter tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/rag/splitters/test_knowledge_splitter.py -q`

Expected: PASS.

### Task 6: 자동 품질 차단과 보고서

**Files:**
- Modify: `ai_worker/services/knowledge_pilot_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py`

**Interfaces:**
- Consumes: page warnings and chunk `content_kind`
- Produces: `TABLE_STRUCTURE_UNSAFE`, `READING_ORDER_UNSAFE`, table chunk locations, automatic `BLOCKED`

- [ ] **Step 1: Write failing quality status tests**

Add one test per unsafe warning and assert `automatic_status == BLOCKED` with the matching reason code. Add a passing structured-table case and assert it does not receive either unsafe reason.

- [ ] **Step 2: Run service tests and confirm RED**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py -q`

Expected: unsafe warnings remain REVIEW or are not represented.

- [ ] **Step 3: Implement blocking reason mapping**

Add both reason codes to the enum and `_BLOCKING_QUALITY_REASONS`, derive them from page warnings, and count table chunks by `content_kind` rather than only matching `Table N` text.

- [ ] **Step 4: Run service tests and confirm GREEN**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py -q`

Expected: PASS.

### Task 7: 대표 문서 재전처리와 수동 검수 갱신

**Files:**
- Modify: `data/knowledge/manifests/additional_research_pilot_manifest.json`
- Modify: `docs/superpowers/plans/2026-09-04-additional-pdf-preprocessing-quality.md`
- Generated locally: `data/knowledge/processed/additional_research_pilot/**`

**Interfaces:**
- Consumes: representative pilot manifest and the new preprocessing pipeline
- Produces: refreshed JSONL chunks, automatic quality report, and review Markdown for four documents

- [ ] **Step 1: Reprocess only the representative manifest**

Run: `uv run --group ai --group dev python -m scripts.preprocess_knowledge_corpus --manifest data/knowledge/manifests/additional_research_pilot_manifest.json`

Expected: exactly four document reports; no OpenAI or Qdrant call.

- [ ] **Step 2: Inspect the known failure pages**

Check FDA p.5/9/10/14-17, Levothyroxine p.4-8, Aspirin·Warfarin p.2/8/9/17, and Botanical p.3-5. Confirm table rows retain headers, numeric tokens and units, and page block order matches the rendered PDF.

- [ ] **Step 3: Record before/after evidence**

Update the quality plan with per-document chunk counts, table counts, warning/blocking reasons, and whether each known failure is fixed or still blocked. Keep manual review `PENDING`; this implementation does not auto-approve medical evidence.

### Task 8: 전체 회귀 검증

**Files:**
- Verify only; do not modify unrelated files

**Interfaces:**
- Consumes: all prior task outputs
- Produces: fresh verification evidence

- [ ] **Step 1: Format and lint affected code**

Run: `uv run --group dev ruff format ai_worker`

Run: `uv run --group dev ruff check ai_worker`

Expected: all checks pass.

- [ ] **Step 2: Run the full AI Worker suite**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests -q`

Expected: all non-integration tests pass and configured integration tests remain skipped.

- [ ] **Step 3: Verify whitespace and worktree scope**

Run: `git diff --check`

Run: `git status --short`

Expected: no whitespace errors; only intended PDF preprocessing files plus pre-existing unrelated user files are listed.

## 2026-09-05 대표 논문 복원 결과

대상 문서는 `research_aspirin_warfarin_nutrient_interactions_2024.pdf`이며,
토크나이저는 다음 불변 컬렉션 후보에 맞춰 `o200k_base`를 사용했다.

- 페이지 경계: 앞 페이지가 문장 종결 기호 없이 끝나고 다음 페이지가 소문자로
  시작할 때 한 칸으로 연결한다. 실제로 `two macronutrients, fatty acids`가 한
  문장으로 복원됐다.
- 수용성 비타민: `Thiamine (B1)` 같은 영양소 소제목을 의미 경계로 먼저 찾고,
  소제목 단위들을 800토큰 상한 안에서 묶는다. 결과는 612토큰과 752토큰의 두
  청크이며 두 번째 청크는 `Cobalamins (B12)`로 시작하고 `Ascorbic Acid (C)`를
  포함한다.
- 표 문맥: `Table 2...` 캡션과 `Effect on Nutrient`, `Human Studies` 같은 상위
  헤더를 본문에서 분리해 `table_title`, `table_super_headers` 메타데이터로
  보존한다. `DNI`와 `DNIs` 약어도 상호작용 표 신호로 처리해 같은 표에서
  분할된 모든 청크가 `INTERACTION`으로 유지된다.
- 표 행 복원: 좌표 기반 Number 열의 정수 시작점을 논리 행 앵커로 사용한다.
  `calciferol (D)` 1행과 `K vitamin` 3행이 별도 행으로 복원됐으며, 좌표가
  부족하면 추정하지 않고 `TABLE_STRUCTURE_UNSAFE`로 격리한다.

재전처리 결과는 총 41청크 중 38개 `PENDING`, 3개 `REPAIR_REQUIRED`다. 남은
3개는 4~6페이지 다단 본문의 `READING_ORDER_UNSAFE` 경고이므로 자동 승인하지
않았다.

## 거리 함수 결정

OpenAI `text-embedding-3` 계열은 길이 1로 정규화된 임베딩을 반환하므로 DOT과
COSINE의 순위는 이론상 거의 같다. 다만 현재 PDF 복원 변경과 거리 함수 변경을
한 실험에 섞지 않는다. 새 불변 컬렉션에서만 DOT을 적용하고 다음을 COSINE
기준선과 A/B 비교한 뒤 활성화한다.

- 저장 벡터와 질의 벡터의 L2 norm 분포
- Top-k 결과 일치율
- Hit@5와 MRR
- Qdrant 검색 구간 P50/P95

현재 규모에서 정규화 비용은 전체 지연의 핵심 병목이 아니므로, 정확도가
동일하다는 실측 결과 없이 DOT을 운영 컬렉션에 바로 적용하지 않는다.

## 2026-09-05 수동 대조 후 텍스트 복원 보완

대표 Aspirin·Warfarin 논문의 청크 0과 10을 원문 PDF와 다시 대조해 다음 문제를
확인했다.

- 청크 0에는 검색 근거가 아닌 저자 소속과 `* Correspondence:` 이메일이 남았다.
- 청크 10의 줄 끝 `mi-`와 다음 줄 `nor`가 `mi-nor`로 남았다.
- PDF에서 위첨자인 `10⁵`, `cm²`가 평문 `105`, `cm2`로 추출됐다.

보완은 추측 범위를 제한하는 방식으로 적용했다.

- 연구 논문의 앞부분에 `*`, `†`, `‡` 장식이 붙은 `Correspondence:`도 출판
  앞표지로 판정해 첫 Abstract 이전 내용을 제외한다.
- `mi-nor → minor`는 모든 문서에 적용하는 사전이 아니라, 사람이 원문을 대조한
  해당 문서의 `verified_text_replacements` 매니페스트에 기록한다. 치환은 줄바꿈
  복원 전후에 적용해 `mi-\nnor` 형태도 처리한다.
- 위첨자는 PDF 글자별 크기와 기준선 좌표를 비교해 복원한다. 작은 알파벳이나 세로
  글자를 위첨자로 오인하지 않도록 숫자 글리프만 `^` 표기로 변환한다.

`additional-research-pilot-v13-o200k` 재전처리 결과는 41청크이며 38개
`PENDING`, 3개 `REPAIR_REQUIRED`로 기존 격리 상태를 유지했다. 확인 결과 청크
0은 `Abstract`로 시작하고 이메일이 제거됐으며, 청크 10은 `minor strokes`,
`2.7 × 10^5`, `4.4 × 10^5`, `cm^2`로 복원됐다. 기존 수동 검수 대상인
청크 7·8·9의 섹션 경계와 청크 39·40의 표 행도 유지됐다. 자동 품질 검사를
통과했다는 뜻이 아니라, 남은 3개 다단 읽기 순서 경고는 계속 수동 검수 대상으로
격리한다.

## 2026-09-05 청크 7·8·9 수동 승인 반영

사용자가 원문과 직접 대조해 청크 7·8·9의 내용과 순서가 일치함을 확인했다.
재청킹 때 번호가 바뀌어 다른 내용이 승인되는 일을 막기 위해 청크 번호가 아니라
정규화된 내용의 SHA-256 `content_hash` 세 개를 매니페스트에 기록했다.

승인 후 결과는 41청크 중 3개 `APPROVED`, 38개 `PENDING`, 0개
`REPAIR_REQUIRED`다. 승인된 세 청크에는 기존 `READING_ORDER_UNSAFE` 사유를
감사 기록으로 유지한다. 문서 단위 자동 상태와 수동 검수 상태는 각각 `BLOCKED`,
`PENDING`이고 `release_ready=false`이므로, 일부 청크 승인만으로 전체 문서가
컬렉션에 자동 반영되지는 않는다.
