# RxVita 수동 승인 배포

## 설정

저장소 기본 브랜치에 `.github/workflows/deploy.yml` 및 함께 추가한 scripts 파일을 반영한다.
실제 실행은 `main`에서만 허용한다. 해당 커밋의 `checks.yml` push CI가 성공해야 한다.

Settings → Secrets and variables → Actions:

| 종류 | 이름 | 값 |
| --- | --- | --- |
| Secret | DOCKERHUB_TOKEN | rxvita 저장소 이미지 push 권한 토큰 |
| Variable | DOCKERHUB_USERNAME | blesseunmi82 |
| Variable | VITE_VAPID_PUBLIC_KEY | 운영 웹 푸시 공개키 (개인키 금지) |

Settings → Environments → RxVita:

| 종류 | 이름 | 값 |
| --- | --- | --- |
| Secret | EC2_SSH_PRIVATE_KEY | 배포 SSH 개인키 전체 내용 |
| Secret | EC2_KNOWN_HOSTS | 신원을 검증한 서버의 known_hosts 줄 |
| Secret | PROD_ENV_FILE | 최신 운영 envs/.prod.env 전체 내용 |
| Variable | EC2_HOST | 현재 EC2 주소 |
| Variable | EC2_USER | ubuntu |
| Variable | DEPLOY_PATH | /home/ubuntu/rxvita |

RxVita에 필수 승인자를 설정하고 배포 브랜치를 main으로 제한한다. 승인은 이미지 빌드 후다.
PROD_ENV_FILE은 운영 서버 `.env` 전체를 대체한다. 서버에서만 바꾼 설정도 시크릿에 먼저 동기화한다.
자동 생성한 버전과 DOCKER_USER/DOCKER_REPOSITORY만 자동 교체하며 로컬 env 파일은 수정하지 않는다.
파일 내용/개인키를 Git에 커밋하지 않는다. 생성한 env는 GitHub artifact에 올리지 않는다.

## 자동 버전 규칙

버전 형식은 `build-YYYYMMDD-N`이며 날짜는 번호 예약 시점의 **Asia/Seoul(한국 시간)** 기준이다.
FastAPI와 AI worker는 같은 버전을 사용한다.

```text
build-20260917-1
build-20260917-2
build-20260918-1
```

- 저장소의 `build-YYYYMMDD-N` Git 태그 중 해당 날짜의 가장 큰 번호에 1을 더한다.
- 빌드 전에 해당 커밋에 lightweight Git 태그를 생성해 번호를 예약한다.
- 번호 예약 이후 실패/취소해도 태그를 유지한다. 이미지를 일부만 push한 경우에도 번호를 재사용하지 않는다.
- 새 빌드 또는 빌드 작업 재실행 시 새 번호를 받는다. 번호 예약 전 CI 검사에서 중단되면 번호를 소비하지 않는다.
- **실패한 배포 작업만 재실행**하면 성공한 build 작업의 버전/산출물 ID를 그대로 사용한다.
- 한국 날짜가 바뀌면 그 날짜의 첫 번호는 1이다. 성공한 배포 횟수가 아니라 예약된 빌드 번호다.
- 동시 태그 생성 충돌은 기존 태그가 실제 존재하는지 확인하고 다음 번호로 제한적으로 재시도한다.
- 이 태그들은 번호 기록이므로 삭제하거나 다른 커밋으로 옮기지 않는다. 삭제하면 번호 재사용 위험이 있다.
- build job만 `contents: write`를 사용한다. deploy job은 읽기 권한을 유지한다.
  조직 정책/태그 ruleset이 GitHub Actions의 태그 생성을 금지하면 예약 단계에서 실패한다.
  운영 정책에 맞는 허용 설정이 필요하며, 워크플로가 보호 규칙을 우회하지는 않는다.

## AWS 사전 조건

- 기존 Docker Compose 서비스, 인증서, 볼륨이 정상 운영 중이어야 한다. 초기 설치용이 아니다.
- Compose v2의 `up --wait --wait-timeout` 및 `config --format json` 지원이 필요하다.
- 배포 계정에 Docker 실행 권한, 프로젝트/설정 파일/프런트 dist 쓰기 권한이 필요하다.
- bash, python3, rsync, curl, flock, tar가 설치되어 있어야 한다.
- fastapi의 Compose 작업 경로 라벨이 `/home/ubuntu/rxvita`여야 한다.
- GitHub runner에서 SSH 접속이 가능해야 한다. 이를 위해 22번 포트를 무조건 전체 공개하지 않는다.
  고정 송신 IP runner/VPN 등 접근 방식을 조직 보안 정책에 맞춰 준비한다.
