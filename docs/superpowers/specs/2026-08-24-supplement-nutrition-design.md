# 건강기능식품 영양성분 검색·사용자 복용 등록 설계

## 1. 목적

전국 건강기능식품 영양성분정보 표준데이터를 제품 기준정보로 저장하고, 로그인 사용자가 제품명을 부분 검색한 뒤 자신이 복용하는 제품과 복용 정보를 등록·조회·수정·종료할 수 있게 한다.

이 설계의 핵심은 국가 표준 제품 정보와 사용자 개인 복용 정보를 분리하는 것이다. 제품 정보는 `supplement_nutrients`, 사용자 복용 정보는 `user_suppl_nutrient`, 복용 시간대는 `user_suppl_nutrient_slots`가 각각 정본이다.

## 2. 범위

포함 범위:

- Tortoise ORM 모델 3개와 `SupplementStatus` enum
- Aerich 마이그레이션 및 Docker MySQL 반영
- 첨부 `.numbers` 파일 5,556건을 재실행 가능하게 적재하는 import 스크립트
- 제품명 앞뒤 부분 검색 및 제품 상세 API
- 사용자 복용 영양제 등록·목록·상세·수정·복용 종료 API
- `MealSlot`과 `user_settings`를 이용한 실제 복용 시각 응답
- dbdiagram의 신규 테이블·컬럼·인덱스·관계 note
- 모델, Repository, Service, API, importer 및 OpenAPI 테스트

제외 범위:

- 영양제 복용 알람 자동 생성 및 Web Push 발송
- 건강기능식품 성분 간 상호작용 판정
- 사용자 직접 입력 제품 또는 표준데이터에 없는 제품 등록
- 데이터 원본에서 사라진 제품의 자동 삭제

## 3. 데이터 원본

원본 파일:

`/Users/admin/Downloads/전국건강기능식품영양성분정보표준데이터-20260824.numbers`

분석 결과:

- 데이터 행: 5,556건
- 원본 컬럼: 31개
- `식품코드`: 5,556개 모두 고유
- 제품명 최대 길이: 62자
- 식품코드 최대 길이: 19자
- 빈 영양성분 셀은 값이 0이라는 의미가 아니므로 `NULL`로 보존

## 4. 데이터 모델

### 4.1 SupplementStatus

```text
ACTIVE     현재 복용 중
PAUSED     일시 중지
COMPLETED  복용 종료
```

### 4.2 supplement_nutrients

전국 표준 제품 한 건을 한 행으로 저장한다. 모든 영양성분은 `basis_qty`에 표시된 제공 단위를 기준으로 한다.

| 모델 필드 | DB 타입 | 필수 | 원본·설명 |
|---|---|---:|---|
| id | bigint PK | Y | 내부 식별자 |
| food_code | varchar(20) unique | Y | 식품코드 |
| name | varchar(100) | Y | 식품명 |
| basis_qty | varchar(10) | Y | 영양성분제공단위량 |
| energy_kcal | int | Y | 에너지(kcal) |
| water_g | decimal(10,3) | N | 수분(g) |
| protein_g | decimal(5,2) | Y | 단백질(g) |
| fat_g | decimal(5,2) | N | 지방(g) |
| ash_g | decimal(10,3) | N | 회분(g) |
| carb_g | decimal(6,2) | Y | 탄수화물(g) |
| sugar_g | decimal(5,2) | N | 당류(g) |
| fiber_g | decimal(7,1) | N | 식이섬유(g) |
| calcium_mg | int | N | 칼슘(mg) |
| iron_mg | decimal(5,2) | N | 철(mg) |
| phosphorus_mg | int | N | 인(mg) |
| potassium_mg | int | N | 칼륨(mg) |
| sodium_mg | int | N | 나트륨(mg) |
| vitamin_a_ug_rae | int | N | 비타민 A(μg RAE) |
| retinol_ug | int | N | 레티놀(μg) |
| beta_carotene_ug | int | N | 베타카로틴(μg) |
| thiamine_mg | decimal(6,3) | N | 티아민(mg) |
| riboflavin_mg | decimal(6,3) | N | 리보플라빈(mg) |
| niacin_mg | decimal(6,3) | N | 니아신(mg) |
| vitamin_c_mg | decimal(7,2) | N | 비타민 C(mg) |
| vitamin_d_ug | decimal(7,2) | N | 비타민 D(μg) |
| cholesterol_mg | decimal(6,2) | N | 콜레스테롤(mg) |
| sat_fat_g | decimal(4,2) | N | 포화지방산(g) |
| trans_fat_g | decimal(4,2) | N | 트랜스지방산(g) |
| serving_desc | varchar(10) | Y | 1회분량. 예: 1정, 1캡슐 |
| serving_size | varchar(10) | Y | 1회분량중량/부피 |
| daily_freq | varchar(5) | Y | 1일섭취횟수. 원본 문자열 |
| target | varchar(10) | N | 섭취대상 |

