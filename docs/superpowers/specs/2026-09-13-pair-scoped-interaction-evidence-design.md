# Pair-Scoped Interaction Evidence Design

## Goal

다중 성분 질문의 모든 2개 조합을 독립적으로 검색하고, 각 상호작용 claim이 질문한 조합의 직접 근거 단락만 사용하게 한다.

## Scope

- 명시적으로 확인된 N개 대상은 `N choose 2` pair를 만든다. 현재 schema의 최대 16개 pair를 초과하면 명확화 경로를 사용한다.
- Conditional Question Interpretation은 명시된 다중 pair 집합을 줄일 수 없다.
- 수동 상호작용 주석은 문서별 검수 경계를 선언할 수 있다. splitter는 선언된 경계에서만 원문을 나눈다.
- 와파린–비타민 K 주석은 비타민 K 단락에만 적용한다. 캐모마일 등 다른 와파린 상호작용 단락에는 해당 pair key를 적용하지 않는다.
- Evidence Reasoning은 각 claim에서 질문 pair와 직접 관계없는 제3 성분의 독립 상호작용을 만들지 않는다.

## Non-goals

- 근거가 없는 마그네슘–아연 pair를 직접 상호작용으로 승격하지 않는다.
- 새 Qdrant 컬렉션 생성 또는 OpenAI 임베딩 호출은 포함하지 않는다. 코드·로컬 청크 검증 뒤 별도 승인으로 수행한다.
- Chain 4의 표시 형식은 변경하지 않는다.

## Data flow

```text
entities A, B, C
  -> pair planner: A-B, A-C, B-C
  -> per-pair exact metadata retrieval
  -> pair-scoped evidence chunks
  -> Chain 3 claims bound to one pair key and its evidence IDs
```

## Acceptance criteria

1. 세 성분 질문의 Query Plan은 세 pair key와 세 pair 검색 자극을 유지한다.
2. 와파린 문서의 비타민 K 단락에는 와파린–비타민 K pair key가 있고 캐모마일 단락에는 없다.
3. 입력 evidence에 허용 pair key가 있어도 질문 밖 독립 상호작용 claim은 Chain 3 결과로 허용되지 않는다.
4. 비타민 D–칼슘과 아세트아미노펜–알코올의 기존 직접 근거 회귀 테스트가 유지된다.
