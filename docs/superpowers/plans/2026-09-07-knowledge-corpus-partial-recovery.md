# Knowledge Corpus Partial Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대표 문서 규칙을 전체 코퍼스에 적용하고, 문서 전체 차단 대신 승인된 청크만 릴리스하여 사용 가능한 PDF 내용을 최대한 복원한다.

**Architecture:** 기존 후보 전처리와 품질 감사는 유지하되 `KnowledgeChunkReviewStatus.APPROVED`인 청크만 별도 릴리스에 기록한다. 전체 문서 상태와 청크별 상태를 분리하고, OCR 필요 문서는 외부 OCR 호출 없이 명시적인 대기 목록으로 내보낸다. 최종 dry-run 보고서는 기존 `full-v2` 대비 복원량과 남은 제외 사유를 출처별로 집계한다.

**Tech Stack:** Python 3.13, Pydantic, pypdf, tiktoken, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-09-07-knowledge-corpus-partial-recovery-design.md`

## Global Constraints

- 원본 PDF는 수정하거나 삭제하지 않는다.
- `PENDING`, `REPAIR_REQUIRED`, `EXCLUDED_NON_CONTENT` 청크는 임베딩 릴리스에 포함하지 않는다.
- 품질 임계값을 낮추지 않는다.
- OCR 문서를 외부 서비스로 전송하지 않는다.
- 기존 미추적 파일과 다른 팀원의 변경을 수정하거나 커밋하지 않는다.
- 기존 릴리스 보고서와의 하위 호환성을 유지한다.

---

### Task 1: 부분 릴리스 보고서 계약

**Files:**
- Modify: `ai_worker/services/knowledge_pilot_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py`

**Interfaces:**
- Consumes: 기존 `KnowledgeChunkReviewRecord`, `KnowledgeDocumentPreprocessingReport`
- Produces: `released_chunk_count: int`, `partial_release: bool`, 승인 청크 선택 함수

- [ ] **Step 1: 실패 테스트 작성**

차단 사유가 있는 문서에서도 `APPROVED` 청크 수와 부분 릴리스 여부가 계산되는 테스트를 추가한다.

- [ ] **Step 2: RED 확인**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py -q`

Expected: 새 필드 또는 승인 청크 선택 동작이 없어 실패한다.

- [ ] **Step 3: 최소 구현**

보고서에 기본값이 있는 하위 호환 필드를 추가하고, 청크와 리뷰를 `zip(strict=True)`로 결합하여 `APPROVED` 청크만 반환하는 단일 함수를 구현한다.

- [ ] **Step 4: GREEN 확인**

동일 테스트 파일을 실행하여 통과시킨다.

### Task 2: 청크 단위 릴리스 출력

**Files:**
- Modify: `ai_worker/services/knowledge_pilot_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py`

**Interfaces:**
- Consumes: Task 1의 승인 청크 선택 함수
- Produces: `release/chunks/<document_id>.jsonl`, 부분 승인 보고서

- [ ] **Step 1: 실패 테스트 작성**

정상 청크 1개와 복원 필요 청크 1개가 있는 차단 문서에서 정상 청크만 `release/chunks`에 기록되는 테스트를 추가한다.

- [ ] **Step 2: RED 확인**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_pilot_preprocessing_service.py -q`

Expected: 기존 코드는 `release_ready=False` 문서를 전부 생략하여 실패한다.

- [ ] **Step 3: 최소 구현**

`_write_candidate_and_release_outputs`가 문서 전체 상태가 아니라 승인 청크 존재 여부로 릴리스 파일을 만들도록 변경한다. 전체 페이지 텍스트는 후보·격리 출력에만 남기고 임베딩 입력은 승인 청크 JSONL로 제한한다.

- [ ] **Step 4: GREEN 확인**

테스트를 다시 실행하여 정상 청크만 출력되는지 확인한다.

### Task 3: 전체 코퍼스 부분 릴리스 확정

**Files:**
- Modify: `ai_worker/services/knowledge_corpus_preprocessing_service.py`
- Modify: `ai_worker/services/knowledge_release_composition_service.py`
- Test: `ai_worker/tests/services/test_knowledge_corpus_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_release_composition_service.py`

**Interfaces:**
- Consumes: `release/chunks`와 문서별 승인 청크 수
- Produces: 승인 청크만 포함한 `preprocessing-quality.json`

- [ ] **Step 1: 실패 테스트 작성**

자동 `BLOCKED` 문서에 승인 청크가 있으면 부분 릴리스에 포함되고, 승인 청크가 0개이면 제외되는 테스트를 추가한다. 조합 서비스가 부분 릴리스의 실제 청크 수를 검증하는 테스트도 추가한다.

- [ ] **Step 2: RED 확인**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_corpus_preprocessing_service.py ai_worker/tests/services/test_knowledge_release_composition_service.py -q`

- [ ] **Step 3: 최소 구현**

