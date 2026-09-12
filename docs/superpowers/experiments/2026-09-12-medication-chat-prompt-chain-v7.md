# Medication Chat Prompt Chain v7 실험 기록

## 목적

기존의 결정론적 질문 해석·검색·안전성 검사를 유지하면서, 필요한 구간에만 구조화 LLM 체인을 추가한다. 이번 작업의 성공 기준은 다음과 같다.

- 모든 프롬프트가 Role, Task, Content, Format, Constraint, Example 6요소를 명시한다.
- 낮은 신뢰도·복수 대상·세션 참조 질문만 Directional Query 후보가 된다.
- 상호작용 질문과 실제 근거가 함께 있을 때만 Evidence Reasoning 후보가 된다.
- LLM 출력은 서버가 제공한 entity key, pair key, 검색어, evidence ID 범위 안에서만 채택한다.
- 자유형 CoT는 모델 출력, Trace, API 응답에 남기지 않는다.
- 기존 Exact-pair → Entity → Semantic 검색, Small-to-Big 문맥 확장, 최대 1회 coverage retry를 유지한다.
- 새 Evidence Reasoning은 기본 비활성화 상태로 배포한다.

## 실험 1: 단계별 프롬프트 팩 로더

### 문제

단계별 프롬프트가 여러 파일에 흩어지면 공통 안전 규칙이 달라질 수 있고, 한 단계의 지시가 다른 단계에 섞일 수 있다.

### 실험

- RED: stage loader가 없어서 신규 테스트 4개가 `AttributeError`로 실패했다.
- 구현: `medication_chat_prompt_v7.md` 한 파일을 common/system/user/examples marker로 분리했다.
- 서버는 요청한 stage만 읽고 common과 해당 stage의 system·Example만 결합한다.
- marker 누락, 중복, 빈 구역을 오류로 처리했다.

### 결과

- 성공: 프롬프트 관련 테스트 21개 통과.
- 이유: 문자열 위치가 아니라 명시적인 marker 쌍과 enum stage를 사용해 구역 혼입을 차단했다.

## 실험 2: Directional Query

### 문제

규칙 기반 해석 결과가 낮은 신뢰도이거나 여러 대상·세션 참조를 포함하면 검색어가 부족할 수 있다. 반대로 LLM이 자유롭게 검색어를 만들면 입력에 없던 효과나 제품이 검색 의도에 섞일 수 있다.

### 실험

- RED: LLM 입력에 `allowed_search_terms`가 없어 허용 어휘 검증 테스트가 실패했다.
- 구현: 카탈로그 entity key, pair key, 허용 검색어, 현재 query plan을 구조화 입력으로 전달했다.
- 출력 stimulus는 검증된 대상명과 허용 검색어를 모두 포함할 때만 기존 `alternate_queries`에 추가했다.
- 예: `마그네슘 효능`은 채택하고, 입력에 없는 주장인 `마그네슘 피로회복`은 폐기한다.

### 결과

- 성공: 조건부 질문 해석·UseCase 회귀 테스트 98개 통과.
- 이유: LLM은 검색 방향을 제안하지만 서버의 subset 검증이 최종 채택 권한을 가진다.

## 실험 3: Evidence Reasoning 구조화 판정

### 문제

두 성분이 한 문서에 함께 등장했다는 이유만으로 직접 상호작용 근거로 오인할 수 있다. 자유형 CoT를 반환받으면 검증과 비노출 보장이 어렵다.

### 실험

- RED: 신규 스키마·체인이 없어 테스트 수집 단계에서 import 실패했다.
- 구현: `INTERACTION_CONFIRMED`, `NO_DIRECT_EVIDENCE`, `CONFLICTING_EVIDENCE`, `NOT_APPLICABLE` 판정과 claim을 Pydantic으로 제한했다.
- 모든 claim, supported action, conflict는 입력 evidence ID를 필수로 참조한다.
- 입력에 없는 ID, 상호작용 claim 없는 확정 판정, 충돌 ID가 2개 미만인 충돌 판정, 자유형 `reasoning` 필드를 거부한다.

### 결과

- 성공: Evidence Reasoning 단위 테스트 6개 통과.
- 이유: 모델 설명문이 아니라 검증 가능한 판정·claim·ID만 다음 단계로 전달한다.

## 실험 4: 조건부 런타임 연결과 실패 복구

### 문제

