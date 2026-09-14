# V16 Chat Evidence and Output Design

## Goal

Use the V16 collection's retrieved evidence in the correct answer path, and render concise, pair-labelled Korean chat answers without creating unsupported medical claims.

## Observed baseline

- `독사조신 복용 후 심한 어지러움이 보고된 사례가 있나요?` retrieved two V16 public chunks but returned the assembler's raw public-data prose.
- `수면의 질 개선과 관련된 건강기능식품 기능 정보가 있나요?` stopped at product-name clarification before retrieval.
- `펙소페나딘을 자몽주스나 사과주스와 함께 먹어도 되나요?` retrieved a V16 food-interaction chunk but omitted question pair headings.
- `와파린–비타민 K` reached an active-intake no-evidence response with patient sources only.
- `칼슘–철분` retrieved four V16 public chunks but did not mark the direct pair as verified.

## Boundaries

- The V16 Qdrant collection, embedding model, and release corpus remain unchanged.
- No database migration or new persisted personal-health field is required.
- Chain 2 owns query intent, explicit entities, pair keys, and supplement function-goal routing.
- Chain 3 owns direct-evidence verification for each requested pair.
- Chain 4 owns display subject, required section/pair structure, and concise final rendering.
- The LLM may summarize only supplied evidence. Code supplies all display labels and rejects unsupported structure.

## Architecture

```text
Question
  -> Chain 2: explicit entity/pair priority or supplement function-goal plan
  -> V16 RAG + approved rule lookup
  -> Chain 3: pair-specific evidence coverage and claims
  -> deterministic draft with display contract
  -> Chain 4 LLM summary
  -> deterministic structural guard + grounded claim validation
```

### Chain 2 rules

1. An explicit two-target interaction question keeps its resolved targets and generated pair keys.
2. Active intake expands a query only when the user explicitly refers to their saved intake or when the question has no explicit target pair.
3. A health-function phrase such as `수면의 질 개선` is a supplement function-goal query, not an ambiguous product-name query. It searches only supported supplement-function evidence and returns only retrieved ingredient names.

### Chain 3 rules

1. Each requested pair is verified independently.
2. A chunk supports a pair only when its metadata pair key matches, or a direct pair-aware evidence mapping confirms the exact two targets.
3. A retrieved generic chunk does not become an interaction claim.
4. An unverified pair produces one non-safety notice; it never produces a safety or dosage instruction.

### Chain 4 rules

1. Medication or supplement function/caution/adverse-event answers begin with `**[product or ingredient]**` when the server has a resolved display subject.
2. Every verified or requested question interaction pair is rendered as `**[left-right]**` below `🔁 **질문 상호작용**`.
3. The summarizer returns only requested sections. Each bullet contains one short factual point.
4. The structural guard restores required headings/pair labels if the LLM omits them. It does not add medical facts.
5. Raw internal labels such as `공공자료 추가 설명` never appear in a rewritten final answer.

## Safety constraints

- No new product, ingredient, pair key, dosage, diagnosis, interaction, or safety assertion may be introduced.
- A general supplement function-goal response describes only ingredients supported by retrieved public evidence and does not recommend a product.
- Active medication names are shown only under the existing explicit display policy.

## Acceptance cases

| Question | Required result |
| --- | --- |
| 와파린과 비타민 K 영양제를 같이 먹어도 되나요? | Explicit pair survives planning and reaches RAG/approved-rule lookup. |
| 칼슘을 철분과 함께 먹으면 흡수에 영향이 있나요? | Direct pair evidence is verified and displayed under the pair heading. |
| 펙소페나딘을 자몽주스나 사과주스와 함께 먹어도 되나요? | Each resolved food pair has its own heading. |
| 독사조신 복용 후 심한 어지러움이 보고된 사례가 있나요? | `**독사조신**` and `🚨 **이상반응**` with concise fact bullets. |
| 수면의 질 개선과 관련된 건강기능식품 기능 정보가 있나요? | Ingredient-based functional guidance, not product-name clarification. |