`name LIKE '%검색어%'`는 선행 와일드카드 때문에 일반 B-tree 인덱스를 활용하지 못한다. 현재 데이터 규모가 5,556건이므로 별도 검색 인덱스나 전문검색 엔진을 추가하지 않는다.

### 4.3 user_suppl_nutrient

사용자와 표준 제품을 연결하고 사용자의 실제 복용량·기간·상태를 저장한다.

```dbml
Table user_suppl_nutrient {
  id bigint [pk, increment, note: '사용자 복용 영양제 등록 식별자']
  user_id bigint [not null, note: '영양제를 복용하는 사용자 식별자']
  supplement_nutrient_id bigint [not null, note: '국가 표준 영양제 제품 식별자']
  dose_amount decimal(8,3) [not null, note: '1회 실제 섭취 수량']
  dose_unit varchar(20) [not null, note: '섭취 수량 단위. 예: 정, 캡슐, 포, ml']
  start_date date [not null, note: '복용 시작일']
  end_date date [note: '복용 종료일. 복용 중이면 null']
  status supplement_status [not null, note: '현재 복용 상태']
  note varchar(500) [note: '사용자가 입력한 복용 참고사항']
  created_at datetime [not null, default: `current_timestamp`, note: '최초 등록 시각']
  updated_at datetime [note: '마지막 변경 시각']

  indexes {
    (user_id, supplement_nutrient_id) [unique, note: '사용자별 동일 제품 중복 등록 방지']
    (user_id, status) [note: '사용자의 현재 복용 영양제 목록 조회']
  }

  checks {
    `dose_amount > 0`
    `end_date IS NULL OR end_date >= start_date`
  }

  Note: '''
  사용자가 실제로 복용하는 건강기능식품과 복용량·기간·상태를 저장한다.
  동일 제품 재등록 시 새 행을 만들지 않고 기존 행을 갱신한다.
  '''
}
```

고유키 `(user_id, supplement_nutrient_id)`는 같은 제품의 중복 등록을 DB 수준에서 차단한다. 재등록 요청은 기존 행을 갱신하고 `ACTIVE`로 재활성화한다.

### 4.4 user_suppl_nutrient_slots

```dbml
Table user_suppl_nutrient_slots {
  id bigint [pk, increment, note: '사용자 영양제 복용 시간대 식별자']
  user_suppl_nutrient_id bigint [not null, note: '사용자 복용 영양제 등록 식별자']
  slot meal_slot [not null, note: '복용 시간대. MORNING, LUNCH, EVENING, BEDTIME']
  created_at datetime [not null, default: `current_timestamp`, note: '시간대 최초 등록 시각']

  indexes {
    (user_suppl_nutrient_id, slot) [unique, note: '같은 복용정보에 동일 시간대 중복 등록 방지']
  }

  Note: '''
  사용자 영양제의 복용 시간대를 저장한다.
  실제 시각은 user_settings의 시간대별 복용 시각을 사용한다.
  '''
}
```

하루 복용 횟수는 이 테이블의 시간대 행 개수로 계산한다. 별도 `times_per_day` 컬럼을 저장하지 않아 중복 상태를 만들지 않는다.

### 4.5 관계와 삭제 정책

```dbml
/* 사용자 삭제 시 개인 복용정보도 함께 삭제한다. */
Ref: user_suppl_nutrient.user_id > user.id [delete: cascade]

/* 기준 제품이 복용정보에서 사용 중이면 제품 삭제를 제한한다. */
Ref: user_suppl_nutrient.supplement_nutrient_id > supplement_nutrients.id [delete: restrict]

/* 사용자 복용정보 삭제 시 소속 시간대도 함께 삭제한다. */
Ref: user_suppl_nutrient_slots.user_suppl_nutrient_id > user_suppl_nutrient.id [delete: cascade]
```