Evidence Reasoning을 모든 질문에 적용하면 비용과 지연이 늘고, 외부 모델 실패가 기존 답변까지 중단시킬 수 있다.

### 실험

- RED: 설정, 서비스 의존성, 내부 결과 필드, 최종 프롬프트 payload가 없어 관련 테스트가 실패했다. 공용 UseCase 팩토리에 새 인자를 먼저 추가해 기존 테스트도 연쇄 실패했으며, 이는 생성자 계약 미구현이 원인이었다.
- 구현: `INTERACTION_EVIDENCE_REASONING_ENABLED=false`를 기본값으로 추가했다.
- 활성화된 경우에도 상호작용 질문, 두 개 이상의 검증된 대상, 승인 규칙 또는 검색 청크가 모두 있어야 호출한다.
- 체인 오류나 출력 검증 실패는 Trace에 오류 유형만 기록하고 기존 결정론적 초안을 유지한다.
- 판정 결과는 `exclude=True` 내부 필드로 최종 Answer Generation에만 전달한다.

### 결과

- 성공: 설정·서비스·UseCase·최종 payload 관련 테스트 131개 통과.
- 이유: feature flag와 호출 조건이 비용 범위를 제한하고, 예외 경계가 기존 답변 경로를 보존한다.

## 실험 5: 기존 LLM 단계의 v7 전환

### 문제

Conversation Gate, 증상 후속 응답, 복약메모 요약, 최종 답변이 각각 이전 프롬프트 파일을 사용하고 있었다.

### 실험

- RED 1: `CONVERSATION_RESPONSE_PROMPT_VERSION`이 없어 테스트 수집 단계에서 실패했다.
- RED 2: v7의 활성 복약·영양제 입력 키가 명시되지 않았고, 이전 테스트의 `# 제목` 계약이 현재 굵은 제품명 형식과 충돌해 3개가 실패했다.
- 수정: 네 컴포넌트가 v7의 자기 stage만 로드하도록 전환했다.
- 각 stage에 Role, Task, Content, Format, Constraint, Example을 명시했다.
- 최종 답변에는 `active_medication_names`, `active_supplement_names`, 표시 조건, 빈 섹션 제외, 굵은 제품명 형식을 명시했다.

### 결과

- 성공: v7 단계 전환과 관련 회귀 테스트 138개 통과.
- 이유: 공통 근거 경계는 한 번만 유지하고, 각 단계의 역할과 출력 형식을 분리했다.

## 보존된 기존 검색 구조

이번 변경은 검색기를 교체하지 않았다.

1. Query Plan이 검증된 대상, 요청 section, pair key를 만든다.
2. Qdrant는 Exact-pair → Entity → Semantic tier 순서로 후보를 찾는다.
3. 작은 청크로 찾은 뒤 Parent 문맥을 가져오는 Small-to-Big 흐름을 유지한다.
4. 요청 section의 근거가 부족할 때 coverage 기반으로 최대 한 번만 재검색한다.
5. Directional Query는 검증된 stimulus를 `alternate_queries`에 더할 뿐 tier와 필터를 우회하지 않는다.
6. Evidence Reasoning은 검색 후 근거를 판정할 뿐 검색 순위와 안전 규칙을 대체하지 않는다.
7. 최종 답변 뒤 `GroundedClaimValidator` 검사를 그대로 수행한다.

## 실험 6: 구현 후 단순화·안전성 검토

### 문제

초기 GREEN 구현에는 검색 section 용어의 중복, pair key의 느슨한 검증, LLM 구조화 출력 크기 무제한, 조건부 LLM 확인 질문의 미사용 문제가 남아 있었다.

### 실험

- RED: 잘못된 pair key, 다른 조합의 근거를 참조한 interaction claim, 5개 이상의 claim, 240자를 넘는 statement, 공백 statement를 기존 스키마가 허용했다.
- RED: 조건부 LLM이 `needs_clarification=true`와 확인 질문을 반환해도 RAG 검색과 일반 답변 생성이 계속됐다.
- RED: Evidence Reasoning에 관계없는 section 청크를 제외하는 경계가 없었다.
- 수정: 기존 SHA-256 pair-key 정규화 함수를 재사용하고, interaction claim이 요청 pair와 일치하는 `INTERACTION` 근거만 참조하도록 검증했다.
- 수정: claim 최대 4개, 문장·근거 ID·충돌 ID 길이와 개수를 제한하고 공백 값은 검증 전에 정리해 거부했다.
- 수정: 조건부 LLM의 확인 질문을 검색 전에 `CLARIFICATION` 응답으로 반환하고, 검색 자극 허용어는 Query Plan의 `expanded_query`에서 파생했다.
- 수정: 상호작용 section 또는 요청 pair에 연결된 청크만 Evidence Reasoning에 전달했다.
- 단순화: v7 자산명과 marker parser를 한 곳으로 모으고, 재검색 후 확정된 `MedicationEvidenceBundle`을 근거 추론의 단일 입력으로 사용했다.

