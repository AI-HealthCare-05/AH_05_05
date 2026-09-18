# AI 보고서 프롬프트 편집 안내

다음 UTF-8 Markdown 파일이 코드에서 직접 읽는 원본입니다. 설명용 복사본이 아닙니다.
각 파일의 전체 내용이 모델에 전달되므로 프롬프트와 관계없는 작업 메모를 넣지 마세요.

| 파일 | 용도 | 메시지 역할 |
| --- | --- | --- |
| `intake_report_planner.md` | 섹션·등록 대상·검색 질문 계획 | system |
| `intake_report_claims.md` | 검색 원문 기반 섹션 초안 | system |
| `intake_report_verifier.md` | 원문 대조, 충돌 검사, 편집·재검증 | system |
| `intake_report_spacing.md` | 기존 약 안내의 공백만 교정 | system |
| `intake_report_spacing_retry.md` | 교정 거부 후 재시도 | user |

RAG의 입력 JSON과 출력 스키마, 검색 한도, 대상·인용·수치 검증은 코드가 담당합니다.
문서 분리 당시에는 기존 문구를 유지했습니다. 이후 RAG 3개 문서에 아래 지침을 보완했습니다.
프롬프트 보완 당시 모델 설정·출력 스키마·코드 검증·호출 한도는 유지했습니다.
후속 코드 보완에서 내부 주장 스키마를 `evidence: [{chunk_id, exact_quote}]`로 변경했습니다.
공개 카드 스키마, 모델 설정, 검색·호출 상한은 그대로입니다.
프론트·메일의 표시 규칙만 뒤에서 바뀌었으며 담당 위치는 아래 표에 적었습니다.
주장별 형식 검증으로 잘못된 후보만 제외하며, 삭제·정렬만 바뀐 경우에는 재검증을 하지 않습니다.
수정된 주장만 재검증하고, 재검증 실패가 이미 검증된 다른 주장을 지우지 않도록 분리합니다.
제외 사유는 `claim_rejected_*` 집계 수치로 기록하며 원문·제품명은 기록하지 않습니다.
`intake_report_spacing_retry.md`의 `{repair_error}`는 실행 시 오류 사유로 치환합니다.
그 외 중괄호를 리터럴로 추가하려면 `{{`, `}}`로 작성하세요.

## 로딩 및 반영

- 공통 로더: `ai_worker/llm/prompts/prompt_assets.py`의 `load_prompt_asset()`.
- 작업 디렉터리와 무관하게 Python 패키지의 `assets`에서 읽습니다.
- 허용 목록에 등록된 파일만 읽으며, 누락·빈 파일은 오류입니다. 코드 내 문구로 대체하지 않습니다.
- 로더가 프로세스별로 캐시하므로 편집 후 해당 서버/워커 프로세스를 재시작해야 합니다.
- Docker는 `COPY ./ai_worker ./ai_worker`로 문서를 포함합니다. 배포본 변경은 이미지 재빌드·재배포가 필요합니다.
- RAG 경로는 이제 기본으로 켜져 있습니다(`INTAKE_REPORT_RAG_ENABLED: bool = True`,
  `ai_worker/core/config.py`). 환경변수로 `false`를 주는 것이 명시적 opt-out입니다.
  기본값에서는 planner·claims·verifier 3개 문서가 모두 실행되고,
  `intake_report_spacing*.md`는 함께 도는 기존 카드 생성기 쪽에서 실행됩니다.
  `false`로 끄면 planner·claims·verifier는 호출되지 않고, 대신 검토된 등록 기반
  생활 안내(`include_fixed_lifestyle_guidance`)가 켜집니다.

기존 `intake_report_prompt_v11.md`는 별도 Markdown 생성 경로의 문서입니다.
`intake_report_plain_language*.md`는 별도 쉬운 말 편집 경로입니다. 이번 분리 대상과 혼동하지 마세요.

## 출력 규칙의 담당 위치

카드 생성 이후의 표시 규칙은 프롬프트가 아니라 코드가 결정합니다. 아래 표는
같은 규칙이 웹과 메일에서 어긋나지 않도록 실제 담당 파일을 적은 것입니다.