`finalize_release`가 후보 `chunks` 대신 `release/chunks`를 기준으로 문서와 청크를 집계하게 변경한다. 조합 계약은 완전 승인 문서와 부분 승인 문서를 모두 허용하되 실제 릴리스 청크가 모두 `APPROVED`임을 검증한다.

- [ ] **Step 4: GREEN 확인**

두 테스트 파일을 다시 실행한다.

### Task 4: OCR 대기 목록과 복원 보고서

**Files:**
- Create: `ai_worker/services/knowledge_recovery_reporting_service.py`
- Modify: `ai_worker/services/knowledge_corpus_preprocessing_service.py`
- Test: `ai_worker/tests/services/test_knowledge_recovery_reporting_service.py`

**Interfaces:**
- Consumes: `documents.jsonl`, 기존 기준선 품질 보고서, 새 dry-run 결과
- Produces: `recovery-summary.json`, `recovery-summary.md`, `ocr-required.jsonl`

- [ ] **Step 1: 실패 테스트 작성**

OCR 문서가 출처·경로·SHA-256과 함께 대기 목록에 남고, 기준선 대비 복원 문서 수 및 사유별 격리 수가 계산되는 테스트를 추가한다.

- [ ] **Step 2: RED 확인**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/services/test_knowledge_recovery_reporting_service.py -q`

- [ ] **Step 3: 최소 구현**

보고서 전용 서비스를 구현한다. 원문이나 청크 본문은 보고서에 넣지 않고 식별자와 집계만 저장한다.

- [ ] **Step 4: GREEN 확인**

테스트를 다시 실행한다.

### Task 5: 여러 대표 규칙 병합과 CLI 연결

**Files:**
- Modify: `ai_worker/services/knowledge_corpus_preprocessing_service.py`
- Modify: `scripts/preprocess_knowledge_corpus.py`
- Test: `ai_worker/tests/scripts/test_preprocess_knowledge_corpus.py`
- Modify: `data/knowledge/CHUNKING_STRATEGY.md`

**Interfaces:**
- Consumes: 기존 대표 품질 보고서·매니페스트, 추가 연구 대표 품질 보고서·매니페스트, 기준선 보고서와 Task 4 보고 서비스
- Produces: 전체 dry-run 명령과 재현 가능한 품질 산출물

- [ ] **Step 1: 실패 테스트 작성**

CLI가 여러 `--pilot-quality-report`와 `--pilot-manifest`를 받아 승인 출처와 문서별 검수 규칙을 중복 없이 병합하고, 기준선 보고서를 복원 보고 서비스에 전달하는 테스트를 추가한다. 동일 문서의 서로 다른 검수 정의는 오류로 차단한다.

- [ ] **Step 2: RED 확인**

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests/scripts/test_preprocess_knowledge_corpus.py -q`

- [ ] **Step 3: 최소 구현 및 문서화**

반복 가능한 `--pilot-quality-report`, `--pilot-manifest`와 단일 `--baseline-quality-report` 옵션을 추가한다. 청크 단위 릴리스·OCR 대기·임베딩 전 승인 절차를 `CHUNKING_STRATEGY.md`에 기록한다.

- [ ] **Step 4: 전체 검사**

Run: `uv run --group dev ruff check ai_worker scripts`

Run: `uv run --group ai --group dev python -m pytest ai_worker/tests -q`

Run: `git diff --check`

### Task 6: 전체 PDF Dry-run

**Files:**
- Generate: `data/knowledge/processed/full-v4-o200k-partial-dry-run/`

**Interfaces:**
- Consumes: PDF 1,286개 매니페스트와 대표 문서 승인 규칙
- Produces: 임베딩 전 전체 후보·승인·격리·OCR 집계

- [ ] **Step 1: 임베딩 없는 전체 실행**

Run:

```bash
uv run --group ai python -m scripts.preprocess_knowledge_corpus \
  --documents data/knowledge/manifests/documents.jsonl \
  --sources data/knowledge/manifests/sources.yaml \
  --pilot-quality-report data/knowledge/processed/full-v2/reports/preprocessing-quality.json \
  --pilot-quality-report data/knowledge/processed/additional-research-bulk-o200k-dry-run-v16/reports/preprocessing-quality.json \
  --pilot-manifest data/knowledge/manifests/pilot_manifest.json \
  --pilot-manifest data/knowledge/manifests/additional_research_bulk_manifest.json \
  --output data/knowledge/processed/full-v4-o200k-partial-dry-run \
  --dataset-version knowledge-full-v4-o200k-partial-dry-run \
  --tokenizer-encoding o200k_base \
  --baseline-quality-report data/knowledge/processed/full-v2/reports/preprocessing-quality.json
```

- [ ] **Step 2: 산출물 검증**

OCR 대기 19개가 모두 기록되었는지, 승인되지 않은 청크가 릴리스에 없는지, 실제 파일 수와 보고서 수가 일치하는지 확인한다.

- [ ] **Step 3: 결과 기록**

복원 문서·청크 수, 남은 문서 단위 제외 수, 격리 사유 상위 항목을 사용자에게 보고한다. OpenAI 임베딩과 Qdrant 생성은 실행하지 않는다.
