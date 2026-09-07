# Challenge Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공식 챌린지·배지 관리와 사용자 참여·진행률·인증·배지 지급 이력을 구현하고 dbdiagram.io 및 Docker MySQL 스키마에 반영한다.

**Architecture:** `app.models.challenges`가 여섯 테이블의 영속 모델을 제공하고, 관리자용 관리 서비스와 사용자 참여 서비스가 저장소를 통해 접근한다. 참여 생성, 인증 승인, 진행률 집계, 완료 및 배지 지급은 트랜잭션 경계 안에서 처리하며 API는 관리자와 사용자 라우터로 분리한다.

**Tech Stack:** Python 3.13, FastAPI, Tortoise ORM, Aerich, MySQL 8, Pydantic v2, Jinja-style static HTML, vanilla JavaScript, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-07-challenge-participation-design.md`

## Global Constraints

- 프로젝트 루트는 `/Users/admin/PycharmProjects/FinalProject`이다.
- 동일 사용자는 동일 공식 챌린지에 한 번만 참여한다.
- `challenges.check_type`은 `CHL/CHK_TYPE`의 `SELF` 또는 `MANUAL`을 사용하며 별도 승인방식 컬럼을 만들지 않는다.
- `D30 + WEEKLY_3`은 완전한 7일 구간 네 개만 만들고 마지막 2일은 목표 집계에서 제외한다.
- 날짜 계산은 `Config.TIMEZONE`을 사용하고 종료 시각은 배타적이다.
- 참여자용 화면 UI는 만들지 않되 사용자 API는 구현한다.
- 기존 요청에 따라 Git 커밋을 생성하지 않는다.

---

### Task 1: dbdiagram.io 클라우드 ERD 반영

**Files:**
- Reference: `docs/superpowers/specs/2026-09-07-challenge-participation-design.md`

**Interfaces:**
- Consumes: 승인된 DBML 정의와 기존 클라우드 ERD
- Produces: `badges`, `challenges`, `user_challenges`, `challenge_progress`, `challenge_verifications`, `user_badges` 및 Ref가 저장된 클라우드 ERD

- [ ] **Step 1: 현재 dbdiagram DBML을 읽고 기존 테이블명 충돌을 확인한다**

  URL: `https://dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`

- [ ] **Step 2: 승인된 enum과 여섯 테이블을 DBML 편집기에 추가한다**

  정확한 정의는 스펙 3장과 4장을 사용하고 `approval_type_id`를 추가하지 않는다.

- [ ] **Step 3: FK Ref를 추가하고 저장한다**

  `user`, `admin`, `common_codes`, 신규 테이블 간 Ref가 중복 없이 한 번씩 존재해야 한다.

- [ ] **Step 4: 저장 후 페이지를 다시 읽어 테이블 6개와 핵심 유일 인덱스를 검증한다**

  확인 대상: `uq_user_challenges_user_challenge`, `uq_challenge_progress_period`, `uq_user_badges_participation_badge`.

### Task 2: 모델과 마이그레이션

**Files:**
- Create: `app/models/challenges.py`
- Modify: `app/models/enums.py`
- Modify: `app/models/__init__.py`
- Modify: `app/core/db/databases.py`
- Create: `app/core/db/migrations/models/32_20260907185920_add_challenge_domain.py`
- Test: `app/tests/models/test_challenge_models.py`
- Test: `app/tests/models/test_challenge_migration.py`

**Interfaces:**
- Consumes: `User`, `Admin`, `CommonCode` 모델
- Produces: `Badge`, `Challenge`, `UserChallenge`, `ChallengeProgress`, `ChallengeVerification`, `UserBadge`와 세 상태 enum

- [ ] **Step 1: 실패하는 모델 메타데이터 테스트를 작성한다**

```python
def test_challenge_models_expose_tables_and_unique_constraints() -> None:
    assert Badge._meta.db_table == "badges"
    assert Challenge._meta.db_table == "challenges"
    assert UserChallenge._meta.unique_together == (("user", "challenge"),)
    assert ChallengeProgress._meta.unique_together == (("user_challenge", "period_start", "period_end"),)
    assert UserBadge._meta.unique_together == (("user_challenge", "badge"),)
```

- [ ] **Step 2: 테스트가 모델 import 실패로 RED인지 확인한다**

  Run: `uv run pytest app/tests/models/test_challenge_models.py -q`

- [ ] **Step 3: enum과 여섯 Tortoise 모델을 구현한다**

  `ChallengeParticipationStatus`, `ChallengeVerificationStatus`, `BadgeAwardStatus`를 `str, Enum`으로 만들고 모든 필드, 설명, 인덱스, FK 삭제 정책을 스펙과 동일하게 선언한다.

