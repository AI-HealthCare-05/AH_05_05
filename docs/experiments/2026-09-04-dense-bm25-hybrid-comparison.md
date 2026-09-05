# Dense·BM25·Hybrid 검색 비교 실험

- 판정 원칙: 속도보다 정확도 우선
- 최종 결정: `KEEP_DENSE`
- 차단 사유: NO_ACCURACY_IMPROVEMENT, HYBRID_EVALUATION_FAILED, SOURCE_ACCURACY_REGRESSION
- 경고: 없음

| 모드 | Recall@20 | Hit@5 | MRR | 출처 정확도 | 근거 커버리지 | 잘못된 대상 혼입 | 중복률 | P95(ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DENSE | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0 | 0.000 | 566.6 |
| BM25 | 1.000 | 1.000 | 1.000 | 0.923 | 1.000 | 0 | 0.000 | 389.1 |
| HYBRID | 1.000 | 1.000 | 1.000 | 0.923 | 1.000 | 0 | 0.000 | 464.4 |

## Hybrid - Dense 변화량

| 지표 | 변화량 |
|---|---:|
| recall_at_20 | +0.000000 |
| hit_at_5 | +0.000000 |
| mrr | +0.000000 |
| source_accuracy | -0.076923 |
| evidence_coverage_rate | +0.000000 |
| wrong_target_mixing_count | +0.000000 |
| duplicate_retrieval_rate | +0.000000 |
| search_p95_ms | -102.184000 |

Hybrid는 Hit@5 또는 MRR이 개선되고 Recall@20·출처 정확도·근거 커버리지가 하락하지 않으며 잘못된 대상 혼입과 중복이 늘지 않을 때만 활성화 후보가 됩니다.

## 질문별 안전 실패

| 모드 | 질문 ID | 실패 사유 |
|---|---|---|
| BM25 | `short-unsafe-correction` | 대상이 확정되지 않았지만 일반 기능성 문서를 반환함 |
| BM25 | `in-scope-no-evidence` | 확인할 수 없는 약 질문에 다른 약물백과 문서를 반환함 |
| Hybrid | `short-unsafe-correction` | 대상이 확정되지 않았지만 일반 기능성 문서를 반환함 |
| Hybrid | `in-scope-no-evidence` | 확인할 수 없는 약 질문에 다른 약물백과 문서를 반환함 |

## 해석과 결정

Dense는 강화된 고정 평가 14건을 모두 통과했습니다. BM25와 Hybrid는 정답 문서 Recall@20·Hit@5·MRR은 유지했지만, 근거가 없어야 하는 두 질문에서 문서를 반환했고 칼슘–철분 질문에 잘못 주석된 아연–철분 연구를 섞어 출처 정확도가 낮아졌습니다.

따라서 현재 서비스 설정은 `DENSE`를 유지합니다. 실험용 Hybrid 컬렉션은 비교 재현에만 사용하며 활성 컬렉션으로 전환하지 않습니다. P95에는 OpenAI query embedding 호출이 포함되므로 검색 엔진만의 속도라고 해석하지 않으며, 정확도 개선 없이 속도만 좋아진 결과는 채택 근거로 사용하지 않습니다.
