# 포케 · 프론트엔드 구현 계약서

**대상 Figma 파일**: 포케 와이어프레임 (`rXdIMgnJTBnFXia6Eb5hAn`) / 작업 페이지 `Screens`
**기준 문서**: 노션 요구사항정의서 · 노션 API 명세
**작성 시점 상태**: 앱 UI 색상 토큰 바인딩 100% 완료 (하드코딩 색상 0건)
**스택**: React 19 + Vite + TypeScript + Tailwind v4 + pnpm + shadcn/ui, 폴더 구조는 FSD

---

## 0. 이 문서의 목적

Figma 디자인과 프론트엔드 코드를 같은 어휘로 묶기 위한 계약입니다. 핵심 원칙은 하나입니다 — **디자인은 토큰과 컴포넌트 안에서만 바꾸고, 코드는 토큰과 컴포넌트 이름으로만 참조한다.** 그러면 색이나 간격을 바꿔도 코드를 고칠 필요가 없습니다.

---

## 1. 색상 토큰 계약

Figma에는 2단 구조로 되어 있습니다. `Primitives`는 실제 색값이고, `Color`는 의미 이름으로 Primitives를 참조합니다. **프론트는 반드시 `Color` 레이어(의미 이름)만 사용하세요.** Primitives를 직접 쓰면 나중에 테마 변경이 불가능해집니다.

| Figma 변수 (Color) | 참조하는 Primitive | 실제 값 | 권장 CSS 변수 | 용도 |
|---|---|---|---|---|
| `background` | slate/50 | `#F8FAFC` | `--color-background` | 화면 바탕 |
| `card` | white | `#FFFFFF` | `--color-card` | 카드·입력창 등 표면 |
| `foreground` | slate/900 | `#0F172A` | `--color-foreground` | 본문·제목 텍스트 |
| `muted-foreground` | slate/600 | `#475569` | `--color-muted-foreground` | 보조 설명 텍스트 |
| `disabled-foreground` | slate/400 | `#94A3B8` | `--color-disabled-foreground` | 비활성 텍스트 |
| `border` | slate/200 | `#E2E8F0` | `--color-border` | 테두리·구분선 |
| `input` | slate/200 | `#E2E8F0` | `--color-input` | 입력창 테두리 |
| `ring` | blue/600 | `#2563EB` | `--color-ring` | 포커스 링 |
| `primary` | blue/600 | `#2563EB` | `--color-primary` | 주요 버튼·링크 |
| `primary-strong` | blue/700 | `#1D4ED8` | `--color-primary-strong` | 강조 링크 텍스트 |
| `primary-bg` | blue/50 | `#EFF6FF` | `--color-primary-bg` | 정보 카드 배경 |
| `danger` | red/600 | `#DC2626` | `--color-danger` | 오류·삭제 |
| `danger-strong` | red/700 | `#B91C1C` | `--color-danger-strong` | 오류 텍스트 강조 |
| `danger-bg` | red/50 | `#FEF2F2` | `--color-danger-bg` | 오류 카드 배경 |
| `warning` | amber/700 | `#B45309` | `--color-warning` | 주의 |
| `warning-strong` | amber/800 | `#92400E` | `--color-warning-strong` | 주의 텍스트 강조 |
| `warning-bg` | amber/50 | `#FFFBEB` | `--color-warning-bg` | 주의 카드 배경(즉시 연락할 증상, 확인 필요 항목) |
| `success` | green/700 | `#15803D` | `--color-success` | 완료·정상 |
| `success-strong` | green/800 | `#166534` | `--color-success-strong` | 완료 텍스트 강조 |
| `success-bg` | green/50 | `#F0FDF4` | `--color-success-bg` | 상태 뱃지 배경(활성) |

### 디자인 측 규칙
색을 바꿀 때는 **Primitives의 값만** 수정하세요(예: `blue/600`을 다른 파랑으로). `Color` 레이어의 참조 관계나 이름은 바꾸지 마세요 — 프론트 코드가 이 이름으로 연결돼 있습니다. 새 색이 필요하면 Primitive를 추가하고 `Color`에 의미 이름을 새로 만든 뒤 이 문서에 한 줄 추가해주세요.

### 프론트 측 규칙
색을 코드에 직접 쓰지 마세요. 위 CSS 변수 또는 Tailwind 테마 키로만 참조합니다. 화면에서 어떤 색인지 모를 때는 Figma에서 해당 요소를 선택하면 바인딩된 변수 이름이 보입니다.

---

## 2. 레이아웃·타이포 토큰 계약

