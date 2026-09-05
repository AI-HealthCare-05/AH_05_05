# Dense·Hybrid 프론트엔드 LangSmith 비교 실험

- 실행일: 2026-09-04
- 평가 세트: `data/knowledge/evaluation/user_expression_queries.yaml` 14건
- 비교 방식: 동일 질문을 프론트엔드에서 Dense와 Hybrid로 각각 실행하고 `chat-team-eval-content`의 root Trace와 `rag.retrieve` 진단값을 비교
- 판정 원칙: 응답 시간보다 출처 정확도와 근거 없는 답변 방지를 우선
- 현재 결정: `HYBRID_GUARDRAIL_PASS` — 골드 문서 순위 A/B 전까지 운영 기본값은 Dense 유지

## 질문별 결과

| 질문 | Dense 결과 | Hybrid 결과 | 판정 |
|---|---|---|---|
| 마그오캡슐500mg 효능·복용법 | `MEDICATION_GUIDE`, 근거 1, 4,779ms | `MEDICATION_GUIDE`, 근거 2, 9,343ms | 동일 경로, Hybrid 지연 |
| 타이래놀 효능·주의사항 | `MEDICATION_GUIDE`, 근거 1, 9,748ms | `MEDICATION_GUIDE`, 근거 2, 3,513ms | 동일 경로, Hybrid 단축 |
| 아세트아미노팬 부작용 | `MEDICATION_GUIDE`, 근거 2, 3,729ms | `MEDICATION_GUIDE`, 근거 3, 8,403ms | 동일 경로, Hybrid 지연 |
| 타이레놀ㄹ 복용법 | `CLARIFICATION`, 근거 0, 492ms | `CLARIFICATION`, 근거 0, 616ms | 동일; 오타는 교정됐으나 제품 확정 필요 |
| 마그 네슘 기능성 | `SUPPLEMENT_GUIDE`, 근거 1, 2,227ms | `SUPPLEMENT_GUIDE`, 근거 3, 2,404ms | 동일 경로 |
| 타이레놀 효능·주의사항 | `MEDICATION_GUIDE`, 근거 1, 2,568ms | `MEDICATION_GUIDE`, 근거 2, 3,187ms | 동일 경로 |
| 마그네 복용법 | `CLARIFICATION`, 근거 0, 482ms | `MEDICATION_GUIDE`, 근거 2, 3,261ms | **Hybrid 오탐** |
| 찰 영양제 기능성 | `RESTRICTED`, 근거 0, 305ms | `SUPPLEMENT_GUIDE`, 근거 3, 2,451ms | **Hybrid 오탐** |
| 오늘 너무 배고파요 | `OUT_OF_SCOPE`, 근거 0, 71ms | `OUT_OF_SCOPE`, 근거 0, 62ms | 동일 경로 |
| 처음 보는 약 주의사항 | `RESTRICTED`, 근거 0, 594ms | `MEDICATION_GUIDE`, 근거 6, 3,362ms | **Hybrid 오탐** |
| 와파린–메트로니다졸 | `INTERACTION`, 근거 2, 4,621ms | `INTERACTION`, 근거 3, 2,771ms | 동일 경로 |
| 와파린–비타민 K | `INTERACTION`, 근거 1, 2,414ms | `INTERACTION`, 근거 2, 2,146ms | 동일 경로 |
| 칼슘–철분 | `INTERACTION`, 근거 2, 2,694ms | `INTERACTION`, 근거 6, 2,038ms | **Hybrid 출처 혼입** |
| 펙소페나딘–과일주스 | `INTERACTION`, 근거 1, 2,223ms | `INTERACTION`, 근거 2, 2,040ms | 동일 경로 |

## 집계

| 지표 | Dense | Hybrid | 변화 |
|---|---:|---:|---:|
| 기대 동작 충족 | 14/14 | 10/14 | -4건 |
| 근거가 없어야 하는 질문의 오탐 | 0건 | 3건 | +3건 |
| 잘못된 대상 문서 혼입 | 0건 | 1건 | +1건 |
| 평균 전체 응답시간 | 2,639ms | 3,257ms | +23.4% |
| 중앙값 | 2,320ms | 2,611ms | +12.5% |
| P95 | 6,518ms | 8,732ms | +34.0% |

