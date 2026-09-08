# 조건부 구조화 LLM 질문 해석 실험 기록

## 상태

`PARTIAL` — `with_structured_output` 기반 JSON Schema 어댑터와 안전 게이트를 구현했지만, 기본값은 비활성이고 실제 모델 비용이 드는 고정 평가 세트 비교는 아직 수행하지 않았다.

## 가설

규칙·카탈로그 해석이 고신뢰 단일 엔터티를 이미 확정한 경우에는 LLM을 호출하지 않고, 저신뢰·복수 엔터티·동일 세션 참조인 경우에만 구조화 출력으로 요청 섹션을 보완하면 정확도를 개선할 여지가 있다.

## 변경

- `ConditionalQuestionInterpretationInput`에는 질문, 기존 카탈로그 후보 최대 12개, 현재 요청 섹션, 호출 사유만 담는다.
- `ConditionalQuestionInterpretationOutput`은 버전, 후보 정식명 목록, 요청 섹션, 신뢰도, 사유 코드만 허용한다. `extra="forbid"`로 자유 형식 `reasoning`/CoT 필드를 거부한다.
- OpenAI 호출은 `ChatOpenAI.with_structured_output(..., method="json_schema", strict=True)`를 사용한다.
- `CONDITIONAL_QUESTION_INTERPRETATION_ENABLED=false`가 기본값이다. 꺼져 있으면 기존 규칙 기반 LCEL 계획만 사용한다.
- 활성화 조건은 다음 셋 중 하나다.
  - 규칙 해석 신뢰도가 `HIGH`가 아님
  - 확정 엔터티가 둘 이상임
  - 현재 세션 참조 엔터티가 있음
- 모델이 제시한 이름은 기존 `query_plan.entities`의 정식명과 정규화 비교해 교집합만 인정한다. 미확인 이름은 검색·제품 조회·답변 근거에 전달하지 않는다.
- 모델은 기존 엔터티를 삭제하지 않는다. 허용 섹션만 기존 검색 계획에 추가할 수 있다.

## 검증

| 사례 | 기대 결과 | 결과 |
| --- | --- | --- |
| 고신뢰 단일 `타이레놀` 질문 | 조건부 LLM 미호출 | PASS |
| 모델이 `존재하지않는성분` 제시 | 검색 계획 엔터티에 미포함 | PASS |
| JSON에 `reasoning` 필드 주입 | Pydantic 검증 거부 | PASS |
| 기본 설정 | 조건부 체인 `None` | PASS |

`query.plan.conditional` Trace에는 버전·호출 사유·모델 신뢰도·사유 코드·허용/폐기 개수·추가 섹션 수만 남긴다. 콘텐츠 수집을 명시적으로 켠 개발 환경에서만 검증된 정식명을 추가로 볼 수 있다.

## PARTIAL 이유와 채택 기준

현재는 외부 호출을 하지 않는 fixture 검증만 완료했다. 활성화 전에 규칙 단독과 조건부 모드를 같은 평가 계약으로 비교해야 한다.

- 정확한 경로·엔터티·요청 섹션 비율은 비감소
- 잘못된 대상 혼입률은 비증가
- P95와 LLM 호출 비율을 함께 기록
- 개선이 없으면 환경 변수 기본값을 유지하고 실험 어댑터만 보존

숨겨진 CoT는 어떤 환경에서도 DB·LangSmith 메타데이터·응답에 저장하지 않는다.