### 결과

- 성공: 신규 회귀를 포함한 대상 테스트 108개 통과.
- 이유: LLM이 입력 밖 근거나 과도한 출력으로 다음 프롬프트를 오염시키는 경계를 코드와 Pydantic 양쪽에서 제한했고, 확인이 필요한 질문은 검색 전에 종료한다.

## 실험 7: 검토에서 발견된 쌍 근거·실패 경계 보강

### 문제

구현 검토에서 다음 경계 문제가 확인됐다.

- 근거 항목이 허용 길이를 넘으면 Pydantic 입력 생성이 예외 복구 바깥에서 실패했다.
- 여러 상호작용 조합이 함께 있을 때 claim, 행동 안내, 충돌 판정이 다른 조합의 근거 ID를 인용할 수 있었다.
- 조건부 LLM이 일부 pair key만 선택해도 기존 pair 목록, interaction type, 재검색어, 승인 규칙에 선택되지 않은 조합이 남았다.
- LLM 확인 질문이 최종 근거·안전성 검사를 거치지 않고 바로 반환됐다.
- 모든 Directional Stimulus가 서버 검증에서 거부돼도 일부 LLM 해석값이 기존 Query Plan을 변경했다.

### 실험

- RED: 과대 근거 입력이 결정론적 답변 대신 `ValidationError`를 발생시키는 테스트를 추가했다.
- RED: 다른 pair의 근거를 claim·supported action·conflict에 연결하는 출력이 채택되는 테스트를 추가했다.
- RED: 단일 pair 선택 뒤 선택되지 않은 pair와 승인 규칙이 실행 계획에 남는 테스트를 추가했다.
- RED: 안전하지 않은 확인 질문과 전부 거부된 stimulus가 기존 흐름을 변경하는 테스트를 추가했다.
- 수정: 근거 입력 모델 생성까지 예외 복구 범위에 포함했다.
- 수정: 상호작용 claim, supported action, conflict가 각각 명시한 `pair_key`와 동일한 pair metadata를 가진 `INTERACTION` 근거만 참조하도록 검증했다.
- 수정: 조건부 pair 선택 시 pair 목록·타입·재검색어·승인 규칙을 같은 선택 집합으로 좁혔다.
- 수정: 확인 질문도 `GroundedClaimValidator`를 통과시키고, 유효 stimulus가 하나도 없으면 원래 Query Plan을 그대로 유지했다.
- 수정: LLM 텍스트·배열 필드에 길이와 항목 수 제한을 추가하고, `PARTIAL + NO_DIRECT_EVIDENCE` 계약을 명세와 코드에서 일치시켰다.

### 결과

- 성공: 신규 경계 테스트를 포함한 관련 테스트 141개 통과.
- 이유: evidence ID 존재 여부만 검사하던 경계를 정확한 pair 단위로 강화했고, LLM 결과를 부분 채택할 때 파생 필드 전체를 동일한 범위로 정렬했다.

## 최종 검증

- `uv run ruff check ai_worker`: 통과.
- `uv run ruff format --check ai_worker`: 378개 파일 포맷 확인.
- `uv run pytest ai_worker/tests -q`: 1,383 passed, 1 skipped.
- 검토 보완 뒤 전체 테스트를 단독 실행했으며 종료 코드 0으로 통과했다. 이전 검증에서 한 차례 발생한 macOS `libc++`의 `recursive_mutex lock failed`는 재현되지 않았다.

## 현재 결론

- 구현 계약 검증: 성공.
- 기존 검색·안전 경계 회귀: 성공.
- 실제 OpenAI 모델을 사용한 품질·지연 A/B: 아직 수행하지 않음.
- Evidence Reasoning 런타임 활성화: 보류. 고정 평가 질문에서 정확도, 잘못된 대상 혼입률, P95를 비교한 뒤 환경별로 활성화한다.
