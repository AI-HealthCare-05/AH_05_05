# 사용자 표현·검색 기준선 보고서

- Git commit: `9c192a677a568cd14f4c0ec89a7ab8563b9c7306`
- 미커밋 변경 포함: 예
- Collection: `medication_knowledge_full_v5`
- 기준선 관측 시점: `2026-09-08`
- 기준선 환경: `feature/325 개발 환경, Dense/DOT, medication_knowledge_full_v5. 질문 원문은 프론트에서 실행했고 원본 Trace ID는 개인정보·운영 데이터 분리를 위해 Git에 저장하지 않는다.`
- 검색 모드: `DENSE`
- Dataset: `knowledge-full-v5-o200k`
- Embedding: `text-embedding-3-small` / 1536
- 벡터 거리 / 정규화: `DOT` / 예
- 유사도 기준: 0.65
- 후보/최종: Top-20 / Top-5
- 평가 YAML SHA-256: `f15907209ce6a57ebc20e0b7e4e4fd286796121d5c61199fadcced64f3fe462e`

## 실험 근거

- 목적: source-backed typed entity와 FOOD 메타데이터 도입 전후를 같은 21문항으로 비교하여, 정확한 대상·pair·근거가 유지되는지 검증한다.
- 채택 기준: ACTIVE_PHASE의 모든 문항이 통과하고 잘못된 대상 혼입이 0건이며, 기존 PASS 11건보다 2026-09-08 자동 v5 기준선 PASS 13건보다 전체 PASS가 감소하지 않을 때만 새 불변 Qdrant 릴리스를 활성화 후보로 검토한다.
- Trace 참조 정책: LangSmith 비교는 질문 SHA-256과 실행 시점의 ChatMessage.langsmith_trace_id로만 수행한다. 이 fixture에는 실제 사용자·세션·Trace ID를 기록하지 않는다.

| 지표 | 선정 이유 |
|---|---|
| recall_at_20 | 관련 근거가 재정렬 전 후보 20건 안에 포함되는지 확인한다. |
| hit_at_5 | 최종 답변에 전달되는 상위 5건에 정답 근거가 있는지 확인한다. |
| mrr | 첫 정답 근거가 사용자 답변에 사용하기 좋은 순위에 있는지 확인한다. |
| source_accuracy | 선택된 근거가 질문 대상과 직접 연결되는지 확인한다. |
| evidence_coverage_rate | 질문이 요구한 효능·복용법·주의사항·상호작용 근거의 범위를 확인한다. |
| wrong_target_mixing_count | 이름이나 주제가 비슷한 다른 약·성분·음식의 혼입을 안전 오류로 측정한다. |
| duplicate_retrieval_rate | 같은 청크가 반복되어 근거 다양성을 잃는지 확인한다. |
| search_p95_ms | 정확도 조건을 통과한 뒤 상위 지연 구간을 운영 경고로 기록한다. |

## 집계

| 지표 | 값 |
|---|---:|
| 활성 단계 통과 | 16 / 18 (0.889) |
| 후속 단계 문항 | 3 |
| 범위 판별 정확도 | 1.000 |
| 표현 처리 정확도 | 1.000 |
| 자동 교정 정확도 | 1.000 |
| 오교정률 | 0.000 |
| 모호성 확인 정확도 | 1.000 |
| Recall@20 | 0.750 |
| Hit@5 | 0.750 |
| MRR | 0.750 |
| 출처 정확도 | 0.800 |
| 근거 커버리지 | 0.875 |
| P50 / P95 | 240.1 / 784.6 ms |

## 질문별 결과

