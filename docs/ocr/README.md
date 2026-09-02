# 조제약 OCR 로컬 실행 가이드

팀원이 로컬 환경에서 조제약 복약안내 이미지를 OCR하고, 결과를 수정·확정해 MySQL에 저장하기 위한 실행 순서다.

이 문서는 **실행 안내서**다. API 요청·응답의 전체 필드 계약은
[조제약 OCR API 명세서](../medication-guide-ocr-api-spec-v1.md)를 참고한다.

## 전체 흐름

```text
프론트엔드
  └─ POST /api/v1/ocr
       ├─ FastAPI: OcrJob 생성 + 원본 이미지 임시 저장
       └─ Redis: OCR 작업 대기열 등록
            └─ ocr-worker: 전처리 → CLOVA OCR → 조건부 LLM → 검증
                 └─ MySQL: READY_FOR_REVIEW 결과 저장

프론트엔드가 2초마다 GET /api/v1/ocr/jobs/{ocrJobId} 조회
  └─ 사용자가 결과 수정·확인
       └─ PATCH /api/v1/ocr/jobs/{ocrJobId}
            └─ CareEpisode 1건 + Medication N건 저장
```

OCR을 실행하려면 `fastapi`만 아니라 다음 네 서비스가 모두 필요하다.

업로드와 원본·전처리 이미지 조회는 10초 HTTP 제한 시간(`@api_timeout(10)`: 라우트 데코레이터 아래)을 사용하고, 상태 조회·확정은 공통 3초 제한을 사용한다. 제한 시간 초과 응답은 `504 {"code":"API_TIMEOUT","message":"요청 처리 시간이 초과되었습니다."}`다. worker의 전처리·CLOVA·조건부 LLM·검증은 대기열에서 비동기로 실행되므로 이 HTTP 제한 시간과 별개다.

| 서비스 | 역할 |
| --- | --- |
| `mysql` | 사용자, OCR 작업, 확정된 복약 기록 저장 |
| `redis` | FastAPI와 OCR worker 사이의 비동기 작업 대기열 |
| `fastapi` | 업로드·상태 조회·확정 API |
| `ocr-worker` | CLOVA 호출과 OCR 결과 구조화 |

## 0. 사전 준비

- Docker Desktop 실행
- 프로젝트 저장소 내려받기
- 프론트까지 실행할 경우 Node.js와 pnpm 설치
- 팀에서 공유받은 CLOVA Template OCR Invoke URL, Secret, Template ID 준비

모든 Docker 명령은 저장소 루트, 즉 `docker-compose.yml`이 있는 위치에서 실행한다.

```powershell
cd <저장소 경로>
```

## 1. 백엔드 환경변수 준비

처음 실행할 때만 루트 `.env.example`을 `.env`로 복사한다.

```powershell
Copy-Item .env.example .env
```

이미 `.env`가 있다면 덮어쓰지 말고 필요한 값만 확인한다.

### DB와 Docker 필수값

```dotenv
DB_ROOT_PASSWORD=<로컬 MySQL root 비밀번호>
DB_NAME=ai_health
DB_USER=ai_health_user
DB_PASSWORD=<로컬 애플리케이션 DB 비밀번호>
DB_EXPOSE_PORT=3306
DB_PORT=3306

DOCKER_USER=local
DOCKER_REPOSITORY=ai-health
APP_VERSION=dev
```

### CLOVA OCR 필수값

```dotenv
CLOVA_TEMPLATE_OCR_INVOKE_URL=<CLOVA Template OCR Invoke URL>
CLOVA_TEMPLATE_OCR_SECRET=<CLOVA OCR Secret>
CLOVA_TEMPLATE_ID=<활성화된 조제약 템플릿 ID>
```

선택값은 기본값을 그대로 사용해도 된다.

```dotenv
CLOVA_CONNECT_TIMEOUT_SECONDS=5
CLOVA_READ_TIMEOUT_SECONDS=60
OCR_REVIEW_CONFIDENCE_THRESHOLD=0.90
OCR_REVIEW_TTL_MINUTES=60
OCR_RETRY_BASE_SECONDS=5
```

주의:

- Secret을 Git에 커밋하거나 채팅·문서에 실제 값으로 적지 않는다.
- `CLOVA_TEMPLATE_ID`는 숫자만 입력한다.
- Invoke URL, Secret, Template ID 중 하나라도 맞지 않으면 worker가 시작하지 못하거나 OCR이 실패한다.
- OCR 처리 시간에 별도 화면 제한은 없지만, CLOVA 응답 읽기 제한은 기본 60초다.

