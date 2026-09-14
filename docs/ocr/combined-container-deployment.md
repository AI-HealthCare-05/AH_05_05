# OCR 통합 컨테이너 배포

## 변경 범위

`ocr-worker`, `ocr-images` 독립 서비스를 제거하고 FastAPI 컨테이너가 API, ARQ OCR 워커, 이미지 전용 Redis를 관리한다. 이메일·알림·AI 워커와 기존 Redis 브로커는 변경하지 않는다. 로컬/운영 Compose 모두 컨테이너가 두 개 줄어든다.

컨테이너 통합만으로 프로세스 메모리가 사라지지는 않는다. API 실행 수 1개, OCR 동시 실행 기본 1개(`OCR_MAX_JOBS`, 1~2 허용)로 중복 실행과 전처리 동시 피크를 제한한다. FastAPI 컨테이너의 3GB 제한은 세 프로세스 합계에 적용되며 메모리 예약량이 아니다. OOM은 세 프로세스 모두에 영향을 줄 수 있으므로 실제 OCR 요청으로 피크를 측정해 서버 사양을 결정한다.

이 구성은 **FastAPI 컨테이너 1개** 배포를 전제로 한다. 이미지가 컨테이너별 RAM에 있으므로 같은 OCR 큐를 소비하는 통합 컨테이너를 여러 개 띄우면 다른 컨테이너의 이미지를 읽지 못한다. AWS에서 복제 수를 늘리거나 수평 자동 확장을 켜기 전에는 이미지 저장소/큐 분배 설계를 변경해야 한다.

`CLOVA_GENERAL_OCR_INVOKE_URL`, `CLOVA_GENERAL_OCR_SECRET` 등 기존 OCR 설정을 FastAPI에도 전달해야 한다(Compose의 공통 `.env` 사용 유지). 필수 설정 오류로 OCR 워커 시작이 반복 실패하면 통합 컨테이너 전체가 종료되고 재시작된다. API만 살아 있는 잘못된 배포를 정상으로 취급하지 않는다.

## 이미지 저장 원칙

- `OCR_IMAGE_REDIS_URL=redis://127.0.0.1:6380/0`: 같은 컨테이너에서만 접근.
- 일반 Redis `redis:6379`는 기존 ARQ 큐에 계속 사용하며 이미지와 합치지 않는다.
- 이미지용 Redis는 RDB/AOF를 끄고 `noeviction` 및 384MB 한도를 유지한다.
- `/run/ocr-images`와 `/run/ocr-runtime`은 tmpfs다. 컨테이너 swap/core dump를 막는다.
- 원본과 전처리 이미지는 기존 저장 어댑터·무결성 검증을 이용한다. OCR 완료 후 사진 TTL은 `OCR_IMAGE_HANDOFF_TTL_SECONDS`(기본 300초, 30~600초)로 줄인다. 브라우저가 두 사진을 확보한 뒤 소유자 인증된 `POST /api/v1/ocr/jobs/{id}/release-images`로 서버 사진을 삭제한다. OCR 결과와 등록 가능 시간은 유지된다.
- 미리보기 사진은 등록 검토 중 브라우저 메모리에서만 사용한다. 새로고침·검토 종료 시 유지하지 않으며, 원본 파일이나 사진 URL을 라우터 이력·브라우저 영구 저장소에 넣지 않는다. 사용자가 처음 선택한 기기의 원본 파일을 삭제하는 기능은 아니다.
- 수신 확인 실패·브라우저 종료 시에는 사진 TTL이 안전망이다. 탭 종료 이벤트의 실행이나 운영체제 메모리의 물리적 즉시 소거를 보장하지 않는다. 서버 OCR 처리 중 임시 보유는 필요하므로 “서버에 전송하지 않음”이 아닌 “처리·미리보기에 일시 사용하며 장기 보관하지 않음”으로 안내한다.
- 재시작하면 RAM 이미지가 소실된다. 이전 미리보기를 유지하려고 디스크로 복사하지 않는다. 저장소가 가득 차면 새 요청을 거절하며 기존 큐를 임의 삭제하지 않는다.

## 빌드 및 전환 순서

