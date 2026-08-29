# 전용 Email Worker 설계

## 목적

관리자 생성과 관리자 임시 비밀번호 재설정 과정의 이메일 발송을 FastAPI 요청에서 분리한다. FastAPI는 이메일 작업을 `background_jobs`와 Redis/ARQ에 등록하고 즉시 응답하며, 별도 `email-worker`가 SMTP 발송과 자동 재시도를 담당한다.

이 변경은 다음 목표를 가진다.

- SMTP 지연이나 장애가 API의 3초 응답 제한을 방해하지 않게 한다.
- 이메일 작업 상태를 기존 작업 모니터링 화면과 내부 작업 API에서 추적한다.
- 임시 비밀번호를 DB나 로그에 평문으로 저장하지 않는다.
- Web Push, OCR, AI 작업과 이메일 처리 자원을 분리한다.

## 범위

### 포함

- `BackgroundJobType.EMAIL` 추가
- 이메일 전용 ARQ 큐와 `email-worker` Docker 서비스 추가
- 관리자 생성 및 비밀번호 재설정 이메일을 비동기 작업으로 전환
- SMTP 발송 성공, 자동 재시도, 최종 실패 상태 관리
- 이메일 작업 인자의 Fernet 암호화
- 관리자 임시 비밀번호 안내용 HTML 이메일 템플릿과 평문 대체 본문 제공
- 관리자 작업 모니터링의 `EMAIL` 유형 지원
- 기존 동기 이메일 발송 경로와 개발용 콘솔 이메일 백엔드 제거

### 제외

- `EMAIL` 작업의 내부 작업 API 수동 재시도
- 별도 `email_outbox` 테이블
- `background_jobs`에 이메일 본문 또는 범용 payload 컬럼 추가
- 사용자용 마케팅·알림 이메일 기능

## 구성 요소

### 작업 유형과 DB 메타데이터

애플리케이션 enum에 `BackgroundJobType.EMAIL`을 추가한다. 현재 MySQL의 `background_jobs.job_type`은 네이티브 ENUM이 아니라 `VARCHAR(13)`이며 `EMAIL`은 기존 길이 안에 들어가므로 컬럼 크기 변경은 필요하지 않다.

다만 DB 컬럼 comment에 작업 유형 목록이 기록되어 있으므로 Aerich 마이그레이션에서 comment와 모델 상태를 `EMAIL` 포함 목록으로 갱신한다. 테이블이나 신규 payload 컬럼은 추가하지 않는다.

### Email 작업 생산자

FastAPI 프로세스에서 사용하는 서비스다. 관리자 생성 또는 임시 비밀번호 재설정이 DB에 반영된 뒤 다음 순서로 동작한다.

1. 관리자 임시 비밀번호 안내에 필요한 수신 이메일, 수신자명(`recipient_name`), 임시 비밀번호와 template ID를 하나의 JSON payload로 직렬화한다.
2. `EMAIL_PAYLOAD_ENCRYPTION_KEY`로 payload를 Fernet 암호화한다.
3. `background_jobs`에 `EMAIL/QUEUED` 작업을 생성한다.
4. 이메일 전용 ARQ 큐 `arq:email`에 작업 ID와 암호문을 등록한다.

`background_jobs`에는 다음 참조 정보만 저장한다.

- `job_type = EMAIL`
- `status = QUEUED`
- `reference_table = admin`
- `reference_id = 대상 관리자 ID`
- `max_retry_count = EMAIL_MAX_RETRY_COUNT`

수신 이메일, 수신자명과 임시 비밀번호는 `background_jobs`에 저장하지 않는다.

Redis 등록에 실패하면 생성된 작업을 즉시 `FAILED`로 바꾸고 `EMAIL_QUEUE_UNAVAILABLE` 오류를 기록한다. 관리자 계정 생성 또는 변경된 비밀번호는 기존 정책과 같이 롤백하지 않는다. 호출자는 응답의 이메일 작업 상태로 실패를 확인하고 비밀번호 재설정 API를 다시 호출할 수 있다.

### Email Worker

`app.workers.email_worker.WorkerSettings`를 실행하는 별도 Docker Compose 서비스다. 전용 큐 `arq:email`만 소비하여 다른 ARQ 워커가 이메일 작업을 가져가지 않게 한다.

Worker는 다음 순서로 처리한다.