## 2. Docker 기본 서비스와 FastAPI 실행

처음 실행하거나 Python 의존성·Dockerfile이 바뀌었으면 `--build`를 붙인다. 첫 실행에서는 migration을
적용하기 전에 worker가 DB를 조회하지 않도록 `mysql`, `redis`, `fastapi`까지만 먼저 켠다.

```powershell
docker compose up -d --build mysql redis fastapi
```

이미 migration까지 적용된 환경을 다시 켜는 경우에는 네 서비스를 한 번에 실행해도 된다.

```powershell
docker compose up -d mysql redis fastapi ocr-worker
```

상태 확인:

```powershell
docker compose ps mysql redis fastapi
```

기대 상태:

- `mysql`: `Up ... (healthy)`
- `redis`: `Up ... (healthy)`
- `fastapi`: `Up`

## 3. DB migration 적용

처음 실행하거나 migration 파일이 추가된 브랜치를 받은 경우 적용한다.

```powershell
docker compose exec fastapi uv run --no-sync aerich upgrade
```

현재 migration 상태 확인:

```powershell
docker compose exec fastapi uv run --no-sync aerich heads
```

`No available heads.`가 나오면 현재 적용할 migration이 더 없다는 뜻이다.

OCR 비동기 구조에는 다음 migration이 포함되어야 한다.

```text
7_20260825114656_async_medication_ocr.py
```

이 migration은 `6_20260825155701_add_nutrient_standard.py` 다음에 적용된다.

migration 전에 `fastapi` 컨테이너가 실행 중이어야 한다.

migration이 끝나면 OCR worker를 실행한다.

```powershell
docker compose up -d ocr-worker
docker compose ps ocr-worker
```

기대 상태는 `ocr-worker: Up`이다.

worker 로그 확인:

```powershell
docker compose logs --tail=100 ocr-worker
```

FastAPI와 worker 로그를 계속 보는 경우:

```powershell
docker compose logs -f fastapi ocr-worker
```

`Ctrl+C`는 로그 보기만 종료하며 컨테이너는 계속 실행된다.

## 4. 백엔드와 worker 동작 확인

Swagger 접속:

- http://127.0.0.1:8000/api/docs

Redis 확인:

```powershell
docker compose exec redis redis-cli ping
```

정상 응답:

```text
PONG
```

worker가 내려가 있으면 업로드 요청은 생성되더라도 상태가 계속 `queued`에 머문다.

## 5. 프론트엔드 실 API 연결

새 PowerShell 창을 열고 `frontend` 폴더로 이동한다.

```powershell
cd frontend
```

처음 실행할 때:

```powershell
pnpm install
Copy-Item .env.example .env.local
```

`frontend/.env.local`을 다음처럼 설정한다.

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE_URL=/api
```

프론트 실행:

```powershell
pnpm dev
```

접속 주소:

- 로그인: http://127.0.0.1:5173/login
- 개발용 약봉투 등록 시작점: http://127.0.0.1:5173/dev/document-upload

Vite가 `/api` 요청을 `http://127.0.0.1:8000`으로 전달하므로 기본 설정에서는 별도 CORS 설정이 필요 없다.

## 6. 테스트 사용자 준비

현재 실서버 회원가입은 프론트 화면이 아니라 Swagger에서 진행한다.

1. Swagger에서 `POST /api/v1/auth/signup`을 연다.
2. 팀원마다 겹치지 않는 이메일과 전화번호로 가입한다.

예시:

```json
{
  "email": "ocr-test-pjy@example.com",
  "password": "Password123!",
  "name": "OCR테스터",
  "phone_number": "01012345678"
}
```

3. 프론트 `/login`에서 같은 이메일과 비밀번호로 로그인한다.

예시의 `pjy` 부분은 본인의 영문 이니셜로 바꾼다. 공용 DB를 사용하는 경우 이메일과 전화번호가 다른
팀원 데이터와 중복되지 않게 바꾼다.

## 7. 프론트에서 OCR 실행

1. 로그인한다.
2. 홈에서 **약봉투 등록**으로 이동하거나 개발용 등록 URL에 접속한다.
3. **갤러리에서 선택**을 눌러 JPG 또는 PNG 한 장을 선택한다.
4. **등록하기**를 누른다.
5. 로딩 화면에서 기다린다.
   - 프론트가 2초마다 상태 API를 조회한다.
   - 처리 시간은 이미지와 CLOVA 상태에 따라 달라질 수 있다.