1. 기존 설정과 현재 배포 이미지 태그를 기록한다. 운영 DB 볼륨은 보존한다.
2. 변경된 `app/Dockerfile`로 새 앱 이미지를 빌드·배포 레지스트리에 업로드한다. Compose 파일만 바꾸고 예전 이미지를 실행하면 런타임 모듈/Redis가 없으므로 실패한다.
3. 유지보수 시간에 새 OCR 접수를 중단하고 진행 중/대기 중 OCR 작업이 끝났는지 확인한다. 기존 미리보기는 최대 TTL(기본 60분)까지 기다리거나 재등록 필요성을 안내한다. 큐를 비우는 `FLUSHDB`는 사용하지 않는다.
4. 이전 `ocr-worker`를 먼저 정상 종료한다. 새/구 워커가 서로 다른 이미지 저장소로 같은 큐를 소비하지 않게 한다.
5. 통합 FastAPI를 새 이미지로 재생성하고 healthcheck가 healthy인지 확인한다. 운영용 Compose의 기존 DB 마이그레이션 절차는 그대로 따른다. 로컬 Compose는 기존처럼 시작 시 `aerich upgrade`를 먼저 실행한다.
6. 익명 테스트 이미지로 업로드 → OCR 완료 → 원본/전처리 미리보기 → 등록 흐름을 확인한다. 외부 OCR 호출에는 실제 제공자 설정이 필요하다.
7. 성공 후 이전 `ocr-worker`, `ocr-images` 컨테이너만 제거한다. `down -v`, `system prune --volumes`, 무차별 `--remove-orphans`는 사용하지 않는다.

운영 Compose는 `.env`와 상대 경로 기준을 확인한 기존 배포 방식으로 실행한다. 기존 정상 명령에 지정된 `--project-directory`/프로젝트 이름을 임의로 바꾸지 않는다.

## 진단

Supervisor가 PID 1로 실행되어 API·OCR·이미지 Redis와 장애 감시 프로세스를 관리한다. API와 OCR은 이미지 Redis 준비를 최대 5초 기다린다. 프로세스 종료 시 재기동하며, 반복 시작 실패는 컨테이너 종료로 전파한다. Healthcheck는 관리 프로세스 상태, 이미지 Redis 응답, 10초 간격 OCR heartbeat, API 응답을 모두 확인한다. Docker Compose의 `unhealthy` 표시 자체가 컨테이너 자동 재시작을 의미하지는 않으므로, 프로세스가 종료되지 않은 장기 멈춤은 운영 모니터링 대상으로 남는다.

```sh
docker compose ps fastapi
docker compose exec -T fastapi uv run --no-sync python -m app.runtime.healthcheck
docker stats --no-stream fastapi
docker compose logs --tail 100 fastapi
```

로그에 환자 원문·사진·토큰을 남기지 않는다. FastAPI 컨테이너 로그는 local 드라이버로 파일당 10MB, 최대 3개로 제한한다.

## 롤백

새 OCR 요청을 중단하고 통합 컨테이너를 정상 종료한 뒤 이전 Compose와 이전 이미지 태그를 함께 복구한다. 일반 Redis/DB/Qdrant 볼륨은 그대로 유지한다. 전환 중 소실된 RAM 이미지는 복구할 수 없으므로 해당 OCR은 재등록한다. 통합 Redis에 접근해야 하는 워커만 따로 구형 이미지로 되돌리면 안 된다.

## 로컬 검증 기록 (2026-09-14)

- 최종 Compose·런타임·OCR 워커·휘발성 저장소 테스트: 38개 통과.
- Linux AI 전체 테스트: 1,778개 통과, 기존 skip 1개.
- 전체 Ruff 검사 통과, 938개 파일 포맷 검사 통과.
- 실제 `app/Dockerfile` 빌드 성공. 격리된 MySQL/큐 Redis와 통합 컨테이너로 검증했으며 기존 사용자 서비스·DB에는 연결하지 않았다.
- 최종 이미지에서 Supervisor PID 1, 관리 프로세스 전체 RUNNING, 복합 healthcheck healthy 확인.
- 합성 JPEG의 원본/전처리 이미지 저장·읽기·해시 검증 및 TTL 만료 삭제 확인. 이미지 Redis 설정, tmpfs, 다른 컨테이너에서 6380 접근 불가 확인.
- OCR 워커 SIGTERM 종료 후 자동 재시작과 health 복구 확인. SIGSTOP으로 살아 있으나 멈춘 워커는 heartbeat 만료 후 health 실패, SIGCONT 후 정상 복구 확인.
- OCR 설정을 의도적으로 누락한 테스트에서 반복 시작 실패 → FATAL 감지 → 통합 컨테이너 종료 확인.
- 최종 이미지 SIGTERM 종료 시 API → OCR → 이미지 Redis 순서 확인, 종료 코드 0, OOM 없음. 유휴 상태에서 측정한 약 364MiB는 테스트 환경 참고치이며 실제 OCR 피크나 AWS 비용 절감률을 보장하지 않는다.
- 독립 읽기 전용 코드 리뷰에서 차단 이슈 없음. 검증용 컨테이너·네트워크·이미지 태그는 정리했다.
- 외부 CLOVA/OpenAI 호출과 운영 재배포는 수행하지 않았다. 실제 이미지 업로드부터 등록까지의 제공자 연동 확인은 배포 전환 절차에 따라 진행한다.
- 변경은 미커밋 상태이며 이 작업에서 commit/push는 수행하지 않았다.
