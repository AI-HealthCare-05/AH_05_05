# 약·영양제 Knowledge Qdrant 파일럿 설계

## 1. 목적

문서 유형별 전처리와 청킹으로 생성된 `KnowledgeChunk` JSONL을 기존 공공 가이드라인 컬렉션과 분리된 Qdrant 파일럿 컬렉션에 적재하고, 실제 질문 세트로 검색 정확도와 지연시간을 평가한다.

이 단계의 성공 조건은 새 컬렉션을 Chat Core에 즉시 연결하는 것이 아니다. 새 데이터 release가 정해진 검색 품질을 충족하는지 확인하고, 기존 `public_guidelines_small_v1`을 유지한 상태에서 안전하게 전환 가능 여부를 판단하는 것이다.

## 2. 범위

### 포함

- `processed/chunks/*.jsonl`의 `KnowledgeChunk` 스키마 검증과 로딩
- dataset version 및 `index_eligible` 검증
- `embedding_text`의 OpenAI 배치 임베딩
- 새 Qdrant release 컬렉션 생성과 배치 upsert
- 약명, 성분명, 문서 유형, 상호작용 유형, 특수대상 기반 metadata filter
- 평가 질문별 Top-K 검색
- Hit@5, MRR, 출처 정확도, 약·성분 혼합 오류, 중복 검색 비율, 검색 P95 계산
- 기계 판독 가능한 JSON 평가 보고서와 사람이 읽는 콘솔 요약

### 제외

- 기존 `public_guidelines_small_v1` 삭제 또는 변경
- Chat Core의 기본 컬렉션 전환
- RDBMS 약·영양제 구조 변경
- OCR 파이프라인 변경
- LLM 답변 품질 평가
- 전체 Chat API P95 3초 평가

## 3. 대안과 결정

### 대안 A: 기존 Guideline 파이프라인에 강제 매핑

현재 `GuidelineMetadata`의 `condition`, `care_phase`, `topic`에 약·영양제 지식을 끼워 넣는다. 구현량은 적지만 약명, 성분명, 상호작용 유형, 특수대상 메타데이터가 손실되고 기존 퇴원 가이드 검색 계약을 오염시킨다. 채택하지 않는다.

### 대안 B: Knowledge 전용 인덱싱·검색·평가 경로

기존 임베딩 제공자는 재사용하고, `KnowledgeChunk` 전용 Qdrant 저장소와 평가기를 추가한다. 기존 서비스와 격리되며 향후 Chat 연결 시에도 계약이 명확하다. 이 방식을 채택한다.

### 대안 C: 모든 벡터 저장소를 즉시 범용화

기존 Guideline과 새 Knowledge 저장소를 하나의 generic vector store로 통합한다. 장기적으로 중복을 줄일 수 있지만 현재 동작하는 Chat Core와 인덱싱 Worker까지 동시에 바꾸므로 파일럿 검증 범위를 넘어선다. 검색 품질이 확인된 후 별도 리팩터링으로 검토한다.

## 4. 아키텍처

```text
KnowledgeChunk JSONL
  -> KnowledgeChunkLoader
  -> KnowledgeReleaseValidator
  -> OpenAIEmbeddingProvider.embed_documents(embedding_text 배치)
  -> QdrantKnowledgeStore.upsert_chunks(content + metadata)
  -> 저장 건수 및 release 검증
  -> KnowledgeRetrievalEvaluator
  -> JSON 평가 보고서
```

기존 `OpenAIEmbeddingProvider`는 재사용한다. 기존 `QdrantGuidelineStore`는 `GuidelineMetadata`에 강하게 결합되어 있으므로 수정하지 않는다.

## 5. 컬렉션과 release 정책

- 컬렉션 이름은 CLI에서 명시하며 기본 파일럿 이름은 `medication_knowledge_pilot_v1`이다.
- 컬렉션은 단일 vector, cosine distance, 설정된 임베딩 차원을 사용한다.
- 동일 이름의 컬렉션이 이미 존재하면 기본 동작은 실패다. 기존 데이터를 덮어쓰지 않는다.
- 인덱싱 실패로 일부 point만 저장되어도 Chat 설정이나 alias는 변경하지 않는다.
- 성공 조건은 입력 청크 수, 생성 벡터 수, Qdrant 저장 point 수가 모두 같은 것이다.
- 실패한 파일럿 컬렉션 삭제는 별도의 명시적 관리 작업으로만 수행한다. 인덱서가 자동 삭제하지 않는다.
- 기존 컬렉션과 Qdrant 볼륨은 이 작업에서 삭제하지 않는다.

## 6. 데이터 계약

Qdrant payload는 다음 구조를 사용한다.

```json
{
  "content": "사용자 인용과 LLM 근거에 사용할 정규화 원문",
  "embedding_text": "검색 보강 접두어가 포함된 임베딩 입력",
  "token_count": 320,
  "metadata": {
    "source_id": "...",
    "document_id": "...",
    "dataset_version": "knowledge-pilot-v1",
    "document_type": "SUPPLEMENT_FUNCTION_GUIDE",
    "section_type": "CAUTION",
    "drug_names": [],
    "ingredient_names": ["비타민 B6"],
    "interaction_type": null,
    "special_populations": [],
    "page_start": 10,
    "page_end": 10,
    "content_hash": "...",
    "index_eligible": true
  }
}
```

