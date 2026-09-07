# 회원가입 이메일 인증 설계

## 목적

모바일 웹 회원가입 과정에서 사용자가 입력한 이메일의 소유권을 6자리 인증번호로 확인한다. 인증 메일은 기존 전용 `email-worker`와 Redis/ARQ 큐를 사용해 비동기로 발송하며, 최종 회원가입 API도 인증 결과를 필수로 검증하여 화면 우회를 차단한다.

## 범위

- 회원가입 이메일 인증 요청·확인 API 추가
- `email_verifications` 모델과 Aerich 마이그레이션 추가
- 기존 `background_jobs`에 `EMAIL` 발송 작업 등록 및 인증 건 연결
- 회원가입 인증번호 HTML·텍스트 이메일 템플릿 추가
- 기존 `email-worker`에 회원가입 인증 메일 지원 및 만료 작업 취소 처리 추가
- `/login` 회원가입 1·2단계를 실제 API와 연결
- 최종 회원가입 API에 일회성 이메일 인증 토큰 검증 추가
- dbdiagram.io 클라우드 ERD에 신규 테이블과 논리적 연결 note 반영

## 전체 흐름

1. 사용자가 회원가입 1단계에서 이메일을 입력하고 `인증코드 받기`를 누른다.
2. 백엔드는 이메일 형식과 기존 가입 여부, 재발송 대기시간을 확인한다.
3. 백엔드는 `secrets.randbelow(1_000_000)`으로 앞자리 0을 허용하는 6자리 번호를 생성한다.
4. 인증번호 원문은 이메일 작업의 암호화된 Redis/ARQ payload에만 포함한다. DB에는 서버 비밀키를 이용한 HMAC-SHA256 결과만 저장한다.
5. `email_verifications`를 생성한 후 `background_jobs`에 `job_type=EMAIL`, `reference_table=email_verifications`, `reference_id=<인증 ID>` 작업을 생성한다.
6. `email-worker`가 SMTP 설정을 읽고 회원가입 인증 메일을 발송한다. 발송 결과와 재시도 상태는 `background_jobs`에 기록한다.
7. 사용자는 1분 안에 인증번호를 입력한다. 서버는 최신 인증 건, 만료 여부, 실패 횟수, 해시 일치 여부를 검사한다.
8. 인증 성공 시 `verified_at`을 저장하고 10분짜리 일회성 `verification_token`을 반환한다.
9. 최종 회원가입 요청은 해당 토큰을 포함한다. 서버는 토큰 이메일과 가입 이메일, 인증 완료·미사용 상태를 검사한다.
10. 사용자와 설정을 생성하는 트랜잭션에서 `consumed_at`을 함께 기록한다.

## 데이터 모델

### email_verifications

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | bigint | PK, auto increment | 이메일 인증 식별자 |
| `email` | varchar(255) | not null | 인증 대상 이메일 |
| `purpose` | varchar(30) | not null | 인증 목적, 현재 값은 `SIGNUP` |
| `code_digest` | char(64) | not null | 인증번호 HMAC-SHA256 결과 |
| `expires_at` | datetime | not null | 인증번호 만료 시각 |
| `attempt_count` | int | not null, default 0, 0~5 | 인증번호 확인 실패 횟수 |
| `verified_at` | datetime | nullable | 인증 성공 시각 |
| `consumed_at` | datetime | nullable | 회원가입에서 사용한 시각 |
| `created_at` | datetime | not null | 인증 요청 시각 |
| `updated_at` | datetime | nullable | 변경 시각 |

인덱스:

- `(email, purpose, created_at)` — 이메일·목적별 최신 인증 건 조회
- `(expires_at)` — 만료 건 조회 및 정리
- `(verified_at, consumed_at)` — 인증 완료·사용 여부 조회

DB CHECK 제약조건으로 `attempt_count BETWEEN 0 AND 5`를 적용한다.

`background_jobs`에는 신규 이메일 전용 컬럼을 추가하지 않는다. 다음 기존 필드로 인증 건을 연결한다.

- `job_type = EMAIL`
- `reference_table = email_verifications`
- `reference_id = email_verifications.id`
- `idempotency_key = email:signup-verification:<verification_id>:<uuid>`

이 연결은 다형 참조이므로 물리적 FK를 추가하지 않고 모델·ERD note로 관계를 명시한다.

## API 계약

### 인증번호 요청

