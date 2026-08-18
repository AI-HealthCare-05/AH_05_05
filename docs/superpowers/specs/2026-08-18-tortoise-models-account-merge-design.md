# Tortoise 전체 도메인 모델 및 계정 테이블 통합 설계

## 목적

dbdiagram의 데이터 모델을 프로젝트의 Tortoise ORM 모델로 구현한다. 기존 `accounts`, `user`, `admin` 3개 테이블은 `accounts` 없이 `user`, `admin` 2개 테이블로 통합하고, 새 데이터베이스를 위한 Aerich 초기 마이그레이션을 생성한다.

## 범위

- dbdiagram에 정의된 도메인 테이블을 Tortoise ORM 모델로 구현한다.
- `accounts` 테이블과 `account_type` enum을 제거한다.
- 계정 공통 필드를 `user`, `admin`에 직접 배치한다.
- 모델을 Tortoise 설정에 등록한다.
- 기존 사용자 인증 흐름을 새 `User` 구조에 맞게 최소 조정한다.
- 새 데이터베이스 기준 Aerich 초기 마이그레이션을 생성한다.
- 온라인 dbdiagram 원본에 같은 구조를 반영한다.
- 관리자 Repository, 관리자 API, 관리자 로그인은 구현하지 않는다.

## 계정 구조

### User

`user` 테이블은 다음 필드를 가진다.

- `id`: bigint PK, auto increment
- `email`: varchar(255), not null, unique
- `hashed_password`: varchar(255), not null
- `status`: `account_status`, not null, default `PENDING`
- `name`: varchar(100), not null
- `phone`: text, nullable
- `is_alarm`: boolean, not null, default true
- `created_at`: datetime, not null, 생성 시각 자동 기록
- `updated_at`: datetime, nullable, 수정 시각 자동 기록

기존 모델의 `gender`, `birthday`, `last_login`, `is_active`, `is_admin`은 제거한다.

### Admin

`admin` 테이블은 다음 필드를 가진다.

- `id`: bigint PK, auto increment
- `email`: varchar(255), not null, unique
- `hashed_password`: varchar(255), not null
- `status`: `account_status`, not null, default `PENDING`
- `name`: varchar(100), not null
- `role`: `admin_role`, not null, default `STAFF`
- `created_by_admin_id`: nullable self FK
- `approved_at`: datetime, nullable
- `created_at`: datetime, not null, 생성 시각 자동 기록
- `updated_at`: datetime, nullable, 수정 시각 자동 기록

`created_by_admin_id`는 최초 관리자 생성을 위해 null을 허용한다. 생성한 관리자가 삭제되면 참조는 `SET NULL`로 처리한다.

사용자와 관리자는 서로 다른 인증 영역이므로 이메일 unique 제약은 각 테이블 내부에서만 적용한다.

## 도메인 모델

계정 통합 후 구현 대상은 총 19개 테이블이다.

1. `user`
2. `admin`
3. `care_episodes`
4. `ocr_jobs`
5. `ocr_extracted_fields`
6. `recovery_guides`
7. `recovery_guide_sources`
8. `chat_sessions`
9. `chat_messages`
10. `chat_message_sources`
11. `push_subscriptions`
12. `alarms`
13. `alarm_events`
14. `background_jobs`
15. `medications`
16. `medication_times`
17. `care_advices`
18. `follow_up_visits`
19. `user_consents`

모델은 계정, 케어, OCR, 회복 가이드, 채팅, 알람, 백그라운드 작업, 복약, 동의 도메인별 파일로 분리한다. enum은 순환 import를 피할 수 있는 공용 모듈에 둔다. 각 모델 모듈은 `TORTOISE_APP_MODELS`에 명시적으로 등록한다.

## 관계 및 삭제 정책

