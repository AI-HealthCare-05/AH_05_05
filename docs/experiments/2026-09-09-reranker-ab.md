# Reranker A/B 평가 기록

## 목적

Reranker를 실제 챗봇 검색 경로에 연결하기 전에, 현재 검색 후보의 순서만 조정했을 때 정확도가 개선되는지 확인한다. 후보에 정답 근거 자체가 없는 검색 실패는 reranker가 해결할 수 없으므로 평가 대상에서 제외한다.

## 평가 계약

- 후보 집합: 검색 기준 Top 30. Reranker는 후보를 추가하거나 삭제할 수 없고 순서만 바꾼다.
- 적격 질문: 정답 문서가 기준선 Top 30 안에 있으면서 Top 5 밖에 있는 질문만 포함한다.
- 제외 질문: 정답이 이미 Top 5인 질문, Top 30에 정답이 없는 질문.
- 비교 지표: `Hit@5`, `MRR`, 출처 정밀도(Top 5 중 잘못된 대상이 아닌 비율), 잘못된 대상 혼입률, 검색 전체 `P95`.
- 채택 기준: `Hit@5` 또는 `MRR`이 개선되고, 출처 정밀도·잘못된 대상 혼입률이 나빠지지 않으며, Reranker 추가 후 `P95` 증가가 1,000ms 이하여야 한다.

## 구현

- `CandidateReranker`는 후보 순서만 반환하는 Protocol이다.
- `DeterministicScoreCandidateReranker`는 점수 기반의 테스트 adapter일 뿐이며, 실제 Qdrant Retriever나 Chat UseCase에 연결하지 않았다.
- `RerankerABEvaluator`는 적격 사례만 집계하고, 채택 기준을 충족하지 않으면 `KEEP_RUNTIME_DISABLED`를 반환한다.

## 자동 검증 결과

| 시나리오 | 결과 |
| --- | --- |
| 정답이 6위에서 1위로 이동 | `Hit@5` 0 → 1, `MRR` 0.166667 → 1.0, 조건부 활성화 가능 판정 |
| 잘못된 대상이 상위로 이동 | 출처 정밀도 하락·잘못된 대상 혼입률 상승으로 런타임 비활성 유지 |
| 정확도 개선 없이 지연시간 예산 초과 | `NO_ACCURACY_IMPROVEMENT`, `SEARCH_P95_BUDGET_EXCEEDED`로 런타임 비활성 유지 |

## 결론

상기 결과는 점수 adapter로 평가기 계약을 검증한 결과다. 실제 cross-encoder 또는 LLM reranker의 채택 여부는 고정 평가 세트와 실측 Top 30 후보·지연시간으로 같은 계약을 다시 실행한 뒤 결정한다. 따라서 이 변경만으로는 런타임 reranker를 활성화하지 않는다.