- [ ] **Step 4: 모델을 Tortoise 앱과 공개 import에 등록한다**

  `TORTOISE_APP_MODELS`에 `app.models.challenges`를 추가하고 `app/models/__init__.py`에서 여섯 모델을 내보낸다.

- [ ] **Step 5: 모델 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/models/test_challenge_models.py -q`

- [ ] **Step 6: Aerich 마이그레이션을 생성하고 SQL 계약 테스트를 작성한다**

  Run: `uv run aerich migrate --name add_challenge_domain`

  테스트는 여섯 `CREATE TABLE`, FK, 세 유일 인덱스, CHECK, 컬럼 COMMENT가 마이그레이션에 포함되는지 확인한다.

- [ ] **Step 7: 마이그레이션 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/models/test_challenge_migration.py -q`

### Task 3: 관리자 배지·공식 챌린지 CRUD

**Files:**
- Create: `app/dtos/challenges.py`
- Create: `app/repositories/badge_repository.py`
- Create: `app/repositories/challenge_repository.py`
- Create: `app/services/badges.py`
- Create: `app/services/challenges.py`
- Create: `app/apis/v1/admin_challenge_router.py`
- Modify: `app/apis/v1/__init__.py`
- Modify: `app/core/exceptions.py`
- Test: `app/tests/challenge_apis/test_admin_badge_api.py`
- Test: `app/tests/challenge_apis/test_admin_challenge_api.py`

**Interfaces:**
- Consumes: Task 2의 `Badge`, `Challenge`, `CommonCode`, `Admin`
- Produces: `/api/v1/admin/badges`, `/api/v1/admin/challenges` CRUD와 snake_case DTO

- [ ] **Step 1: 배지와 챌린지 CRUD API 실패 테스트를 작성한다**

  배지는 생성·목록·상세·수정·비활성화, 챌린지는 생성·목록·상세·수정·소프트 삭제를 검증한다. ADMIN은 쓰기 가능, STAFF는 조회만 가능하도록 기존 관리자 권한 정책을 따른다.

- [ ] **Step 2: API 테스트가 404 또는 import 실패로 RED인지 확인한다**

  Run: `uv run pytest app/tests/challenge_apis/test_admin_badge_api.py app/tests/challenge_apis/test_admin_challenge_api.py -q`

- [ ] **Step 3: snake_case 요청·응답 DTO와 저장소를 구현한다**

  목록 응답은 `items`, `total_count`, `offset`, `limit`을 제공한다. 챌린지 생성·수정 시 네 공통코드가 각각 `CHL_TYPE`, `CHL_PERIOD`, `CHK_TYPE`, `CHK_FREQ` 그룹에 속하고 활성 상태인지 검증한다.

- [ ] **Step 4: 배지 이미지 저장 검증을 구현한다**

  PNG/JPG/WebP만 허용하고 최대 2MB를 검사한 뒤 안전한 UUID 파일명으로 `app/static/media/badges/`에 저장한다. DTO에는 `/media/badges/<filename>` 상대 URL을 반환한다.

- [ ] **Step 5: 서비스, 예외, 관리자 라우터를 구현한다**

  배지명이 중복이면 `409 BADGE_NAME_ALREADY_EXISTS`, 사용 중인 배지를 비활성화할 때는 기존 챌린지 이력을 유지한다. 챌린지 모집 종료는 시작보다 늦어야 하며 삭제는 `is_deleted=true`, `deleted_at=now`로 처리한다.

