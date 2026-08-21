# Alarm Workflow API and Worker Design

## 목적

알람, Web Push 구독, 알람 이벤트, 백그라운드 작업을 업무 프로세스 단위로 제공한다. 사용자 API는 로그인 사용자의 리소스만 다루고, 백그라운드 작업 관리 API는 내부 API 키로 보호한다. 예약된 알람은 ARQ와 Redis를 통해 기기별 작업으로 분배하고 `pywebpush`로 발송한다.

## 범위

이 설계에 포함되는 기능은 다음과 같다.

- 알람 생성, 조회, 변경, 일시정지, 재개, 완료, 건너뛰기, 취소
- Web Push 구독 등록, 조회, 비활성화
- 알람 이벤트 조회와 서비스 워커 수신 확인
- 도래 알람 폴링과 기기별 발송 작업 생성
- Web Push 발송, 자동 재시도, 만료 구독 비활성화
- 백그라운드 작업 목록, 상세, 수동 재처리, 취소
- Docker Compose의 독립 `alarm-worker` 프로세스

다음 항목은 포함하지 않는다.

- 프론트엔드 Service Worker 구현
- 관리자 계정 또는 관리자 로그인 API
- OCR, LLM, CHAT, DATA_DELETION 실제 작업 핸들러
- 알람 또는 이벤트의 물리 삭제 API

## 기술 선택

- 큐와 스케줄러: ARQ + Redis
- Web Push: `pywebpush.webpush_async`
- 영속 저장소: 기존 Tortoise ORM + MySQL
- 반복 일정: `python-dateutil` RRULE
- API: FastAPI

ARQ는 현재 비동기 애플리케이션 구조와 Redis를 재사용하며, cron 작업과 지연 재시도를 제공한다. Celery보다 현재 프로젝트에 필요한 설정과 운영 요소가 적다.

## 컴포넌트 경계

### 사용자 알람 API

`app/apis/v1/alarm_router.py`는 JWT 인증을 요구하고 다음 업무 프로세스를 노출한다.

| Method | Path | 역할 |
| --- | --- | --- |
| POST | `/api/v1/alarms` | 알람과 최초 `SCHEDULED` 이벤트 생성 |
| GET | `/api/v1/alarms` | 사용자의 알람 목록 조회 |
| GET | `/api/v1/alarms/{alarm_id}` | 사용자의 알람 상세 조회 |
| PATCH | `/api/v1/alarms/{alarm_id}` | 예약 정보와 표시 정보 변경 |
| DELETE | `/api/v1/alarms/{alarm_id}` | `CANCELLED` 소프트 삭제 |
| POST | `/api/v1/alarms/{alarm_id}/actions` | `pause`, `resume`, `complete`, `skip` 업무 동작 실행 |
| GET | `/api/v1/alarms/{alarm_id}/events` | 알람 이벤트 이력 조회 |
| POST | `/api/v1/alarms/{alarm_id}/delivery-ack` | 기기 수신 확인과 `DELIVERED` 이벤트 생성 |
| GET | `/api/v1/alarms/push-public-key` | 브라우저 구독에 필요한 VAPID 공개 키 제공 |
| PUT | `/api/v1/alarms/push-subscriptions` | endpoint 기준 구독 등록 또는 갱신 |
| GET | `/api/v1/alarms/push-subscriptions` | 사용자의 구독 목록 조회 |
| DELETE | `/api/v1/alarms/push-subscriptions/{subscription_id}` | 구독 비활성화 |

정적 경로인 `push-public-key`, `push-subscriptions`는 `/{alarm_id}`보다 먼저 등록하여 경로 충돌을 방지한다.

### 내부 작업 API

`app/apis/v1/job_router.py`는 `X-Internal-API-Key` 헤더를 `INTERNAL_API_KEY`와 상수 시간 비교하고 다음 기능을 제공한다.

| Method | Path | 역할 |
| --- | --- | --- |
| GET | `/api/v1/internal/jobs` | 유형, 상태, 사용자, 요청 시각 조건으로 작업 조회 |
| GET | `/api/v1/internal/jobs/{job_id}` | 작업과 재시도 관계 상세 조회 |
| POST | `/api/v1/internal/jobs/{job_id}/retry` | 실패한 작업을 새 자식 작업으로 재처리 |
| POST | `/api/v1/internal/jobs/{job_id}/cancel` | 대기·재시도 대기 작업 취소 |

