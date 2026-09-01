# #213 영양제 페이지 개편 설계

## 목표

기존 영양제 화면을 `내 영양제`와 `둘러보기`로 나누고, 제품 검색·정렬·상세 조회 흐름을 추가한다. 기존 내 영양제 목록과 #185 성분 합계는 동작과 표현을 바꾸지 않는다.

## 화면 구조

- `/supplements`는 `내 영양제`를 기본으로 연다.
- `/supplements?tab=browse`는 `둘러보기`를 연다.
- 탭 변경은 `navigate(..., { replace: true })`를 사용한다.
- 헤더의 영양제 추가 버튼과 하단 탭바는 두 탭에서 유지한다.
- 둘러보기는 랭킹 5개, 제품명 검색, 네 개 정렬 칩, 20개 단위 더 보기를 제공한다.
- 랭킹과 검색 결과는 `/supplements/product/:productId`로 이동한다.
- 제품 상세는 제품 기본 정보와 1회분 성분만 표시하며 섭취 기준선과 후기 영역은 만들지 않는다.
- 등록하지 않은 제품은 `AddSupplementSheet`를 `presetProductId`로 열고, 등록 제품은 `/supplements`로 이동한다.
- 홈 랭킹은 3개만 표시하고 `더보기`로 둘러보기에 진입한다.

## 서버 계약

- `GET /api/v1/med/nutr`에 `sort=name|registered|rating|reviews`를 추가한다.
- 기본 정렬은 `name`; 알 수 없는 값은 FastAPI 검증으로 422를 반환한다.
- 공백 이름은 422를 유지한다.
- 응답 항목에 `rating_average`와 `review_count`를 추가한다.
- 후기 집계는 표준 제품 등록 중 `score IS NOT NULL`인 행만 센다.
- 등록 수는 표준 제품의 `ACTIVE` 행만 센다.
- 집계는 LEFT JOIN 의미를 유지해 후기 없는 제품도 검색 결과에 남긴다.
- 평점순은 평점 null을 마지막으로 보내고, 평점 내림차순, 후기 수 내림차순, id 순으로 정렬한다.
- `list_popular()`과 모델·스키마·마이그레이션은 변경하지 않는다.

## 변경 경계

- 기존 `NutrientTotalCard`, `StandardStatus`, `NutrientRangeBar`, `rangePositions`는 수정하지 않는다.
- `AddSupplementSheet`, `EditSupplementSheet`, `summary.ts`, 복약 관련 파일은 수정하지 않는다.
- 정렬 상태는 URL에 저장하지 않으며 AddSupplementSheet 검색에는 전달하지 않는다.
- 후기 공개·신고 및 후기 플레이스홀더는 #216 범위로 남긴다.

## 검증

- 서버 검색 정렬·집계 API 테스트를 먼저 실패시킨 뒤 구현한다.
- 프론트 탭·둘러보기·상세·홈 랭킹 E2E를 먼저 실패시킨 뒤 구현한다.
- 375px에서 정렬 칩과 화면 오버플로우를 확인한다.
- 목업과 실 API 모드 E2E를 각각 실행한다.
- TypeScript, Vite build, Ruff, 마이그레이션·모델·금지 파일 diff를 확인한다.