- 사용자 소유 데이터는 `user.id`를 참조한다.
- 케어 하위의 OCR, 가이드, 채팅, 복약, 권고, 일정은 dbdiagram의 cascade 정책을 유지한다.
- OCR 원본을 추적하는 nullable FK는 원본 삭제 시 확정 데이터가 남도록 `SET NULL`을 사용한다.
- 가이드와 채팅 메시지 출처의 nullable OCR 필드 참조도 `SET NULL`을 사용한다.
- `background_jobs.reference_table/reference_id`는 의도된 polymorphic 참조이므로 FK를 만들지 않는다.
- `background_jobs.parent_job_id`와 `chat_messages.reply_to_message_id`는 nullable self FK로 구현한다.
- 역참조 이름은 도메인 의미가 드러나고 서로 충돌하지 않도록 명시한다.

## 제약과 인덱스

- DBML의 단일·복합 unique와 index를 Tortoise `Meta.indexes`, `unique_together` 및 필드 옵션으로 옮긴다.
- 숫자 범위처럼 필드 단위로 표현 가능한 조건은 Tortoise validator를 사용한다.
- 여러 컬럼을 함께 비교하는 날짜 조건처럼 Tortoise 0.25.3 모델 선언만으로 안전하게 표현하기 어려운 check는 Aerich 마이그레이션 SQL에 포함한다.
- MySQL 예약어 가능성이 있는 `user` 테이블은 ORM과 마이그레이션에서 식별자 quoting이 유지되는지 검증한다.

## 기존 사용자 기능 호환

현재 회원가입과 사용자 수정 코드가 제거 대상 필드를 참조하므로 다음만 조정한다.

- 회원가입 요청에서 `gender`, `birth_date`를 제거한다.
- 사용자 수정 요청에서 `gender`, `birthday`를 제거한다.
- 회원 생성 시 제거된 필드를 전달하지 않는다.
- 로그인 활성 여부는 `User.status == ACTIVE`로 판단한다.
- `last_login` 갱신을 제거한다.
- JWT의 사용자 식별자는 기존처럼 `user.id`를 사용한다.

관리자용 Repository, 서비스, DTO, 라우터, JWT 흐름은 추가하지 않는다.

## Aerich 마이그레이션

기존 데이터 보존은 요구하지 않는다. 기존 초기 마이그레이션을 새 모델 기준의 초기 마이그레이션으로 교체한다.

1. 모델 및 Tortoise 등록을 완료한다.
2. 개발용 MySQL의 테스트/신규 데이터베이스를 준비한다.
3. 기존 마이그레이션 이력을 제거한 새 상태에서 Aerich 초기 마이그레이션을 생성한다.
4. 초기 마이그레이션을 빈 DB에 적용한다.
5. 생성된 19개 테이블, FK, index, unique, check를 검사한다.

마이그레이션 생성은 로컬 개발 DB에만 수행하며 기존 운영 데이터에 적용하지 않는다.

## dbdiagram 반영

온라인 원본에서 다음을 수정한다.

- `accounts` 테이블 삭제
- `account_type` enum 삭제
- `user`, `admin`에 계정 필드 병합
- `user.account_id`, `admin.account_id` 삭제
- 두 account FK 삭제
- `admin.created_by_account_id`를 `created_by_admin_id`로 변경
- `admin.created_by_admin_id > admin.id [delete: set null]` 자기참조 추가
- `user`에서 `gender`, `birthday`, `last_login`, `is_active`, `is_admin`이 존재하지 않도록 유지
- 나머지 사용자 참조가 모두 `user.id`를 가리키는지 확인

온라인 편집은 저장 직전에 사용자 확인을 받은 후 실행한다.

## 검증

- 모든 모델 모듈 import 및 Tortoise 초기화 테스트
- enum 기본값과 필드 nullability 검사
- FK 대상, 역참조 이름 및 삭제 정책 검사
- table name, unique constraint, index 메타데이터 검사
- 새 회원가입, 로그인, 내 정보 조회·수정 테스트 수정 및 실행
- Aerich 초기 migration을 빈 MySQL DB에 적용한 뒤 실제 스키마 검사
- 전체 Python 테스트, Ruff 및 Mypy 실행
- dbdiagram의 테이블 수와 참조 관계를 최종 DBML과 대조

## 비범위

- 기존 데이터 이전 또는 보존
- 관리자 Repository/API/로그인
- 정적 관리자 화면의 백엔드 연동
- background job polymorphic 참조를 실제 FK로 변경
- 모델 생성과 무관한 UI 또는 서비스 리팩터링