| 구분 | Figma 변수 | 값 | 용도 |
|---|---|---|---|
| 간격 | `spacing/4·8·12·16·24·32` | 4·8·12·16·24·32 | auto-layout gap, padding |
| 모서리 | `radius/card` | 12 | 카드 |
| 모서리 | `radius/button` | 8 | 버튼 |
| 모서리 | `radius/input` | 8 | 입력창 |
| 모서리 | `radius/pill` | 9999 | 뱃지 |
| 크기 | `size/header` | 56 | 상단 헤더 높이 |
| 크기 | `size/tabbar` | 64 | 하단 탭바 높이 |
| 크기 | `size/touch-min` | 44 | 최소 터치 영역(NFR-ACC-001) |
| 크기 | `size/page-width` | 375 | 기준 화면 폭 |
| 크기 | `size/page-height` | 812 | 기준 화면 높이 |
| 크기 | `size/page-x` | 16 | 좌우 여백 |
| 크기 | `size/container-max` | 480 | 반응형 최대 폭(NFR-USE-001) |
| 폰트 | `family/sans` | Noto Sans KR | 전체 |
| 크기 | `size/sm·base·lg·xl·2xl` | 14·16·18·20·24 | 본문~제목 |
| 행간 | `line/sm·base·lg·xl·2xl` | 21·25.6·27·28·33.6 | 각 크기 대응 |

화면 컨테이너는 375px 기준으로 그려져 있고 좌우 여백 16px, 콘텐츠 폭 343px입니다. 반응형은 최대 480px까지 늘어나되 그 이상은 가운데 정렬입니다.

---

## 3. 컴포넌트 계약

현재 Figma에 정의된 컴포넌트와 프론트 컴포넌트 대응입니다. **variant 이름을 그대로 prop 이름으로 쓰는 것을 권장**합니다 — 그러면 디자인과 코드의 어휘가 일치해 소통 비용이 사라집니다.

| Figma 컴포넌트 | Variant (Figma) | 권장 React 인터페이스 | 현재 화면 사용 |
|---|---|---|---|
| `Button` | `Style`: Primary / Secondary<br>`State`: Default / Disabled | `<Button style="primary\|secondary" disabled>` | 13곳 |
| `Input` | `State`: Default / Error | `<Input error?>` | 12곳 |
| `Checkbox` | `Checked`: True / False | `<Checkbox checked>` | 3곳 |
| `Card` | (variant 없음, 단일) | `<Card tone="default\|info\|warning\|success">` | **0곳 — 화면은 직접 그린 프레임 사용** |
| `Status Badge` | `Type`: New / Stopped / Dose / Frequency / Review | `<StatusBadge type="...">` | 0곳 |
| `Header` | — | `<Header title back?>` | 화면마다 직접 그림 |
| `Bottom Tabbar` | — | `<BottomTabbar active="home\|med\|life\|schedule\|chat">` | 화면마다 직접 그림 |
| `ActiveRecordCard/Unified` | `State`: Default (단일) | `<ActiveRecordCard>` — prop 없음 | 6곳(홈 계열) |

### shadcn/ui와의 분업

인터랙티브 컴포넌트는 shadcn/ui(Radix 기반)를 쓰고, 표현용 컴포넌트는 이 파일에 정의된 것을 씁니다. 모달·셀렉트·탭은 포커스 트랩, 키보드 조작, 스크린리더 처리를 직접 구현하면 반드시 빠뜨리는 부분이 생기고, 이 앱은 모달이 많고 사용자가 고령자라 접근성이 실질적으로 중요합니다.

| 구분 | 담당 | 대상 |
|---|---|---|
| 인터랙티브 | shadcn/ui | Dialog, Select, Tabs, Checkbox, Switch, Toast(sonner) |
| 표현용 | `shared/ui` (직접 구현) | Button, Card, StatusBadge, Header, BottomTabbar |

토큰 이름이 겹칠 때는 우리 이름(Figma 기준)을 유지하고 shadcn이 요구하는 이름을 같은 값의 별칭으로 추가합니다. 예: `--color-destructive` = `danger`, `--color-muted` = `muted-bg`.

### 컴포넌트 계약의 알려진 공백
아래는 프론트가 코드로 구현할 때 필요한데 Figma 컴포넌트에는 아직 없는 것들입니다. 프론트에서 먼저 만들고 디자인이 나중에 Figma 컴포넌트로 따라오는 편이 빠릅니다.

- **Card의 톤 variant**: 화면에는 흰색(기본), 파란색(`primary-bg`, 정보 강조), 노란색(`warning-bg`, 주의) 세 가지 카드가 쓰이는데 Card 컴포넌트에는 variant가 없습니다. 코드에서는 `tone` prop으로 구현하세요.
- **Button의 Secondary + Disabled 조합**: Primary+Disabled만 있고 Secondary+Disabled가 없습니다. 코드에서는 두 조합 모두 지원하세요.
- **활성/완료 상태 뱃지**: `Status Badge`의 Type은 약물 비교용(New/Stopped/Dose/Frequency/Review)이라, 진료기록의 활성·완료 뱃지는 별개입니다. 홈·히스토리에서 쓰는 초록 뱃지(`success-bg` + `success`)를 `<StatusBadge type="active|done">`로 추가하세요.
- **Toggle(스위치)**: 알림 설정 화면에서 3개 사용 중입니다. 코드에서는 shadcn `Switch`를 씁니다.

