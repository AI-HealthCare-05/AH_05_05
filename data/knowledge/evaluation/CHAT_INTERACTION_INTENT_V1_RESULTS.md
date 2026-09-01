# Chat 상호작용 의도 분류 1차 개선 결과

## 실행 정보

- 실행일: 2026-08-31 (Asia/Seoul)
- LangSmith 프로젝트: `chat-team-eval-content`
- 실행 리비전: `b073faf-dirty`
- 평가 질문: `chat_representative_queries.yaml`의 10개 질문
- 비교 목적: `피해야 하나요` 계열 상호작용 질문의 경로 및 검색 섹션 개선 확인

## 결과 요약

| 지표 | 개선 전 | 개선 후 | 변화 |
| --- | ---: | ---: | ---: |
| 전체 계약 통과 | 2/10 | 2/10 | 변화 없음 |
| 질문 경로 정확도 | 80% | 90% | +10%p |
| 필수 엔터티 포함률 | 90% | 90% | 변화 없음 |
| 검색 섹션 정확도 | 80% | 90% | +10%p |
| 출처 계약 충족률 | 40% | 40% | 변화 없음 |
| 안전성 계약 충족률 | 50% | 60% | +10%p |
| LangSmith Trace 생성률 | 100% | 100% | 변화 없음 |
| 타임아웃 비율 | 0% | 0% | 변화 없음 |

- 응답 시간 평균: `2,316.1ms`
- 응답 시간 P50: `2,346.7ms`
- 응답 시간 P95: `7,830.9ms`
- 정확도를 우선하는 현재 단계에서는 응답 시간 변화로 품질 결론을 내리지 않는다.

## 질문별 결과

| 질문 ID | 실제 경로 | 필수 엔터티 | 검색 섹션 | 출처 계약 | 안전성 | 시간 | 결과 및 주요 원인 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| `rdb-exact-medication-guide` | `MEDICATION_GUIDE` | 충족 | `FUNCTION` | 충족 | `SAFE` | 7,830.9ms | PASS |
| `rdb-common-brand-medication-guide` | `MEDICATION_GUIDE` | 충족 | `CAUTION` | 충족 | `SAFE` | 1,903.9ms | FAIL · `FUNCTION` 섹션 누락 |
| `rdb-drug-drug-interaction` | `INTERACTION` | 충족 | `INTERACTION` | 미충족 | `SAFE` | 279.9ms | FAIL · 활성 약과 승인 규칙 없음 |
| `vector-magnesium-function` | `SUPPLEMENT_GUIDE` | 충족 | `FUNCTION` | 충족 | `SAFE` | 3,141.7ms | PASS |
| `vector-calcium-iron-interaction` | `INTERACTION` | 충족 | `INTERACTION` | 충족 | `RESTRICTED` | 3,353.7ms | FAIL · `UNSUPPORTED_GENERATED_CLAIM` |
| `vector-fexofenadine-fruit-juice` | `INTERACTION` | 충족 | `INTERACTION` | 미충족 | `SAFE` | 310.8ms | FAIL · 경로는 개선됐지만 검색 근거 0건 |
| `mixed-active-medication-public-caution` | `CLARIFICATION` | 충족 | `CAUTION` | 미충족 | `RESTRICTED` | 279.9ms | FAIL · 로사르탄 제품 모호성 및 활성 약 없음 |
| `mixed-drug-supplement-interaction` | `INTERACTION` | 충족 | `INTERACTION` | 미충족 | `SAFE` | 294.9ms | FAIL · 활성 약·영양제와 검색 근거 없음 |
| `mixed-registered-calcium-iron` | `INTERACTION` | 충족 | `INTERACTION` | 미충족 | `RESTRICTED` | 2,975.7ms | FAIL · 사용자 영양제 출처 없음, `UNSUPPORTED_GENERATED_CLAIM` |
| `mixed-prioritized-active-interactions` | `INTERACTION` | 미충족 | `INTERACTION` | 미충족 | `RESTRICTED` | 2,789.4ms | FAIL · 와파린·비타민 K 정규화 누락 및 사용자 출처 없음 |

## 직접 확인된 개선

`펙소페나딘을 먹을 때 과일주스를 피해야 하나요?`는 다음과 같이 변경됐다.

| 항목 | 개선 전 | 개선 후 |
| --- | --- | --- |
| 경로 | `CLARIFICATION` | `INTERACTION` |
| 검색 섹션 | 없음 | `INTERACTION` |
| 안전성 | `RESTRICTED` | `SAFE` |
| 검색 근거 | 0건 | 0건 |

질문의 관계 의도는 올바르게 판별하지만, `펙소페나딘`과 `과일주스`를 검색 가능한 표준 엔터티로 정규화하고 관련 청크를 회수하는 작업은 다음 단계다.

## 데이터 검증 및 한계

- 최신 10개 Trace는 질문별로 한 건씩 존재하고 오류 및 타임아웃이 없었다.
- 모든 Trace의 환자 컨텍스트는 `medication_count=0`, `supplement_count=0`이며 동일한 컨텍스트 해시를 사용했다.
- 따라서 RDBMS 출처가 필요한 5개 질문은 평가 전제조건을 충족하지 않았다. 이 실패는 분류 모델의 실패와 테스트 데이터 부재를 구분해서 해석해야 한다.
- 필수 엔터티 포함률은 필요한 이름이 결과에 포함됐는지만 측정한다. `내`, `중인`, `되나요` 같은 불필요한 토큰이 포함되는 정밀도 문제는 아직 반영하지 않는다.
- 전체 계약 통과율이 유지된 이유는 경로 개선 이후에도 검색 근거가 0건이어서 출처 계약을 충족하지 못했기 때문이다.

## 다음 개선 우선순위

1. 통칭·제품명·성분명·음식명 정규화
2. 엔터티 종류를 `DRUG`, `SUPPLEMENT`, `FOOD`로 분류
3. 약-약, 약-음식, 약-영양제, 영양제-영양제 관계 유형 확정
4. 다중 의도 질문에서 `FUNCTION`과 `CAUTION`을 함께 유지
5. 영어 논문 근거를 사실 구조로 추출한 뒤 한국어로 간결하게 요약
6. 테스트 계정에 평가 전제조건에 맞는 활성 약·영양제와 승인 규칙 구성

## LangSmith Trace ID

| 질문 ID | Trace ID |
| --- | --- |
| `rdb-exact-medication-guide` | `090a5ec1-98ae-4b69-85ad-afea2554fade` |
| `rdb-common-brand-medication-guide` | `ab2760a6-4566-47b1-88ea-cb5149cc0f1f` |
| `rdb-drug-drug-interaction` | `613cb0ed-221e-4b43-a3ca-edf252341481` |
| `vector-magnesium-function` | `89765ea0-ad02-401c-80ee-110c3b005f85` |
| `vector-calcium-iron-interaction` | `da5c6462-7f6c-42d4-a426-6d351a14b982` |
| `vector-fexofenadine-fruit-juice` | `9ba9a8fe-8eff-4ebd-860b-6afbae990016` |
| `mixed-active-medication-public-caution` | `a3093784-23cd-40f3-813d-58dcbe7f958d` |
| `mixed-drug-supplement-interaction` | `1c1de5fa-fdf1-4af7-b98c-71864871ce4d` |
| `mixed-registered-calcium-iron` | `f308c95c-a4f4-4bd9-a954-70d51611ed51` |
| `mixed-prioritized-active-interactions` | `3a761ff1-e49b-4bd3-94ef-1b5ef40f0dd8` |
