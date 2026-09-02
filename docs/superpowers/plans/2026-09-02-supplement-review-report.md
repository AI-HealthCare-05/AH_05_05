# #216 Supplement Review and Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 제품 상세에 개인정보 경계를 지킨 공개 후기 목록을 추가하고 신고 세 건 누적 시 자동 숨김 처리한다.

**Architecture:** 기존 `UserSupplementNutrient` 등록 행을 후기의 원본으로 유지하고 `SupplementReviewReport`만 별도 모델로 둔다. 리포지토리는 표시 대상과 평점 모집단의 공통 제외 조건을 공유하며, 프론트는 supplement 엔티티 API를 통해 제품 상세 목록과 신고를 처리한다.

**Tech Stack:** FastAPI, Pydantic, Tortoise ORM, Aerich, MySQL 8, React 19, TypeScript, Tailwind CSS, Playwright, pytest

**Spec:** `docs/superpowers/specs/2026-09-02-supplement-review-report-design.md`

## Global Constraints

- 브랜치는 최신 `main`에서 만든 `feature/216`이다.
- 커밋 메시지는 `[feature/216][신동훈]내용` 형식만 사용한다.
- `note`는 개인 메모이며 공개 응답에 절대 포함하지 않는다.
- 원본 이름과 `user_id`, 이메일, `report_count`를 공개 응답에 포함하지 않는다.
- 프론트는 이름을 마스킹하지 않는다.
- `review_body`는 PATCH DTO와 본인 응답에만 추가하고 PUT upsert DTO에는 넣지 않는다.
- `is_hidden`과 닉네임 컬럼을 만들지 않는다.
- 기존 Tortoise annotate, LEFT JOIN 성질, 정렬 tie-break, `registration_count`, `list_popular()`을 유지한다.
- #185 성분 합계 카드와 #213 제품 상세 성분 표를 수정하지 않는다.
- 모든 기능은 RED→GREEN→REFACTOR 순서로 구현한다.
- Task 1 완료 후 생성 SQL을 사용자에게 보고하고 다음 Task 전에 승인을 받는다.

---

### Task 1: 후기 모델과 22_ 마이그레이션

**Files:**
- Modify: `app/models/supplement_nutrients.py`
- Create: `app/core/db/migrations/models/22_*_add_supplement_review_report.py`

**Interfaces:**
- Produces: `UserSupplementNutrient.review_body`, `SupplementReviewReport(user, registration, created_at)`

- [ ] `UserSupplementNutrient`에 nullable `review_body` CharField(max_length=500)를 추가한다.
- [ ] `SupplementReviewReport`에 CASCADE FK 두 개, `(user, registration)` unique, registration index를 추가한다.
- [ ] `docker compose exec fastapi uv run aerich migrate --name add_supplement_review_report`를 실행한다.
- [ ] 파일명이 `22_`인지 확인하고 upgrade가 review_body ALTER와 report table CREATE만 포함하는지 읽는다.
- [ ] downgrade가 report table DROP과 review_body DROP을 모두 포함하는지 읽는다.
- [ ] SQL을 사용자에게 붙여 보고하고 승인을 기다린다.

### Task 2: 이름 마스킹과 내 프로필 표시명

**Files:**
- Modify: `app/core/validators/user_validators.py`
- Modify: `app/tests/user_apis/test_name_rules.py`
- Modify: `app/dtos/users.py`
- Modify: `app/apis/v1/user_routers.py`
- Modify: `frontend/src/entities/account/types.ts`
- Modify: `frontend/src/entities/account/api.ts`
- Modify: `frontend/src/entities/account/api.mock.ts`

**Interfaces:**
- Produces: `mask_name(raw: str) -> str`, `UserInfoResponse.masked_name`, `AccountProfile.maskedName`

- [ ] 2·3·4·5자, 영문, 빈 이름, 20자 이름의 마스킹 기대값을 `test_name_rules.py`에 추가한다.
- [ ] 테스트를 실행해 `mask_name` 부재로 실패하는지 확인한다.
- [ ] 별 최대 3개 규칙의 최소 구현을 `validate_name` 옆에 추가한다.
- [ ] `/users/me` GET과 PATCH 응답이 원본 name과 별도로 `maskedName`을 반환하도록 DTO 생성 지점에서 계산한다.
- [ ] account API의 실 응답·목업·화면 타입에 `maskedName`을 매핑한다.
- [ ] 이름 단위 테스트와 사용자 프로필 API 테스트를 실행한다.
- [ ] `[feature/216][신동훈]후기 작성자 이름 마스킹 추가`로 커밋한다.

