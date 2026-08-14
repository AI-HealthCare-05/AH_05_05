# 포케 프론트엔드

퇴원 환자용 회복 안내 웹앱. 퇴원 서류를 사진으로 올리면 OCR로 정보를 뽑고, 의학용어를 풀어
복약·생활·일정 안내를 만들어 보여줍니다. 모르는 것은 RAG 챗봇에 물어볼 수 있습니다.

**사용자는 수술·입원 후 퇴원한 환자이고 상당수가 고령입니다.** 정보는 적게, 글자는 크게,
부담을 주는 UI(미완료 체크리스트·달성률 등)는 넣지 않습니다.

## 처음 오셨다면

**→ [`../docs/README.md`](../docs/README.md) 를 먼저 읽어주세요.**
역할별로 무엇부터 해야 하는지, 문서가 어디 있는지, 자주 막히는 것이 정리돼 있습니다.

| 하려는 일 | 볼 곳 |
|---|---|
| 화면 만들기 (프론트) | 이 문서 아래 계속 |
| 엔드포인트 · OCR/LLM/RAG 파이프라인 | 루트 `app/` · `ai_worker/` |
| 요청·응답 형태 확인 | 노션 API 명세 (붙은 뒤에는 FastAPI `/docs`) |
| 동작 규칙 · 계산식 확인 | 노션 요구사항정의서 |
| 토큰 · 컴포넌트 · Figma node-id | [`docs/design-tokens.md`](docs/design-tokens.md) |

빠르게 화면만 보려면 `pnpm install && pnpm dev` 후 **`/dev/gallery`**. 백엔드 없이도 돕니다.

## 스택

React 19 + Vite 6 + TypeScript + Tailwind CSS v4 + react-router v7(declarative).

패키지 매니저는 **pnpm만 사용**합니다. npm/yarn 명령은 쓰지 마세요.

## 시작하기

```bash
pnpm install
pnpm dev
```

`/` 는 아직 실제 진입 분기(user.status_code 기준 pending/active 분기)가 없어 안내 문구만 보여줍니다. 화면은 아래 dev 라우트로 바로 열어보세요.

- `/dev/gallery` — 컴포넌트 갤러리(`src/app/DevGallery.tsx`). 새 컴포넌트를 추가하면 여기에 사용 예시를 붙입니다.
- `/dev/document-upload`, `/dev/document-confirm`, `/dev/ocr-review` 등 — 화면 단위 dev 라우트. `src/app/router.tsx`에서 관리합니다.

```bash
pnpm typecheck   # 타입 검사만
pnpm build       # 타입 검사 + 프로덕션 빌드 (tsc -b && vite build)
pnpm preview     # 빌드 결과 로컬 미리보기
```

### WSL + Windows IDE 조합으로 작업할 때

`pnpm-workspace.yaml`에 `nodeLinker: hoisted`를 두었습니다. WSL(`/mnt/c/...`)에서 `pnpm install`을 돌리고 Windows 네이티브 IDE(PyCharm·WebStorm 등)로 편집하면, pnpm 기본 방식이 만드는 symlink를 Windows 쪽 TypeScript 서비스가 따라가지 못해 모든 의존성이 `Cannot find module 'react'`로 뜹니다. hoisted는 실제 폴더를 깔아 이 문제를 없앱니다.

> **주의:** pnpm 11부터 pnpm 설정은 `.npmrc`가 아니라 `pnpm-workspace.yaml`에서 읽습니다. `.npmrc`에 `node-linker=hoisted`를 써도 조용히 무시됩니다(`pnpm config get node-linker`가 `undefined`로 나오면 이 경우). pnpm 10 이하와 섞여 있는 팀이라면 `.npmrc`도 함께 두면 양쪽 모두 커버됩니다.

적용됐는지 확인하려면:

```bash
pnpm config get node-linker     # hoisted 가 나와야 함
ls -la node_modules | grep ^l   # 아무것도 안 나와야 함
```

대신 pnpm의 엄격한 의존성 격리가 약해지므로, **새 패키지는 반드시 `pnpm add`로 먼저 선언**하고 쓰세요. package.json에 없는 패키지를 import해도 통과해버릴 수 있습니다.

설치 시 `[ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: esbuild`가 뜨면 `pnpm approve-builds`로 esbuild를 승인하세요. 승인 결과도 `pnpm-workspace.yaml`에 기록됩니다.

## 폴더 구조 (Feature-Sliced Design)