6. **확인해주세요** 화면이 나오면 OCR 결과를 원본 이미지와 비교한다.
7. 약품명을 누르면 약 정보를 수정할 수 있다.
   - 약 추가·수정·삭제 가능
   - 조제일, 약품명, 용량, 효능, 복용 방법, 주의사항, 횟수, 일수 확인
8. **저장**을 누른다.
9. 신뢰도가 낮은 항목이 있으면 **확인 후 저장**을 누른다.
10. **저장했어요**가 표시되면 RDB 저장까지 완료된 것이다.

약이 4개이면 확정 API를 4번 호출하는 것이 아니다. 약 4개를 배열에 담아 PATCH를 한 번 호출하고,
MySQL `medications` 테이블에는 약마다 한 행씩 총 4행이 저장된다.

## 8. Swagger에서 직접 OCR 실행

프론트 없이 API만 확인할 때 사용한다.

1. `POST /api/v1/auth/login`을 실행해 `access_token`을 받는다.
2. Swagger 우측 상단 **Authorize**에 access token을 입력한다.
3. `POST /api/v1/ocr`를 실행한다.
   - `Idempotency-Key`: `ocr-`로 시작하는 UUID
   - `file`: JPG 또는 PNG 한 장
4. 응답의 `documentIds[0]` 값을 `ocrJobId`로 사용한다.
5. `GET /api/v1/ocr/jobs/{ocrJobId}`를 실행한다.
6. `queued` 또는 `processing`이면 같은 GET을 다시 실행한다.
7. `ready_for_review`가 되면 결과를 확인한다.
8. `PATCH /api/v1/ocr/jobs/{ocrJobId}`에 수정한 전체 약 목록을 한 번에 넣는다.
9. 응답의 `recordId`가 생성된 `care_episodes.id`다.

PowerShell에서 UUID만 만들려면:

```powershell
"ocr-$((New-Guid).Guid)"
```

Swagger는 GET 결과를 PATCH 입력란으로 자동 복사하지 않는다. GET 결과를 보고 필요한 필드만 PATCH 예시에
맞춰 직접 입력해야 한다.

## 9. 상태값 해석

| API 상태 | 의미 | 확인할 내용 |
| --- | --- | --- |
| `queued` | Redis 대기열에 등록됨 | 오래 지속되면 worker 상태와 로그 확인 |
| `processing` | worker가 CLOVA OCR 처리 중 | 완료될 때까지 polling |
| `ready_for_review` | 결과 수정·확인 가능 | 60분 안에 확정 |
| `complete` | RDB 저장 완료 | `care_episodes`, `medications` 확인 |
| `failed` | OCR 실패 | `errorCode`와 worker 로그 확인 |

`ready_for_review` 작업은 기본 60분 뒤 만료된다. 만료된 미확정 작업은 원본 이미지와 구조화 결과가 삭제되므로
이미지를 다시 올려야 한다.

## 10. MySQL 저장 결과 확인

### Docker Desktop에서 확인

1. Docker Desktop에서 `mysql` 컨테이너를 선택한다.
2. **Exec** 탭을 연다.
3. 다음 명령을 실행한다.

```bash
mysql -u root -p
```

4. `.env`의 `DB_ROOT_PASSWORD`를 입력한다.

### 터미널에서 확인

```powershell
docker compose exec mysql mysql -u root -p
```

MySQL에 접속한 뒤 조회:

```sql
SHOW DATABASES;
USE ai_health;

SELECT
  id,
  user_id,
  status,
  care_episode_id,
  error_code,
  created_at,
  completed_at
FROM ocr_jobs
ORDER BY id DESC
LIMIT 10;

SELECT
  id,
  care_episode_id,
  source_ocr_job_id,
  name,
  dose,
  efficacy,
  administration,
  precautions,
  times_per_day,
  days
FROM medications
ORDER BY id DESC
LIMIT 20;
```

`DB_NAME`을 `ai_health`가 아닌 값으로 설정했다면 `USE ai_health;` 대신 해당 값을 사용한다.

한글이 깨져 보이면 UTF-8 모드로 다시 접속한다.

```powershell
docker compose exec mysql mysql --default-character-set=utf8mb4 -u root -p
```