1. `background_jobs` 행을 원자적으로 `QUEUED` 또는 `RETRY_WAITING`에서 `PROCESSING`으로 선점한다.
2. ARQ 인자의 암호문을 복호화하고 이메일 payload를 검증한다.
3. template ID에 해당하는 HTML 템플릿과 평문 대체 본문을 렌더링한다.
4. SMTP STARTTLS 연결로 multipart 이메일을 발송한다.
5. 성공하면 작업을 `COMPLETED`로 변경한다.
6. 일시 오류면 `retry_count`를 증가시키고 `RETRY_WAITING`으로 변경한 뒤 ARQ `Retry`를 발생시킨다.
7. 영구 오류 또는 최대 재시도 횟수 초과 시 `FAILED`로 변경한다.

재시도 지연은 `EMAIL_RETRY_BASE_SECONDS * 2^(retry_count - 1)`의 지수 백오프를 사용한다.

### SMTP 오류 분류

- 재시도 가능: 연결 오류, 타임아웃, SMTP 4xx 응답
- 영구 실패: 인증 오류, 수신자 거부, SMTP 5xx 응답, payload 복호화·검증 실패

오류 로그와 `background_jobs.error_message`에는 이메일 본문, 비밀번호, SMTP 인증정보를 포함하지 않는다. 오류 코드는 분류 가능한 상수로 저장한다.

### HTML 이메일 템플릿

관리자 임시 비밀번호 이메일은 `app/static/templates/emails/admin_temporary_password.html`의 Jinja2 템플릿을 사용한다. 템플릿 렌더링은 `email-worker`에서 수행하며 Jinja2 autoescape를 활성화한다.

표시 문구는 다음과 같다.

```text
{수신자명} 님 안녕하세요.

임시비밀번호 : {임시비밀번호}

시스템 로그인 후 비밀번호를 변경해 주세요.

감사합니다.
```

HTML은 이메일 클라이언트 호환성을 위해 외부 JavaScript나 외부 CSS 없이 단순한 테이블 레이아웃과 inline style만 사용한다. 임시 비밀번호는 복사할 수 있는 독립된 강조 영역에 표시한다.

HTML을 표시하지 못하는 이메일 클라이언트를 위해 동일한 문구의 `text/plain` 본문을 함께 넣고, HTML을 `text/html` 대체 본문으로 추가한 multipart 메시지를 발송한다.

## 데이터 흐름

```text
POST 관리자 생성/비밀번호 재설정
  -> 관리자 DB 변경 커밋
  -> 수신자명·임시 비밀번호·template ID payload 생성
  -> Fernet 암호화
  -> background_jobs(EMAIL, QUEUED) 생성
  -> Redis arq:email 등록
  -> API가 emailJobId/emailJobStatus 응답

email-worker
  -> EMAIL 작업 선점(PROCESSING)
  -> payload 복호화
  -> HTML·평문 본문 렌더링
  -> SMTP 발송
     -> 성공: COMPLETED
     -> 일시 오류: RETRY_WAITING -> ARQ 자동 재시도
     -> 영구 오류/재시도 초과: FAILED
```

## API 계약

기존 `emailSent`는 실제 발송 완료를 의미하지만 비동기 처리에서는 API 응답 시점에 알 수 없으므로 제거한다.

관리자 생성과 비밀번호 재설정 응답에 다음 값을 추가한다.

- Python 필드: `email_job_id`, `email_job_status`
- JSON 필드: 기존 관리자 API의 `CamelModel` 규칙에 따라 `emailJobId`, `emailJobStatus`

정상 등록 시 일반적으로 `QUEUED`를 반환한다. Redis 등록 자체가 실패하면 같은 응답에서 `FAILED`를 반환한다.

내부 작업 재시도 API는 기존과 같이 `ALARM`만 처리한다. `EMAIL` 작업을 전달하면 `409 Job retry handler is not available.`을 반환한다. 최종 실패한 이메일은 관리자 임시 비밀번호 재설정 API를 다시 호출해 새 비밀번호와 새 작업으로 처리한다.

## 설정

다음 설정을 추가한다.

```env
EMAIL_QUEUE_NAME=arq:email
EMAIL_MAX_RETRY_COUNT=3
EMAIL_RETRY_BASE_SECONDS=30
EMAIL_PAYLOAD_ENCRYPTION_KEY=<Fernet key>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<SMTP account>
SMTP_PASSWORD=<SMTP app password>
SMTP_FROM=<sender address>
```

