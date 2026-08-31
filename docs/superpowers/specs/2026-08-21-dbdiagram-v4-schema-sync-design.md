# DBDiagram v4 Schema Sync Design

## Goal

`dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`의 2026-08-20 v4 스키마를 Tortoise ORM 모델과 Docker MySQL에 반영하면서 기존 데이터를 보존한다.

## Scope

- `user_settings`에 `terms_agreed_at`, `notify_consented_at` nullable datetime 필드를 추가한다.
- `NotifySettingKey` enum과 append-only `UserNotifyHistory` 모델/`user_notify_histories` 테이블을 추가한다.
- `ChatSession`에 필수 `user` FK를 추가하고 `care_episode` FK를 nullable로 변경한다.
- `CareAdviceCategory` enum과 `CareAdvice.category` 필수 필드를 추가한다.
- `Medication`에 `efficacy`, `administration`, `precautions` nullable 문자열 필드를 추가하고 `note`를 500자로 확장하며 `days` 상한 365를 적용한다.
- `FollowUpVisit.visit_at`을 필수 `visit_date`와 nullable `visit_time`으로 분리하고 nullable `source_ocr_job` FK를 추가한다. `department`와 `doctor_name`은 255자로 확장한다.
- `RecoveryGuideSource`와 `ChatMessageSource`가 참조하는 medication/care advice/follow-up visit FK 삭제 정책을 `RESTRICT`로 변경한다.
- 이미 반영된 `Alarm.follow_up_visit` 관계는 유지한다.

## Data Migration

### User settings and notification history

두 동의 시각 필드는 nullable로 추가하므로 기존 `user_settings` 행을 추정값으로 채우지 않는다. `user_notify_histories`는 빈 테이블로 생성하며 과거 토글 변경 이력을 역산하지 않는다.

### Chat sessions

`chat_sessions.user_id`를 nullable로 먼저 추가하고 기존 행은 `chat_sessions.care_episode_id -> care_episodes.user_id`로 백필한다. 백필 이후 null이 남아 있으면 마이그레이션을 실패시키고, 모두 채워진 경우에만 NOT NULL로 변경한다. 이후 `care_episode_id`를 nullable로 변경한다.

### Care advice category

`care_advices.category`는 nullable로 먼저 추가하고 기존 행을 `OTHER`로 백필한 다음 NOT NULL로 변경한다. 기존 데이터에 신뢰할 수 있는 의미 분류가 없으므로 임의의 의료 카테고리를 추정하지 않는다.

### Follow-up visit date/time split

`visit_date`, `visit_time`을 먼저 nullable로 추가한다. 기존 `visit_at`은 `DATE(visit_at)`과 `TIME(visit_at)`으로 보존하여 백필한다. `visit_date`를 NOT NULL로 변경한 뒤 기존 `visit_at` 컬럼과 인덱스를 제거한다. 날짜·시간·PK 복합 인덱스와 OCR 작업 SET NULL FK를 추가한다.

## Migration Ordering

현재 적용된 Aerich head는 `3_20260821043505_add_alarm_follow_up_visit.py`다. 다음 번호의 단일 v4 마이그레이션에 ERD 변경을 함께 담는다.

Aerich 자동 생성 결과를 기준으로 하되, 데이터 백필과 MySQL CHECK/FK 변경처럼 모델 상태만으로 안전하게 만들 수 없는 SQL은 마이그레이션 파일에서 명시적으로 보완한다.

## Model Design

- 새 enum은 기존 `StrEnum` 패턴을 따른다.
- `UserNotifyHistory.user`는 `User`에 대한 CASCADE FK이며 `(user, setting_key, created_at)` 및 `created_at` 인덱스를 가진다.
- `ChatSession.user`는 CASCADE FK이고 `care_episode`도 기존 CASCADE 정책을 유지하되 nullable이다.
- `FollowUpVisit.source_ocr_job`은 `OcrJob`에 대한 nullable SET NULL FK다.
- 출처 감사 이력을 보존하기 위해 `RecoveryGuideSource`와 `ChatMessageSource`의 환자 확정 데이터 FK는 `RESTRICT`를 사용한다.
- Tortoise validator는 ERD 범위 검증을 표현하고 MySQL CHECK는 마이그레이션에서 별도로 유지한다.

## Compatibility

`FollowUpVisit`을 직접 생성하는 테스트는 `visit_date`/`visit_time` API로 전환한다. 현재 알람 API는 follow-up visit ID만 사용하므로 외부 알람 요청/응답 계약은 변경하지 않는다. 새 스키마만 요청된 범위이므로 사용자 설정 저장 API나 채팅 API의 신규 업무 로직은 이번 작업에 추가하지 않는다.

## Verification

- 변경 전 모델 메타데이터 테스트를 추가하고 예상 실패를 확인한다.
- 모델을 수정하고 해당 테스트를 통과시킨다.
- Aerich 마이그레이션을 생성·검토한 뒤 Docker MySQL에 적용한다.
- 기존 `follow_up_visits.id=1`의 날짜, 시간 및 관계가 보존됐는지 확인한다.
- information_schema로 신규 컬럼, nullable, 길이, 인덱스, FK 삭제 정책과 CHECK를 검증한다.
- 전체 모델 테스트와 영향받는 알람 API/워커 테스트, Ruff 검사를 실행한다.
- Redis와 alarm-worker 상태가 정상인지 확인한다.

## Non-goals

- dbdiagram 페이지 자체를 수정하지 않는다.
- 신규 CRUD/API 업무 로직을 구현하지 않는다.
- 기존 테스트 데이터를 삭제하거나 DB를 재생성하지 않는다.
- Git 커밋을 생성하지 않는다.