`POST /api/v1/auth/email-verifications`

요청:

```json
{
  "email": "user@example.com"
}
```

성공: `202 Accepted`

```json
{
  "verification_id": 123,
  "expires_in": 60,
  "resend_available_in": 60
}
```

발송 후 60초 동안 같은 이메일과 목적의 재발송을 막는다. 60초가 지난 뒤 재발송하면 기존 미사용 인증 건을 즉시 만료시키고 새 인증 건과 이메일 작업을 생성한다.

### 인증번호 확인

`POST /api/v1/auth/email-verifications/{verification_id}/verify`

요청:

```json
{
  "code": "123456"
}
```

성공: `200 OK`

```json
{
  "verification_token": "signed-one-time-token",
  "expires_in": 600
}
```

번호가 틀리면 실패 횟수를 원자적으로 증가시킨다. 5회 실패하면 해당 인증 건은 더 이상 확인할 수 없다.

### 최종 회원가입

기존 `POST /api/v1/auth/signup` 요청에 다음 필드를 추가한다.

```json
{
  "email": "user@example.com",
  "email_verification_token": "signed-one-time-token"
}
```

토큰은 `purpose`, `verification_id`, `email`, 만료 시각을 서명해 포함한다. 서버는 토큰 검증 후 DB 인증 건을 행 잠금으로 조회하고 `verified_at` 존재, `consumed_at` 부재, 이메일 일치를 검사한다. 사용자 생성과 인증 건 소비를 같은 트랜잭션에서 처리한다.

## 오류 계약

| HTTP | 코드 | 메시지/용도 |
|---|---|---|
| 409 | `EMAIL_ALREADY_EXISTS` | 이미 사용 중인 이메일 |
| 429 | `EMAIL_VERIFICATION_RATE_LIMITED` | 재발송 대기시간이 지나지 않음 |
| 400 | `INVALID_EMAIL_VERIFICATION_CODE` | `인증번호를 확인해주세요.` |
| 410 | `EMAIL_VERIFICATION_EXPIRED` | 인증번호 입력시간 만료 |
| 429 | `EMAIL_VERIFICATION_ATTEMPTS_EXCEEDED` | 최대 확인 횟수 초과 |
| 503 | `EMAIL_DELIVERY_UNAVAILABLE` | 이메일 작업 암호화·큐 등록 실패 |
| 400 | `EMAIL_VERIFICATION_INVALID` | 가입 토큰 누락·변조·만료·재사용·이메일 불일치 |

오류 응답은 기존 `code`, `message`, `field` 형식을 사용한다.

## 이메일 작업과 템플릿

`EmailTemplate`에 `SIGNUP_VERIFICATION_CODE`를 추가하고 이메일 payload에 인증 ID와 인증번호를 담는다. payload 전체는 기존 `EMAIL_PAYLOAD_ENCRYPTION_KEY`로 암호화한다.

제목은 `RxVita 회원가입 이메일 인증번호`로 고정한다. HTML 본문은 다음 요소로 구성한다.

- 기존 RxVita PNG 로고를 CID 인라인 이미지로 첨부
- 회원가입 이메일 인증번호 안내
- 본문 중앙에 6개 칸으로 나눈 크고 명확한 숫자 표시
- 인증번호 유효시간 1분 안내
- 본인이 요청하지 않은 경우 무시하라는 안내
- HTML을 볼 수 없는 클라이언트를 위한 텍스트 대체 본문

기존 이메일 메시지 객체에 CID 인라인 첨부 파일을 표현하는 구조를 추가한다. 기존 관리자 임시비밀번호 이메일에는 영향을 주지 않는다.

`email-worker`는 회원가입 인증 메일을 보내기 전에 연결된 `email_verifications`를 조회한다. 인증 건이 없거나 이미 만료·소비되었으면 SMTP 발송과 재시도를 수행하지 않고 작업을 `CANCELLED`로 종료한다. 일시적인 SMTP 오류는 기존 지수 백오프를 따르되, 다음 재시도 시각이 인증 만료 이후라면 재시도하지 않는다.

## 프론트엔드 동작

회원가입 1단계:

- 이메일 형식이 유효할 때만 `인증코드 받기` 활성화
- 클릭 중 버튼 중복 실행 차단
- 인증 요청 API 성공 시에만 2단계 이동
- 실패 시 이메일 입력란 아래에 서버 메시지 표시

