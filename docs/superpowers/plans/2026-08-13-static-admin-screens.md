# Static Admin Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 로그인·대시보드 시안을 정리해 `app/static/index.html`에서 시작하고 실제 브라우저 상호작용이 가능한 정적 관리자 화면을 만든다.

**Architecture:** Tailwind CDN은 기존 시안 호환을 위해 유지하고 프로젝트 공통 스타일은 `styles.css`로 이동한다. 로그인과 대시보드 동작은 각각 독립 ES 모듈로 구현하며, 순수 함수는 Node 내장 테스트로 검증하고 DOM 연결은 로컬 브라우저로 확인한다.

**Tech Stack:** HTML5, Tailwind CDN, CSS3, JavaScript ES modules, Node.js `node:test`, Python static HTTP server

## Global Constraints

- 템플릿 위치는 `app/static/templates`를 유지한다.
- 실제 인증 API를 호출하거나 비밀번호를 저장하지 않는다.
- 기존 로그인·대시보드 콘텐츠와 시각 구성을 유지한다.
- 이 작업에서는 Git 커밋을 생성하지 않는다.

---

### Task 1: 로그인 화면과 동작

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/css/styles.css`
- Create: `app/static/js/login.js`
- Create: `app/tests/static_ui/login.test.mjs`
- Modify: `app/static/templates/screen-login.html`

**Interfaces:**
- Produces: `validateCredentials(loginId, password) -> { valid, errors }`
- Produces: `setRememberedLoginId(storage, loginId, remember) -> void`
- Produces: 로그인 폼 제출 시 `templates/screen-dashboard.html` 이동

- [ ] **Step 1: 로그인 입력 검증과 저장 동작 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/login.test.mjs`를 실행해 모듈 부재로 실패 확인**
- [ ] **Step 3: `login.js`의 순수 함수와 DOM 이벤트 최소 구현**
- [ ] **Step 4: `index.html`을 입력 가능한 로그인 문서로 생성하고 시안 파일도 같은 자원을 사용하도록 정리**
- [ ] **Step 5: 테스트 통과 확인**

### Task 2: 대시보드 동작

**Files:**
- Create: `app/static/js/dashboard.js`
- Create: `app/tests/static_ui/dashboard.test.mjs`
- Modify: `app/static/templates/screen-dashboard.html`
- Modify: `app/static/css/styles.css`

**Interfaces:**
- Produces: `selectPeriod(periods, selected) -> string[]`
- Produces: `formatRefreshTime(date) -> string`
- Produces: 기간 선택, 새로고침 시각 갱신, 로그아웃 후 `../index.html` 이동

- [ ] **Step 1: 기간 선택과 갱신 시각 형식 테스트 작성**
- [ ] **Step 2: `node --test app/tests/static_ui/dashboard.test.mjs`를 실행해 모듈 부재로 실패 확인**
- [ ] **Step 3: `dashboard.js` 순수 함수와 DOM 이벤트 최소 구현**
- [ ] **Step 4: 대시보드 시안에 접근 가능한 버튼·상태·스크립트 연결 추가**
- [ ] **Step 5: 전체 Node 테스트 통과 확인**

### Task 3: 통합 및 회귀 검증

**Files:**
- Verify: `app/static/index.html`
- Verify: `app/static/templates/screen-dashboard.html`
- Verify: `app/tests/`

**Interfaces:**
- Consumes: Task 1과 Task 2의 정적 파일 및 브라우저 이벤트
- Produces: 브라우저에서 검증된 로그인 → 대시보드 → 로그아웃 흐름

- [ ] **Step 1: `python -m http.server`로 `app/static` 제공**
- [ ] **Step 2: 브라우저에서 빈 입력 오류, 비밀번호 표시, 상태 유지, 로그인 이동 확인**
- [ ] **Step 3: 기간 선택, 새로고침, 로그아웃 이동 확인**
- [ ] **Step 4: `uv run pytest app/tests`로 백엔드 회귀 테스트 실행**
- [ ] **Step 5: 변경 파일과 테스트 결과 최종 확인**