`background_jobs.user_id`는 작업 대상 추적용이며 내부 API의 접근 범위를 제한하지 않는다. 애플리케이션 내부 모듈은 Router 대신 공용 `BackgroundJobService`를 직접 사용한다.

### Service와 Repository

- `AlarmRepository`: Alarm, PushSubscription, AlarmEvent의 조회와 영속화
- `BackgroundJobRepository`: BackgroundJob 조회, 상태 변경, 멱등 생성
- `AlarmService`: 소유권, 입력 규칙, 상태 전환, 트랜잭션
- `BackgroundJobService`: 작업 생성, 취소, 자동·수동 재시도, Redis 등록
- `WebPushService`: VAPID 설정과 Web Push 전송 결과 분류
- `AlarmWorker`: 도래 알람 폴링, 작업 복구, 발송 실행

Router는 DTO 변환과 HTTP 상태 코드만 담당하며 데이터 접근과 업무 규칙을 포함하지 않는다.

## 입력 및 도메인 규칙

### 알람 생성과 변경

- `alarm_type=MEDICATION`이면 `meal_slot`이 필수다.
- 다른 알람 유형이면 `meal_slot`은 `null`이어야 한다.
- `(user_id, alarm_type, meal_slot)` 유일성 충돌은 HTTP 409로 응답한다.
- `care_episode_id`와 `source_guide_id`가 주어지면 로그인 사용자 소유 관계를 검증한다.
- IANA timezone을 검증하고 잘못된 값은 HTTP 422로 응답한다.
- `recurrence_rule`은 RRULE로 파싱 가능해야 하며 다음 발생 시각을 계산할 수 있어야 한다.
- 생성 시 `scheduled_at`과 `next_trigger_at`을 정하고 같은 트랜잭션에서 `SCHEDULED` 이벤트를 추가한다.
- 취소된 알람은 재개하거나 변경할 수 없다.
- 완료된 알람은 읽기만 가능하다.

### 상태 전환

허용 전환은 다음과 같다.

- `ACTIVE -> PAUSED`
- `PAUSED -> ACTIVE`
- `ACTIVE|PAUSED -> COMPLETED`
- `ACTIVE|PAUSED -> CANCELLED`

동일한 완료, 취소 요청은 현재 결과를 반환하는 멱등 동작으로 처리한다. 허용되지 않은 전환은 HTTP 409로 응답한다.

`SKIPPED`는 알람 자체의 상태를 종료하지 않는다. 반복 알람에서는 다음 회차를 계산하고, 단발 알람에서는 해당 회차를 소비 처리한다.

### 소프트 삭제

- 알람 DELETE는 `status=CANCELLED`, `cancelled_at`, `updated_at`을 설정한다.
- PushSubscription DELETE는 `is_active=false`로 설정한다.
- AlarmEvent와 BackgroundJob은 API로 물리 삭제하지 않는다.

## 스케줄링과 발송 흐름

### 도래 알람 조회

ARQ cron은 짧은 주기로 다음 조건을 만족하는 알람을 조회한다.

- `status=ACTIVE`
- `next_trigger_at <= now`
- `last_triggered_at IS NULL OR last_triggered_at < next_trigger_at`

여러 Worker의 중복 처리를 막기 위해 트랜잭션과 행 잠금을 사용한다. 한 회차를 처리하면 `last_triggered_at`을 회차 시각으로 갱신한다.

- 반복 알람: RRULE로 다음 `next_trigger_at` 계산
- 단발 알람: `next_trigger_at`은 유지하고 `last_triggered_at == next_trigger_at` 조건으로 재조회에서 제외

활성 구독이 없으면 `FAILED/NO_ACTIVE_SUBSCRIPTION` 이벤트를 남기고 회차를 소비한다.

### 기기별 작업 생성

활성 PushSubscription마다 BackgroundJob을 한 개 만든다.