Qdrant point ID는 64자리 `chunk_id`를 UUID5로 변환해 사용한다. 같은 release 입력은 같은 point ID를 만들지만, 컬렉션 자체는 immutable 정책으로 재사용하지 않는다.

## 7. 로딩과 인덱싱

### 로딩 검증

- 파일이 없거나 JSONL이 비어 있으면 실패한다.
- 각 줄은 `KnowledgeChunk`로 검증한다.
- `index_eligible=false`가 포함되면 조용히 제외하지 않고 실패한다. 전처리 단계의 release 경계 오류이기 때문이다.
- 서로 다른 `dataset_version`이 섞이면 실패한다.
- 기대한 dataset version과 실제 값이 다르면 실패한다.
- 중복 `chunk_id`가 있으면 실패한다.

### 배치 처리

- 기본 임베딩 배치 크기는 64개다.
- 기본 Qdrant upsert 배치 크기도 64개다.
- 배치 크기는 CLI 인자로 조정할 수 있지만 1 이상이어야 한다.
- 임베딩에는 `embedding_text`를 사용한다.
- Qdrant에는 `content`, `embedding_text`, `token_count`, 전체 metadata를 저장한다.

## 8. 검색 계약

파일럿 검색은 query text를 임베딩한 뒤 다음 metadata 조건을 선택적으로 적용한다.

- `dataset_version`: 항상 필수
- `document_types`: 선택
- `drug_names`: 선택, 배열 값 중 하나가 일치
- `ingredient_names`: 선택, 배열 값 중 하나가 일치
- `interaction_type`: 선택
- `special_populations`: 선택, 배열 값 중 하나가 일치
- `section_types`: 선택

필터가 너무 엄격해 결과가 없더라도 평가기는 자동으로 필터를 제거해 재검색하지 않는다. 정확한 원인을 측정하기 위해 fallback은 평가 질문에 명시적으로 별도 케이스로 작성한다.

## 9. 평가 데이터와 지표

평가 질문은 YAML로 관리하며 각 항목에 다음을 기록한다.

- `query_id`
- 사용자 질문 `query`
- 적용할 metadata filter
- 정답으로 인정할 `expected_document_ids`
- 필요하면 `expected_section_types`, `expected_drug_names`, `expected_ingredient_names`
- `top_k`, 기본값 5

지표 정의:

- Hit@5: Top 5 안에 기대 문서가 하나 이상 있으면 1
- MRR: 첫 기대 문서 순위의 역수 평균
- 출처 정확도: 검색된 결과 중 기대 문서 또는 기대 엔티티 조건을 만족한 결과 비율
- 약·성분 혼합 오류: 기대 엔티티와 무관한 약·성분이 같은 결과에 잘못 포함된 건수
- 중복 검색 비율: 같은 `content_hash` 또는 같은 문서·섹션·내용이 Top-K에 반복된 비율
- Qdrant 검색 P95: query embedding 시간을 제외한 `query_points` 호출 시간의 95백분위수

파일럿 합격 기준:

- Hit@5 0.90 이상
- 출처 정확도 0.90 이상
- 약·성분 혼합 오류 0건
- Qdrant 검색 P95 300ms 이하

MRR과 중복 검색 비율은 이번 파일럿에서 수치를 기록하고, 관측 결과를 바탕으로 다음 release의 최소 기준을 결정한다.

## 10. 오류 처리

- JSONL 검증 오류는 줄 번호와 파일 경로를 포함한다.
- OpenAI 임베딩 실패는 해당 배치 범위를 포함해 상위로 전달한다.
- Qdrant collection 설정이 임베딩 차원 또는 cosine distance와 다르면 실패한다.
- 저장 건수 불일치는 성공으로 보고하지 않는다.
- 평가 질문이 없거나 정답 문서 ID가 비어 있으면 평가를 시작하지 않는다.
- 보고서에는 성공 여부뿐 아니라 실패한 query ID와 검색된 document ID를 남긴다.

## 11. 테스트 전략

- Loader 단위 테스트: 정상 JSONL, 잘못된 JSON, 중복 ID, dataset 혼합, index 불가 청크
- Store 단위 테스트: in-memory Qdrant를 이용한 생성, 불변 컬렉션 보호, payload, filter, count 검증
- Indexer 단위 테스트: 배치 경계, `embedding_text` 사용, 벡터 수 불일치, 부분 실패
- Evaluator 단위 테스트: Hit@5, MRR, 출처 정확도, 중복률, P95 계산
- CLI 테스트: 인자 전달, 성공 출력, 품질 기준 미달 exit code
- 전체 AI Worker 테스트와 Ruff 검사
- 실제 OpenAI/Qdrant 파일럿 실행은 명시적인 수동 통합 테스트로 수행하고 자동 CI에서는 호출하지 않는다.

## 12. 완료 조건

다음 조건을 모두 만족하면 구현 완료로 본다.

1. 480개 파일럿 청크를 새 컬렉션에 손실 없이 적재할 수 있다.
2. 기존 `public_guidelines_small_v1`과 Chat 설정이 변경되지 않는다.
3. 평가 질문을 실행해 JSON 보고서를 생성한다.
4. 합격 기준 충족 여부가 명확하게 표시된다.
5. Ruff와 전체 AI Worker 테스트가 통과한다.
6. 실제 파일럿 결과는 `chunking_experiments.yaml` 또는 별도 평가 report에 기록할 수 있다.