### Task 3: 후기 본문 PATCH 보존

**Files:**
- Modify: `app/dtos/user_supplement_nutrients.py`
- Modify: `app/services/user_supplement_nutrients.py`
- Modify: `app/tests/med_apis/test_user_suppl_nutr_api.py`
- Modify: `app/tests/med_apis/test_user_suppl_nutr_service.py`

**Interfaces:**
- Produces: `UserSupplementNutrientUpdateRequest.review_body`, `UserSupplementNutrientResponse.review_body`

- [ ] PATCH의 본문 공백 정리·빈 문자열 null·500자 상한·다른 필드 보존 테스트를 작성한다.
- [ ] 중단 후 PUT 재등록이 기존 `score`와 `review_body`를 보존하는 테스트를 작성한다.
- [ ] 테스트가 DTO 필드 부재로 실패하는지 확인한다.
- [ ] 기존 note 정규화 패턴으로 PATCH DTO와 본인 응답에만 필드를 추가한다.
- [ ] PUT upsert DTO와 `_write_upsert`에는 `review_body`를 추가하지 않는다.
- [ ] 관련 API·서비스 테스트와 Ruff를 실행한다.
- [ ] `[feature/216][신동훈]영양제 공개 후기 수정 경로 추가`로 커밋한다.

### Task 4: 공개 후기 리포지토리와 집계 보정

**Files:**
- Modify: `app/repositories/supplement_nutrient_repository.py`
- Create: `app/repositories/supplement_review_repository.py`
- Test: `app/tests/med_apis/test_med_nutr_api.py`

**Interfaces:**
- Produces: 공개 후기 목록·total·rating_average·review_count, 숨김 registration ID 조회, 기존 search 집계 필터

- [ ] 별점만·본문만·COMPLETED 포함, WITHDRAWN·직접입력·신고 3건 제외 테스트를 작성한다.
- [ ] 신고가 없는 빈 hidden_ids에서 평점이 유지되고 후기 없는 제품도 검색에 남는 테스트를 작성한다.
- [ ] 테스트가 신고 모델·공개 조건 부재로 실패하는지 확인한다.
- [ ] 신고 수 3 이상인 registration ID를 별도 집계 쿼리로 구한다.
- [ ] 표시 대상과 평점 모집단이 탈퇴·숨김·직접입력 제외 조건을 공유하도록 리포지토리 헬퍼를 구성한다.
- [ ] search의 `review_filter`에 ACTIVE owner와 조건부 hidden_ids 제외만 추가하고 registration_count와 정렬을 유지한다.
- [ ] 리포지토리·검색 API 테스트와 Ruff를 실행한다.
- [ ] `[feature/216][신동훈]공개 후기 조회와 평점 집계 보정`으로 커밋한다.

### Task 5: 후기 목록·신고 API

**Files:**
- Create: `app/dtos/supplement_reviews.py`
- Create: `app/services/supplement_reviews.py`
- Modify: `app/apis/v1/med_router.py`
- Create: `app/tests/med_apis/test_supplement_review_api.py`

**Interfaces:**
- Produces: `GET /med/nutr/{id}/reviews`, `POST /med/nutr/reviews/{registration_id}/report`

- [ ] 목록 응답, total과 review_count 차이, 원본 이름·note·user_id·report_count 미노출 테스트를 작성한다.
- [ ] 중복 204, 본인 400, 없는·빈·탈퇴·숨김 후기 404, 세 번째 신고 즉시 숨김 테스트를 작성한다.
- [ ] 테스트가 라우트 부재로 실패하는지 확인한다.
- [ ] DTO 변환 시 `mask_name()`으로 author_label을 만들고 is_mine/reported_by_me를 계산한다.
- [ ] unique 충돌을 멱등 204로 처리하고 다른 DB 오류는 삼키지 않는다.
- [ ] 정적 `/nutr/reviews/...` 신고 라우트와 제품별 `/nutr/{id}/reviews`를 동적 상세 라우트보다 앞에 둔다.
- [ ] 신규 API 테스트와 Ruff를 실행한다.
- [ ] `[feature/216][신동훈]영양제 후기 목록과 신고 API 추가`로 커밋한다.

