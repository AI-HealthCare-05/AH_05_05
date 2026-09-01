# #213 Supplement Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영양제 탭에 내 영양제·둘러보기 전환, 검색 정렬 집계, 제품 상세, 홈 랭킹 더 보기를 추가한다.

**Architecture:** `SupplementsPage`가 기존 사용자 영양제 상태와 시트를 계속 소유하고, 신규 `SupplementsBrowseView`와 `SupplementProductPage`를 독립 화면 단위로 추가한다. 서버 검색은 기존 `SupplementNutrientRepository.search()` 안에서만 조건부 집계를 수행하며 `list_popular()`과 영구 스키마는 유지한다.

**Tech Stack:** FastAPI, Pydantic, Tortoise ORM, MySQL 8, React 19, React Router 7, TypeScript, Tailwind CSS, Playwright, pytest

**Spec:** `docs/superpowers/specs/2026-09-01-supplement-page-redesign-design.md`

## Global Constraints

- 브랜치는 최신 `main`에서 만든 `feature/213`이다.
- 커밋 메시지는 `[feature/213][신동훈]내용` 형식만 사용한다.
- 모델·스키마·마이그레이션·복약 파일을 변경하지 않는다.
- #185 성분 합계 코드와 Add/EditSupplementSheet를 변경하지 않는다.
- 후기 공개·신고·플레이스홀더를 만들지 않는다.
- `list_popular()`을 수정하거나 검색에 재사용하지 않는다.
- 새 기능과 버그 수정은 RED→GREEN→REFACTOR 순서로 검증한다.

---

### Task 1: 탭 컨테이너와 내 영양제 회귀 보존

**Files:**
- Modify: `frontend/src/pages/supplements/SupplementsPage.tsx`
- Test: `frontend/tests/e2e/supplement-browse.spec.ts`

**Interfaces:**
- Consumes: React Router `useSearchParams`, 기존 SupplementsPage 상태·시트
- Produces: `tab=my|browse` 화면 분기와 `replace: true` 전환

- [ ] `/supplements`, `?tab=browse`, 반복 탭 변경 후 뒤로가기, 양쪽 헤더 추가 버튼을 검증하는 Playwright 테스트를 작성한다.
- [ ] 새 테스트가 탭 UI 부재로 실패하는지 실행한다.
- [ ] AuthPage의 시각 패턴만 참고해 두 칸 세그먼트 탭을 구현한다.
- [ ] 기존 내 영양제 JSX와 `NutrientTotalCard` 이하 코드를 변경하지 않고 my 분기에 둔다.
- [ ] 기존 `supplements.spec.ts`와 신규 탭 테스트를 실행한다.
- [ ] 개편 전 기준 스크린샷과 my 탭 스크린샷을 375px에서 비교한다.
- [ ] `[feature/213][신동훈]영양제 탭 분리`로 커밋한다.

### Task 2: 서버 검색 정렬과 집계

**Files:**
- Modify: `app/apis/v1/med_router.py`
- Modify: `app/apis/v1/admin_routers.py`
- Modify: `app/dtos/supplement_nutrients.py`
- Modify: `app/services/supplement_nutrients.py`
- Modify: `app/repositories/supplement_nutrient_repository.py`
- Test: `app/tests/med_apis/test_med_nutr_api.py`

**Interfaces:**
- Consumes: `UserSupplementNutrient.user_registrations`, `SupplementStatus.ACTIVE`
- Produces: `SupplementSort = Literal['name', 'registered', 'rating', 'reviews']`, `search(name, *, sort, offset, limit)`, `rating_average`, `review_count`

- [ ] 기본 이름순, 네 정렬, null-last, 평점 동률 후기 수, 직접 입력 제외, ACTIVE 등록 수, null·0 응답, 잘못된 sort, 공백 name 테스트를 작성한다.
- [ ] 테스트가 sort 미지원·응답 필드 부재로 실패하는지 확인한다.
- [ ] FastAPI 쿼리 타입으로 네 값 외 입력을 422 처리하고 서비스 기본값을 `name`으로 둔다.
- [ ] Tortoise conditional `Count`/`Avg`가 LEFT JOIN을 유지하는지 생성 SQL과 테스트로 확인한다.
- [ ] ORM 표현이 필터를 JOIN에 유지하지 못할 때만 search 내부 raw SQL로 전환하고 이유를 주석으로 남긴다.
- [ ] 평점은 서버에서 소수 첫째 자리로 반올림하고 상세·기존 admin 호출에는 null·0 기본을 유지한다.
- [ ] 서버 테스트와 Ruff를 실행한다.
- [ ] `list_popular()` diff가 없는지 확인한다.
- [ ] `[feature/213][신동훈]영양제 검색 정렬 집계 추가`로 커밋한다.

### Task 3: 프론트 검색 계약과 목 데이터

**Files:**
- Modify: `frontend/src/entities/supplement/types.ts`
- Modify: `frontend/src/entities/supplement/api.ts`
- Modify: `frontend/src/entities/supplement/api.mock.ts`
- Modify: `frontend/src/entities/supplement/index.ts`
- Test: `frontend/tests/e2e/supplement-ranking-api.spec.ts`

**Interfaces:**
- Produces: `SupplementSortKey`, `SupplementProduct.ratingAverage`, `SupplementProduct.reviewCount`, `SearchSupplementProductsParams.sort`

