# 정적 관리 화면 동작 설계

## 목적

로그인, 대시보드, 관리 화면, 오버레이 시안을 브라우저에서 상호작용 가능한 하나의 정적 관리자 데모로 연결한다. 실제 백엔드 API는 호출하지 않으며 화면 상태는 현재 브라우저 메모리에서만 변경한다.

## 대상 파일

### 진입·기본 화면

- `app/static/index.html`
- `app/static/templates/login.html`
- `app/static/templates/dashboard.html`

### 관리 화면

- `app/static/templates/user-management.html`
- `app/static/templates/screen-4-admin-management.html`
- `app/static/templates/screen-5-task-management.html`

### 오버레이

- `overlay-user-detail.html`
- `overlay-user-suspend-confirm.html`
- `overlay-admin-register.html`
- `overlay-admin-edit.html`
- `overlay-admin-status-confirm.html`
- `overlay-password-reset.html`
- `overlay-task-detail-processing.html`
- `overlay-task-detail-success.html`
- `overlay-task-retry.html`

모든 대상 HTML에 실제 입력·버튼·링크, 공통 정적 자원 경로, 동작 연결용 `data-*` 속성, 접근성 속성을 직접 반영한다.

## 정적 자원 구조

```text
app/static/
├── index.html
├── css/
│   ├── styles.css
│   ├── management.css
│   └── overlays.css
├── js/
│   ├── login.js
│   ├── dashboard.js
│   ├── navigation.js
│   ├── overlay.js
│   ├── user-management.js
│   ├── admin-management.js
│   └── task-management.js
└── images/
    └── logo-mark.svg
```

## 구성요소 책임

- `navigation.js`: 사이드바 화면 이동과 로그아웃을 처리한다.
- `overlay.js`: 별도 오버레이 HTML을 불러와 현재 화면 위에 표시하고 닫기·확인·알림 이벤트를 제공한다.
- `user-management.js`: 회원 검색, 상태 필터, 행 선택, 상세 보기, 정지 상태 변경, CSV 내보내기를 담당한다.
- `admin-management.js`: 관리자 검색, 등록, 수정, 계정 정지, 비밀번호 재설정, CSV 내보내기를 담당한다.
- `task-management.js`: 작업 검색, 유형·상태 필터, 상태별 상세 표시, 실패 작업 재시도를 담당한다.
- `management.css`: 관리 화면의 입력, 버튼, 테이블, 알림 등 공통 상태를 표현한다.
- `overlays.css`: 모달 배경, 패널, 폼, 열림·닫힘 애니메이션과 반응형 레이아웃을 담당한다.
- `logo-mark.svg`: 화면에서 공통으로 사용할 서비스 로고다.

## 사용자 흐름

### 진입과 로그인

- `/`의 `index.html`은 `templates/login.html`로 이동시키는 단일 진입점으로 사용한다.
- 로그인 화면은 관리자 ID와 비밀번호 필수 입력을 검증한다.
- 비밀번호 표시·숨김과 로그인 ID 기억 선택을 제공한다.
- 유효한 입력으로 제출하면 `dashboard.html`로 이동한다.

### 대시보드

- 오늘·7일·30일 기간 선택 상태를 전환한다.
- 새로고침 버튼으로 최종 점검 시각을 현재 시각으로 갱신한다.
- 공통 사이드바를 통해 세 관리 화면으로 이동한다.

### 공통 탐색

- 사이드바에서 대시보드, 회원 관리, 관리자 관리, 업무 관리 화면으로 이동한다.
- 로그아웃을 누르면 `login.html`로 이동한다.

### 회원 관리

- 이름·이메일 검색과 활성·정지 상태 필터를 적용한다.
- 필터 초기화로 기본 목록을 복원한다.
- 행 또는 상세 보기 버튼을 누르면 회원 상세 오버레이를 연다.
- 계정 정지를 선택하면 확인 오버레이를 거쳐 해당 행의 상태를 정지로 변경한다.
- 현재 표시 데이터는 CSV 파일로 내려받을 수 있다.

### 관리자 관리

- 관리자 검색과 역할·상태 필터를 적용한다.
- 등록 오버레이에서 필수 입력을 검증한 뒤 새 행을 추가한다.
- 수정 오버레이에서 역할과 활성 상태를 변경한다.
- 계정 정지는 확인 후 해당 행 상태를 갱신한다.
- 비밀번호 재설정은 발송 완료 알림을 표시한다.

### 업무 관리

- 작업 ID·유형 검색과 상태 필터를 적용한다.
- 행의 상태에 따라 성공, 진행 중, 실패 상세 오버레이를 연다.
- 실패 작업의 재시도를 확인하면 상태를 진행 중으로 변경한다.

### 오버레이 공통 동작

- 취소, 닫기, 닫기 아이콘, 배경 클릭, `Escape` 키로 닫는다.
- 처리 완료 시 오버레이를 닫고 현재 화면에 짧은 성공 알림을 표시한다.
- 오버레이가 열려 있는 동안 배경 페이지 스크롤을 막고 키보드 포커스를 오버레이 내부로 이동한다.

## 오류 처리

- 필수 입력이 비어 있거나 이메일 형식이 잘못되면 해당 입력 아래에 오류를 표시하고 처리하지 않는다.
- 오버레이 HTML 로드에 실패하면 화면 내 오류 알림을 표시한다.
- 필터 결과가 없으면 빈 결과 메시지를 표시한다.
- CSV 생성 대상이 없으면 다운로드 대신 안내 알림을 표시한다.

## 접근성과 반응형 처리

- 클릭 가능한 요소는 실제 `button`, `a`, `input`, `select` 요소를 사용한다.
- 오버레이에는 `role="dialog"`, `aria-modal="true"`, 접근 가능한 제목을 제공한다.
- 선택·상태 변화는 색상뿐 아니라 텍스트와 ARIA 속성으로 전달한다.
- 좁은 화면에서는 사이드바와 테이블이 화면을 깨뜨리지 않도록 가로 스크롤 또는 축약 레이아웃을 적용한다.

## 검증

- 순수 필터·상태 변경·입력 검증 함수는 Node 내장 테스트로 먼저 실패를 확인한 뒤 구현한다.
- 모든 대상 HTML이 공통 CSS와 해당 JavaScript를 올바른 상대 경로로 불러오는지 검사한다.
- 로컬 브라우저에서 관리 화면 이동, 검색, 필터, 오버레이, 상태 변경, CSV 다운로드 흐름을 확인한다.
- 브라우저 콘솔에 정적 자원 로드 오류나 JavaScript 오류가 없는지 확인한다. Tailwind CDN의 개발용 경고는 기존 설계상 허용한다.
- 기존 정적 화면 테스트와 FastAPI 정적 마운트 테스트를 함께 실행한다.