- [ ] **Step 6: 관리자 CRUD 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/challenge_apis/test_admin_badge_api.py app/tests/challenge_apis/test_admin_challenge_api.py -q`

### Task 4: 관리자 챌린지·배지 화면

**Files:**
- Modify: `app/static/templates/partials/sidebar.html`
- Create: `app/static/templates/challenge-management.html`
- Create: `app/static/templates/badge-management.html`
- Create: `app/static/templates/overlay-challenge-form.html`
- Create: `app/static/templates/overlay-badge-form.html`
- Create: `app/static/js/challenge-management.js`
- Create: `app/static/js/badge-management.js`
- Test: `app/tests/static_ui/challenge-management.test.mjs`
- Test: `app/tests/static_ui/test_challenge_management_pages.py`

**Interfaces:**
- Consumes: Task 3의 관리자 CRUD API와 기존 공통코드 조회 API
- Produces: `챌린지관리 > 공식챌린지`, `챌린지관리 > 배지관리` 화면

- [ ] **Step 1: 사이드바 링크·폼·API 연결을 검사하는 실패 테스트를 작성한다**

  테스트는 `data-nav="challenges"`, `data-nav="badges"`, 공통코드 그룹 네 개, 배지 이미지 두 개, 페이지별 20/50/100, 조회·초기화·등록·수정·삭제/비활성화 버튼을 확인한다.

- [ ] **Step 2: 정적 UI 테스트가 RED인지 확인한다**

  Run: `node --test app/tests/static_ui/challenge-management.test.mjs`

- [ ] **Step 3: 사이드바 그룹과 두 관리 화면을 구현한다**

  기존 `management.css`, `sidebar.js`, `overlay.js`, `api.js`를 재사용하고 선택 메뉴 표시와 SMTP 설정 팝업이 모든 화면에서 유지되도록 기존 페이지 구조를 따른다.

- [ ] **Step 4: 목록 조회·페이지 이동·검색·폼 저장 JavaScript를 구현한다**

  챌린지 폼은 공통코드와 활성 배지 목록을 불러오고 날짜 관계를 브라우저와 서버 양쪽에서 검증한다. 배지 폼은 활성/비활성 이미지를 미리보기한다.

- [ ] **Step 5: 정적 UI 테스트를 GREEN으로 만든다**

  Run: `node --test app/tests/static_ui/challenge-management.test.mjs`
  Run: `uv run pytest app/tests/static_ui/test_challenge_management_pages.py -q`

### Task 5: 진행 구간 계산과 사용자 참여 서비스

**Files:**
- Create: `app/dtos/challenge_participation.py`
- Create: `app/repositories/challenge_participation_repository.py`
- Create: `app/services/challenge_periods.py`
- Create: `app/services/challenge_participation.py`
- Test: `app/tests/challenges/test_challenge_periods.py`
- Test: `app/tests/challenges/test_challenge_participation_service.py`

**Interfaces:**
- Consumes: Task 2 모델과 `Config.TIMEZONE`
- Produces: `build_progress_periods(started_at, period_code, frequency_code) -> list[ProgressPeriod]`, `ChallengeParticipationService.join(user_id, challenge_id)`

- [ ] **Step 1: 기간 계산 실패 테스트를 작성한다**

```python
def test_d30_weekly_3_excludes_trailing_two_days() -> None:
    periods = build_progress_periods(started_at, "D30", "WEEKLY_3")
    assert len(periods) == 4
    assert sum(period.target_count for period in periods) == 12
```

  함께 `D7/D14/D30 + DAILY`, `TOTAL_10`, 알 수 없는 공통코드 거부를 검사한다.

- [ ] **Step 2: 기간 테스트가 RED인지 확인한다**

  Run: `uv run pytest app/tests/challenges/test_challenge_periods.py -q`

- [ ] **Step 3: 순수 기간 계산 모듈을 구현한다**

  `D<number>`를 허용 목록 `D7/D14/D30`으로 제한하고 `DAILY`, `WEEKLY_3`, `TOTAL_10`만 처리한다. 모든 날짜는 `Config.TIMEZONE`의 로컬 날짜로 변환한다.

- [ ] **Step 4: 참여 서비스 실패 테스트를 작성한다**

  모집 중이고 전시된 챌린지는 참여와 진행 구간을 한 트랜잭션으로 생성하고, 중복·모집 외·삭제·미전시는 명시한 오류 코드로 거부하는지 확인한다.

- [ ] **Step 5: 저장소와 참여 서비스를 구현한다**

  `user_id + challenge_id` 유일조건의 `IntegrityError`를 `CHALLENGE_ALREADY_JOINED`로 변환하고 참여의 `target_count`는 생성된 진행 구간 목표 합계로 저장한다.

- [ ] **Step 6: 서비스 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/challenges/test_challenge_periods.py app/tests/challenges/test_challenge_participation_service.py -q`

### Task 6: 인증·진행률·배지 지급 서비스

**Files:**
- Modify: `app/repositories/challenge_participation_repository.py`
- Modify: `app/services/challenge_participation.py`
- Test: `app/tests/challenges/test_challenge_verification_service.py`

**Interfaces:**
- Consumes: `ChallengeParticipationService`, `ChallengeVerification`, `UserBadge`
- Produces: `submit_verification`, `review_verification`, `cancel_participation`, `list_user_badges`

- [ ] **Step 1: SELF/MANUAL 인증과 상태 전이 실패 테스트를 작성한다**

  SELF는 즉시 승인, MANUAL은 대기, MANUAL 증빙 누락은 422, 승인·반려 재처리는 409, 종료·완료·취소 상태 제출은 409인지 검사한다.

- [ ] **Step 2: 테스트가 RED인지 확인한다**

  Run: `uv run pytest app/tests/challenges/test_challenge_verification_service.py -q`

- [ ] **Step 3: 인증 제출과 멱등 처리를 구현한다**

  서버가 `verification_date`로 `ChallengeProgress`를 선택한다. 동일 `idempotency_key`면 기존 레코드를 반환하며 MANUAL은 `content` 또는 `image_path` 중 하나를 요구한다.