dbdiagram에는 세 테이블의 모든 컬럼에 note를 두고, 인덱스와 주요 관계에도 용도 또는 삭제 정책을 설명한다.

## 5. API 설계

모든 API는 `get_request_user` 인증을 요구한다. 다른 사용자의 `user_suppl_nutrient`는 존재 여부를 노출하지 않고 `404`를 반환한다.

### 5.1 제품 검색

```http
GET /api/v1/med/nutr?name={검색어}&offset=0&limit=20
```

- `name`: 필수, 공백 제거 후 1~100자
- 검색 조건: Tortoise ORM `name__icontains`, SQL 의미는 `LIKE '%검색어%'`
- `offset`: 0 이상, 기본 0
- `limit`: 1~100, 기본 20
- 정렬: `name`, `id`
- 응답: `items`, `total`, `offset`, `limit`

```http
GET /api/v1/med/nutr/{supplement_nutrient_id}
```

제품의 원본 식별정보와 전체 영양성분을 반환한다. 없는 제품은 `404`다.

### 5.2 사용자 복용 영양제 등록 또는 재등록

```http
PUT /api/v1/med/user-suppl-nutr/{supplement_nutrient_id}
```

요청:

```json
{
  "dose_amount": 1,
  "dose_unit": "정",
  "start_date": "2026-08-24",
  "end_date": null,
  "slots": ["MORNING", "EVENING"],
  "note": "식후 복용"
}
```

규칙:

- `dose_amount > 0`
- `dose_unit`: 공백 제거 후 1~20자
- `slots`: 1개 이상이며 중복 불가
- `end_date`: null 또는 `start_date` 이상
- 경로의 제품이 없으면 `404`
- 같은 `(user_id, supplement_nutrient_id)`가 있으면 기존 행을 갱신
- 최초 등록과 재등록은 모두 `status = ACTIVE`로 저장한다
- 등록 시 `UserSettings.get_or_create(user_id=...)`로 시간대 설정 존재를 보장한다
- 복용 정보 갱신과 slots 전체 교체를 하나의 DB 트랜잭션에서 처리
- 최초 생성은 `201`, 기존 행 갱신은 `200`으로 구분하지 않고 멱등 PUT 응답을 일관되게 `200`으로 반환

### 5.3 사용자 복용 목록과 상세

```http
GET /api/v1/med/user-suppl-nutr?status=ACTIVE&offset=0&limit=20
GET /api/v1/med/user-suppl-nutr/{user_suppl_nutrient_id}
```

- 목록은 현재 사용자 행만 조회
- 상태 필터는 선택 사항
- 정렬은 `status`, `start_date DESC`, `id DESC`
- 응답에 제품 전체 정보와 slots를 포함
- 각 slot은 `user_settings`에서 계산한 실제 시각을 함께 반환

시간대 매핑:

| slot | user_settings 필드 |
|---|---|
| MORNING | morning_medication_time |
| LUNCH | lunch_medication_time |
| EVENING | evening_medication_time |
| BEDTIME | bedtime_medication_time |

### 5.4 수정과 복용 종료

```http
PATCH /api/v1/med/user-suppl-nutr/{user_suppl_nutrient_id}
DELETE /api/v1/med/user-suppl-nutr/{user_suppl_nutrient_id}
```

PATCH는 전달된 일반 필드만 수정하고, `slots`가 전달되면 시간대를 전체 교체한다. 빈 `slots`는 허용하지 않는다. `status = COMPLETED`로 수정하면서 `end_date`를 생략하면 현재 날짜를 자동으로 기록한다.

DELETE는 물리 삭제하지 않고 아래 상태로 전환한 뒤 `204`를 반환한다.

```text
status = COMPLETED
end_date = 현재 날짜(Asia/Seoul)
updated_at = 현재 시각(Asia/Seoul)
```

이미 `COMPLETED`인 행에 대한 DELETE는 동일하게 `204`를 반환한다.

## 6. 코드 구조

```text
app/models/supplement_nutrients.py
app/dtos/supplement_nutrients.py
app/repositories/supplement_nutrient_repository.py
app/services/supplement_nutrients.py
app/apis/v1/med_router.py
scripts/import_supplement_nutrients.py
```

