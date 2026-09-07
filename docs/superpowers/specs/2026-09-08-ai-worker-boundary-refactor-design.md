# AI Worker 경계 분리 리팩터링 설계

2026-09-08 사용자 승인: 최신 `main` 병합과 Aerich 마이그레이션 적용 후, 새로운 검색 기능을 추가하기 전에 AI Worker의 전처리·청킹, 검색, 채팅 오케스트레이션 경계를 동작 변경 없이 분리한다.

## 문제와 범위

현재 AI Worker는 기능적으로 동작하지만 다음 파일에 서로 다른 책임이 누적되어 있다.

- `rag/splitters/knowledge_splitter.py`: 공통 청킹과 검수 완료 문서별 복원 규칙이 함께 있다.
- `rag/retrievers/medication_knowledge_retriever.py`: 후보 검색, 단계적 검색, 적합성 판정, score boost, 다양성 선택, 진단이 함께 있다.
- `use_cases/answer_medication_question.py`: 질문 해석, 규칙·RAG 근거 수집, 결정론적 초안, LLM 정제, 안전성 검증, 관측을 함께 조율한다.

이번 작업은 위 세 경계를 분리하는 데 한정한다. reranker, LangGraph, 대화 메모리, 새 Qdrant 컬렉션, 프롬프트 내용 변경, 데이터베이스 스키마 변경은 다음 실험 브랜치의 범위다.

## 고정 계약

1. 공개 진입점은 유지한다.
   - `KnowledgeSplitter.split()`
   - `MedicationKnowledgeRetriever.search_with_diagnostics()`
   - `AnswerMedicationQuestionUseCase.execute()`
2. 수동 검수로 확정한 문서별 복원 규칙과 현재 청크 내용·순서를 변경하지 않는다.
3. 검색 모드, 최저 유사도, 필터 순서, score boost 값, 다양성 선택 정책을 변경하지 않는다.
4. 안전성 검증은 항상 LLM 답변 생성 뒤에 실행하며, 검증 전 LLM 답변을 외부 응답으로 노출하지 않는다.
5. Qdrant, MySQL, Aerich 마이그레이션, API 응답 스키마는 이 리팩터링에서 수정하지 않는다.

## 목표 구조

### 1. 전처리·청킹

`KnowledgeSplitter`는 문서 유형별 공통 경계 인식, 토큰 제한, overlap, 청크 메타데이터 작성만 담당한다. 검수 완료 PDF의 예외 복원은 `DocumentChunkRepairer` 프로토콜과 문서 ID 기반 registry로 이동한다.

```text
PDF Loader → Normalizer → Generic KnowledgeSplitter → Repairer Registry → Quality/Release
```

Repairer는 입력 청크 목록을 받아 해당 문서에만 적용되는 텍스트·표·페이지 경계 복원을 수행한다. Registry에 없는 문서는 입력을 그대로 반환한다. 따라서 새 PDF를 추가할 때 공통 Splitter를 수정하지 않고 별도 Repairer와 테스트를 추가할 수 있다.

### 2. 검색

Retriever는 다음 순서를 유지하되 정책을 분리한다.

```text
Query Plan → Candidate Retrieval → Eligibility Policy → Ranking Policy → Diversity Selector → Diagnostics
```

- Candidate Retrieval: 질의 임베딩, semantic/entity-filtered fallback tier 요청
- Eligibility Policy: 유사도·엔터티·상호작용 쌍·섹션 일치 판정
- Ranking Policy: 기존 dense score와 metadata boost 합산
- Diversity Selector: 문서당 최대 청크 수 및 섹션 커버리지
- Diagnostics: 후보별 raw/adjusted score와 탈락 사유

향후 reranker는 Ranking Policy 뒤에 후보 재정렬 단계로 삽입한다. 기존 Dense/Hybrid 기준선은 Candidate Retrieval 구현으로 그대로 유지한다. 단, reranker와 대화 메모리 실험은 이 리팩터링 PR이 merge된 뒤 최신 `main`에서 각각 별도 브랜치로 진행한다.

### 3. 채팅 Use Case

Use Case는 파이프라인 순서와 조기 반환만 조율한다. 내부 단계는 불변 결과 객체로 정보를 전달한다.

```text
Question Preparation
  → Question Planning
  → Evidence Collection
  → Deterministic Draft Assembly
  → LLM Rewrite
  → Grounded Safety Validation
```

- Question Preparation: 표현 교정, 범위 외·명확화 결과
- Question Planning: LCEL Query Plan 및 질문 해석
- Evidence Collection: RDB 승인 규칙, RAG, 제품 가이드 조회
- Draft Assembly: route, 출처, 근거 커버리지, 결정론적 답변 초안
- LLM Rewrite / Safety: 기존 생성기와 grounded validator 호출 순서 유지

각 단계는 Trace span 이름과 현재 LangSmith 메타데이터를 보존한다.

## 검증 전략

- 전처리: 기존 대표 문서의 청크 ID, content hash, page range, section type이 리팩터링 전과 동일한지 확인한다.
- 검색: fixture store로 선택된 chunk ID, search tier, 후보 탈락 사유, adjusted score를 비교한다.
- 채팅: 기존 fake provider/repository 기반 테스트에서 route, source, safety status, 조기 반환과 LLM·안전성 호출 순서를 보장한다.
- 전체: `ruff check ai_worker`, `pytest ai_worker/tests`, `git diff --check`를 최종 수행한다.

## 작업 순서와 커밋 경계

1. 전처리·청킹 Repairer Registry 분리
2. Retriever 정책 분리
3. Chat Use Case 단계 분리

리팩터링은 `feature/263`의 단일 PR로 검증·병합한다. 병합 뒤 최신 main에서 reranker 평가 브랜치와 대화 메모리 브랜치를 별도로 만든다.