| 규칙 | 담당 |
| --- | --- |
| 제품 묶음 1개 제목, 카테고리·주의 제목 중복 제거 | `ai_worker/reports/guidance_groups.py`의 `product_guidance_display()` |
| 같은 설명·행동 병합, 성분 공통 안내 1회 표시 | 같은 함수. 공백만 다른 문구는 합치고 다른 문구는 보존합니다. |
| 본문 200자(공백 포함) 규칙과 펼치기 | 같은 모듈의 `summarize_guidance_body()`와 `BODY_PREVIEW_LIMIT` |
| 근거를 대상 → 출처로 묶어 제목 1회 + 인용 목록 | 같은 모듈의 `group_guidance_evidence()` |
| 일반적인 과다 섭취 경고의 상한 초과 확인 | `ai_worker/reports/report_rag_pipeline.py`의 `_filter_generic_overconsumption_cards()` |
| 위 규칙의 웹 표시 | `frontend/src/pages/reports/V11ReportBody.tsx` |
| 위 규칙의 메일·첨부 표시 | `app/core/email/intake_report_renderer.py`, `app/static/templates/emails/intake_report_cards.html` |

- 200자 규칙: 본문이 200자 이하이면 그대로 보여 주고, 넘으면 문장 경계에서만 자른
  요약을 먼저 보여 준 뒤 펼치기로 원문 전체를 그대로 제공합니다. 요약을 만들기 위한
  추가 모델 호출은 없습니다. 웹은 React 상태, 첨부 HTML은 `<details>`로 펼치며,
  `<details>`가 없을 수 있는 메일 본문에는 전체 본문을 그대로 넣습니다.
  한 문장이 혼자 200자를 넘는 경우에만 문장을 자르지 않고 통째로 보여 주므로 요약이
  200자를 넘을 수 있습니다. 문장 중간에서 끊어 경고를 반쪽만 보여 주지 않기 위한 선택입니다.
- 과다 섭취 경고: 성분 합계와 상한이 모두 확인되고 합계가 상한을 실제로 초과할 때만
  일반적인 과다 섭취 경고를 남깁니다. 합계·상한을 모르거나 같은 성분 행이 둘 이상이면
  그 경고만 보류하며, 이를 안전하다는 뜻으로 바꿔 쓰지 않습니다. 특정 반응·질환명이
  들어간 경고와 병용 경고는 이 판단과 무관하게 그대로 둡니다. 성분 합계의 비교 가능
  조건은 `ai_worker/reports/v11_lifestyle_guidance.py`의
  `SUPPORTED_CALCULATION_STATUSES` 하나만 사용합니다.
- 일반 상담 문구 제외는 코드가 아니라 `intake_report_claims.md`가 담당합니다. 특정
  반응·질환명이나 심각도 표현이 없는 상담 권고 문장만 claim에서 빼고, 같은 문단의
  구체적인 경고는 남깁니다. 어떤 약·성분 이름도 코드에 넣지 않습니다.
- 위 규칙의 합성 입력 회귀 시험은 `ai_worker/tests/reports/test_report_guidance_quality.py`에 있습니다.

## 프롬프트 수준 보완

- Planner: 한국어 질의, 등록 대상 유지, 중복 검색 억제, 입력에 없는 성분·질환 추측 금지.
- 작성: 섹션 경계, 각 문장의 조건명 유지, 원문 인용과 청크의 순서 대응, 근거 없는 행동 안내 금지.
- 검증: 대상·조건·부정·수치·행동을 각각 대조. 유효한 문장은 `grounded` 외에 그대로 유지하고 잘못된 주장만 제외.
- 띄어쓰기 프롬프트는 변경하지 않았습니다. 기존 글자 보존 제약을 유지합니다.

가상 입력으로 비교하려면 저장소 루트에서 아래 명령을 사용합니다.
외부 모델을 3회 호출하므로 비용이 발생합니다. 실제 환자 데이터는 사용하지 않습니다.

```powershell
.venv/Scripts/python.exe -m scripts.evaluate_report_prompts --run-live
```

이 평가는 제한된 조건 보존·대상 결합·원문 일치·검증 유지 사례만 검사합니다.
의학적 품질 전체나 환각 방지를 보장하지 않습니다. 문서가 길어져 입력 토큰은 증가할 수 있습니다.
