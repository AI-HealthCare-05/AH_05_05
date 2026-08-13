# 포케 — 프로젝트 안내

퇴원 환자용 회복 안내 웹앱. 퇴원 서류를 사진으로 올리면 OCR로 정보를 뽑고, 의학용어를
풀어 복약·생활·일정 안내를 만들어 보여줍니다. 모르는 것은 RAG 챗봇에 물어봅니다.

**사용자는 수술·입원 후 퇴원한 환자이고 상당수가 고령입니다.** 통증과 피로가 있는 상태로
앱을 씁니다. 여기서 나온 설계 원칙이 세 개입니다.

- 정보는 적게, 글자는 크게. 오늘 해야 할 것이 첫 화면에 보이게
- 터치 대상은 최소 44px
- **부담이나 죄책감을 주는 UI를 넣지 않습니다** — 미완료 체크리스트, 달성률, 연속 기록.
  퇴원 환자에게 숙제를 주는 앱이 되면 안 된다는 결정입니다

## 저장소 구조

```
app/         FastAPI 백엔드
ai_worker/   AI 워커 (OCR · LLM · RAG)
frontend/    React 프론트엔드
infra/  envs/  scripts/
docs/        이 폴더 — 프로젝트 안내와 테스트 입력
```

## 실행

**백엔드** — 저장소 루트 [`README.md`](../README.md) 참고 (uv · docker compose)

**프론트엔드**

```bash
cd frontend
pnpm install
pnpm dev
```

브라우저에서 **`/dev/gallery`** 를 열면 컴포넌트가 다 보이고, **`/dev/document-upload`** 로
시작하면 만들어진 화면을 순서대로 지나갑니다. 백엔드를 띄우지 않아도 목업으로 끝까지 돕니다.

자세한 내용은 [`frontend/README.md`](../frontend/README.md) 에 있습니다.

## 역할별 첫 걸음

**프론트엔드** — `frontend/README.md` 의 폴더 구조(FSD)·색·컴포넌트 규칙을 먼저 읽으세요.
디자인 토큰과 화면별 Figma node-id 는 [`frontend/docs/design-tokens.md`](../frontend/docs/design-tokens.md) 에 있습니다.

**백엔드 · AI 파이프라인** — 프론트가 기대하는 요청·응답 형태는 노션 API 명세를 보세요
(아래 표). 프론트는 백엔드 없이도 목업으로 돌아가므로 엔드포인트를 하나씩 붙여도
나머지 화면이 죽지 않습니다.

OCR 테스트 입력은 [`sample-docs/`](sample-docs/README.md) 에 있습니다 — 가상 진료문서 14장
(환자 2명 × 문서 3~4종 × 깔끔한 버전 / 그늘지고 잘린 버전). 확인해야 할 항목이 같은 폴더
README 에 적혀 있습니다.

## 저장소 밖 문서

기획 산출물과 협업 문서는 저장소에 두지 않습니다. 코드와 함께 버전이 움직이지 않고,
xlsx 는 git 에서 diff 도 되지 않습니다.

| 문서 | 무엇이 있나 | 위치 |
|---|---|---|
| 요구사항정의서 | **화면에 안 보이는 동작 규칙의 기준.** 활성 기간 계산, 화면 순서 등 | (노션 링크) |
| API 명세 | 엔드포인트별 요청·응답 형태 | (노션 링크) |
| ERD | 테이블 설계 | (dbdiagram 링크) |
| Figma | 화면 디자인 | (Figma 링크) |

백엔드가 붙은 뒤에는 API 의 진실의 출처가 FastAPI 의 `/docs`(OpenAPI) 입니다.
손으로 쓴 명세는 그때부터 참고용입니다.

## 어긋날 때 무엇이 기준인가

**화면에 보이지 않는 규칙은 Figma를 봐도 알 수 없습니다.** 추측하지 말고 문서를 보세요.

| 무엇 | 기준 |
|---|---|
| 레이아웃 · 간격 · 색 · 문구 | Figma |
| 동작 규칙 · 계산식 · 화면 순서 | 요구사항정의서 |
| API 요청 · 응답 형태 | API 명세 → (백엔드 구현 후) OpenAPI |
| 토큰 · 컴포넌트 prop 이름 | `frontend/docs/design-tokens.md` |

**문서끼리 어긋나는 것을 발견하면 한쪽을 골라 진행하지 말고 먼저 알려주세요.**
실제로 여러 번 있었고, 그때마다 사람의 판단이 필요했습니다.

## 자주 막히는 것

**`Cannot find module 'react'` 가 IDE에서만 뜬다**
WSL에서 `pnpm install` 하고 Windows IDE로 편집하는 조합입니다. `frontend/pnpm-workspace.yaml`
의 `nodeLinker: hoisted` 로 해결해뒀습니다. `pnpm config get node-linker` 가 `hoisted` 로
나오는지 확인하세요. 대신 의존성 격리가 약해지므로 **새 패키지는 꼭 `pnpm add`** 로 선언하세요.

**`ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION` 으로 설치가 막힌다**
pnpm 11부터 배포된 지 24시간이 안 된 패키지를 거부합니다(공급망 공격 방어). 전이 의존성이
방금 배포됐을 때 걸립니다. `frontend/pnpm-workspace.yaml` 의 `minimumReleaseAgeExclude` 에
해당 패키지만 추가하세요. **`minimumReleaseAge` 를 0으로 낮추거나 정책을 끄지 마세요.**

**`ERR_PNPM_IGNORED_BUILDS: esbuild`**
`pnpm approve-builds` 로 esbuild를 승인하세요.

**WSL과 PowerShell을 번갈아 쓰면 깨진다**
`node_modules` 의 esbuild 바이너리가 OS별로 다릅니다. 한쪽만 정해서 쓰세요.

**Figma MCP로 화면을 읽으면 Cover 페이지만 나온다**
정상 동작입니다. 파일 키만 주면 첫 페이지만 반환됩니다. **node-id를 반드시 함께** 넘겨야
합니다. 화면별 node-id는 `frontend/docs/design-tokens.md` 에 있습니다.

## 지금 어디까지 됐나

**되는 것 (프론트, 목업 데이터로)** — 문서 업로드 → 등록 확인 → OCR 결과 확인·수정
(복약 편집 모달, 저신뢰 확인) → 복약 시간 설정 → 시간 선택. 6화면이 끝까지 이어집니다.

**안 되는 것** — 로그인·회원가입, 동의 화면, 홈 대시보드, 복약/생활/일정 안내, RAG 챗봇,
마이페이지, 재업로드 시 히스토리 매칭.

`/dev/flow-complete` 는 홈 화면이 없어서 만든 개발용 임시 화면입니다. 홈이 생기면 지웁니다.

## 용어

| 말 | 뜻 |
|---|---|
| **활성 기간** | `퇴원일 + 처방 복용일수`. 오늘이 이 안에 있는 진료기록만 홈에 노출됩니다 |
| **신뢰도 구간** | OCR 확신도를 `high`/`medium`/`low` 세 단계로만 표현. 화면에 퍼센트를 노출하지 않습니다 |
| **`batchId`** | 한 번에 올린 문서 묶음의 ID. OCR 결과를 조회하는 키 |
| **`tempId`** | 저장 확정 전 OCR 항목의 임시 ID. 확정되면 실제 ID가 생깁니다 |
| **`statusCode`** | 계정 상태(`pending`/`active`). 로그인 후 홈으로 갈지 문서 등록으로 갈지 이걸로 판단합니다 |
| **REQ-XXX-NNN** | 요구사항 번호. 화면 하나 = REQ 하나 = 페이지 하나 |
