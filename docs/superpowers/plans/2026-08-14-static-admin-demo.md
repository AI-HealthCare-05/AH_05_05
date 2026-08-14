# Static Admin Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인, 대시보드, 회원·관리자·업무 관리 화면과 9개 오버레이를 하나의 상호작용 가능한 정적 관리자 데모로 연결한다.

**Architecture:** 공통 탐색과 오버레이 로딩은 재사용 ES 모듈로 제공하고 각 관리 화면은 자신의 데이터 필터·상태 변경만 담당한다. 기존 Tailwind 기반 시각 구성은 유지하면서 공통 상태·반응형·접근성 스타일을 별도 CSS로 추가하고, 실제 API 대신 현재 페이지 메모리의 표 데이터를 갱신한다.

**Tech Stack:** HTML5, Tailwind CDN, CSS3, JavaScript ES modules, SVG, Node.js `node:test`, FastAPI StaticFiles, in-app browser testing

## Global Constraints

- `app/static/templates`의 모든 HTML을 수정 대상에 포함한다.
- 실제 백엔드 API를 호출하거나 비밀번호를 저장하지 않는다.
- `index.html`은 `templates/login.html`로 이동하는 단일 진입점이다.
- 기존 시각 디자인과 Tailwind CDN을 유지한다.
- 클릭 가능한 요소는 실제 HTML 대화형 요소로 변경한다.
- 이 작업에서는 Git 커밋을 생성하지 않는다.

---

### Task 1: 공통 자원과 탐색·오버레이 기반

**Files:**
- Create: `app/static/css/management.css`
- Create: `app/static/css/overlays.css`
- Create: `app/static/js/navigation.js`
- Create: `app/static/js/overlay.js`
- Create: `app/static/images/logo-mark.svg`
- Create: `app/tests/static_ui/common-ui.test.mjs`

**Interfaces:**
- Produces: `getNavigationTarget(section) -> string`
- Produces: `openOverlay(path, options) -> Promise<HTMLElement>`
- Produces: `closeOverlay() -> void`
- Produces: `showToast(message, type) -> HTMLElement`
- Produces: `downloadCsv(filename, rows) -> boolean`

- [ ] **Step 1: `getNavigationTarget`과 CSV 직렬화의 예상 결과를 리터럴로 검증하는 Node 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/common-ui.test.mjs` 실행 후 모듈 부재 실패 확인**
- [ ] **Step 3: 화면 경로 매핑, 오버레이 fetch·DOMParser·포커스·Escape 처리, 토스트, CSV 다운로드 구현**
- [ ] **Step 4: 관리 화면 및 오버레이 공통 CSS와 재사용 SVG 로고 작성**
- [ ] **Step 5: 공통 UI Node 테스트 통과 확인**

### Task 2: 로그인·대시보드와 진입점

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/templates/login.html`
- Modify: `app/static/templates/dashboard.html`
- Modify: `app/static/js/login.js`
- Modify: `app/static/js/dashboard.js`
- Modify: `app/static/css/styles.css`
- Modify: `app/tests/static_ui/login.test.mjs`
- Modify: `app/tests/static_ui/dashboard.test.mjs`

**Interfaces:**
- Consumes: `getNavigationTarget(section)` from Task 1
- Produces: `validateCredentials(loginId, password) -> { valid, errors }`
- Produces: `selectPeriod(periods, selected) -> string[]`
- Produces: 로그인 → 대시보드 → 관리 화면 → 로그아웃 흐름

- [ ] **Step 1: index 진입 경로와 로그인·대시보드 HTML 연결을 검증하는 테스트 추가**
- [ ] **Step 2: 변경된 기대 조건이 기존 HTML에서 실패하는지 확인**
- [ ] **Step 3: index를 로그인 이동 진입점으로 변경하고 로그인 폼을 실제 입력 요소로 정리**
- [ ] **Step 4: 대시보드 버튼·사이드바·새로고침·로그아웃을 공통 탐색 모듈과 연결**
- [ ] **Step 5: 로그인·대시보드 Node 테스트 통과 확인**

### Task 3: 회원 관리와 회원 오버레이

**Files:**
- Modify: `app/static/templates/user-management.html`
- Modify: `app/static/templates/overlay-user-detail.html`
- Modify: `app/static/templates/overlay-user-suspend-confirm.html`
- Create: `app/static/js/user-management.js`
- Create: `app/tests/static_ui/user-management.test.mjs`

**Interfaces:**
- Consumes: `openOverlay`, `closeOverlay`, `showToast`, `downloadCsv`
- Produces: `filterUsers(users, query, status) -> User[]`
- Produces: `suspendUser(users, memberId) -> User[]`

