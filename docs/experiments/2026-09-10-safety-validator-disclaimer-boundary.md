# 안전성 검사 면책문구 경계 검증 기록

## 목적

`타이레놀은 어디에 좋고 먹을 때 뭘 조심해야 해?`처럼 효능·주의사항을 묻는
답변이 `MEDICATION_CHANGE_INSTRUCTION`으로 과차단될 수 있다는 관측을
검증했다. 실제 복약 변경 지시는 계속 차단해야 한다.

## 가설과 결과

| 항목 | 결과 |
| --- | --- |
| 가설 | 고정 `MEDICAL_DISCLAIMER`가 복약 변경 정규식에 매칭된다. |
| 재현 | 실패 — 현재 고정 문구는 `복용 시작·중단·용량 변경은 … 상의하세요` 형태여서, 명령형 `중단하세요`를 요구하는 정규식과 매칭되지 않았다. |
| 안전 회귀 | 성공 — `오늘부터 약 복용을 중단하세요`는 면책문구가 함께 있어도 계속 `BLOCKED`다. |
| 답변 회귀 | 성공 — 타이레놀 효능·주의사항과 고정 면책문구는 `MEDICATION_GUIDE` / `SAFE`로 유지된다. |

## 적용한 경계

정책 정규식은 고정 `MEDICAL_DISCLAIMER`을 제거한 사본만 검사한다. 표시할
원문과 면책문구 존재 여부 판정에는 원문을 그대로 사용한다. 따라서 이후
면책문구 문구가 바뀌더라도 정책 안내가 복약 변경 명령으로 해석되지 않으며,
LLM 또는 근거가 생성한 실제 변경 지시는 기존과 동일하게 차단된다.

## 원래 Trace와의 관계

DB에는 `safety_reason_code`만 저장되고 매칭된 원문 조각은 저장되지 않는다.
매칭 조각의 해시는 LangSmith `safety.validate` span에만 남는다. 따라서 당시
Trace의 `MEDICATION_CHANGE_INSTRUCTION`은 이 고정 상수가 아닌 생성 답변 또는
출처 문구에서 나온 직접 명령으로 판단한다. 재발 시 해당 span의
`matched_fragment_hash`, `matched_action`, `matched_target`을 함께 확인한다.

## 검증

```text
uv run --group ai --group app pytest \
  ai_worker/tests/safety/test_grounded_claim_validator.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py -q

85 passed

uv run ruff check \
  ai_worker/safety/grounded_claim_validator.py \
  ai_worker/tests/safety/test_grounded_claim_validator.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py

All checks passed
```