## 원인 진단

Dense는 모호하거나 근거가 없는 세 질문에서 최고 원시 유사도가 각각 `0.483`, `0.557`, `0.523`에 머물러 임계값 아래 후보를 제거했습니다. 반면 Hybrid는 Dense 점수와 BM25 순위를 결합한 점수를 사용하면서 `0.143`~`0.342` 수준의 낮은 결합 점수 후보도 `BELOW_SCORE`로 차단하지 않고 채택했습니다.

칼슘–철분 질문에서는 Hybrid가 기대 문서 외에 `Supplemental Zinc Lowers Measures of Iron Status...` 문서를 선택했습니다. 해당 문서는 아연–철분 연구이므로 칼슘–철분 답변의 직접 근거로 사용하면 안 됩니다.

## 결정

현재 Hybrid는 관련 질문의 후보 수를 늘리는 장점은 있지만, 근거가 없어야 하는 질문에서 다른 문서를 붙이고 상호작용 대상이 다른 문서를 섞는 회귀가 발생했습니다. 정확도 우선 정책에 따라 운영 설정은 Dense를 유지합니다.

다음 Hybrid 실험 전에는 결합 점수를 신뢰도로 직접 해석하지 않고, Dense 원시 유사도 하한·정확한 엔터티/상호작용 쌍 일치·근거 없음 게이트를 별도로 적용해야 합니다.

## 후속 개선 구현

- Hybrid 검색 시 RRF 결과와 동일 필터의 Dense 후보를 병렬 조회합니다.
- RRF 점수는 후보 순위에만 사용하고, 최종 채택에는 별도로 보존한 `dense_similarity_score`를 사용합니다.
- Dense 후보에 없는 Hybrid 전용 후보는 근거로 채택하지 않습니다.
- 낮은 Dense 점수 후보는 기존 엔터티·섹션·동일 문장 상호작용 보정 기준을 통과할 때만 구조적으로 구제합니다.
- LangSmith 후보 진단에 RRF 점수와 Dense 검증 점수를 함께 기록하도록 확장했습니다.

자동 검증은 AI Worker 전체 `723 passed, 5 skipped`와 Ruff 통과로 완료했습니다. 실제 Qdrant·프론트엔드 14개 재실험 결과는 다음 실행 후 이 문서에 추가합니다.

## 후속 개선 프론트엔드 1차 재검증

- 실행 시각: 2026-09-04 15:36 KST
- 대상 질문: Hybrid 오탐 3건과 정상 상호작용 1건
- 설정: `KNOWLEDGE_SEARCH_MODE=HYBRID`, `KNOWLEDGE_QDRANT_COLLECTION=medication_knowledge_full_v2`
- 결과 상태: **INVALID_CONFIGURATION**

| 질문 | 관측 경로 | 근거 | 안전성 | 전체 시간 | 실험 판정 |
|---|---|---:|---|---:|---|
| 마그네 복용법 알려줘. | `CLARIFICATION` | 0 | `RESTRICTED` | 5,355.1ms | 판정 제외 |
| 찰 영양제는 왜 먹나요? | `RESTRICTED` | 0 | `RESTRICTED` | 710.3ms | 판정 제외 |
| 처음 보는 약의 복용 시 주의사항을 알려줘. | `RESTRICTED` | 0 | `RESTRICTED` | 416.2ms | 판정 제외 |
| 칼슘과 철분을 같이 먹어도 되나요? | `RESTRICTED` | 0 | `RESTRICTED` | 271.7ms | 판정 제외 |

네 Trace 모두 `rag.retrieve.rag_unavailable=true`, `attempted_search_tiers=[]`, `raw_candidate_count=0`으로 기록되었습니다. 이는 후보가 신뢰도 게이트에서 탈락한 결과가 아니라 검색 저장소 초기 검증 실패입니다.