```
src/
├── app/                    앱 진입점 · 라우터 · 전역 스타일
│   ├── main.tsx
│   ├── router.tsx          BrowserRouter/Routes. 실제 화면 + /dev/* 라우트
│   ├── DevGallery.tsx      컴포넌트 갤러리 (/dev/gallery)
│   └── styles/index.css    디자인 토큰 (Tailwind v4 @theme). 색은 여기만 수정
├── pages/                  화면 단위 (예: document-upload, document-confirm, ocr-review)
├── widgets/                여러 feature를 조합한 화면 조각 (현재 비어있음)
├── features/               사용자 행동 단위 기능 (현재 비어있음)
├── entities/                도메인 모델 + API 함수 (예: entities/document)
└── shared/
    ├── ui/                 공용 컴포넌트 (아래 표 참고)
    ├── lib/cn.ts           조건부 클래스 병합 헬퍼 (clsx + tailwind-merge)
    ├── api/client.ts       공통 fetch 헬퍼 (인증 헤더 · 오류 정규화)
    └── config/env.ts       VITE_USE_MOCK · API 경로. 여기서만 import.meta.env 를 읽습니다
docs/
└── design-tokens.md        토큰 표 · 컴포넌트 인터페이스 · 화면별 Figma node-id
```

프로젝트 전체 안내와 OCR 테스트 문서는 저장소 루트 [`../docs/`](../docs/README.md) 에 있습니다.

**임포트 방향은 위에서 아래로만** 허용합니다: `app → pages → widgets → features → entities → shared`. 역방향 임포트는 금지입니다. 경로는 전부 `@/*` alias(`src/*`)로 씁니다.

같은 코드가 3번째 반복될 때만 `shared`로 승격합니다.

## 색을 쓸 때

값을 직접 쓰지 말고 의미 토큰을 씁니다.

```tsx
// 이렇게
<div className="bg-card text-foreground border-border rounded-card" />

// 이렇게 하지 않기
<div className="bg-[#FFFFFF] text-[#0F172A]" />
```

토큰은 2단 구조입니다. `Primitives`(실제 색값) → 의미 토큰(`card`, `foreground`, `primary`, `warning-bg` 등). 코드에서는 의미 토큰만 참조하고, 색을 바꿀 때는 `src/app/styles/index.css`의 Primitives 값만 고칩니다. Figma 쪽도 같은 이름으로 100% 바인딩되어 있습니다.

주요 토큰: `background` `card` `foreground` `muted-foreground` `disabled-foreground` `muted-bg` `border` `input` `ring` `primary` `primary-strong` `primary-bg` `danger(-strong/-bg)` `warning(-strong/-bg)` `success(-strong/-bg)`

크기: `rounded-card`(12) `rounded-button`(8) `rounded-input`(8) `rounded-pill` / `h-header`(56) `h-tabbar`(56) `h-touch`·`size-touch`(44, NFR-ACC-001 최소 터치 영역) `px-page-x`(16) `max-w-app`(480)

shadcn/ui(Radix 기반) 컴포넌트가 요구하는 이름(`destructive`, `muted`, `accent`, `popover` 등)은 새 색을 만들지 않고 기존 값을 가리키는 **별칭**으로만 추가했습니다. 자세한 내용은 `index.css`의 "shadcn/ui 별칭 토큰" 블록 주석 참고.

## 컴포넌트

### 직접 작성 (Figma 치수 기준, shadcn으로 교체하지 않음)

| 컴포넌트 | 주요 prop |
|---|---|
| `Button` | `variant="primary\|secondary"`, `disabled`, `fullWidth` |
| `Card` | `tone="default\|info\|warning\|success"`, `title`, `titleRight`, `onClick` |
| `Input` | `label`, `error`, `hint` |
| `StatusBadge` | `type="new\|stopped\|dose\|frequency\|review\|active\|done"` |
| `Header` | `title`, `onBack`, `right` |
| `BottomTabbar` | `active`, `onChange` |

prop 이름은 Figma variant 이름과 일치시켜 두었습니다. 예를 들어 Figma의 `Status Badge / Type=Review`는 코드에서 `<StatusBadge type="review" />`입니다.

### shadcn/ui · Radix 기반 (인터랙티브 컴포넌트)

