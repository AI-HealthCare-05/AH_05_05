# medication_knowledge_full_v2 tokenizer 비교 기준선

## 실험 목적

현재 `cl100k_base`로 전처리한 `medication_knowledge_full_v2`의 검색·답변 결과를 기준선으로 고정하고, 동일 원문을 `o200k_base`로 재전처리했을 때 검색 정확도와 청크 품질이 실제로 개선되는지 비교한다.

## 고정 조건

- Qdrant 컬렉션: `medication_knowledge_full_v2`
- 데이터셋 버전: `knowledge-full-v2-interaction-metadata`
- tokenizer: `cl100k_base`
- 최소 유사도: `0.65`
- LangSmith 프로젝트: `chat-team-eval-content`
- 측정 시각: 2026-09-01
- 원문 답변은 보고서에 저장하지 않고 Trace 지표만 기록한다.

## 기준선 결과

| 질문 | 경로 | 정규화 결과 | 사용 근거 | 안전성 | LLM 상태 | 전체 시간 | 판정 |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| 로사르탄의 효능과 주의사항을 알려주세요. | `MEDICATION_GUIDE` | 로사르탄 / 성분명 | Qdrant 2건, 최고 0.552, `DRUG_ENCYCLOPEDIA` | `SAFE` | `REWRITTEN` | 3,405.0ms | PASS |
| 타이레놀의 효능과 주의사항을 알려주세요. | `MEDICATION_GUIDE` | 타이레놀 / 통칭 | RDBMS 의약품 가이드 1건 | `SAFE` | `REWRITTEN` | 2,464.3ms | PASS |
| 와파린과 메트로니다졸을 같이 복용해도 되나요? | `INTERACTION` | 와파린, 메트로니다졸 | Qdrant 2건, 최고 0.628, `EXACT_PAIR` | `SAFE` | `REWRITTEN` | 2,724.0ms | 부분 PASS |
| 와파린과 비타민 K 영양제를 같이 먹어도 되나요? | `INTERACTION` | 와파린, 비타민 K | Qdrant 1건, 최고 0.618, `EXACT_PAIR` | `SAFE` | `REWRITTEN` | 3,537.1ms | 부분 PASS |
| 수면의 질 개선과 관련된 건강기능식품 기능 정보가 있나요? | `SUPPLEMENT_GUIDE` | 수면 관련 기능 질문 | Qdrant 2건, 최고 0.709, `SUPPLEMENT_FUNCTION_GUIDE` | `SAFE` | `REWRITTEN` | 3,414.6ms | PASS, 정규화 보완 필요 |

## 집계

| 지표 | 결과 |
| --- | ---: |
| 검색·경로 PASS | 3/5 |
| 부분 PASS | 2/5 |
| fallback 발생 | 0/5 |
| 평균 응답 시간 | 3,109.0ms |
| 중앙값 | 3,405.0ms |
| 최대 응답 시간 | 3,537.1ms |
| 오류 Trace | 0건 |

상호작용 2건은 Qdrant 근거를 찾았지만 `approved_rule_count=0`이므로 부분 PASS로 판정했다. 수면 질문은 검색에는 성공했지만 `개선`, `관련된`, `정보` 같은 불필요어가 엔터티 후보에 포함되어 정규화 개선 대상으로 남겼다.

## o200k_base 비교 원칙

기존 v2 컬렉션의 tokenizer 설정만 변경해서는 유효한 비교가 되지 않는다. 저장된 청크 경계와 임베딩은 이미 `cl100k_base` 기준으로 확정되어 있기 때문이다.

1. 동일 원문과 동일 전처리 규칙을 사용한다.
2. tokenizer만 `o200k_base`로 변경한다.
3. 별도 불변 컬렉션을 생성한다. 예: `medication_knowledge_full_v3_o200k`.
4. 임베딩 모델, 차원, 검색 후보 수, 재정렬 규칙, 최소 유사도는 유지한다.
5. 위의 동일 질문을 다시 실행한다.
6. 청크 수, Hit@5, MRR, 출처 정확도, 잘못된 대상 혼입률, fallback 발생률, 응답 시간을 비교한다.
7. 정확도 지표가 개선될 때만 활성 컬렉션을 전환한다.

응답 시간과 비용은 보조 지표로 사용하고, 출처 정확도와 근거 충실도를 우선한다.
