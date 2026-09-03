# 공통코드 관리 및 채팅 평가 전환 설계

## 1. 목표

다음 변경을 하나의 일관된 배포 단위로 반영한다.

- `common_code_groups`, `common_codes` 테이블을 추가한다.
- 공통코드 그룹에 영문 대문자 기반 `category` 대분류를 도입한다.
- 관리자 공통코드 CRUD API와 A 분할형 관리 화면을 실제 데이터에 연결한다.
- `chat_sessions.score`를 제거하고 `is_like`, `reason_code` 기반 평가로 전환한다.
- 채팅 평가 사유를 활성 공통코드로 검증한다.
- 관리자 대시보드의 챗봇 만족도를 별점 평균에서 긍정 평가 비율로 변경한다.
- Aerich 마이그레이션을 Docker MySQL에 적용하고 실제 스키마를 확인한다.

기존 사용자 작업과 무관한 소스는 수정하지 않으며 Git 커밋은 생성하지 않는다.

## 2. 선택한 접근

정규화된 그룹·상세코드 구조를 사용한다.

- 대분류를 별도 테이블로 만들지 않고 `common_code_groups.category`에 저장한다.
- 상세코드는 `common_codes.group_id`로 코드그룹에 연결한다.
- 채팅 평가 사유는 문자열로 저장하되 서비스 계층에서 공통코드의 활성 상태와 평가 방향을 검증한다.

단일 공통코드 테이블은 그룹 정보가 반복되고, 대분류 테이블 추가 방식은 현재 범위에 비해 관리 계층이 과도하므로 사용하지 않는다.

## 3. 데이터 모델

### 3.1 `common_code_groups`

| 컬럼 | 타입 | 제약/용도 |
| --- | --- | --- |
| `id` | BIGINT | PK |
| `category` | VARCHAR(50) | NOT NULL, 영문 대문자·숫자·밑줄만 허용 |
| `group_code` | VARCHAR(50) | NOT NULL, UNIQUE, 생성 후 변경 불가 |
| `group_name` | VARCHAR(100) | NOT NULL |
| `description` | VARCHAR(500) | NULL |
| `is_active` | BOOLEAN | NOT NULL, 기본값 true |
| `created_by_admin_id` | BIGINT | NULL, `admin.id`, 삭제 시 SET NULL |
| `updated_by_admin_id` | BIGINT | NULL, `admin.id`, 삭제 시 SET NULL |
| `created_at` | DATETIME | NOT NULL |
| `updated_at` | DATETIME | NULL |

인덱스와 제약:

- `group_code` 유일조건
- `(category, is_active, group_code)` 조회 인덱스
- 생성·수정 관리자 FK 인덱스

`category`와 `group_code`는 입력 시 앞뒤 공백을 제거하고 대문자로 정규화한다. 허용 정규식은 `^[A-Z][A-Z0-9_]*$`이다.

### 3.2 `common_codes`

| 컬럼 | 타입 | 제약/용도 |
| --- | --- | --- |
| `id` | BIGINT | PK |
| `group_id` | BIGINT | NOT NULL, `common_code_groups.id`, 삭제 시 CASCADE |
| `detail_code` | VARCHAR(50) | NOT NULL, 그룹 내 고유, 생성 후 변경 불가 |
| `detail_name` | VARCHAR(100) | NOT NULL |
| `description` | VARCHAR(500) | NULL |
| `sort_order` | INT | NOT NULL, 기본값 0 |
| `is_active` | BOOLEAN | NOT NULL, 기본값 true |
| `created_by_admin_id` | BIGINT | NULL, `admin.id`, 삭제 시 SET NULL |
| `updated_by_admin_id` | BIGINT | NULL, `admin.id`, 삭제 시 SET NULL |
| `created_at` | DATETIME | NOT NULL |
| `updated_at` | DATETIME | NULL |

인덱스와 제약:

- `(group_id, detail_code)` 유일조건
- `(group_id, is_active, sort_order)` 조회 인덱스
- 생성·수정 관리자 FK 인덱스

`detail_code`에도 그룹 코드와 동일한 영문 대문자·숫자·밑줄 규칙을 적용한다.

### 3.3 `chat_sessions`

