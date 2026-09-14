# 이메일 Background Tasks 전환 설계

## 목적

별도 ARQ `email-worker` 컨테이너를 제거하고 이메일 발송을 FastAPI 프로세스의 응답 후 Background Task로 처리한다. 기존 `background_jobs` 작업 이력, 자동 재시도, 인증 만료 취소와 비밀번호 후처리는 유지하며 FastAPI 재시작 뒤 미완료 이메일 작업도 복구한다.

## 범위

### 포함

- 관리자 임시 비밀번호, 회원가입 인증번호, 사용자 비밀번호 재설정, 복약 보고서 이메일 전환
- `background_jobs`를 이용한 이메일 작업 상태 및 암호화 payload 영속화
- FastAPI `BackgroundTasks`를 통한 요청 후 실행
- 지수 백오프 자동 재시도와 재시도 예정 시각 기록
- FastAPI 시작 시 미완료 이메일 작업 복구
- 개발·운영 Docker Compose의 `email-worker` 서비스 제거
- 이메일 전용 ARQ 큐 설정과 Worker 진입점 제거

### 제외

- ALARM·OCR·AI Worker 구조 변경
- SMTP 공급자 변경
- 이메일 작업의 관리자 수동 재시도 기능 추가
- 정확히 한 번(exactly-once) SMTP 전달 보장

## 선택한 구조

### 작업 저장 모델

`background_jobs`에 다음 nullable 컬럼을 추가한다.

- `encrypted_payload TEXT`: `EMAIL_PAYLOAD_ENCRYPTION_KEY`로 암호화한 이메일 작업 payload
- `next_attempt_at DATETIME`: 재시도 가능한 최초 시각
- `lease_expires_at DATETIME`: 실행 중인 작업의 선점 임대 만료 시각

세 컬럼은 EMAIL 작업에서만 사용한다. 임시 비밀번호, 인증번호, 수신 주소와 보고서 내용은 평문으로 저장하지 않는다. 작업이 `COMPLETED`, `FAILED`, `CANCELLED` 중 하나로 끝나면 `encrypted_payload`, `next_attempt_at`, `lease_expires_at`을 `NULL`로 지워 민감정보 보존 시간을 최소화한다.

기존 `EMAIL_MAX_RETRY_COUNT`, `EMAIL_RETRY_BASE_SECONDS`, `EMAIL_PAYLOAD_ENCRYPTION_KEY` 설정은 유지한다. Redis 큐 전용인 `EMAIL_QUEUE_NAME`은 제거한다.

### 요청 후 작업 등록

각 이메일 API 라우트는 FastAPI `BackgroundTasks`를 주입받아 도메인 서비스에 전달한다. `EmailJobService`는 다음 순서로 처리한다.

1. EMAIL/QUEUED `background_jobs` 행을 생성한다.
2. 이메일 payload를 암호화해 `encrypted_payload`에 저장한다.
3. `background_tasks.add_task()`로 작업 ID의 경량 실행 등록을 예약한다.
4. 기존 API 응답의 `emailJobId`, `emailJobStatus` 계약을 유지한다.

암호화나 작업 예약 준비가 실패하면 작업을 `FAILED`로 바꾸고 민감 payload를 제거한다. SMTP 발송은 API 응답을 만들기 전에 실행하지 않는다. 현재 `ApiTimeoutMiddleware`는 응답 이후 Starlette Background Task까지 기본 3초 제한으로 감싸므로, Background Task 콜백은 SMTP를 직접 기다리지 않고 lifespan manager가 추적하는 `asyncio.Task`를 생성한 뒤 즉시 반환한다. 실제 SMTP·재시도 대기는 manager 소유 task에서 수행한다.

### 실행기와 상태 전이

신규 이메일 Background Task 실행기는 요청 경로와 시작 시 복구 경로가 함께 사용하는 단일 서비스다.

