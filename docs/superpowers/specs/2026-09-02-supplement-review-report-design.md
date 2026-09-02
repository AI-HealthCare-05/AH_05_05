# #216 영양제 후기 공개와 신고 설계

## 목표

기존 `user_suppl_nutrient` 등록 행의 별점과 신규 공개 본문을 제품 상세 후기에서 보여주고, 사용자 신고가 세 건 누적된 후기는 자동으로 숨긴다. 기존 `note`는 개인 메모로 계속 비공개이며 후기 공개 응답에는 포함하지 않는다.

## 데이터 모델

- `user_suppl_nutrient.review_body varchar(500) null`을 추가한다.
- 한 사용자와 표준 제품의 등록 행 하나가 후기 하나를 겸한다. 별도 후기 본문 테이블은 만들지 않는다.
- `supplement_review_report`는 신고자 `user_id`, 신고 대상 `registration_id`, `created_at`만 저장한다.
- `(user_id, registration_id)`를 유일하게 유지해 중복 신고를 멱등 처리한다.
- 숨김 플래그를 저장하지 않고 신고 수가 3 이상인지 조회할 때 계산한다.
- 마이그레이션은 `22_`이며 `review_body` 추가와 신고 테이블 생성만 포함한다.

## 공개와 집계 규칙

- 표시 대상은 표준 제품 등록 중 `score IS NOT NULL OR review_body IS NOT NULL`인 행이다.
- 평점 모집단은 같은 공개 조건을 통과한 행 중 `score IS NOT NULL`인 행이다.
- 두 술어는 탈퇴 회원 제외, 신고 3건 이상 제외, 직접 입력 제품 제외를 공유한다.
- 등록 상태는 공개 조건이 아니다. `COMPLETED` 후기도 남기며 `WITHDRAWN` 회원 후기는 제외한다.
- `registration_count`는 현재 복용 중인 사람 수이므로 후기 숨김·탈퇴 조건을 적용하지 않는다.
- 검색 집계는 기존 Tortoise `annotate`와 LEFT JOIN 의미를 유지하고 `list_popular()`은 수정하지 않는다.

## 개인정보 경계

- 공개 API는 `note`, `user_id`, 이메일, 원본 이름, 신고 수를 반환하지 않는다.
- 작성자 이름은 응답 시 서버의 `mask_name()`으로 계산한다. 첫 글자와 마지막 글자만 남기고 가운데 별은 최대 세 개이며 2자 이름은 마지막 글자를 가린다.
- `/users/me` 응답에 `masked_name`을 추가해 사용자가 후기 작성 전에 실제 공개 표시명을 확인하게 한다.
- 마스킹 결과는 저장하거나 프론트에서 다시 계산하지 않는다.

## API 계약

- `GET /api/v1/med/nutr/{supplement_nutrient_id}/reviews?offset=0&limit=10`
  - 인증 필수, limit 최대 50, 최신 등록 ID 순이다.
  - `items`, `total`, `offset`, `limit`, `rating_average`, `review_count`를 반환한다.
  - 항목에는 `id`, `author_label`, `score`, `review_body`, `updated_at`, `is_mine`, `reported_by_me`만 포함한다.
- `POST /api/v1/med/nutr/reviews/{registration_id}/report`
  - 본문 없이 204를 반환한다.
  - 중복 신고는 204, 본인 후기는 400, 존재하지 않거나 공개 대상이 아닌 후기는 404다.
- 두 라우트는 `/nutr/{supplement_nutrient_id}`보다 먼저 선언한다.
- 후기 본문은 사용자 등록 PATCH에서만 수정한다. PUT upsert DTO에는 넣지 않아 재등록 시 기존 후기와 별점을 보존한다.

## 프론트 흐름

- 제품 상세의 기존 성분 표 아래에 후기 요약과 10개 단위 목록을 붙인다.
- 별점 또는 본문이 null이면 해당 줄만 생략하며 빈 후기는 유도 버튼 없이 `아직 후기가 없어요`만 표시한다.
- 내 후기는 `내 후기` 배지, 다른 후기는 `신고` 버튼을 표시한다.
- 신고 확인 시트는 사유를 받지 않으며 성공하면 토스트와 함께 해당 카드를 로컬 목록에서 제거한다.
- 목록 끝에 `개인의 경험이며 효능을 보장하지 않습니다`를 한 번만 표시한다.
- 편집 시트에 공개 후기 입력을 추가하고 메모에는 `나만 볼 수 있어요`, 후기에는 서버의 마스킹 이름과 `다른 사람에게 보여요`를 표시한다.
- API 목업은 동일 마스킹 이름 중복, 2·4자·영문 이름, 별점만·본문만·내 후기 사례를 포함한다.

## 검증과 중간 승인

- 새 동작은 서버 단위·API 테스트와 Playwright E2E를 먼저 실패시킨 뒤 구현한다.
- 모델 변경 후 Aerich가 만든 `22_` SQL을 읽어 ALTER 1건과 CREATE TABLE 1건, 대응 downgrade만 존재하는지 사용자에게 먼저 보고한다.
- 승인 뒤 서버 API·집계와 프론트 화면을 이어서 구현한다.
- 마지막에는 upgrade/downgrade/upgrade, 목업·실 API E2E, TypeScript·빌드, Ruff를 실행한다.
- #185 성분 합계 카드와 #213 제품 상세 성분 표는 변경하지 않는다.