- `job_type=ALARM`
- `status=QUEUED`
- `user_id=alarm.user_id`
- `idempotency_key=alarm:{alarm_id}:{subscription_id}:{trigger_at}`
- `max_retry_count`는 설정값 사용
- 발송 결과 이벤트가 생성되기 전에는 `reference_table`, `reference_id`가 `null`

DB 생성 후 Redis enqueue가 실패할 수 있으므로 복구 cron이 오래된 `QUEUED`와 도래한 `RETRY_WAITING` 작업을 찾아 같은 ARQ job id로 다시 등록한다.

### Web Push payload

발송 직전에 해당 알람과 활성 구독을 다시 조회한다. 취소된 작업, 비활성 구독, 취소·완료된 알람은 전송하지 않는다.

payload에는 최소 다음 값을 포함한다.

- alarm id
- title
- body
- click URL
- alarm type
- meal slot
- scheduled/trigger time

`alarm_events.payload`에는 실제 발송한 title, body, click URL 스냅샷을 저장한다. MEDICATION 알람의 최종 문구는 발송 시점의 활성 medication과 medication slot을 조회하여 구성한다.

## 성공, 오류, 재시도

### 성공

Push 서버가 요청을 접수하면 다음을 같은 DB 트랜잭션에서 처리한다.

- 기기별 `SENT` AlarmEvent 생성
- PushSubscription `last_used_at` 갱신
- BackgroundJob을 `COMPLETED`로 전환
- `reference_table=alarm_events`, `reference_id=sent_event.id`
- `completed_at`, `duration_ms` 기록

`SENT`는 기기 표시를 보장하지 않는다. 실제 브라우저 Service Worker가 `delivery-ack` API를 호출한 경우에만 `DELIVERED` 이벤트를 추가한다.

### 영구 실패

HTTP 404와 410은 만료 또는 폐기된 구독으로 분류한다.

- 구독 `is_active=false`
- `FAILED` AlarmEvent 생성
- BackgroundJob `FAILED`
- 이벤트를 작업 reference로 연결

그 밖의 재시도 불가능한 4xx도 즉시 실패 처리한다.

### 일시 실패

네트워크 오류, timeout, HTTP 429, 5xx만 자동 재시도한다.

- `retry_count < max_retry_count`: `RETRY_WAITING`으로 전환하고 지수 백오프로 재등록
- 최대 횟수 초과: `FAILED` AlarmEvent와 최종 `FAILED` 작업 상태 기록

자동 재시도는 같은 BackgroundJob 행을 사용한다. 내부 API의 수동 retry는 `FAILED` 작업만 허용한다. `parent_job_id`로 원본을 가리키는 새 행과 새 idempotency key를 만들며, 원본 실패 이벤트에서 alarm과 subscription을 복원한다. 취소된 작업은 결과 이벤트가 없어 입력을 안전하게 복원할 수 없으므로 재처리하지 않는다.

### 취소

`QUEUED`와 `RETRY_WAITING`만 취소할 수 있다. `PROCESSING`은 HTTP 409로 거부한다. Worker는 실행 직전에 DB 상태를 다시 읽어 취소된 작업을 발송하지 않는다.

## 동시성과 멱등성

- Alarm 생성과 SCHEDULED 이벤트는 하나의 트랜잭션이다.
- due alarm 소비는 행 잠금으로 보호한다.
- 기기별 idempotency key는 같은 회차의 중복 작업 생성을 막는다.
- ARQ job id에도 같은 idempotency key를 사용한다.
- delivery acknowledgement는 alarm, subscription, event type 조합의 중복 요청을 멱등 처리한다.
- Worker 상태 변경은 예상 이전 상태를 조건으로 갱신하여 중복 실행의 부작용을 막는다.

## 보안

- 모든 사용자 알람 API는 JWT를 요구한다.
- alarm, care episode, recovery guide, push subscription의 사용자 소유권을 검증한다.
- 내부 작업 API는 `X-Internal-API-Key`를 요구한다.
- 내부 API 키와 VAPID private key는 응답과 로그에 노출하지 않는다.
- `error_message`와 이벤트 payload에는 의료 원문이나 Push 인증 키를 저장하지 않는다.
- VAPID public key만 사용자 API로 제공한다.

