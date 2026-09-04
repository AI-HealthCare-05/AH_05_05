# 답변 근거 커버리지와 하이브리드 검색 설계

## 목표

의약품·영양제 챗봇이 질문에서 요구한 효능·복용법·주의사항·상호작용을 실제 근거가 있는 항목만 답하도록 제한하고, 현재 Dense 검색과 BM25 및 Dense+BM25 RRF 검색을 동일 평가 세트로 비교한다. 정확도가 개선되고 잘못된 대상 혼입이 늘지 않을 때만 하이브리드를 활성화한다.

## 현재 기준선

- 질문은 `Question Resolve → Query Plan → 단계적 검색` 순서로 처리한다.
- Qdrant 검색은 OpenAI Dense 임베딩과 메타데이터 필터를 사용한다.
- Retriever는 정확 조합, 엔터티, Semantic tier 순으로 검색하고 엔터티·섹션·조합 일치 점수를 보정한다.
- 검색 단계에는 요청 섹션 커버리지 확인이 있지만, 답변 생성 전후의 항목별 근거 계약은 완전하지 않다.
- LLM 출력 검사는 새 용량 수치와 근거 없는 안전 단정만 차단한다.

## 답변 근거 커버리지

### 지원 항목

질문에서 요청한 섹션을 다음 네 가지 사용자 답변 항목으로 정규화한다.

| 답변 항목 | Knowledge 섹션 | 근거로 인정하는 자료 |
|---|---|---|
| 효능 | `FUNCTION` | 의약품 가이드 효능 또는 FUNCTION 청크 |
| 복용법 | `DAILY_INTAKE` | 의약품 가이드 사용법 또는 DAILY_INTAKE 청크 |
| 주의사항 | `CAUTION` | 의약품 가이드 경고·주의·이상반응 또는 CAUTION 청크 |
| 상호작용 | `INTERACTION` | 승인 규칙 또는 질문의 정확한 pair를 포함한 INTERACTION 청크 |

### 생성 전 계약

1. Query Plan의 요청 섹션으로 `requested`를 만든다.
2. RDBMS 가이드, 승인 규칙, 최종 Qdrant 청크에서 `covered`를 계산한다.
3. `missing = requested - covered`를 계산한다.
4. 초안에는 `covered` 항목만 포함한다.
5. `missing` 항목은 근거가 없다는 제한 문구로 표시하며 내용을 생성하지 않는다.
6. 상호작용은 단순히 INTERACTION 문서라는 이유로 인정하지 않고 질문의 pair key 또는 동일 문장 내 양쪽 대상 일치를 요구한다.

### 생성 후 계약

- LLM이 초안에 없던 답변 항목의 제목이나 주장을 추가하면 결정론적 초안으로 되돌린다.
- 기존 용량·안전 단정 검사는 유지한다.
- LangSmith의 `answer.evidence_coverage` span에 요청·충족·누락 항목과 정확 pair 충족 여부를 기록한다.
- 원문과 사용자 질문은 `LANGSMITH_CAPTURE_CONTENT=false`일 때 기록하지 않는다.

## 하이브리드 검색 실험

### 불변 릴리스

- 현재 `medication_knowledge_full_v2` 컬렉션은 변경하거나 삭제하지 않는다.
- 실험 컬렉션은 새 이름으로 생성한다.
- 기존 v2의 Dense 벡터와 payload를 읽어 새 컬렉션에 복사하므로 같은 문서를 OpenAI 임베딩 API로 다시 보내지 않는다.
- 새 컬렉션은 named vectors를 사용한다.
  - `dense`: 기존 1536차원 Cosine 벡터
  - `bm25`: Qdrant sparse vector, `Modifier.IDF`
- BM25 문서 및 질의에는 `qdrant/bm25`와 `tokenizer=multilingual`을 사용한다.

### 검색 모드

| 모드 | 후보 생성 | 최종 정제 |
|---|---|---|
| `DENSE` | Dense Top-20 | 기존 적격성·중복 제거·점수 보정 |
| `BM25` | BM25 Top-20 | 기존 적격성·중복 제거·점수 보정 |
| `HYBRID` | Dense Top-20 + BM25 Top-20을 Qdrant RRF로 결합 | 기존 적격성·중복 제거·점수 보정 |

기존 Retriever의 정확 조합 → 엔터티 → Semantic tier는 유지한다. 바뀌는 것은 각 tier에서 후보를 만드는 방식뿐이다.

### 설정과 실패 처리

- 기본 검색 모드는 `DENSE`로 유지한다.
- `KNOWLEDGE_SEARCH_MODE`로 `DENSE`, `BM25`, `HYBRID`를 선택한다.
- BM25 또는 HYBRID 모드인데 컬렉션 스키마가 맞지 않으면 조용히 Dense로 바꾸지 않고 설정 오류를 반환한다.
- Dense 유사도 임계값은 Dense 후보에만 적용한다. RRF 점수에 Cosine 임계값 0.65를 적용하지 않는다.

## 평가 및 채택 조건

동일한 고정 질문·정답 문서 계약으로 세 모드를 각각 실행한다.

- Recall@20
- Hit@5
- MRR
- 출처 정확도
- 잘못된 대상 혼입 건수
- 중복 검색률
- 질문 항목별 답변 근거 커버리지
- 검색 P50/P95

HYBRID는 다음 조건을 모두 만족할 때만 활성 후보가 된다.

1. Hit@5 또는 MRR이 Dense보다 개선된다.
2. Recall@20이 Dense보다 낮아지지 않는다.
3. 출처 정확도가 낮아지지 않는다.
4. 잘못된 대상 혼입 건수가 증가하지 않는다.
5. 답변 근거 커버리지가 낮아지지 않는다.

조건을 만족하지 않으면 Dense를 유지하고 실험 코드와 보고서만 보존한다.

## 범위 밖

- Cross-encoder 또는 LLM reranker 도입
- LangGraph 반복 검색
- 기존 Qdrant v2 삭제 또는 덮어쓰기
- OCR, Frontend, RDBMS 스키마 변경
- 검색 점수 기준의 임의 하향