`EMAIL_BACKEND` 선택 설정은 제거한다. `email-worker`는 SMTP 전용이며 필수 SMTP 설정이 없으면 시작 단계에서 명확히 실패한다. FastAPI 프로세스는 SMTP에 연결하지 않는다.

## 제거 및 유지

### 제거

- `ConsoleEmailBackend`
- `EMAIL_BACKEND` 선택 분기
- 모듈 로드 시 전역 백엔드를 만드는 `app/core/email/state.py`
- API 프로세스에서 SMTP를 호출하는 `send_temporary_password()`
- `TemporaryCredential.send_to()`
- `emailSent` DTO 필드
- 콘솔 이메일 전용 테스트와 환경변수 설명

### 유지·재배치

- `EmailMessage` 계약
- 관리자 임시 비밀번호 HTML 템플릿과 렌더러
- SMTP 전송 구현

SMTP 구현은 Worker가 의존성으로 생성하여 사용한다. 테스트에서는 가짜 전송 구현을 주입할 수 있게 한다.

## Docker 구성

`email-worker`는 `app/Dockerfile` 이미지를 재사용한다.

- 명령: `uv run --no-sync arq app.workers.email_worker.WorkerSettings`
- 네트워크: 기존 `ws`
- 의존 서비스: `mysql`, `redis`
- 환경: DB, Redis, SMTP, 이메일 payload 암호화 키
- 전용 queue name: `arq:email`

FastAPI, `alarm-worker`, `ocr-worker`, `ai-worker`의 실행 책임은 변경하지 않는다.

## 보안 및 수명

- 임시 비밀번호 평문은 생성 직후 해시 저장과 암호화된 ARQ payload 생성에만 사용한다.
- Redis에는 Fernet 암호문만 저장한다.
- DB와 애플리케이션 로그에 평문을 기록하지 않는다.
- ARQ 작업이 성공 또는 최종 실패 후 정리되면 이메일 본문을 복구할 영속 저장소는 남지 않는다.
- `EMAIL` 수동 재시도를 지원하지 않으므로 최종 실패 뒤에는 새 비밀번호 재설정을 수행한다.
- `EMAIL_PAYLOAD_ENCRYPTION_KEY`는 전화번호 키와 분리하여 교체와 접근 범위를 독립적으로 관리한다.

## 테스트 전략

- enum: `BackgroundJobType.EMAIL` 직렬화
- migration: `job_type`의 크기와 기존 데이터는 유지하면서 DB comment에 `EMAIL`이 반영되는지 확인
- producer: 이메일 작업 생성, 암호화, 전용 큐 등록, Redis 실패 상태 기록
- worker: 선점, payload 복호화, SMTP 성공, 일시 오류 재시도, 영구 실패, 최대 재시도 초과
- template: 수신자명·임시 비밀번호 치환, HTML escaping, 지정 문구, 평문 대체 본문 확인
- SMTP: `text/plain`과 `text/html`을 포함한 multipart 메시지 생성 확인
- 보안: Redis 작업 인자와 로그에 임시 비밀번호 평문이 없는지 확인
- API: 관리자 생성·비밀번호 재설정 응답의 `emailJobId`, `emailJobStatus`
- 내부 작업 API: `EMAIL` 수동 재시도 요청이 409인지 확인
- Docker Compose: `email-worker` 명령, DB/Redis 의존성, 전용 큐 설정 확인
- 회귀: 알람, OCR 및 기존 관리자 인증 흐름 유지

## 완료 조건

- 관리자 이메일 발송이 FastAPI 요청 안에서 실행되지 않는다.
- 이메일 작업이 `background_jobs`에서 `EMAIL` 유형으로 조회된다.
- `email-worker`가 전용 큐에서 SMTP 발송과 자동 재시도를 처리한다.
- 관리자 임시 비밀번호 메일이 지정된 HTML 템플릿과 평문 대체 본문의 multipart 형식으로 발송된다.
- API 응답은 실제 발송 여부 대신 작업 ID와 현재 상태를 반환한다.
- 동기 이메일 및 콘솔 이메일 경로가 제거된다.
- `EMAIL` 내부 수동 재시도는 지원되지 않는다.
- 이메일 평문과 임시 비밀번호가 DB 및 로그에 남지 않는다.