- [ ] 실제 API 요청에 sort가 포함되고 Decimal 문자열 평점이 숫자로 매핑되는 테스트를 작성한다.
- [ ] 목 검색이 네 정렬과 null-last를 재현하는 테스트를 작성한다.
- [ ] 테스트가 신규 타입·필드·쿼리 부재로 실패하는지 확인한다.
- [ ] `mapSupplementProduct`에서 평점만 `Number()`로 변환하고 후기 수는 숫자로 정규화한다.
- [ ] AddSupplementSheet 호출부는 sort를 전달하지 않은 상태로 유지한다.
- [ ] 프론트 API 테스트와 TypeScript 검사를 실행한다.
- [ ] `[feature/213][신동훈]영양제 검색 정렬 계약 연결`로 커밋한다.

### Task 4: 둘러보기 랭킹·검색·정렬

**Files:**
- Create: `frontend/src/pages/supplements/SupplementsBrowseView.tsx`
- Modify: `frontend/src/pages/supplements/SupplementsPage.tsx`
- Test: `frontend/tests/e2e/supplement-browse.spec.ts`

**Interfaces:**
- Consumes: `getSupplementRanking()`, `searchSupplementProducts()`, 사용자 `registeredProductIds`
- Produces: 랭킹 5개, 이름/등록/평점/후기 칩, 20개 더 보기, 상세 이동

- [ ] 랭킹 5개·RxVita 부제·등록 배지·상세 이동 테스트를 추가하고 실패를 확인한다.
- [ ] 검색 결과 평점 표기, 후기 없음 무표기, 네 정렬 칩, offset 초기화, 더 보기 테스트를 추가하고 실패를 확인한다.
- [ ] 검색어가 비어 있으면 랭킹을 표시하고 입력 후 검색 결과로 전환한다.
- [ ] 정렬 변경 시 결과·offset을 초기화하고 URL은 `tab=browse`만 유지한다.
- [ ] 375px에서 칩 네 개가 가로 오버플로우 없이 보이는지 검증한다.
- [ ] 신규 및 기존 supplements E2E를 실행한다.
- [ ] `[feature/213][신동훈]영양제 둘러보기 화면 추가`로 커밋한다.

### Task 5: 제품 상세 화면

**Files:**
- Create: `frontend/src/pages/supplements/SupplementProductPage.tsx`
- Modify: `frontend/src/pages/supplements/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Test: `frontend/tests/e2e/supplement-product-detail.spec.ts`

**Interfaces:**
- Consumes: `getSupplementProduct(productId)`, `getSupplements()`, `AddSupplementSheet(presetProductId)`
- Produces: `/supplements/product/:productId`

- [ ] 제품명·제조/대상·섭취 정보·성분 목록·등록 버튼 테스트를 작성하고 실패를 확인한다.
- [ ] 등록 제품의 `내 영양제에서 보기`, 미등록 제품 preset 시트, 오류·404 상태 테스트를 작성한다.
- [ ] 성분 기준선과 후기 플레이스홀더가 렌더되지 않는지 사용자 관찰 결과로 검증한다.
- [ ] 최소 상세 화면과 라우트를 구현한다.
- [ ] 상세 E2E와 TypeScript 검사를 실행한다.
- [ ] `[feature/213][신동훈]영양제 제품 상세 추가`로 커밋한다.

### Task 6: 홈 랭킹 3개와 더보기

**Files:**
- Modify: `frontend/src/pages/home/SupplementRankingCard.tsx`
- Modify: `frontend/src/pages/home/HomePage.tsx`
- Test: `frontend/tests/e2e/supplement-ranking-home.spec.ts`

**Interfaces:**
- Produces: 홈 상위 3개, `더보기` → `/supplements?tab=browse`

- [ ] 홈 랭킹 3개와 텍스트 더보기 이동 테스트를 작성하고 실패를 확인한다.
- [ ] API limit을 바꾸지 않고 `items.slice(0, 3)`을 화면에만 적용한다.
- [ ] 기존 등록 동작과 둘러보기 5개를 함께 회귀 검증한다.
- [ ] `[feature/213][신동훈]홈 영양제 랭킹 더보기 추가`로 커밋한다.

### Task 7: 목업·실 API 통합 검증

**Files:**
- Modify only if a failing #213 behavior requires it: `frontend/tests/e2e/supplement-browse.spec.ts`, `frontend/tests/e2e/supplement-product-detail.spec.ts`, `frontend/tests/e2e/supplements-real-api.spec.ts`

- [ ] e2e-mock 모드 전체 Playwright를 실행하고 실패 0을 확인한다.
- [ ] e2e-real 모드 전체 Playwright를 실행하고 실패 0을 확인한다.
- [ ] TypeScript `tsc -b`와 Vite production build를 실행한다.
- [ ] 375px에서 내 영양제·둘러보기·검색·상세·홈 스크린샷을 저장하고 비교한다.
- [ ] 기존 my 화면의 목록·성분 합계·안내 문구가 기준과 같은지 확인한다.

### Task 8: 백엔드·범위 최종 검증

**Files:**
- No production changes unless verification exposes a covered regression.

- [ ] 영양제 API 테스트와 전체 `app/tests`를 실행한다.
- [ ] `uv run ruff format . --check`와 `uv run ruff check .`를 실행한다.
- [ ] `git diff main...HEAD`에서 migrations, `app/models`, 복약 파일, Add/EditSupplementSheet, summary.ts 변경이 없는지 확인한다.
- [ ] `grep -rn "#[0-9a-fA-F]\{6\}" frontend/src/ --include=*.tsx` 결과가 0인지 확인한다.
- [ ] 독립 코드 리뷰를 받아 Critical/Important 항목을 수정하고 재검증한다.
- [ ] 최종 상태와 환경상 차단된 검증이 있다면 실제 출력과 함께 보고한다.