## 11. 자주 막히는 문제

### 업로드 후 `queued`에서 바뀌지 않음

`ocr-worker`가 실행 중인지 확인한다.

```powershell
docker compose ps ocr-worker
docker compose logs --tail=200 ocr-worker
```

Redis 연결도 확인한다.

```powershell
docker compose exec redis redis-cli ping
```

### worker가 계속 재시작됨

대부분 CLOVA 환경변수 또는 DB 연결 문제다.

```powershell
docker compose logs --tail=200 ocr-worker
```

`.env`의 Invoke URL, Secret, Template ID와 DB 설정을 확인한 뒤 컨테이너를 다시 만든다.

```powershell
docker compose up -d --force-recreate fastapi ocr-worker
```

환경변수 변경은 단순 `docker compose restart`만으로 반영되지 않을 수 있으므로 `--force-recreate`를 사용한다.

### 프론트 요청이 목업 데이터로 동작함

`frontend/.env.local`에 다음 값이 있는지 확인하고 Vite를 다시 실행한다.

```dotenv
VITE_USE_MOCK=false
```

### 프론트에서 백엔드 연결 실패

1. http://127.0.0.1:8000/api/docs 접속 여부 확인
2. `fastapi` 로그 확인
3. `frontend/.env.local`의 `VITE_API_BASE_URL=/api` 확인

```powershell
docker compose logs --tail=200 fastapi
```

### `PROVIDER_CONFIG_MISSING` 또는 CLOVA 관련 실패

- `CLOVA_TEMPLATE_OCR_INVOKE_URL` 확인
- `CLOVA_TEMPLATE_OCR_SECRET` 확인
- `CLOVA_TEMPLATE_ID`가 활성 템플릿 ID인지 확인
- CLOVA 콘솔에서 템플릿이 배포·활성 상태인지 확인

### 이미지 업로드가 422 또는 413

- JPG 또는 PNG 한 장인지 확인
- 확장자만 바꾼 파일이 아닌지 확인
- 파일이 손상되지 않았는지 확인
- 파일 크기가 50 MiB 이하인지 확인

### 컨테이너 이름 충돌

이 프로젝트는 `mysql`, `redis`, `fastapi`, `ocr-worker`라는 고정 컨테이너 이름을 사용한다.
같은 이름의 이전 컨테이너가 있으면 그 컨테이너를 만든 프로젝트 폴더에서 먼저 종료한다.

```powershell
docker compose down
```

DB 데이터를 유지하려면 `docker compose down -v`는 사용하지 않는다.

## 12. 코드 변경 후 재실행

Python 코드만 변경:

```powershell
docker compose restart ocr-worker
```

FastAPI는 로컬 개발 Compose에서 `--reload`로 실행되지만, worker는 자동 재시작되지 않으므로 직접 재시작한다.

`pyproject.toml`, `uv.lock`, Dockerfile이 변경:

```powershell
docker compose up -d --build fastapi ocr-worker
```

migration이 추가:

```powershell
docker compose exec fastapi uv run --no-sync aerich upgrade
```

## 13. 종료

컨테이너만 종료하고 DB 볼륨은 보존:

```powershell
docker compose down
```

다음 실행:

```powershell
docker compose up -d mysql redis fastapi ocr-worker
```

`-v`를 붙이면 MySQL 데이터와 OCR 공유 볼륨까지 삭제될 수 있으므로 초기화가 목적일 때만 사용한다.

## 팀원 실행 체크리스트

- [ ] 루트 `.env`에 DB와 CLOVA 값이 설정되어 있다.
- [ ] `mysql`과 `redis`가 healthy다.
- [ ] `fastapi`와 `ocr-worker`가 Up 상태다.
- [ ] `aerich upgrade`를 적용했다.
- [ ] Swagger가 열린다.
- [ ] `frontend/.env.local`의 `VITE_USE_MOCK=false`를 확인했다.
- [ ] Swagger에서 테스트 사용자를 만들었다.
- [ ] 프론트에서 이미지 업로드 후 `ready_for_review` 화면이 열린다.
- [ ] 수정·확정 후 `complete`가 되고 MySQL에 약 목록이 저장된다.

## 관련 문서

- [조제약 OCR API 명세서](../medication-guide-ocr-api-spec-v1.md)
- [프로젝트 실행 안내](../README.md)
- [저장소 루트 README](../../README.md)