활성 컬렉션 `medication_knowledge_full_v2`는 기본 Dense 벡터만 보유하며, Hybrid 저장소가 요구하는 `dense` named vector와 `bm25` sparse named vector가 없습니다. 로컬에는 두 벡터를 보유한 실험 컬렉션 `medication_knowledge_full_v2_hybrid_exp_20260904`가 존재합니다. 따라서 후속 재검증은 컬렉션 설정을 해당 Hybrid 실험 컬렉션으로 전환하고 백엔드를 재시작한 뒤 같은 네 질문을 다시 실행해야 합니다.

## 후속 개선 프론트엔드 2차 재검증

- 실행 시각: 2026-09-04 15:42~15:43 KST
- 컬렉션: `medication_knowledge_full_v2_hybrid_exp_20260904`
- 검색 모드: `HYBRID`
- 결과 상태: **VALID_PARTIAL_PASS**

| 질문 | 개선 전 Hybrid | Dense 신뢰도 게이트 적용 후 | 근거 진단 | 시간 변화 | 판정 |
|---|---|---|---|---:|---|
| 마그네 복용법 알려줘. | `MEDICATION_GUIDE`, 근거 2 | `CLARIFICATION`, 근거 0 | 후보 40건 중 엔터티 불일치 38건·Dense 점수 부족 2건 제거 | 3,261.2 → 4,174.5ms | PASS |
| 찰 영양제는 왜 먹나요? | `SUPPLEMENT_GUIDE`, 근거 3 | `RESTRICTED`, 근거 0 | 후보 20건 중 Dense 점수 부족 19건·엔터티 불일치 1건 제거 | 2,451.1 → 296.0ms | PASS |
| 처음 보는 약의 복용 시 주의사항을 알려줘. | `MEDICATION_GUIDE`, 근거 6 | `RESTRICTED`, 근거 0 | 후보 40건 중 Dense 점수 부족 15건·엔터티 불일치 25건 제거 | 3,361.7 → 780.6ms | PASS |
| 칼슘과 철분을 같이 먹어도 되나요? | `INTERACTION`, 근거 6, 아연–철분 문서 혼입 | `INTERACTION`, 근거 3, `SAFE` | `EXACT_PAIR`에서 칼슘–철분 체계적 문헌고찰 청크 2건 채택; Dense 점수 `0.604`, `0.585` | 2,038.2 → 4,042.6ms | PASS |

### 부분 집계

| 지표 | 개선 전 Hybrid | 개선 후 Hybrid | 변화 |
|---|---:|---:|---:|
| 목표 동작 충족 | 0/4 | 4/4 | +4건 |
| 근거가 없어야 하는 질문의 오탐 | 3건 | 0건 | -3건 |
| 다른 상호작용 대상 문서 혼입 | 1건 | 0건 | -1건 |
| 네 질문 평균 응답시간 | 2,778.1ms | 2,323.4ms | -16.4% |

이번 결과는 RRF 점수를 후보 순위에만 쓰고 Dense 유사도를 신뢰도 판정에 별도로 사용한 효과를 보여줍니다. 정확한 상호작용 쌍 메타데이터가 있는 칼슘–철분 문서는 기존의 쌍·섹션·엔터티 보정으로 유지하면서, 모호한 표현과 대상 없는 질문은 낮은 Dense 신뢰도 또는 엔터티 불일치로 제거했습니다.

다만 4건만 재검증한 부분 통과이므로 운영 기본값은 아직 Dense로 유지합니다. 전체 14건을 동일 컬렉션과 코드로 재실행해 기존 통과 10건의 회귀 여부와 전체 P50/P95를 확인한 뒤 Hybrid 채택 여부를 결정합니다.

## 후속 개선 프론트엔드 전체 14건 재검증

- 실행 시각: 2026-09-04 15:48~15:49 KST
- 컬렉션: `medication_knowledge_full_v2_hybrid_exp_20260904`
- 검색 모드: `HYBRID`
- LangSmith 프로젝트: `chat-team-eval-content`
- 결과 상태: **FULL_GUARDRAIL_PASS**

