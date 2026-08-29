# 관리자 SMTP 설정 설계

## 목표

ADMIN 권한 관리자가 공통 sidebar 설정 팝업에서 SMTP 연결 정보를 조회·저장하고, 전용 `email-worker`가 재시작 없이 최신 설정으로 이메일을 발송하도록 한다.

## 저장 구조

`admin_settings`는 `setting_key`가 유일한 전역 관리자 설정 테이블이다. 이번 범위에서는 `SMTP` 한 행만 사용한다.

- `id`: bigint PK
- `setting_key`: varchar(50), unique, `SMTP`
- `smtp_host`: varchar(255), not null
- `smtp_port`: int, not null
- `smtp_user`: varchar(255), not null
- `smtp_password_enc`: varchar(500), not null, Fernet 암호문
- `smtp_from_email`: varchar(255), not null
- `updated_by_admin_id`: bigint, not null, `admin.id` FK
- `created_at`: datetime, not null
- `updated_at`: datetime, not null

모든 DBML 컬럼에는 한국어 `note`를 작성한다. SMTP 비밀번호 암호화에는 `Config.SMTP_SETTINGS_ENCRYPTION_KEY`를 사용하며 API 응답에는 평문과 암호문을 모두 노출하지 않는다.

## API

- `GET /api/v1/admin/settings/smtp`: ADMIN 전용. DB 설정이 있으면 그 값을, 없으면 `Config.SMTP_*` fallback을 반환한다. 비밀번호는 `smtp_password_configured` 불린으로만 표현한다.
- `PUT /api/v1/admin/settings/smtp`: ADMIN 전용 upsert. 포트는 1~65535, 발신 주소는 이메일 형식으로 검증한다. 최초 생성은 비밀번호가 필수이고 수정에서 빈 비밀번호는 기존 암호문을 유지한다.

## worker 연동

`SmtpSettingsService.get_runtime_settings()`가 DB 우선, 환경변수 fallback 순서로 완전한 SMTP 설정을 만든다. `email-worker`는 각 작업 발송 직전에 이 서비스를 호출한다. 따라서 설정 저장 이후 worker 재시작은 필요 없다.

## UI

sidebar 브랜드 영역 오른쪽에 톱니바퀴 버튼을 추가한다. `session.isAdminRole()`이 false이면 버튼을 DOM에서 제거한다. 버튼 클릭 시 SMTP 필드가 있는 overlay를 열고 GET 결과를 채우며 PUT으로 저장한다. 비밀번호 입력은 비워두면 기존 값 유지라는 안내를 표시한다.

## 오류와 보안

- STAFF는 UI에서 숨기고 서버에서도 403으로 거부한다.
- 암호화 키 누락·잘못된 암호문은 설정 저장/발송 실패로 처리하고 비밀번호를 로그에 남기지 않는다.
- DB 행이 없고 환경변수도 완전하지 않으면 worker가 명확한 설정 오류로 작업을 실패 처리한다.

## 검증

모델 메타데이터, 암호화 왕복/오류, API 권한·마스킹·upsert, worker 최신 설정 사용, sidebar 역할별 노출·팝업 저장, Compose/OpenAPI/Ruff를 집중 테스트한다.