- Docker Hub 저장소가 private이면 AWS 배포 계정도 pull 전용 토큰으로 미리 로그인해야 한다.
- 운영 DB 백업을 먼저 수행하고 새 Aerich migration의 호환성을 검토한다.
- `.deploy`에는 env와 렌더링된 Compose 등 비밀정보가 보관되므로 700 권한을 유지한다.

## 실행

1. main 병합 후 Python/AI CI 완료를 확인한다.
2. Actions → **Deploy RxVita (manual)** → **Run workflow**.
3. Branch는 **main**을 선택한다.
4. 운영 DB 백업/마이그레이션 호환성 확인 체크 후 실행한다. 버전 입력란은 없다.
5. 실행 Summary에서 자동 생성된 버전을 확인한다.
6. 프런트 타입검사/빌드 및 amd64 Docker 빌드/push가 끝나면 **Review deployments**에서 승인한다.
7. 서버 배포와 HTTPS 검사 로그를 확인한 뒤 실제 로그인, OCR, 챗봇을 확인한다.

기존 태그는 재사용하지 않는다. 두 이미지는 자동 생성한 공통 버전으로 매번 빌드한다.
기존 태그 조회 결과가 404일 때만 빌드를 진행한다. 조회 오류도 실패 처리한다.
조회 후 외부에서 같은 태그를 push하는 경쟁 조건까지 막으려면 Docker Hub의 immutable tag 정책도 사용한다.
배포 시 이미지 revision 라벨이 승인된 커밋과 다른 경우 중단한다.
빌드 도중 한 이미지 push만 성공해도 빌드 재실행 시 새 번호가 자동 예약된다.
CI 실패/미완료 또는 승인 대기 중 main 변경 시 배포를 차단하므로 최신 main으로 다시 실행한다.

## 배포 동작과 한계

- 기존 수동 절차의 Compose, HTTPS Nginx, env, frontend 파일을 모두 전달한다.
- npm 대신 기존 GitHub frontend CI와 같은 pnpm 11 및 lockfile을 사용한다.
- 기존 설정/프런트를 `.deploy/<run-id>-<attempt>/backup/`에 백업한다. DB 백업은 아니다.
- 전체 `docker compose down` 대신 `up -d --wait`를 사용한다. 변경된 서비스는 재생성된다.
  MySQL/Redis 설정도 바뀌었다면 해당 서비스 역시 재생성될 수 있다. 무중단 배포는 아니다.
- 현재 FastAPI 시작 명령의 `aerich upgrade`를 유지한다. 실패 시 자동 DB/앱 롤백하지 않는다.
- 오류 시 설정/컨테이너가 일부만 바뀌었을 수 있다. 백업과 배포 전 이미지 기록으로 상태를 확인한다.
- DB 호환성을 확인한 후 이전 env/Compose/Nginx/프런트를 복원하고 Compose를 재적용해야 한다.
  이전 이미지로만 되돌려 DB가 복원된다고 가정하면 안 된다.
- AI worker에는 healthcheck가 없어 Compose는 실행 상태만 확인한다. 실제 큐 처리는 별도 검사한다.
- HTTP 검사는 OpenAPI 및 로그인 페이지 접근만 검증한다. 실제 인증 성공이나 OCR 성공 검사가 아니다.
- 기존 브라우저를 위해 이전 해시 assets는 즉시 삭제하지 않는다. 백업/태그/assets 보관 정책은 별도다.
- Actions는 기존 프로젝트와 일관된 major 버전 표기를 사용한다. 운영 보안 강화 시 검증된 commit SHA로 고정한다.

## 최소 로컬 검증

```bash
uv run pytest --confcutdir=app/tests/deployment app/tests/deployment/test_prepare_deploy_env.py -q
node --test app/tests/deployment/build-version.test.cjs
bash -n scripts/deploy-production.sh
actionlint .github/workflows/deploy.yml
```

이 검사들은 실제 AWS 배포를 실행하지 않는다.
