# Small-to-Big 검색 실험 기록

## 상태

`PARTIAL` — 단위·Retriever 통합 fixture에서 작은 청크의 인접 문맥을 안전하게 결합했다. 실제 Qdrant 컬렉션의 고정 평가 세트로 재측정하기 전에는 런타임 활성화 효과를 `SUCCESS`로 판정하지 않는다.

## 가설

벡터 검색은 작은 청크를 사용해 관련 문장을 잘 찾되, 답변에는 같은 문서·같은 절·같은 엔터티의 인접 청크만 붙이면 문맥 단절을 줄이면서 다른 약물·표·문서의 내용 혼입을 막을 수 있다.

## 기준선

기존 Retriever는 적격 후보를 재정렬해 소형 청크 자체만 반환했다. 컬렉션에 별도 parent ID가 없으므로, 검색된 문장이 절 중간이면 앞뒤 설명을 답변 근거로 함께 보지 못했다.

## 변경

`ParentContextResolver`는 재정렬된 child와 이미 적격 판정된 후보만 사용한다.

- child와 문맥 후보의 `source_id`, `document_id`, `document_type`, 절 유형·제목, 표 그룹이 모두 일치해야 한다.
- 후보는 child의 `chunk_index` 바로 앞 또는 뒤여야 하며, 텍스트 청크만 허용한다.
- 약물명·성분명·음식명 메타데이터 집합이 같고 현재 질의 엔터티와 겹칠 때만 결합한다.
- child 식별자는 보존하고, 최대 두 개의 인접 청크만 본문·임베딩 텍스트에 덧붙인다.
- 다른 문서·다른 엔터티·표·같은 위치 청크는 결합하지 않는다. 새 Qdrant 조회, 임베딩, 컬렉션 변경은 없다.

## 검증

| fixture | child-only | Small-to-Big 결과 | 판정 |
| --- | ---: | ---: | --- |
| 같은 문서·절·마그네슘의 인접 두 청크 | 1개 child | 1개 결합 문맥, `attached=1` | PASS |
| 다른 문서 또는 칼슘 엔터티가 인접 | 1개 child | 결합 0, `rejected_mismatch=2` | PASS |
| Retriever 통합 경로 | 2개 child 후보 | 같은 절의 결합 본문 1개, child 수 2 | PASS |

새 진단 필드는 `parent_context_child_count`, `parent_context_attached_count`, `parent_context_rejected_mismatch_count`다. 질문 원문·본문을 추적 메타데이터로 저장하지 않는다.

## PARTIAL 이유와 다음 측정

fixture 기준 문맥 혼입은 0건이지만, 실제 `medication_knowledge_full_v6`의 고정 평가 세트에서 Hit@5·문맥 혼입률·P95를 아직 비교하지 않았다. 다음 전체 프런트/Trace 평가에서 child-only와 이 결합 경로를 같은 질문으로 비교해, 근거 문맥이 늘면서 잘못된 엔터티가 추가되지 않는지 확인한다.

## 제한

- parent 문서를 새로 검색하지 않는다. 처음 적격 후보군 밖의 문맥은 붙이지 않는다.
- 절 경계와 엔터티 메타데이터가 불완전한 기존 청크는 보수적으로 결합하지 않는다.
- 표는 행 구조를 보존해야 하므로 이 단계의 자유 텍스트 결합 대상이 아니다.
