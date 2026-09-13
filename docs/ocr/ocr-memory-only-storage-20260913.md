# OCR 이미지 메모리 전용 저장 설계와 레거시 디스크 정리

작성일: 2026-09-13

## 운영 설계

OCR 원본과 전처리 미리보기는 전용 Redis 인스턴스 `ocr-images`에만 둔다. 애플리케이션은
`OCR_IMAGE_REDIS_URL=redis://ocr-images:6379/0`을 사용한다. 기존 ARQ 큐 Redis와 큐 설정은
그대로 유지하며, OCR 이미지 Redis를 큐 브로커로 재사용하지 않는다.

전용 Redis는 다음 조건을 함께 충족해야 한다.

- RDB 스냅샷 비활성화: `save ""`
- AOF 비활성화: `appendonly no`
- 디스크 볼륨 마운트 없음, 호스트 포트 노출 없음
- `ocr-private` 내부 네트워크에만 연결하며 API와 OCR worker만 같은 네트워크에 참여
- Redis `maxmemory 384mb`, `maxmemory-policy noeviction`
- OCR 이미지 Redis 컨테이너/서비스 메모리 상한 512 MiB, swap 비활성화
- API와 OCR worker는 각각 메모리 `3g`, `memswap` `3g`, core dump `0`으로 제한해 swap·core dump를 방지

원본과 처리본은 `READY_FOR_REVIEW` 전환 시점에 60분 TTL을 갱신한다. 따라서 업로드 시점부터의
절대 60분 제한이 아니다. 검토 TTL 설정은 1~60분만 허용한다. 확인, 취소, 최종 실패에서는 두 이미지 키를 즉시 삭제하며, 확인이 성공한
뒤에는 원본·처리본 미리보기를 제공하지 않는다. 정상 애플리케이션 OCR 경로는 디스크에 이미지 파일을
쓰지 않는다. multipart 및 Nginx 업로드 경로도 메모리 스트리밍 구성으로 반영돼 OCR 임시 파일을 만들지
않는다.

업로드와 두 미리보기 응답은 API 프로세스의 공유 메모리 슬롯 2개로 동시 실행을 제한한다.
검토 화면의 `나가기`도 초기 검토 상태에서는 서버 취소가 성공한 뒤 이동하며, 실패하면 재시도할 수 있다.
확정된 등록 정보를 수정하는 화면에서는 이미 제거된 이미지를 다시 요청하지 않는다.
취소된 작업은 MySQL 상태 제약조건에 맞춰 검토 시각과 미확정 구조화 결과를 비우고 작업 이력만 유지한다.
확정된 복약 정보는 이 취소 경로와 무관하게 보존한다.

삭제 요청 중 Redis 장애가 나면 이미지 API 접근은 즉시 차단하고 5분 주기 정리 작업이 재시도한다.
Redis TTL도 남은 보관을 제한한다. 메모리 저장소가 재시작되면 검토 중인 사진도 복구할 수 없으며,
이미 준비된 구조화 결과는 사진 없이 확인·저장할 수 있다. 처리 완료 전에 사진이 소실되면 재업로드가 필요하다.

이 구성은 애플리케이션 OCR 보존 범위를 제한하는 설계다. 외부 OCR 제공자의 보존 정책, 호스트 swap,
백업 시스템의 보존 여부는 이 문서나 코드만으로 인증되지 않았으며 별도 운영 검증이 필요하다.

## 레거시 디스크 파일 정리

새 도구는 [purge_legacy_ocr_images.py](../../scripts/purge_legacy_ocr_images.py)다. 기본 동작은
dry-run이며 파일명·이미지 내용은 출력하지 않고 후보 수와 바이트 수만 JSON으로 보고한다.

```powershell
python scripts/purge_legacy_ocr_images.py
python scripts/purge_legacy_ocr_images.py --root media/ocr-tmp
```

`--apply`는 API와 OCR worker를 중지한 유지보수 창에서만 `--maintenance-window`와 함께 사용한다.
도구는 삭제 직전 DB를 다시 읽고, 레거시 디스크 파일을 참조하는 `QUEUED`, `PROCESSING`, 또는 만료되지
않은 `READY_FOR_REVIEW` 작업이 하나라도 있으면 삭제를 거부한다.

```powershell
python scripts/purge_legacy_ocr_images.py --apply --maintenance-window
```