회원가입 2단계:

- 타이머를 `01:00`에서 시작
- 인증번호는 숫자 6자리만 입력
- 0초가 되면 인증번호 입력창과 확인 버튼 비활성화
- 만료 전에는 `다시 보내기` 비활성화
- 만료 후 `다시 보내기` 활성화
- 재발송 성공 시 번호·오류를 초기화하고 새 인증 ID와 1분 타이머 적용
- 번호 불일치 시 입력란 아래에 빨간색 `인증번호를 확인해주세요.` 표시
- 확인 성공 시 반환된 토큰을 React 메모리 상태에 보관하고 3단계 이동
- 이메일 단계로 돌아가 이메일을 변경하면 인증 ID와 토큰 폐기

회원가입 4단계:

- 최종 가입 요청에 `email_verification_token` 포함
- 새로고침 등으로 토큰이 사라지면 이메일 인증 단계부터 다시 진행

Mock 모드는 실제 이메일을 보내지 않고 고정 인증번호 `123456`으로 동일한 API 계약을 모사한다.

## 보안과 동시성

- 인증번호 원문은 애플리케이션 로그와 DB에 기록하지 않는다.
- `EMAIL_VERIFICATION_SECRET`은 필수 비밀 환경변수로 관리한다.
- 인증번호 해시는 이메일, 목적, 인증 ID와 함께 HMAC 입력에 포함해 다른 인증 건에서 재사용할 수 없게 한다.
- 인증번호 비교는 `hmac.compare_digest`를 사용한다.
- 인증 확인과 최종 소비는 `SELECT FOR UPDATE` 트랜잭션으로 중복 요청을 직렬화한다.
- 같은 이메일의 최신 미사용 인증 건만 허용한다.
- API 응답과 로그에 인증번호 및 digest를 포함하지 않는다.

## 설정

- `EMAIL_VERIFICATION_SECRET`: 인증번호 HMAC 비밀키
- `EMAIL_VERIFICATION_TTL_SECONDS=60`: 인증번호 유효시간
- `EMAIL_VERIFICATION_TOKEN_TTL_SECONDS=600`: 인증 성공 토큰 유효시간
- `EMAIL_VERIFICATION_MAX_ATTEMPTS=5`: 최대 번호 확인 실패 횟수
- `EMAIL_VERIFICATION_RESEND_SECONDS=60`: 재발송 대기시간

설정값은 백엔드와 `email-worker` Docker 서비스, 개발·운영 예제 환경파일에 동일하게 전달한다.

## 마이그레이션과 ERD

- Tortoise ORM에 `EmailVerification`을 등록한다.
- Aerich 마이그레이션으로 테이블, 인덱스, CHECK 제약조건을 생성한다.
- 마이그레이션을 Docker MySQL에 적용하고 실제 메타데이터를 확인한다.
- dbdiagram.io의 FinalProject ERD에 동일한 테이블과 컬럼 note를 추가한다.
- `background_jobs.reference_table/reference_id`가 `email_verifications`를 논리적으로 참조한다는 note를 추가한다.
- dbdiagram.io 저장 직전에 추가 확인을 요청하지 않는다.

## 테스트와 검증

백엔드:

- 모델 메타데이터와 마이그레이션 SQL
- 인증 요청 성공, 중복 이메일, 재발송 제한, 재발송 후 기존 건 만료
- 인증번호 성공, 불일치, 만료, 5회 초과, 동시 확인
- 가입 토큰 누락, 변조, 만료, 이메일 불일치, 재사용
- 회원 생성과 인증 소비의 원자성
- 템플릿 제목, 텍스트 본문, HTML 6칸 코드, CID 로고
- email-worker 성공, SMTP 실패·재시도, 인증 만료 취소
- background job 참조값과 상태 전이

프론트엔드:

- 인증 요청 성공 전 단계 이동 방지
- 60초 타이머와 만료 후 입력·확인 차단
- 재발송 활성화와 상태 초기화
- 번호 불일치 메시지
- 인증 성공 후 최종 가입 요청에 토큰 포함
- API 실패 시 접근 가능한 오류 표시와 중복 클릭 방지

최종 검증은 Ruff, Python 관련 테스트, TypeScript 타입 검사, 프론트 관련 테스트, Docker Compose 설정 검사, Aerich 적용 결과와 DB 메타데이터 확인으로 수행한다.