- [ ] **Step 4: 트랜잭션 기반 승인·집계·완료·배지 지급을 구현한다**

  인증, 진행 구간, 참여 행을 `select_for_update()`로 잠근다. 승인 횟수는 목표를 초과해도 저장할 수 있으나 진행률은 100으로 제한한다. 모든 구간 완료 시 참여를 완료하고 활성 배지를 스냅샷과 함께 `get_or_create`로 지급한다.

- [ ] **Step 5: 인증 서비스 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/challenges/test_challenge_verification_service.py -q`

### Task 7: 사용자 참여 API와 관리자 인증 검토 API

**Files:**
- Create: `app/apis/v1/challenge_router.py`
- Modify: `app/apis/v1/admin_challenge_router.py`
- Modify: `app/apis/v1/__init__.py`
- Test: `app/tests/challenge_apis/test_user_challenge_api.py`
- Test: `app/tests/challenge_apis/test_admin_challenge_verification_api.py`

**Interfaces:**
- Consumes: Task 5~6 서비스
- Produces: 사용자 참여 API, 관리자 승인·반려 액션 API

- [ ] **Step 1: 사용자 API 실패 테스트를 작성한다**

  `/api/v1/user/challenges/{challenge_id}/join`, `/api/v1/user/challenges`, `/api/v1/user/challenges/{participation_id}`, 인증 제출, 취소, `/api/v1/user/badges`를 검사하고 다른 사용자 자원은 404인지 확인한다.

- [ ] **Step 2: 관리자 인증 API 실패 테스트를 작성한다**

  대기 목록 필터와 `POST /api/v1/admin/challenge-verifications/{verification_id}/actions`의 `APPROVE`, `REJECT`를 검사한다. 반려 시 `rejection_reason`은 필수다.

- [ ] **Step 3: 사용자 및 관리자 라우터를 구현한다**

  모든 필드명은 snake_case로 반환하고 각 operation에 한국어 summary와 description을 작성한다. 인증 이미지는 Task 3과 같은 MIME·크기 검사를 사용하되 `app/static/media/challenges/`에 저장한다.

- [ ] **Step 4: API 테스트를 GREEN으로 만든다**

  Run: `uv run pytest app/tests/challenge_apis/test_user_challenge_api.py app/tests/challenge_apis/test_admin_challenge_verification_api.py -q`

### Task 8: Docker MySQL 업그레이드와 최종 검증

**Files:**
- Modify only if generated-state correction is required: `app/core/db/migrations/models/32_20260907185920_add_challenge_domain.py`

**Interfaces:**
- Consumes: Tasks 1~7 전체 결과
- Produces: 실행 중인 Docker MySQL 스키마와 검증 기록

- [ ] **Step 1: 포맷과 정적 검사를 실행한다**

  Run: `uv run ruff format app app/tests --check`
  Run: `uv run ruff check app app/tests`

- [ ] **Step 2: 챌린지 관련 테스트 전체를 실행한다**

  Run: `uv run pytest app/tests/models/test_challenge_models.py app/tests/models/test_challenge_migration.py app/tests/challenges app/tests/challenge_apis -q`

- [ ] **Step 3: 정적 UI 테스트를 실행한다**

  Run: `node --test app/tests/static_ui/challenge-management.test.mjs`
  Run: `uv run pytest app/tests/static_ui/test_challenge_management_pages.py -q`

- [ ] **Step 4: Docker 서비스와 DB 연결 상태를 확인한다**

  Run: `docker compose ps`

- [ ] **Step 5: 마이그레이션을 기존 MySQL에 적용한다**

  Run: `uv run aerich upgrade`

- [ ] **Step 6: MySQL 실제 구조와 공통코드를 검증한다**

  Run: `docker compose exec -T mysql sh -lc 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --default-character-set=utf8mb4 "$MYSQL_DATABASE" -e "SHOW CREATE TABLE challenges; SHOW CREATE TABLE user_challenges; SHOW CREATE TABLE challenge_verifications; SELECT g.group_code,c.detail_code FROM common_code_groups g JOIN common_codes c ON c.group_id=g.id WHERE g.category='\''CHL'\'' ORDER BY g.group_code,c.sort_order;"'`

  컨테이너 환경변수를 사용해 비밀번호를 출력에 노출하지 않는다. `CHL_PERIOD`, `CHK_FREQ`, `CHK_TYPE`, `CHL_TYPE`과 승인된 상세코드가 존재해야 한다.

- [ ] **Step 7: FastAPI OpenAPI에 신규 경로가 등록됐는지 확인한다**

  Run: `uv run python -c "from app.main import app; paths=app.openapi()['paths']; print('\n'.join(sorted(p for p in paths if 'challenge' in p or p.endswith('/badges'))))"`

- [ ] **Step 8: Git diff를 검토하고 사용자 변경을 보존했는지 확인한다**

  Run: `git diff --check`
  Run: `git status --short`