- `score` 컬럼과 1~5 범위 체크 제약을 삭제한다.
- `is_like BOOLEAN NULL`을 추가한다. `true`는 긍정, `false`는 부정, `null`은 미평가다.
- `reason_code VARCHAR(20) NULL`을 추가한다.
- 기존 별점 데이터는 변환하지 않는다. 새 컬럼은 모두 `null`로 시작하므로 기존 세션은 미평가 상태가 된다.

평가 사유는 의도적으로 DB FK를 두지 않는다. 공통코드가 비활성화되거나 명칭이 변경되어도 과거 평가의 코드값을 보존하고, 쓰기 시점에 서비스 계층에서 유효성을 검증한다.

## 4. 공통코드 상태 규칙

- 그룹 비활성화 시 하위 상세코드의 `is_active` 값은 변경하지 않는다.
- 비활성 그룹의 하위 코드는 서비스용 조회와 신규 채팅 평가 검증에서 제외한다.
- 그룹을 다시 활성화하면 기존에 활성 상태였던 하위 코드가 다시 사용 가능해진다.
- 그룹과 상세코드는 물리 삭제하지 않고 `is_active`로 관리한다.

## 5. API 설계

### 5.1 관리자 공통코드 API

모든 API는 관리자 JWT를 사용한다. ADMIN은 조회·등록·수정이 가능하고 STAFF는 조회만 가능하다.

- `GET /api/v1/admin/common-code-groups`
  - 조건: `category`, `group_code`, `group_name`, `is_active`, `offset`, `limit`
- `POST /api/v1/admin/common-code-groups`
- `GET /api/v1/admin/common-code-groups/{group_id}`
- `PATCH /api/v1/admin/common-code-groups/{group_id}`
- `GET /api/v1/admin/common-code-groups/{group_id}/codes`
  - 조건: `detail_code`, `detail_name`, `is_active`, `offset`, `limit`
- `POST /api/v1/admin/common-code-groups/{group_id}/codes`
- `GET /api/v1/admin/common-codes/{code_id}`
- `PATCH /api/v1/admin/common-codes/{code_id}`

응답 필드명은 관리자 전시 API와 같은 snake_case를 사용한다. 생성 후 `group_code`, `detail_code`는 수정 요청에서 받지 않는다.

### 5.2 서비스용 공통코드 조회 API

- `GET /api/v1/common-codes/{category}/{group_code}`

활성 그룹의 활성 상세코드만 `sort_order`, `id` 오름차순으로 반환한다. category와 group_code는 대문자로 정규화한 뒤 조회한다.

### 5.3 채팅 평가 API

- `PUT /api/v1/chat/sessions/{session_id}/feedback`
- 요청 필드: `isLike: boolean | null`, `reasonCode: string | null`
- 응답 필드: `sessionId`, `isLike`, `reasonCode`

규칙:

- 인증 사용자가 소유한 세션만 평가할 수 있다.
- 동일 세션의 평가는 덮어쓸 수 있다.
- `isLike=null`이면 `reasonCode`도 반드시 `null`이어야 하며 평가가 취소된다.
- `reasonCode`는 선택 입력이다.
- 긍정 평가의 사유는 `category=CHAT`, `group_code=P_REASON`의 활성 상세코드여야 한다.
- 부정 평가의 사유는 `category=CHAT`, `group_code=N_REASON`의 활성 상세코드여야 한다.
- 사유가 전달됐지만 그룹·상세코드가 없거나 비활성이거나 평가 방향과 다르면 422를 반환한다.

### 5.4 관리자 대시보드 API

`GET /api/v1/admin/dashboard/summary`의 채팅 통계를 변경한다.

- `chatResponses.averageScore` 제거
- `chatResponses.likeRate` 추가
- 선택 기간에 생성된 세션 중 `is_like IS NOT NULL`인 세션만 평가 완료로 집계
- 계산식: `is_like=true 수 / 평가 완료 세션 수 * 100`
- 소수점 한 자리로 반올림
- 평가 완료 세션이 없으면 `null`

## 6. 오류 처리

- 유일한 `group_code` 또는 그룹 내 `detail_code` 중복: 409
- 존재하지 않는 그룹·상세코드·채팅 세션: 404
- 다른 사용자의 채팅 세션 접근: 403
- STAFF의 등록·수정 요청: 403
- 잘못된 코드 형식, 평가 방향과 맞지 않는 사유, 미평가 상태의 사유 전달: 422
- 예상하지 못한 DB 오류는 기존 공통 오류 규격으로 처리하고 내부 로그에 원인을 남긴다.