| # | 질문 | 경로 | 최종 출처 | 안전성 | 전체 시간 | 판정 |
|---:|---|---|---:|---|---:|---|
| 1 | 마그오캡슐500mg 효능·복용법 | `MEDICATION_GUIDE` | 2 | `SAFE` | 4,943.2ms | PASS |
| 2 | 타이래놀 효능·주의사항 | `MEDICATION_GUIDE` | 2 | `SAFE` | 3,065.5ms | PASS |
| 3 | 아세트아미노팬 부작용 | `MEDICATION_GUIDE` | 3 | `SAFE` | 2,942.9ms | PASS |
| 4 | 타이레놀ㄹ 복용법 | `CLARIFICATION` | 0 | `RESTRICTED` | 549.1ms | PASS |
| 5 | 마그 네슘 기능성 | `SUPPLEMENT_GUIDE` | 2 | `SAFE` | 7,087.2ms | PASS |
| 6 | 타이레놀 효능·주의사항 | `MEDICATION_GUIDE` | 2 | `SAFE` | 3,770.8ms | PASS |
| 7 | 마그네 복용법 | `CLARIFICATION` | 0 | `RESTRICTED` | 726.7ms | PASS |
| 8 | 찰 영양제 기능성 | `RESTRICTED` | 0 | `RESTRICTED` | 320.7ms | PASS |
| 9 | 오늘 너무 배고파요 | `OUT_OF_SCOPE` | 0 | `SAFE` | 69.4ms | PASS |
| 10 | 처음 보는 약 주의사항 | `RESTRICTED` | 0 | `RESTRICTED` | 859.7ms | PASS |
| 11 | 와파린–메트로니다졸 | `INTERACTION` | 3 | `SAFE` | 4,323.1ms | PASS |
| 12 | 와파린–비타민 K | `INTERACTION` | 2 | `SAFE` | 3,300.8ms | PASS |
| 13 | 칼슘–철분 | `INTERACTION` | 3 | `SAFE` | 3,859.7ms | PASS |
| 14 | 펙소페나딘–과일주스 | `INTERACTION` | 2 | `SAFE` | 2,259.7ms | PASS |

### 전체 비교

| 지표 | Dense 기준선 | 개선 전 Hybrid | 개선 후 Hybrid |
|---|---:|---:|---:|
| 기대 동작 충족 | 14/14 | 10/14 | 14/14 |
| 근거가 없어야 하는 질문의 오탐 | 0건 | 3건 | 0건 |
| 잘못된 대상 문서 혼입 | 0건 | 1건 | 0건 |
| RAG 장애 | 0건 | 0건 | 0건 |
| 평균 전체 응답시간 | 2,639ms | 3,257ms | 2,719.9ms |
| 중앙값(P50) | 2,320ms | 2,611ms | 3,004.2ms |
| P95 | 6,518ms | 8,732ms | 5,693.6ms |

상호작용 검색은 모두 `EXACT_PAIR` 단계에서 처리됐습니다. 선택 문서는 와파린–메트로니다졸 `PHARM_REVIEW`, 와파린–비타민 K `PHARM_REVIEW`, 칼슘–철분 `RESEARCH_ARTICLE`, 펙소페나딘–과일주스 `DRUG_FOOD_INTERACTION_GUIDE`로 질문 조합과 일치했습니다. 칼슘–철분에는 기존에 혼입됐던 아연–철분 문서가 포함되지 않았습니다.

Dense 신뢰도 게이트를 적용한 Hybrid는 현재 14개 회귀 방지 세트에서 Dense와 같은 동작 정확도를 회복했고, 기존 Hybrid의 오탐과 문서 혼입을 제거했습니다. P95도 Dense보다 낮았지만 중앙값은 Dense보다 높으므로 속도 우위로 해석하지 않습니다. 다음 선택 단계는 질문별 골드 문서 ID를 지정하고 Hit@5·MRR·잘못된 대상 혼입률을 Dense와 A/B 비교하는 것입니다. 그 평가에서 Hybrid의 순위 품질이 실제로 더 좋을 때만 운영 기본값을 전환합니다.