| 컴포넌트 | 비고 |
|---|---|
| `Checkbox` | Radix Checkbox. `checked`, `onCheckedChange` |
| `CheckboxField` | Checkbox를 감싼 라벨+설명 조합. `checked`, `onCheckedChange`, `label`, `description?`, `required?` |
| `Switch` | Radix Switch (구 `Toggle`을 대체) |
| `Dialog` 계열 | `DialogTrigger/Content/Header/Title/Description/Footer/Close` |
| `Select` 계열 | `Select/SelectTrigger/SelectValue/SelectContent/SelectItem` 등 |
| `Tabs` 계열 | `Tabs/TabsList/TabsTrigger/TabsContent` |
| `Toaster` | sonner. `src/app/main.tsx`에 전역으로 마운트되어 있고, 어디서든 `toast(...)`로 호출 |

이 사이트 네트워크 정책상 `shadcn` CLI를 실행할 수 없어서, 위 컴포넌트들은 공식 shadcn/Radix 소스를 직접 옮겨 작성했습니다. `components.json`은 FSD 경로에 맞춰 손으로 작성해뒀으니, 네트워크가 열린 환경에서 `pnpm dlx shadcn@latest add <component>`를 돌리면 그대로 이어서 쓸 수 있습니다.

## 중요

**화면에 보이지 않는 규칙은 Figma를 봐도 알 수 없습니다.** 홈 진입 분기, 활성 기간 계산(퇴원일 + 복용일수), OCR 신뢰도 처리, 재업로드 시 화면 순서 같은 것이 그렇습니다.

| 무엇 | 기준 |
|---|---|
| 레이아웃 · 간격 · 색 · 문구 | Figma |
| 동작 규칙 · 계산식 · 화면 순서 | 노션 요구사항정의서 |
| API 요청 · 응답 형태 | 노션 API 명세 → (백엔드 구현 후) FastAPI `/docs` |
| 토큰 · 컴포넌트 prop 이름 | [`docs/design-tokens.md`](docs/design-tokens.md) |

**어긋나는 것을 발견하면 임의로 한쪽을 골라 진행하지 말고 먼저 알립니다.** 실제로 여러 번 있었고 그때마다 사람의 판단이 필요했습니다.

## 하지 말 것

- 요구사항정의서에 없는 로직을 추측해서 구현하기
- 색·간격·폰트 크기를 하드코딩하기 (의미 토큰만 사용)
- 토큰 이름이나 컴포넌트 prop 이름을 임의로 바꾸기
- 승인 없이 라이브러리 추가하기 (`pnpm add` 로 먼저 선언)
- `Card`·`StatusBadge`·`Header`·`BottomTabbar` 를 shadcn 것으로 교체하기
- 환자에게 부담을 주는 완료 체크·달성률·연속 기록 같은 UI 를 넣기
- FSD import 방향(위→아래)을 어기기

## 설치가 안 될 때

패키지 버전 문제로 `pnpm install`이 실패하면, 빈 폴더에서 아래로 새로 만든 뒤 이 폴더의 `src/`, `docs/`, `index.html`만 복사해 넣으세요.

```bash
pnpm create vite@latest . -- --template react-ts
pnpm add tailwindcss @tailwindcss/vite
```

그리고 `vite.config.ts`에 `tailwindcss()` 플러그인을 추가합니다.

## 백엔드 연동

백엔드는 저장소 루트의 `app/`(FastAPI)입니다. 실행 방법은 루트 README 를 보세요.

프로젝트 루트가 아니라 이 폴더에 `.env.local` 을 만들고 한 줄 넣으면 실제 서버를 호출합니다.

```
VITE_USE_MOCK=false
```

없으면 목업 데이터로 돕니다(기본값). 백엔드를 띄우지 않고 화면만 볼 때는 이게 편합니다.
`vite.config.ts` 의 proxy 가 `/api` 요청을 `http://127.0.0.1:8000` 으로 넘기므로 CORS 설정은 필요 없습니다.
포트가 다르면 `.env.local` 에 `VITE_API_PROXY_TARGET` 을 넣으세요.

### 목업 ↔ 실서버 전환 지점

화면(pages/features)은 API 를 직접 부르지 않습니다. `entities/*/api.ts` 만 부릅니다.
그 안에서 `USE_MOCK` 으로 갈라지므로, 엔드포인트가 하나 완성되면 그 함수의 목업 분기만
지우면 되고 **화면 코드는 바뀌지 않습니다.**

```
화면 → entities/*/api.ts → USE_MOCK ? api.mock.ts : shared/api/client.ts → 서버
```

목업 값의 기준은 `../docs/sample-docs` 의 환자1(김철수) 문서입니다.
백엔드와 화면이 어긋나 보이면 `api.mock.ts` 와 대조하세요.