### Task 6: 프론트 후기 계약과 편집 입력

**Files:**
- Modify: `frontend/src/entities/supplement/types.ts`
- Modify: `frontend/src/entities/supplement/api.ts`
- Modify: `frontend/src/entities/supplement/api.mock.ts`
- Modify: `frontend/src/entities/supplement/index.ts`
- Modify: `frontend/src/pages/supplements/EditSupplementSheet.tsx`
- Modify: `frontend/src/pages/supplements/SupplementsPage.tsx`
- Test: `frontend/tests/e2e/supplements.spec.ts`

**Interfaces:**
- Produces: `SupplementReview`, `SupplementReviewList`, `fetchSupplementReviews()`, `reportSupplementReview()`, `UpdateSupplementPayload.reviewBody`

- [ ] 메모 비공개 안내, 마스킹 이름 공개 안내, 후기 500자 입력·저장·재편집 테스트를 작성한다.
- [ ] 테스트가 reviewBody와 입력 UI 부재로 실패하는지 확인한다.
- [ ] 실 API 매핑과 USE_MOCK 분기를 supplement api 경계 안에 구현한다.
- [ ] 목업에 동일 `김*훈` 두 건, `박*`, `남**훈`, `K***g`, 별점만·본문만·내 후기 사례를 추가한다.
- [ ] EditSupplementSheet에 reviewBody 상태·textarea와 두 라벨 안내를 추가하고 SupplementsPage에서 maskedName을 전달한다.
- [ ] 관련 Playwright와 TypeScript 검사를 실행한다.
- [ ] `[feature/216][신동훈]영양제 공개 후기 편집 입력 추가`로 커밋한다.

### Task 7: 제품 상세 후기 목록과 신고 흐름

**Files:**
- Modify: `frontend/src/pages/supplements/SupplementProductPage.tsx`
- Create: `frontend/src/pages/supplements/SupplementReviewSection.tsx`
- Create: `frontend/tests/e2e/supplement-reviews.spec.ts`

**Interfaces:**
- Consumes: `fetchSupplementReviews`, `reportSupplementReview`
- Produces: 10개 최신 후기, 더 보기, 신고 확인 시트, 성공·실패 토스트

- [ ] 별점만·본문만·내 후기·동일 authorLabel·빈 목록·면책 한 줄의 E2E를 작성한다.
- [ ] 더 보기가 다음 10개를 이어붙이고 신고 성공은 카드와 total을 줄이며 실패는 카드를 유지하는 E2E를 작성한다.
- [ ] 테스트가 후기 UI 부재로 실패하는지 확인한다.
- [ ] 제품 성분 표 JSX를 변경하지 않고 그 아래에 전용 후기 섹션을 추가한다.
- [ ] 날짜는 한국어 월·일만 표시하고 null 별점·본문 줄은 렌더하지 않는다.
- [ ] 신고 사유·검토 약속·정렬 칩·무한 스크롤 없이 확인 시트와 토스트만 구현한다.
- [ ] 신규·제품 상세 회귀 E2E와 375px 오버플로우를 확인한다.
- [ ] `[feature/216][신동훈]제품 상세 후기와 신고 흐름 추가`로 커밋한다.

### Task 8: 마이그레이션·통합 최종 검증

**Files:**
- No production changes unless a covered regression is found.

- [ ] `aerich upgrade`, `downgrade`, `upgrade`를 순서대로 실행한다.
- [ ] 실제 후기 목록 JSON에서 원본 실명이 0건이고 note·user_id·report_count가 없는지 확인한다.
- [ ] 서버 후기·검색·사용자 영양제·이름 규칙 테스트와 전체 관련 테스트를 실행한다.
- [ ] `uv run ruff format . --check`와 `uv run ruff check .`를 실행한다.
- [ ] 목업 모드와 실 API 모드 전체 Playwright를 각각 실행한다.
- [ ] TypeScript `tsc -b`와 Vite production build를 실행한다.
- [ ] diff에서 #185 성분 합계와 #213 제품 상세 성분 표, `list_popular()`, upsert DTO가 유지됐는지 확인한다.