- [ ] **Step 1: 이름·이메일 검색, 상태 필터, 정지 상태 변경 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/user-management.test.mjs` 실행 후 모듈 부재 실패 확인**
- [ ] **Step 3: 회원 화면 입력·선택·버튼·빈 결과 영역과 데이터 속성 정리**
- [ ] **Step 4: 필터·행 선택·상세 오버레이·정지 확인·CSV 이벤트 구현**
- [ ] **Step 5: 회원 오버레이를 접근 가능한 dialog와 실제 버튼으로 정리**
- [ ] **Step 6: 회원 관리 Node 테스트 통과 확인**

### Task 4: 관리자 관리와 관리자 오버레이

**Files:**
- Modify: `app/static/templates/screen-4-admin-management.html`
- Modify: `app/static/templates/overlay-admin-register.html`
- Modify: `app/static/templates/overlay-admin-edit.html`
- Modify: `app/static/templates/overlay-admin-status-confirm.html`
- Modify: `app/static/templates/overlay-password-reset.html`
- Create: `app/static/js/admin-management.js`
- Create: `app/tests/static_ui/admin-management.test.mjs`

**Interfaces:**
- Consumes: `openOverlay`, `closeOverlay`, `showToast`, `downloadCsv`
- Produces: `filterAdmins(admins, query, role, status) -> Admin[]`
- Produces: `validateAdminInput({ name, email }) -> { valid, errors }`
- Produces: `updateAdminStatus(admins, adminId, status) -> Admin[]`

- [ ] **Step 1: 관리자 필터, 이메일 검증, 상태 변경 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/admin-management.test.mjs` 실행 후 모듈 부재 실패 확인**
- [ ] **Step 3: 관리자 화면의 검색·필터·등록·행 작업 버튼을 실제 요소로 변경**
- [ ] **Step 4: 등록·수정·정지·비밀번호 재설정 오버레이를 실제 폼과 dialog로 정리**
- [ ] **Step 5: 등록·수정·정지·재설정·CSV 이벤트와 표 갱신 구현**
- [ ] **Step 6: 관리자 관리 Node 테스트 통과 확인**

### Task 5: 업무 관리와 작업 오버레이

**Files:**
- Modify: `app/static/templates/screen-5-task-management.html`
- Modify: `app/static/templates/overlay-task-detail-processing.html`
- Modify: `app/static/templates/overlay-task-detail-success.html`
- Modify: `app/static/templates/overlay-task-retry.html`
- Create: `app/static/js/task-management.js`
- Create: `app/tests/static_ui/task-management.test.mjs`

**Interfaces:**
- Consumes: `openOverlay`, `closeOverlay`, `showToast`
- Produces: `filterTasks(tasks, query, type, status) -> Task[]`
- Produces: `retryTask(tasks, taskId) -> Task[]`
- Produces: 상태별 overlay 파일 선택

- [ ] **Step 1: 작업 ID·유형·상태 필터와 실패 작업 재시도 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/task-management.test.mjs` 실행 후 모듈 부재 실패 확인**
- [ ] **Step 3: 업무 화면 검색·필터·행 상세 버튼과 빈 결과 영역 정리**
- [ ] **Step 4: 성공·진행·실패 오버레이를 접근 가능한 dialog와 실제 버튼으로 정리**
- [ ] **Step 5: 상태별 상세 선택, 재시도 상태 변경, 알림 구현**
- [ ] **Step 6: 업무 관리 Node 테스트 통과 확인**

### Task 6: 전체 통합·접근성·회귀 검증

**Files:**
- Verify: `app/static/index.html`
- Verify: `app/static/templates/*.html`
- Verify: `app/static/css/*.css`
- Verify: `app/static/js/*.js`
- Verify: `app/static/images/logo-mark.svg`
- Verify: `app/tests/static_ui/*.test.mjs`
- Verify: `tests/test_static_mount.py`

**Interfaces:**
- Consumes: Task 1~5의 모든 화면·자원·이벤트
- Produces: 브라우저에서 검증된 전체 정적 관리자 데모

- [ ] **Step 1: 모든 Node 테스트와 FastAPI 정적 마운트 테스트 실행**
- [ ] **Step 2: 로컬 서버에서 로그인·대시보드·세 관리 화면 탐색 확인**
- [ ] **Step 3: 회원 상세·정지, 관리자 등록·수정·정지·재설정, 작업 상세·재시도 확인**
- [ ] **Step 4: 빈 입력 오류, 빈 필터 결과, Escape·배경 클릭 닫기를 확인**
- [ ] **Step 5: 일반·좁은 뷰포트 렌더링과 브라우저 콘솔 오류 확인**
- [ ] **Step 6: `git diff --check`와 최종 변경 범위 확인**