`med_router`는 `/med`를 prefix로 두고 내부에 제품 `/nutr` 및 사용자 `/user-suppl-nutr` endpoint를 등록한다. Router는 HTTP 입력·출력 변환만 담당하고, 소유권·업무 검증·트랜잭션은 Service, 쿼리는 Repository가 담당한다.

모델 모듈은 `app.models.__init__`, `TORTOISE_APP_MODELS`에 등록해 앱과 Aerich가 동일한 모델 집합을 사용하게 한다.

## 7. 원본 데이터 import

`scripts/import_supplement_nutrients.py`는 `.numbers` 경로를 인자로 받는다. `numbers-parser`를 프로젝트 의존성으로 추가한다.

처리 순서:

1. 시트와 테이블을 열고 첫 비어 있지 않은 행을 헤더로 식별
2. 예상한 31개 헤더와 순서가 정확한지 검증
3. 5,556개 행 전체를 메모리에서 타입 변환·검증
4. 빈 셀은 `None`, 정수는 `int`, 소수는 `Decimal`로 변환
5. 중복 `food_code`, 필수값 누락, 자릿수 초과가 하나라도 있으면 DB 변경 없이 실패
6. 기존 `food_code`를 한 번에 조회해 신규와 갱신 대상으로 분리
7. 트랜잭션 안에서 500건 단위 `bulk_create`와 `bulk_update`
8. 생성·갱신·전체 건수를 출력

원본에서 사라진 기존 DB 행은 삭제하지 않는다. import는 upsert만 수행한다.

## 8. 오류 처리

| 상황 | 응답·처리 |
|---|---|
| 인증 없음 또는 토큰 오류 | 기존 인증 정책의 401 |
| 제품 또는 사용자 소유 등록정보 없음 | 404 |
| 검색어 공백·길이 오류 | 422 |
| 복용량 0 이하 | 422 |
| 빈 slots 또는 중복 slots | 422 |
| 종료일이 시작일보다 빠름 | 422 |
| unique 경쟁 조건 | `IntegrityError`를 잡고 트랜잭션에서 기존 행을 다시 잠금 조회한 뒤 갱신 |
| importer 헤더 불일치·타입 오류 | 행 번호와 컬럼명을 출력하고 DB 변경 없이 종료 |

## 9. 테스트 및 검증

### 모델

- 테이블명, 필드 타입, max_length, decimal 자릿수
- enum과 nullability
- unique 및 복합 인덱스
- FK 삭제 정책

### Repository 및 Service

- `name__icontains` 앞뒤 부분 검색과 대소문자 무시
- total/offset/limit 및 안정적인 정렬
- 동일 사용자·제품 PUT 재실행 시 행 수 불변
- slots 교체와 트랜잭션 롤백
- 다른 사용자 데이터 접근 차단
- PATCH 부분 수정
- DELETE 소프트 종료와 멱등성
- slot별 `user_settings` 실제 시각 매핑

### API 및 OpenAPI

- 모든 endpoint의 인증 요구
- 요청 검증과 응답 스키마
- `/api/v1/med/nutr` 및 `/api/v1/med/user-suppl-nutr` 경로 노출
- Swagger summary와 endpoint 용도 docstring

### Importer 및 Docker MySQL

- 헤더 불일치, 숫자 변환, 빈 값 보존
- 같은 원본을 두 번 적재해도 5,556건 유지
- `COUNT(*) = 5556`
- `COUNT(DISTINCT food_code) = 5556`
- 대표 제품명 검색 API smoke test

### 최종 명령

- 관련 pytest
- 전체 pytest
- `uv run ruff check` 신규·변경 파일
- `uv run aerich migrate` 및 `uv run aerich upgrade`
- Docker MySQL 적재 건수 및 제약조건 확인

## 10. 완료 조건

- dbdiagram, Tortoise 모델, Aerich 마이그레이션, Docker MySQL 스키마가 동일하다.
- 모든 신규 dbdiagram 테이블·컬럼에 note가 있다.
- 첨부 파일 5,556건이 중복 없이 적재된다.
- 로그인 사용자가 이름 부분 검색으로 제품을 찾고 자신의 복용 정보와 시간대를 등록·관리할 수 있다.
- 관련 테스트와 전체 회귀 테스트가 통과한다.
- Git 커밋은 생성하지 않는다.
