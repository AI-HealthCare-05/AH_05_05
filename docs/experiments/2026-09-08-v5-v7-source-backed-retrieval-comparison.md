# v5·v7 Source-backed 검색 A/B 비교

## 목적

칼슘–철분과 펙소페나딘–과일주스의 근거 누락을 보완한 `knowledge-full-v7-o200k-source-backed`가 기존 v5보다 대상·상호작용·근거를 더 정확히 검색하는지 확인한다. 기존 v5는 비교가 끝날 때까지 수정하지 않았다.

## 동일 조건

- 평가 세트: `data/knowledge/evaluation/user_expression_queries_v3.yaml` 21문항
- 활성 평가 문항: 18문항, 보류 문항: 세션 메모리·등록 복약정보·안전성 3문항
- 검색: Dense, DOT, 후보 Top-20, 최종 Top-5, 유사도 기준 0.65
- 임베딩: `text-embedding-3-small`, 1,536차원, L2 정규화
- 비교 대상: `medication_knowledge_full_v5` / `medication_knowledge_full_v7`

## 결과

| 지표 | v5 | v7 | 판단 |
|---|---:|---:|---|
| 활성 단계 통과 | 16 / 18 | 18 / 18 | 개선 |
| Recall@20 | 0.750 | 1.000 | 개선 |
| Hit@5 | 0.750 | 1.000 | 개선 |
| MRR | 0.750 | 1.000 | 개선 |
| 출처 정확도 | 0.800 | 0.867 | 개선 |
| 근거 커버리지 | 0.875 | 1.000 | 개선 |
| 잘못된 대상 혼입 | 0 | 0 | 유지 |
| fallback 비율 | 0.400 | 0.333 | 개선 |
| 검색 P50 | 264.9ms | 278.1ms | +13.2ms |
| 검색 P95 | 778.4ms | 481.6ms | 개선 |

## 실패·개선 확인

| 질문 | v5 | v7 |
|---|---|---|
| 칼슘–철분 병용 | 정답 문서가 Top-20 밖 | 칼슘–철분 근거 문서 Top-1 |
| 펙소페나딘–과일주스 | 대상·pair 불일치, 근거 없음 | 약–음식 근거 문서 Top-1 |
| 보류: 등록 칼슘–철분 안전성 | 등록 복약정보 전제 미충족 | 동일하게 보류 |

## 정답 근거 계약 보완

마그네슘 기능성 문항의 기존 정답은 식품안전나라 문서 하나였다. v7에서 함께 검색된 `mfds_supplement_code-0d785fd735e66685`는 같은 마그네슘 기능성 내용을 제공하는 식품의약품안전처 건강기능식품공전 문서임을 원문으로 확인했다. 질문이나 검색 로직을 바꾸지 않고, 이 동등한 공인 근거를 평가 YAML의 허용 정답 문서에 추가한 뒤 두 컬렉션을 다시 평가했다.

## 전환 결정

`medication_knowledge_full_v7`을 로컬 활성 컬렉션으로 전환했다.

- `KNOWLEDGE_QDRANT_COLLECTION=medication_knowledge_full_v7`
- `KNOWLEDGE_DATASET_VERSION=knowledge-full-v7-o200k-source-backed`

되돌려야 할 경우에는 위 두 값을 각각 `medication_knowledge_full_v5`, `knowledge-full-v5-o200k`로 변경한다. v5 컬렉션은 삭제하거나 수정하지 않았다.