1. DB 조건부 갱신으로 `QUEUED`, due 상태의 `RETRY_WAITING`, 또는 임대가 만료된 `PROCESSING` 작업을 `PROCESSING`으로 선점하고 SMTP 제한 시간보다 긴 `lease_expires_at`을 기록한다.
2. 암호문을 복호화하고 기존 템플릿 렌더러와 최신 SMTP 설정을 사용해 발송한다.
3. 발송 성공 후 기존 비밀번호 변경 후처리를 적용하고 `COMPLETED`로 종료한다.
4. 영구 오류는 `FAILED`, 발송 대상 무효 또는 인증 만료는 `CANCELLED`로 종료한다.
5. 일시 오류는 retry count를 증가시키고 `RETRY_WAITING`과 `next_attempt_at`을 저장한다.
6. 실행 코루틴은 예정 시각까지 비동기로 대기한 뒤 같은 작업을 다시 선점한다. 최대 재시도 횟수를 초과하면 `FAILED`로 종료한다.

프로세스 내 작업 ID 집합으로 같은 작업의 중복 예약을 줄이고, 최종 중복 방지는 DB 조건부 선점으로 수행한다. 다중 FastAPI 프로세스가 같은 작업을 발견해도 한 프로세스만 `PROCESSING` 전이에 성공한다. 임대가 만료된 `PROCESSING` 작업만 다른 프로세스가 다시 선점할 수 있다.

### 재시작 복구

FastAPI lifespan 시작 시 EMAIL 작업을 다음과 같이 복구한다.

- `QUEUED`: 즉시 실행 예약
- `RETRY_WAITING`: `next_attempt_at` 이후 실행 예약
- 이전 프로세스가 남긴 `PROCESSING`: 모두 복구 예약하되, `lease_expires_at`이 지난 뒤에만 다시 선점해 실행

복구 예약은 요청 객체의 `BackgroundTasks`가 존재하지 않으므로 애플리케이션 lifespan manager가 직접 추적하는 `asyncio.Task`로 실행한다. 미래 시각의 `RETRY_WAITING`과 아직 유효한 임대의 `PROCESSING`도 예약 대상에 포함하고, 실행 코루틴이 각각 `next_attempt_at`과 `lease_expires_at`까지 비동기로 기다린다. 요청의 Background Task도 같은 manager에 실행을 위임하므로 동일한 실행기·선점 규칙과 종료 처리를 사용한다. 종료 시 manager 소유 작업을 취소하고 DB의 비종료 상태를 남겨 다음 시작에서 복구한다.

SMTP 서버가 메시지를 수락한 직후 프로세스가 종료되면 DB 완료 기록 전에 임대가 만료되어 같은 작업이 복구되고 메일이 중복 발송될 수 있다. 외부 SMTP가 idempotency key를 지원하지 않으므로 이 구조의 전달 보장은 at-least-once이며, 이 경계는 기존 ARQ 구조에도 존재한다.

### 기존 이메일 규칙 유지

- 회원가입 인증번호는 발송 전에 인증 행의 존재, 미소비, 만료 여부를 확인한다.
- 다음 재시도 시각이 인증 만료 이후면 `EMAIL_VERIFICATION_EXPIRED`로 취소한다.
- 사용자 비밀번호 재설정과 복약 보고서는 대상 사용자의 유효성을 발송 직전에 확인한다.
- SMTP 설정은 작업 실행 때마다 DB 우선, `.env` fallback으로 다시 읽는다.
- 오류 메시지와 로그에 암호문 복호화 결과, 임시 비밀번호, 인증번호, SMTP 비밀번호를 기록하지 않는다.

## 코드 구성

- `app/services/email_jobs.py`: 작업 생성, payload 암호화 저장, FastAPI Background Task 등록
- `app/services/email_background_tasks.py`: 선점, 복호화, 렌더링, SMTP 발송, 재시도, 종료 상태 처리
- `app/main.py` 또는 lifespan 모듈: 미완료 EMAIL 작업 복구와 종료 시 task 정리
- 이메일을 생성하는 라우트·서비스: `BackgroundTasks` 전달
- `app/models/background_jobs.py`: payload, 재시도 예정 시각과 실행 임대 필드
- Aerich migration: nullable 컬럼과 EMAIL 복구 조회용 인덱스 반영