정리 대상은 구성된 `OCR_TEMP_DIR`(또는 명시한 `--root`) 바로 아래의 검증된 레거시 이름으로 한정한다:
32자리 UUID hex 원본 `.jpg`, `.jpeg`, `.png`, `.processed.jpg`, 그리고 60분 이상 지난 해당 원자적
쓰기 `.tmp` 파일이다. 심볼릭 링크/Windows reparse point, 하위 디렉터리, 경로 이탈, 메모리 키
`ocr-image:`는 무시한다. Redis 키는 읽거나 삭제하지 않으며, DB는 manifest·상태·만료시각 메타데이터만
읽고 OCR job, 도메인 데이터, 구조화 결과를 변경하거나 삭제하지 않는다.

DB manifest를 대조해 완료·실패·취소 또는 만료된 검토 작업의 참조 파일만 나이와 무관하게 후보로
삼고, 참조되지 않은 파일은 60분 이상 지난 경우에만 후보가 된다. 단, 원자적 쓰기 `.tmp` 파일은 terminal
참조 여부와 무관하게 반드시 60분 이상 지난 경우에만 후보가 된다. 적용 직전 파일의 장치·inode·크기·mtime를
재검사해 dry-run 이후 바뀐 파일은 삭제하지 않는다. 원본 이미지를 백업하거나 복사하지 않는다.

## 현재 상태와 검증 범위

이 설계와 도구는 아직 프로덕션에 배포되지 않았다. 9월 12일의 레거시 파일 139개 관찰은 로컬 시점의
관찰일 뿐, 9월 13일 현재 상태를 의미하지 않는다. 실제 운영 파일 삭제는 이 작업에서 수행하지 않았다.

정리 도구 단위 검증은 합성 임시 파일만 이용한다. 활성 manifest 보호, 만료 검토 작업 처리,
60분 고아 파일 기준, dry-run/집계 출력, 유지보수 게이트, 심볼릭 링크 차단을 다룬다. DB 서비스, Redis,
Docker, 네트워크, 실제 환자 이미지에는 접근하지 않는 테스트다.

별도의 로컬 통합 검증에서는 임시 합성 계정과 메모리에서 만든 한글 약봉투를 사용했다.
Nginx → 실제 API → ARQ worker → CLOVA 처리 후 원본 PNG와 전처리 JPEG가 모두 200으로 조회됐고,
확정(200) 후 구조화 정보가 남으면서 두 이미지 API는 404, 취소(204) 후에도 두 이미지 API는 404였다.
`/app/media/ocr-tmp` 파일 139개의 크기·수정시각 목록은 전후 동일했고 새 OCR 파일은 0개였다.
합성 계정과 해당 복약·OCR 레코드는 검증 후 제거했다. 실제 환자 정보나 보고서를 발송하지 않았다.

최종 로컬 검증:

- 백엔드 OCR·업로드·레거시 정리·worker·Compose 회귀: `195 passed, 3 subtests passed`
- 프런트엔드 원본/전처리 전환, 확정, 완료 후 수정, RAM 소실, 검토 이탈: Playwright `8 passed`
- 모바일 375px·데스크톱 1280px 확대 미리보기 스크린샷을 전환 완료 후 직접 확인
- `pnpm typecheck`, Ruff, 변경 구간 `git diff --check` 통과
- 신규 업로드/메모리 저장소와 OCR router의 scoped MyPy 검사 통과
- 실제 Redis 키 0개, Nginx client/proxy 임시파일 0개, 내부 네트워크 참여자는 API·OCR worker·이미지 Redis뿐
- 공유 테스트 DB 병렬 실행 충돌 후 테스트를 직렬 재실행한 위 최종 결과를 기준으로 함

수정은 미커밋 상태다. 운영 배포, 커밋·푸시, 기존 139개 이미지 삭제는 수행하지 않았다.

자동 검증의 범위 밖 실패도 숨기지 않는다: 전체 등록 화면 E2E 실행은 41개 통과·5개 실패였으며,
실패는 홈 인증/복약 상태·토스트 시나리오다. 해당 코드와 테스트 구간은 이번 OCR 수정 대상이 아니며
일괄 통과로 간주하지 않는다. 기존 OCR 작업 서비스의 MyPy 타입 오류는 HEAD 원본에서도 재현되며
이 작업에서 무관한 모델 타입 선언을 바꾸지 않는다.
