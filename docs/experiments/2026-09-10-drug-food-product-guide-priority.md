# 약–음식 제품 가이드 우선 조회 검증 기록

## 문제

약–음식 질문에서 Resolver는 제품명 끝의 검수된 성분명을 찾아 검색 대상을
성분명으로 정규화한다. 이 과정에서 제품명 유형이 사라져 `타이레놀–술` 같은
질문이 e약은요 제품 가이드를 조회하지 못하고 연구 RAG만 사용했다.

## 변경

1. `MedicationQueryEntity.product_lookup_name`에 원래 검수된 제품명을 보존한다.
2. `MedicationKnowledgeQueryPlan.medication_product_lookup_names`가 이 제품 후보를
   해시 계약에 포함한다.
3. 약–음식 상호작용이면서 제품 후보가 있는 경우, 제품 가이드를 먼저 조회한다.
4. RAG 검색 대상은 계속 성분명으로 유지하고, 제품 가이드가 없으면 기존 RAG
   결과를 그대로 사용한다.

## 성공·실패 기준

| 사례 | 결과 |
| --- | --- |
| `타이레놀과 술을 같이 먹어도 돼?` | 성공 — `아세트아미노펜`으로 검색하면서도 `타이레놀정500밀리그람(아세트아미노펜)` 가이드를 먼저 조회하고 RAG 근거를 함께 반환한다. |
| `아세트아미노펜과 술을 같이 먹어도 돼?` | 성공 — 제품명을 임의로 만들지 않는다. 제품 가이드 우선 경로를 타지 않고 기존 성분 기반 RAG를 유지한다. |
| 제품 가이드가 없는 제품명 질문 | 기존 동작 유지 — 빈 제품 가이드 때문에 답변을 비우지 않고 RAG 흐름을 계속 사용한다. |

## 검증

```text
uv run --group ai --group app pytest \
  ai_worker/tests/rag/query_builders/test_medication_knowledge_query_builder.py \
  ai_worker/tests/domain/test_medication_question_resolver.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py \
  ai_worker/tests/safety/test_grounded_claim_validator.py -q

179 passed
```