---

## 4. 지켜야 하는 경계

**Figma만 보고 정하면 안 되는 것** — 화면에 보이지 않는 규칙은 Figma에 없습니다. 활성 기간 계산(퇴원일 + 복용일수), 상태코드 분기(pending → 문서 등록 / active → 홈), OCR 신뢰도 구간 임계값, 필수 동의 체크 후 버튼 활성화 조건, 히스토리 매칭 순서(재업로드 시 매칭이 OCR보다 먼저)는 모두 요구사항정의서에 있습니다. 추측하지 말고 문서를 봅니다.

**바꾸면 코드가 깨지는 것** — `Color` 레이어의 변수 이름, 컴포넌트 이름과 variant 이름, 화면 프레임 이름. 이 이름들이 코드의 CSS 변수와 prop 이름에 직결됩니다. 색을 바꾸려면 Primitives 값만 고칩니다.

**자유롭게 바꿔도 되는 것** — Primitives 색값, spacing·radius 수치, 폰트 크기·행간, 컴포넌트 내부 구성(패딩·정렬·아이콘), 텍스트 문구. 이 범위는 토큰과 컴포넌트를 통해 코드 수정 없이 반영됩니다.

## 5. 화면 인벤토리 (REQ ID ↔ Figma 프레임 ↔ node-id)

**Figma 조회 시 주의**: `get_metadata`나 `get_screenshot`에 파일 키만 주면 첫 페이지(`Cover`)만 반환되는 것이 정상 동작입니다. 데스크톱에서 페이지를 열어두는 것과 무관하며, **반드시 아래 node-id를 함께 넘겨야** 합니다.

파일 키 `rXdIMgnJTBnFXia6Eb5hAn` / 작업 페이지 `Screens` = `65:2`

| REQ ID | 주 화면 (node-id) | 상태 변형 (node-id) |
|---|---|---|
| REQ-USER-001 | `01 온보딩` **66:2** | — |
| REQ-USER-002 | `02-A 로그인` **66:20**<br>`02-B 회원가입` **66:40** | `A01 로그인 오류` **69:2** · `A02 회원가입 검증 오류` **69:18** · `A03 이메일 중복` **69:37** · `A04 비밀번호 재설정` **69:52** · `A05 임시 비밀번호 발송 안내` **199:25** · `02-A 기록 보유 시나리오` **142:50** |
| REQ-USER-003 | `18 마이페이지 · 설정` **68:2** | `P02 비밀번호 변경` **210:24** · `P04 회원탈퇴 확인` **212:24** |
| REQ-USER-004 | `P03 알림 설정` **211:24** | — |
| REQ-DOC-001 | `05 문서 업로드` **66:97**<br>`22 문서 업로드 · 재업로드` **68:81** | `D01 동의 거부` **69:67** · `D02 업로드 진행` **69:82** · `D03 업로드 완료` **69:101** · `D04 지원하지 않는 파일` **69:114** · `D05 일부 업로드 실패` **70:2** · `D06 전체 업로드 실패` **70:20** · `D07 등록할 문서 확인` **201:25** · `22-A 문서 추가 · 기존 기록 지정` **218:231** |
| REQ-DOC-002 | `03 개인정보 처리 · AI 이용 동의` **66:76** | (동의 거부는 위 D01) |
| REQ-DOC-003 | `07 OCR 결과 확인 · 수정` **66:115** | `07-R 재업로드 경로` **119:212** · `07-R1 기존 기록 연결됨` **147:52** · `O02 OCR 전체 실패` **70:53** · `O03 OCR 저장 오류` **70:68** · `O04 재업로드 확인` **70:81** · `O05 OCR 저신뢰 검토` **70:95** · `O06 복약정보 없음` **142:133** · `O07 복약 정보 편집 모달` **204:25** · `O08 낮은 신뢰도 항목 확인` **205:25** |
| REQ-HOME-001 | `10 홈 대시보드 · 활성 기록 1건` **67:2** | `10-A 홈 · 활성 기록 2건` **209:24** · `H01 복약 없음` **342:106** · `H02 일정 없음` **342:420** · `H03 최근 문답 없음(신규 가입 직후)` **342:481** · `H04 활성 진료기록 0건(복용 기간 종료)` **342:543** |
| REQ-CARE-001 | `11 복약 안내` **67:42** | `11 복약 안내 · 처방 1건 시나리오` **142:80** |
| REQ-CARE-002 | `13 약물 변경 비교` **67:77** | `13 빈 상태 · 등록 유도` **71:47** · `M02 변경사항 확인 완료` **71:60** |
| REQ-CARE-003 | `09 복약 시간 설정` **125:50** | `09-A 시간 선택` **114:11** · `09-B 기존 저장 시각 프리필` **116:241** · `09-R 재업로드 경로` **119:246** |
| REQ-CARE-004 | `15 생활관리 가이드` **67:118** | — (완료 상태 화면은 체크리스트 제거와 함께 삭제됨) |
| REQ-CARE-005 | `16 진료 · 검사 일정` **67:159** | `S01 등록된 일정 없음` **72:2** · `S02 일정 알림 꺼짐` **72:12** |
| REQ-CARE-006 | (화면 없음, 푸시 발송) | `N01 알림 권한 요청` **73:21** · `N02 알림 권한 거부됨` **73:36** |
| REQ-CHAT-001 | `17 RAG 챗봇` **67:194** | `C01 스트리밍` **72:25** · `C02 응답 오류` **72:41** · `C03 근거 출처 상세` **72:54** · `C04 질문·답변 이력` **72:70** |
| REQ-HIST-001 | `23 이전 진료 히스토리 매칭` **68:96** | `23-A 기존 선택` **218:26** · `23-B 신규 선택` **218:42** · `R02 매칭 후보 없음` **73:72** |
| REQ-HIST-002 | `20 입원기록 히스토리` **68:46** | `20-A 진행 중 2건` **216:41** · `R01 입원기록 없음` **73:62** |
| REQ-HIST-003 | `21 입원기록 상세` **68:57** | — |
| 공통 | — | `X01 오프라인` **74:54** · `X02 서버 오류` **74:67** |

