# Admin SMTP Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ADMIN이 sidebar 팝업에서 안전하게 SMTP 설정을 관리하고 email-worker가 최신 DB 설정을 사용하게 한다.

**Architecture:** `admin_settings` 단일 설정 행을 repository/service로 관리하고 비밀번호는 별도 Fernet codec으로 암호화한다. API와 UI는 비밀번호 존재 여부만 읽으며 worker는 매 발송 직전에 DB 우선·Config fallback runtime 설정을 조회한다.

**Tech Stack:** FastAPI, Tortoise ORM, Aerich, Pydantic, cryptography/Fernet, ARQ, vanilla JavaScript

**Spec:** `docs/superpowers/specs/2026-08-29-admin-smtp-settings-design.md`

## Global Constraints

- 프로젝트 루트는 `/Users/admin/PycharmProjects/FinalProject`이다.
- Git 커밋을 생성하지 않는다.
- SMTP 비밀번호 원문·암호문을 API 응답이나 로그에 노출하지 않는다.
- GET/PUT API와 설정 아이콘은 ADMIN 전용이다.
- dbdiagram의 신규 테이블 모든 컬럼에 한국어 note를 작성한다.

---

### Task 1: 모델, 암호화, 마이그레이션

**Files:**
- Create: `app/models/admin_settings.py`
- Create: `app/core/smtp_settings_encryption.py`
- Modify: `app/models/__init__.py`
- Modify: `app/core/config.py`
- Test: `tests/models/test_admin_settings.py`
- Test: `app/tests/email/test_smtp_settings_encryption.py`

**Interfaces:**
- Produces: `AdminSetting`, `encrypt_smtp_password(str) -> str`, `decrypt_smtp_password(str) -> str`

- [ ] 모델 메타데이터와 암호화 왕복/키 오류 테스트를 작성하고 실패를 확인한다.
- [ ] 모델·codec·Config 키를 최소 구현해 테스트를 통과시킨다.
- [ ] `uv run aerich migrate --name add_admin_settings`로 마이그레이션을 생성하고 SQL을 검토한다.

### Task 2: 설정 service와 ADMIN API

**Files:**
- Create: `app/repositories/admin_settings_repository.py`
- Create: `app/services/admin_settings.py`
- Create: `app/dtos/admin_settings.py`
- Create: `app/apis/v1/admin_settings_router.py`
- Modify: `app/apis/v1/__init__.py`
- Test: `app/tests/admin_apis/test_admin_smtp_settings_api.py`

**Interfaces:**
- Produces: `SmtpRuntimeSettings`, `SmtpSettingsService.get_runtime_settings()`, GET/PUT `/api/v1/admin/settings/smtp`

- [ ] ADMIN/STAFF 권한, 비밀번호 비노출, 최초 저장, 비밀번호 유지 수정 테스트를 작성하고 실패를 확인한다.
- [ ] repository/service/DTO/router를 구현해 테스트를 통과시킨다.

### Task 3: email-worker 최신 설정 적용

**Files:**
- Modify: `app/workers/email_worker.py`
- Modify: `app/tests/workers/test_email_worker.py`

**Interfaces:**
- Consumes: `SmtpSettingsService.get_runtime_settings() -> SmtpRuntimeSettings`

- [ ] 작업마다 runtime 설정을 조회하는 테스트를 작성하고 실패를 확인한다.
- [ ] startup의 고정 sender를 제거하고 발송 직전 sender를 생성하도록 수정해 테스트를 통과시킨다.

### Task 4: sidebar 설정 팝업

**Files:**
- Modify: `app/static/templates/partials/sidebar.html`
- Create: `app/static/templates/overlay-smtp-settings.html`
- Create: `app/static/js/smtp-settings.js`
- Modify: `app/static/js/sidebar.js`
- Modify: `app/static/js/api.js`
- Test: `app/tests/static_ui/sidebar.test.mjs`
- Create: `app/tests/static_ui/smtp-settings.test.mjs`

**Interfaces:**
- Consumes: GET/PUT `/admin/settings/smtp`, `session.isAdminRole()`

- [ ] 역할별 아이콘 노출과 팝업 데이터 변환 테스트를 작성하고 실패를 확인한다.
- [ ] 아이콘, overlay, JS API 연결을 구현해 테스트를 통과시킨다.

### Task 5: dbdiagram 및 최종 검증

**Files:**
- Modify externally: `https://dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`

**Interfaces:**
- Consumes: 최종 `AdminSetting` 모델 메타데이터

- [ ] dbdiagram DBML에 `admin_settings`와 FK/note를 추가하고 저장 직전 사용자 확인을 받는다.
- [ ] 집중 pytest, Node UI 테스트, Ruff, OpenAPI, Compose, `git diff --check`를 실행한다.