기존 `app/workers/email_worker.py`는 제거한다. 렌더러, SMTP sender, payload codec은 실행 서비스에서 그대로 재사용한다.

## Docker 및 설정

다음 Compose 파일에서 `email-worker` 서비스를 제거한다.

- `docker-compose.yml`
- `infra/docker/docker-compose.prod.yml`

FastAPI는 이미 DB와 Redis에 연결되지만 EMAIL은 더 이상 Redis를 사용하지 않는다. Redis는 ALARM·OCR 등 다른 기능 때문에 유지한다. FastAPI 환경에는 SMTP 설정, retry 설정, payload 암호화 키를 유지한다.

환경 예제와 설정에서는 `EMAIL_QUEUE_NAME`만 제거한다. 기존 `EMAIL_PAYLOAD_ENCRYPTION_KEY`는 DB payload 암호화에 계속 사용한다. 설정 오류 문구의 `email-worker` 표현은 일반적인 `이메일 발송` 표현으로 변경한다.

## 마이그레이션과 호환성

Aerich upgrade로 신규 nullable 컬럼을 추가한다. 배포 순서는 새 FastAPI 이미지 배포 전에 migration 적용이다. 기존 EMAIL 작업에는 payload가 없으므로 복구할 수 없다. 배포 시 남아 있는 비종료 레거시 EMAIL 작업은 `FAILED/EMAIL_PAYLOAD_UNAVAILABLE`로 종료하고, 이미 종료된 작업 이력은 변경하지 않는다.

다운그레이드는 신규 컬럼과 인덱스만 제거한다. 데이터가 있는 컬럼을 제거하는 일반적인 Aerich downgrade 제약을 따른다.

## 테스트 전략

- 작업 생성: DB에 암호화 payload가 저장되고 평문 민감정보가 남지 않는지 확인
- BackgroundTasks 등록: API 응답 전에 SMTP가 호출되지 않고 응답 후 실행 가능한 작업이 등록되는지 확인
- 실행기: 성공, 영구 실패, 일시 실패, 최대 재시도, 인증 만료 취소, 비밀번호 후처리
- 재시도: `RETRY_WAITING`과 `next_attempt_at` 기록 및 due 이전 선점 방지
- 복구: QUEUED·RETRY_WAITING·임대가 만료된 PROCESSING 복구, 유효한 임대와 종료 상태 제외, payload 없는 레거시 실패 처리
- 동시성: 동일 작업을 동시에 실행해도 DB 선점은 한 번만 성공
- API 회귀: 관리자·회원가입·비밀번호 재설정·복약 보고서 이메일 응답 계약 유지
- Compose: 개발·운영 파일에 `email-worker`가 없고 FastAPI에 필요한 이메일 설정이 유지되는지 확인
- 정적 검사: 이메일 전용 ARQ 큐와 Worker 참조가 운영 코드·환경 예제에 남지 않는지 확인

전체 테스트 대신 변경과 직접 관련된 이메일·인증·관리자·Compose 테스트만 실행한다.

## 완료 조건

- Docker Compose 실행 목록에 `email-worker`가 없다.
- 이메일 API가 SMTP 완료를 기다리지 않고 기존 작업 ID와 상태를 반환한다.
- 모든 이메일 종류가 FastAPI Background Task에서 발송된다.
- 성공·실패·재시도 대기·취소가 `background_jobs`에 기존 의미대로 기록된다.
- FastAPI 재시작 후 미완료 EMAIL 작업이 암호화 payload로 복구된다.
- 종료된 작업에는 민감 payload가 남지 않는다.
- Redis 이메일 큐와 `email-worker` 실행 코드가 제거된다.