컴포넌트 정의는 별도 페이지에 있습니다 — `Button` **27:8** · `Input`(page `26:3`) · `Card` **27:51** · `Status Badge` **27:30** · `Checkbox` **27:47** · `ActiveRecordCard/Unified` **268:31**(Screens 페이지 내)

## 6. 남은 정리 작업 (우선순위 순)

1. **화면의 직접 그린 프레임을 컴포넌트 인스턴스로 전환** — 가장 효과가 큰 작업입니다. 현재 화면 안 프레임 706개 중 컴포넌트 인스턴스는 37개뿐이고, 특히 `Card`는 컴포넌트가 있는데도 화면에서 한 번도 인스턴스로 쓰이지 않습니다. 이 때문에 07 화면의 재업로드 변형 3개가 구버전으로 방치되는 일이 실제로 발생했습니다(하나 고쳐도 나머지에 반영되지 않아서). 다만 카드마다 내용·높이·톤이 달라 일괄 자동 변환은 위험하므로, **화면 하나씩 전환하고 눈으로 확인하는 방식**을 권합니다.
2. **Card에 톤 variant 추가** (Default / Info / Warning) — 위 전환 작업의 선행 조건입니다.
3. **Status Badge에 active / done 타입 추가**.
4. **Button에 Secondary + Disabled 조합 추가**.
5. **07 변형 3개의 나머지 정합성** — 구조는 메인과 맞췄고 복약 카드 모달 연결도 완료했으나, "추출 실패 항목" 카드가 메인의 "확인 필요 항목"과 표현이 다릅니다. 두 개념(신뢰도 낮음 / 추출 실패)을 하나의 카드로 합칠지 정해야 합니다.
6. **입원기록 상세 상단 표기** — 종료된 과거 기록에서 "활성 08.10–08.24"는 어색합니다. 상태에 따라 "복약 종료" 등으로 갈라주는 편이 좋습니다.

---

## 7. 이미 완료된 정리

- 앱 UI 색상 토큰 바인딩 **100%** (채움 743, 텍스트 948, 선 307 — 하드코딩 0건). 순수 검정(`#000000`) 텍스트 61곳과 토큰 근사값 오차(`#0F1729`, `#1F6FEB`, `#ECFDF3` 등) 전부 정식 토큰으로 통일했습니다. 캔버스 주석·DEV NOTE 텍스트는 앱 UI가 아니므로 제외했습니다.
- 터치 영역 44px 미달 **0건** (NFR-ACC-001 충족).
- 미사용 고아 프레임 삭제 — `N03 알림 목록`, `P01 업로드 문서 목록`.
- `S02` 화면 제목을 `알림 설정` → `진료 · 검사 일정`으로 수정(P03과 제목 중복 해소).
- 07 변형 3개에서 삭제 대상 "복약 편집" 카드 제거, 권고사항 리스트 컴포넌트로 통일, 복약 카드 → 편집 모달 연결.
- 입원기록 상세 카드 5개 → 3개로 축소, 복약 이력 전체 노출.