## 설정

Config와 환경변수 예시에 다음 값을 추가한다.

- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`
- `INTERNAL_API_KEY`
- `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`
- `ALARM_POLL_SECONDS`
- `ALARM_MAX_RETRY_COUNT`
- `ALARM_RETRY_BASE_SECONDS`
- `ALARM_PUSH_TTL_SECONDS`
- `ALARM_CLICK_URL`

실제 secret 값은 저장소에 추가하지 않는다.

## Docker 실행 모델

`alarm-worker`는 FastAPI와 같은 앱 이미지를 재사용하고 실행 명령만 ARQ Worker로 바꾼다.

```text
fastapi       -> uvicorn app.main:app
alarm-worker  -> arq app.workers.alarm_worker.WorkerSettings
ai-worker     -> 기존 AI 전용 프로세스
```

Alarm Worker는 MySQL과 Redis가 healthy인 이후 시작한다. AI Worker의 모델 로딩, 긴 추론, 재시작이 시간 민감한 알람 발송에 영향을 주지 않도록 실행 프로세스를 분리한다.

## 변경 파일

주요 신규 파일:

- `app/apis/v1/alarm_router.py`
- `app/apis/v1/job_router.py`
- `app/dtos/alarms.py`
- `app/dtos/background_jobs.py`
- `app/repositories/alarm_repository.py`
- `app/repositories/background_job_repository.py`
- `app/services/alarms.py`
- `app/services/background_jobs.py`
- `app/services/web_push.py`
- `app/workers/__init__.py`
- `app/workers/alarm_worker.py`
- `app/dependencies/internal_auth.py`

주요 수정 파일:

- `app/apis/v1/__init__.py`
- `app/core/config.py`
- `pyproject.toml`
- `uv.lock`
- `docker-compose.yml`
- `infra/docker/docker-compose.prod.yml`
- 환경변수 예시 파일

모델과 현재 DB 스키마가 dbdiagram 정의를 충족하는 한 마이그레이션은 만들지 않는다. 구현 중 모델 차이가 발견되면 별도 Aerich 마이그레이션을 생성한다.

## 테스트 전략

### API 테스트

- 인증 없는 사용자 API 거부
- 다른 사용자의 알람, 이벤트, 구독 접근 거부
- 알람 생성과 SCHEDULED 이벤트의 원자성
- 알람 유형과 meal slot 검증
- 목록 필터와 페이지네이션
- 허용 및 금지 상태 전환
- 알람 취소와 구독 비활성화
- delivery acknowledgement 멱등성
- 내부 API 키 누락 및 불일치 거부
- 내부 작업 목록, 상세, retry, cancel

### Service와 Worker 테스트

- 스케줄러의 due 조건과 중복 소비 방지
- 반복 및 단발 알람 회차 갱신
- 구독별 작업 fan-out과 idempotency key
- Web Push 성공과 SENT 이벤트 연결
- 404/410 구독 비활성화
- 네트워크, 429, 5xx 자동 재시도
- 최대 재시도 초과와 FAILED 이벤트
- 취소 작업 발송 방지
- Redis enqueue 실패 후 복구
- 수동 재처리의 parent job 연결

Web Push 네트워크 호출과 Redis 큐는 테스트에서 대역으로 교체하고, 데이터베이스 상태와 호출 계약을 검증한다.

### 실행 검증

- 대상 pytest 실행
- 전체 pytest 실행
- Ruff 검사
- `docker compose config --quiet`
- Alarm Worker import 및 startup 검증

## 완료 기준

- 명시된 API가 OpenAPI에 등록된다.
- 사용자 리소스 소유권과 내부 API 키가 적용된다.
- Alarm 생성부터 SCHEDULED 이벤트 기록까지 동작한다.
- due alarm이 구독별 BackgroundJob으로 변환된다.
- 성공, 영구 실패, 일시 실패와 재시도가 정의된 상태로 기록된다.
- 소프트 삭제된 리소스가 다시 처리되지 않는다.
- Worker가 FastAPI 및 AI Worker와 독립 프로세스로 실행된다.
- 설정, 정적 검사, 대상 테스트와 전체 테스트 결과가 보고된다.
