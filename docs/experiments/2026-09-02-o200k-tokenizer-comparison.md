# cl100k_base와 o200k_base 검색 품질 비교

## 결론

`o200k_base`는 동일한 776개 문서를 7,138개 청크로 줄였고 검색 P95도 낮췄지만,
14개 고정 평가 질문의 정확도는 기존 `cl100k_base`와 동일했다. 프로젝트는 속도·비용보다
정확도 개선을 우선하므로 활성 컬렉션은 `medication_knowledge_full_v2`로 유지한다.
후보 컬렉션 `medication_knowledge_full_v2_o200k`는 후속 평가를 위해 삭제하지 않는다.

## 실험 범위

이번 브랜치에서는 다음 세 단계까지만 수행했다.

0. `data/knowledge/evaluation/pilot_queries.yaml`의 14개 질문과 품질 게이트를 고정한다.
1. 현재 `cl100k_base` v2 컬렉션을 동일 계약으로 재평가한다.
2. tokenizer만 `o200k_base`로 바꾼 별도 전처리·Qdrant release를 만들고 비교한다.

질문, 정답 문서, 섹션, 약·성분, 상호작용 조합 키, 임베딩 모델과 차원,
검색 필터와 평가기는 바꾸지 않았다. 두 실행의 평가 계약 SHA-256은 모두
`b892240d664cbdc4d5119fd0308de0cd0242c4a2c7142c21c632f6d0892cbf5b`이다.
평가 YAML 원본 SHA-256은
`abb5fbe7eb25dfce9d32b08121991621ce43ca69be29ed85ff7a8ebffa511604`이다.

## 구현 변경

- 전체 코퍼스 전처리 CLI에 `--tokenizer-encoding`을 추가했다.
- 허용값을 `cl100k_base`, `o200k_base`로 제한하고 기본값은 기존 동작인
  `cl100k_base`로 유지했다.
- 평가 질문 14개의 ID 순서와 정확도 게이트를 테스트로 고정했다.
- `o200k_base`에서 드러난 overlap 중첩 조각 위치 추적 오류를 재현 테스트로 고쳤다.
  짧은 조각과 그 조각을 포함하는 다음 청크가 같은 원문 위치에서 시작하면 짧은 중복
  조각을 긴 청크로 교체한다. 임의 문자열 검색이나 문서별 예외는 추가하지 않았다.

## 전처리 결과

| 항목 | cl100k_base | o200k_base | 차이 |
| --- | ---: | ---: | ---: |
| 처리 문서 | 776 | 776 | 0 |
| 청크 | 10,012 | 7,138 | -2,874 (-28.7%) |
| 평균 청크 토큰 | 422.3 | 389.8 | -32.5 |
| 최소 청크 토큰 | 5 | 4 | -1 |
| 최대 청크 토큰 | 797 | 790 | -7 |

`o200k_base`는 한국어를 더 적은 토큰으로 표현하므로 같은 문서 유형별 최대 토큰 안에
더 긴 문맥이 남았다. 청크 감소 자체는 정확도 개선의 증거가 아니므로 검색 평가를 별도로
수행했다.

## Qdrant release

| 항목 | 기준선 | 후보 |
| --- | --- | --- |
| dataset version | `knowledge-full-v2-interaction-metadata` | `knowledge-full-v2-o200k` |
| collection | `medication_knowledge_full_v2` | `medication_knowledge_full_v2_o200k` |
| indexed chunks | 10,012 | 7,138 |
| interaction metadata chunks | 기존 v2 | 128 |
| pair-key chunks | 기존 v2 | 128 |

후보에는 검수된 상호작용 주석, `ingredient_names`, `drug_names`,
`interaction_type`, `interaction_pair_keys`, 근거 수준, 연구 대상과 문서 섹션을 기존과
같이 저장했다. 기존 v2 컬렉션은 덮어쓰거나 삭제하지 않았다.

## 검색 평가 결과

| 지표 | cl100k_base v2 | o200k_base 후보 | 변화 |
| --- | ---: | ---: | ---: |
| 질문 수 | 14 | 14 | 0 |
| Hit@5 | 1.000 | 1.000 | 0 |
| MRR | 1.000 | 1.000 | 0 |
| 출처 정확도 | 1.000 | 1.000 | 0 |
| 중복 검색률 | 0.000 | 0.000 | 0 |
| 잘못된 대상 혼입 | 0 | 0 | 0 |
| 검색 P95 | 213.345ms | 105.518ms | -107.827ms |

초기 기준선 실행은 첫 검색 워밍업 영향으로 P95 364.463ms가 나왔고, 동일 계약 재실행은
213.345ms였다. 시간은 실행 환경의 영향을 받으므로 보조 지표로만 사용했다.

## 판정

자동 release 비교 결과는 다음과 같다.

- 판정: `KEEP_BASELINE`
- 차단 사유: `NO_ACCURACY_IMPROVEMENT`
- 정확도 회귀: 없음
- 정확도 개선: 없음
- 속도 개선: 관측됨

따라서 이 실험만으로 `.env`의 활성 collection과 dataset version을 바꾸지 않는다.
평가 질문을 확장한 뒤 후보가 정확도에서 우세하면 다시 활성화를 검토한다.

## 재현 명령

```bash
.venv/bin/python -m scripts.preprocess_knowledge_corpus \
  --output data/knowledge/processed/full-v2-o200k \
  --dataset-version knowledge-full-v2-o200k \
  --tokenizer-encoding o200k_base

.venv/bin/python -m scripts.index_knowledge_release \
  --chunks-dir data/knowledge/processed/full-v2-o200k/chunks \
  --quality-report data/knowledge/processed/full-v2-o200k/reports/preprocessing-quality.json \
  --dataset-version knowledge-full-v2-o200k \
  --collection medication_knowledge_full_v2_o200k \
  --interaction-annotations data/knowledge/manifests/interaction_annotations.yaml \
  --embedding-batch-size 128 \
  --upsert-batch-size 128 \
  --allow-demo-restricted

.venv/bin/python -m scripts.evaluate_knowledge_retrieval \
  --evaluation-file data/knowledge/evaluation/pilot_queries.yaml \
  --dataset-version knowledge-full-v2-o200k \
  --collection medication_knowledge_full_v2_o200k \
  --output data/knowledge/reports/tokenizer-o200k-v2-candidate-20260902.json
```

`--allow-demo-restricted`는 내부 데모 제한 자료를 외부 임베딩 API로 전송하도록 승인받은
실행에서만 사용한다.

## 2단계 이후 보류 계획

다음 항목은 이번 브랜치에서 구현하지 않고, 2단계 결과를 바탕으로 다시 검토한다.

1. 오타·표기 변형을 높은 신뢰도 자동 교정, 중간 신뢰도 재질문, 낮은 신뢰도 근거 없음으로 분기
2. 원문·청크·메타데이터의 근거 커버리지 점검
3. Dense 단독 기준선 위에 Sparse/BM25 후보를 단계적으로 결합
4. Recall@20은 충분하지만 순위가 낮을 때만 reranker 실험
5. 영어 근거의 한국어 핵심 요약과 근거 충실도 검사
6. 검색 실패와 안전성 차단의 표현 검증
7. 동일 채팅 세션의 이전 문맥 활용과 다른 세션 간 격리 검증

다음 우선순위는 14개 평가에서 이미 포화된 정확도보다 실제 사용자 표현을 포함한 평가
세트 확장이다. 확장 평가에서 실패 유형이 확인된 뒤 필요한 검색 단계를 선택한다.