| 질문 ID | 단계 | 변경 전 | 표현 유형 | 범위 | 처리 상태 | 후보 관련 순위 | Top-5 | 시간(ms) | 판정 |
|---|---|---|---|---|---|---:|---|---:|---|
| exact-product-magnesium | ACTIVE_PHASE | PASS | EXACT_PRODUCT | IN_SCOPE | UNCHANGED | - | - | 548.4 | PASS |
| typo-brand-tylenol | ACTIVE_PHASE | PASS | PRODUCT_TYPO | IN_SCOPE | AUTO_CORRECTED | - | - | 784.6 | PASS |
| typo-ingredient-acetaminophen | ACTIVE_PHASE | PASS | INGREDIENT_TYPO | IN_SCOPE | AUTO_CORRECTED | 1 | PASS | 538.4 | PASS |
| keyboard-tail-tylenol | ACTIVE_PHASE | PASS | KEYBOARD_TYPO | IN_SCOPE | AUTO_CORRECTED | - | - | 244.3 | PASS |
| spacing-magnesium | ACTIVE_PHASE | PASS | SPACING_VARIATION | IN_SCOPE | AUTO_CORRECTED | 1 | PASS | 219.8 | PASS |
| common-name-tylenol | ACTIVE_PHASE | PASS | COMMON_NAME | IN_SCOPE | UNCHANGED | - | - | 229.9 | PASS |
| ambiguous-near-product | ACTIVE_PHASE | PASS | AMBIGUOUS | IN_SCOPE | CLARIFICATION_REQUIRED | - | - | 0.0 | PASS |
| short-unsafe-correction | ACTIVE_PHASE | PASS | SHORT_EXPRESSION | IN_SCOPE | UNRESOLVED | - | - | 0.0 | PASS |
| out-of-scope-hungry | ACTIVE_PHASE | PASS | OUT_OF_SCOPE | OUT_OF_SCOPE | UNRESOLVED | - | - | 0.0 | PASS |
| in-scope-no-evidence | ACTIVE_PHASE | PASS | IN_SCOPE_NO_EVIDENCE | IN_SCOPE | UNRESOLVED | - | - | 0.0 | PASS |
| supplement-guide-magnesium | ACTIVE_PHASE | PASS | COMMON_NAME | IN_SCOPE | UNCHANGED | 1 | PASS | 187.5 | PASS |
| drug-drug-warfarin-metronidazole | ACTIVE_PHASE | PARTIAL | DRUG_DRUG | IN_SCOPE | UNCHANGED | 1 | PASS | 218.7 | PASS |
| drug-supplement-warfarin-vitamin-k | ACTIVE_PHASE | PARTIAL | DRUG_SUPPLEMENT | IN_SCOPE | UNCHANGED | 1 | PASS | 344.1 | PASS |
| supplement-supplement-calcium-iron | ACTIVE_PHASE | PARTIAL | SUPPLEMENT_SUPPLEMENT | IN_SCOPE | UNCHANGED | - | FAIL | 346.2 | EXPECTED_DOCUMENT_NOT_IN_TOP_20, EXPECTED_DOCUMENT_NOT_IN_TOP_5 |
| drug-food-fexofenadine-fruit-juice | ACTIVE_PHASE | PARTIAL | DRUG_FOOD | IN_SCOPE | UNCHANGED | - | FAIL | 238.4 | ENTITY_MISMATCH, TYPED_ENTITY_MISMATCH, INTERACTION_PAIR_MISMATCH, EXPECTED_DOCUMENT_NOT_IN_TOP_20, EXPECTED_DOCUMENT_NOT_IN_TOP_5 |
| drug-food-tylenol-alcohol | ACTIVE_PHASE | FAIL | DRUG_FOOD | IN_SCOPE | UNCHANGED | - | - | 243.4 | PASS |
| alphabet-pronunciation-vitamin-d | ACTIVE_PHASE | FAIL | COMMON_NAME | IN_SCOPE | AUTO_CORRECTED | - | - | 189.5 | PASS |
| colloquial-relation-warfarin-vitamin-k | ACTIVE_PHASE | FAIL | DRUG_SUPPLEMENT | IN_SCOPE | AUTO_CORRECTED | 1 | PASS | 233.0 | PASS |
| deferred-memory-pronoun | DEFERRED_MEMORY | FAIL | COMMON_NAME | IN_SCOPE | UNRESOLVED | - | - | 0.0 | PASS |
| deferred-context-registered-medication | DEFERRED_CONTEXT | FAIL | COMMON_NAME | IN_SCOPE | UNRESOLVED | - | - | 0.0 | PASS |
| deferred-safety-calcium-iron | DEFERRED_SAFETY | FAIL | SUPPLEMENT_SUPPLEMENT | IN_SCOPE | UNCHANGED | - | - | 240.1 | TYPED_ENTITY_MISMATCH |

## 질문별 정답 근거

### exact-product-magnesium

- 평가 이유: 정확한 제품명은 구조화된 제품 가이드가 우선되는지 확인한다.
- 근거 유형: `RDBMS_GUIDE`
- 정답 Qdrant 문서: 해당 없음
### typo-brand-tylenol

- 평가 이유: 제품명 오타를 source-backed 별칭으로 교정하는지 확인한다.
- 근거 유형: `RDBMS_GUIDE`
- 정답 Qdrant 문서: 해당 없음

### typo-ingredient-acetaminophen

- 평가 이유: 성분명 오타 뒤 해당 성분의 주의 근거를 찾는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `kpicia_drug_encyclopedia-33898a903b6cbca7`: 아세트아미노펜의 부작용과 주의사항을 직접 설명한다.

### keyboard-tail-tylenol

- 평가 이유: 끝 자판 오타를 제거해 제품 복용법 경로로 연결하는지 확인한다.
- 근거 유형: `RDBMS_GUIDE`
- 정답 Qdrant 문서: 해당 없음

### spacing-magnesium