## 7. 관리자 화면

기존 `common-code-management.html`의 A 분할형 레이아웃을 실제 API에 연결한다.

### 검색 영역

- 대분류
- 코드그룹
- 코드그룹명
- 사용여부
- 초기화·조회 버튼

검색은 조회 버튼을 눌렀을 때 실행하며 초기화 시 기본 조건으로 다시 조회한다.

### 왼쪽: 코드그룹

- 대분류, 코드그룹, 코드그룹명, 사용여부 표시
- 행 선택 시 오른쪽 상세코드 목록 조회
- 그룹 등록·수정 팝업 제공
- 대분류와 코드값은 소문자 입력을 대문자로 자동 변환하고 허용하지 않는 문자를 검증한다.

### 오른쪽: 상세코드

- 선택한 그룹 정보 표시
- 상세코드, 상세코드명, 정렬순서, 사용여부 표시
- 상세코드 등록·수정 팝업 제공
- 그룹을 선택하지 않은 경우 등록 버튼을 비활성화한다.

### 권한과 상태

- ADMIN은 등록·수정·상태 변경 버튼을 사용한다.
- STAFF는 쓰기 버튼을 숨기고 조회만 제공한다.
- 목록 조회 실패와 빈 결과를 구분해 안내한다.
- 그룹·상세코드 목록에 독립적인 페이징을 적용한다.

## 8. 대시보드 화면

- 별점과 별 모양 시각화를 제거한다.
- `챗봇 만족도 N.N%`를 표시한다.
- 긍정 평가 비율을 진행 막대 또는 원형 비율로 시각화한다.
- 설명을 `챗봇 사용자의 긍정 평가 비율을 나타냅니다.`로 변경한다.
- `likeRate=null`이면 `데이터 없음`을 표시한다.

## 9. 마이그레이션 및 배포

Aerich 마이그레이션 한 건에서 다음 순서로 수행한다.

1. `common_code_groups` 생성
2. `common_codes` 생성 및 FK·유일조건·인덱스 생성
3. `chat_sessions.is_like`, `chat_sessions.reason_code` 추가
4. `chat_sessions.score` 체크 제약 삭제
5. `chat_sessions.score` 컬럼 삭제

역방향 마이그레이션은 공통코드 테이블을 상세코드부터 삭제하고 `score`를 nullable INT와 체크 제약으로 복원한다. 기존 점수는 복원할 수 없으며 모두 `null`이다.

모델과 라우터 등록 후 Docker MySQL에서 `uv run aerich upgrade`를 실행한다. 적용 후 `SHOW CREATE TABLE`, `information_schema` 및 Aerich 이력으로 컬럼·인덱스·FK를 확인한다. DB 초기화나 기존 데이터 삭제는 수행하지 않는다.

`CHAT/P_REASON`, `CHAT/N_REASON` 그룹과 상세 사유는 자동 생성하지 않는다. 관리 화면에서 운영자가 등록하며, 사유 없이도 긍정·부정 평가가 가능하다.

## 10. 검증

- 모델 메타데이터 및 관계·인덱스 검증
- ADMIN 공통코드 등록·수정·상태 변경 검증
- STAFF 조회 허용과 쓰기 403 검증
- 중복 및 코드 형식 오류 검증
- 서비스용 API의 활성 그룹·활성 상세코드 필터 검증
- 채팅 세션 소유권, 평가 저장·수정·취소, 긍정/부정 사유 그룹 검증
- 대시보드 기간별 좋아요 비율과 미평가 제외 검증
- 공통코드 관리자 화면과 대시보드 렌더링 검증
- Ruff 포맷·린트와 관련 테스트 실행
- Docker MySQL 마이그레이션 및 실제 스키마 검증

## 11. 완료 기준

- 신규 공통코드 테이블과 채팅 평가 컬럼이 Docker MySQL에 적용되어 있다.
- 모델과 실제 MySQL 스키마가 일치한다.
- ADMIN은 대분류를 포함해 코드그룹·상세코드를 관리할 수 있다.
- STAFF는 공통코드를 조회할 수 있지만 변경할 수 없다.
- 채팅 평가는 선택적 사유와 함께 저장·수정·취소할 수 있다.
- 대시보드가 선택 기간의 긍정 평가 비율을 정확히 표시한다.
- 기존 별점 기반 코드와 화면 참조가 남아 있지 않다.