- 평가 이유: 띄어쓰기 변형에도 공인 기능성 근거가 검색되는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `food_safety_korea_supplement_ingredients-d4b61ec6752184e6`: 마그네슘의 공인 기능성 내용을 성분 단위로 제공한다.

### common-name-tylenol

- 평가 이유: 사용자가 통칭으로 질문해도 제품 가이드로 연결되는지 확인한다.
- 근거 유형: `RDBMS_GUIDE`
- 정답 Qdrant 문서: 해당 없음

### ambiguous-near-product

- 평가 이유: 짧고 여러 후보가 가능한 표현은 임의 제품 선택 없이 재질문해야 한다.
- 근거 유형: `NOT_APPLICABLE`
- 정답 Qdrant 문서: 해당 없음

### short-unsafe-correction

- 평가 이유: 낮은 신뢰도의 짧은 표현을 특정 성분으로 오교정하지 않아야 한다.
- 근거 유형: `NO_EVIDENCE`
- 정답 Qdrant 문서: 해당 없음

### out-of-scope-hungry

- 평가 이유: 복약·영양제 범위 밖의 일상 질문은 RAG를 호출하지 않아야 한다.
- 근거 유형: `NOT_APPLICABLE`
- 정답 Qdrant 문서: 해당 없음

### in-scope-no-evidence

- 평가 이유: 대상이 특정되지 않은 의료 질문은 무관한 제품 근거를 사용하지 않아야 한다.
- 근거 유형: `NO_EVIDENCE`
- 정답 Qdrant 문서: 해당 없음

### supplement-guide-magnesium

- 평가 이유: 성분의 기능성 질문에 해당 성분 근거를 우선 검색하는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `food_safety_korea_supplement_ingredients-d4b61ec6752184e6`: 마그네슘의 기능성 근거를 직접 제공한다.

### drug-drug-warfarin-metronidazole

- 평가 이유: 두 의약품을 함께 인식하여 약-약 상호작용 근거를 찾는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `kpicia_pharm_review-e8127943c02a5a76`: 와파린과 메트로니다졸 병용을 직접 다룬다.

### drug-supplement-warfarin-vitamin-k

- 평가 이유: 약과 영양성분을 함께 인식해 약-영양제 근거를 찾는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `kpicia_pharm_review-c4ea8e68b35b65b3`: 와파린과 비타민 K 섭취 관계를 직접 다룬다.

### supplement-supplement-calcium-iron

- 평가 이유: 칼슘·철분의 연구가 검색되고 아연·철분 연구가 섞이지 않는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `research_supplement_interactions-016c81c9a3e29ebd`: 칼슘과 철분 흡수 기전 연구다.
  - `research_supplement_interactions-7983c60e9a092828`: 칼슘 섭취와 철분 흡수를 직접 평가한다.

### drug-food-fexofenadine-fruit-juice

- 평가 이유: 약과 음식 범주를 함께 인식해 약-음식 근거를 찾는지 확인한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `mfds_drug_food_interaction_guide-53bfb2433f48a8b0`: 펙소페나딘과 과일주스의 병용 주의사항을 안내한다.

### drug-food-tylenol-alcohol

- 평가 이유: 술이 출처 기반 FOOD 카탈로그에 없으면 약-음식 pair나 임의 음식 근거를 생성하지 않는지 확인한다.
- 근거 유형: `NO_EVIDENCE`
- 정답 Qdrant 문서: 해당 없음

### alphabet-pronunciation-vitamin-d

- 평가 이유: 일반 알파벳 한글 발음은 실제 단일 카탈로그 항목일 때만 교정해야 한다.
- 근거 유형: `NO_EVIDENCE`
- 정답 Qdrant 문서: 해당 없음

### colloquial-relation-warfarin-vitamin-k

- 평가 이유: 관계 표현 보정은 두 source-backed 엔터티가 확인된 뒤에만 pair를 생성해야 한다.
- 근거 유형: `QDRANT_GOLD`
- 정답 문서:
  - `kpicia_pharm_review-c4ea8e68b35b65b3`: 와파린과 비타민 K의 관계를 직접 설명한다.

### deferred-memory-pronoun

- 평가 이유: 이전 채팅 대명사 해소는 후속 memory 범위이므로 이번 변경의 차단 기준에서 제외한다.
- 근거 유형: `NOT_APPLICABLE`
- 정답 Qdrant 문서: 해당 없음

### deferred-context-registered-medication

- 평가 이유: 활성 복용 목록 전체 전개는 patient-context 확장 단계에서 검증한다.
- 근거 유형: `NOT_APPLICABLE`
- 정답 Qdrant 문서: 해당 없음

### deferred-safety-calcium-iron

- 평가 이유: 환자 등록정보와 안전성 validator의 결합은 후속 safety 정밀화에서 처리한다.
- 근거 유형: `NOT_APPLICABLE`
- 정답 Qdrant 문서: 해당 없음
