# OCR stage_results 통합 저장 — 2026-09-07

> 이 문서의 적용 이력·수치는 원본 `906/AH_05_05` 로컬 DB에서 확인한 역사적 결과다. Git 폴더에서는 팀의 31번 이메일 인증 마이그레이션을 보존하고, 병원명을 **32번**, 이 문서의 envelope 이전을 **33번 `33_20260907223001_stage_results_envelope.py`**으로 배치했다. Git 대상 DB에는 적용하지 않았다. 원본 31·32번이 이미 적용된 DB에는 이 체인을 그대로 실행하지 말고 별도 이력 정합 절차가 필요하다. [Git 통합 기록](ocr-git-integration-20260907.md).

## 적용 결과

`stage_results`를 `{"timings": ..., "stages": [...]}` 구조로 변경했다. 애플리케이션에서 조회·직렬화하면 `timings`가 먼저, `stages`가 뒤에 온다. 공개 상태 API의 기존 `timings` 응답 형태는 유지한다.

- `timings`: 기존 `queueWaitMs`, `persistMs`, `totalMs`. 측정하지 않은 경우 `null`이며 추정값을 생성하지 않는다.
- `stages`: 기존 단계 배열 전체를 보존한다. 단계명, 상태, **단계별 `elapsedMs`**, 호출 횟수, 코드가 그대로 들어간다.
- 기존 배열형 기록도 읽을 수 있다. 기존 5단계/새 6단계 검증과 약품 인식 로직은 바꾸지 않았다.
- `totalMs`는 큐·재시도 대기를 포함한 작업 전체 경과 시간이며, 단계별 시간의 합으로 바꾸지 않았다.

MySQL JSON 컬럼은 키를 자체 정렬한다. 실제 DB의 JSON 원문은 `stages`가 먼저 보일 수 있으며, ORM의 JSON decoder에서 `timings → stages` 순서를 복원한다. 표시 순서를 위해 JSON 컬럼을 TEXT로 바꾸지는 않았다. [MySQL 공식 문서](https://dev.mysql.com/doc/refman/8.0/en/json.html).

## 기존 데이터 이전

32번 `32_20260907220000_stage_results_envelope.py`는 데이터 전용 마이그레이션이다. 열/타입 변경이 없어 `MODELS_STATE`는 31번과 동일하다. 과거 마이그레이션 파일은 수정하지 않았다.

- 기존 배열을 `stages`로 감싸고 `input_manifest.timings`를 새 `timings`로 옮긴 다음 manifest에서 제거한다.
- 단계가 없더라도 기존 timings가 있으면 해당 값과 `stages: null`을 보존한다. 단계·타이밍 모두 없던 SQL NULL 기록은 그대로 둔다.
- 이미 객체인 기록, 미지 구조, 비객체 manifest는 덮어쓰지 않는다.
- downgrade는 알려진 두 키 구조만 복원하며, 타이밍 충돌이나 추가 메타데이터가 있으면 보존한다. 측정값 부재인 JSON null은 downgrade에서 manifest 키 부재로 정규화된다.
- upgrade/downgrade의 SQL 대입 순서는 MySQL의 좌→우 평가에 맞춰 원본 값을 복사한 뒤 제거하도록 구성했다.

로컬 실행 DB 적용 직전 활성 OCR/큐가 각각 0건임을 확인하고 worker를 중지했다. Aerich 적용과 전후 검증을 같은 트랜잭션으로 감쌌고, 검증 실패 시 적용 이력과 데이터 모두 롤백되도록 실행했다.

실제 적용 결과:

- 기존 **92개 행의 모든 컬럼**을 메모리에서 전후 비교했다. 요청된 두 JSON 필드 변환 외의 값은 모두 동일했다.
- 기존 단계 기록 **30건** 이전, 기존 타이밍 **5건** 이전.
- 적용 후 legacy 배열 0건, 새 객체 30건, manifest timings 0건.
- ORM 조회에서 새 객체 30건 모두 `timings`, `stages` 순서임을 확인했다.
- 최신 적용 이력은 32번이며 미적용 migration은 없다.
- worker 재시작 후 22:00:52 KST health check 통과(`ongoing=0`, `queued=0`; 새 health 레코드 22:00:21).

## 검증

- 새 저장 순서·legacy/envelope 조회 테스트 2개가 수정 전 실패하고 수정 후 통과했다.
- 데이터 이전 테스트는 no-op 구현에서 실패 후, 실제 MySQL 테스트 DB에서 upgrade 2회 → downgrade 2회 → upgrade의 값 보존을 통과했다.
- 충돌·미지 구조 보존, 빈 기존 단계 배열 보존, timing 후속 저장 실패, 즉시 사용자 확정, 기존 DB 게시 장애 회귀도 확인했다.
- OCR 관련 전체 검사 **520 passed (25.12초)**. OCR 모델 메타데이터 별도 **2 passed**.
- `ruff check app tests`, 수정 Python 4개 format check, scoped `git diff --check` 통과.
- 변경 모델 자체 타입 검사(`mypy --follow-imports=silent app/models/ocr.py`) 통과. 모델을 포함해 의존성까지 확장한 타입 검사는 기존 코드 영역 12개 파일에서 90개 오류가 남아 있으며 전체 타입 검사 통과로 표현하지 않는다.
- 전체 모델 메타데이터까지 확장한 검사에는 범위 밖 기존 실패 2개(사용자 알림 기본값, 삭제된 채팅 score 필드 기대)가 있다. 해당 모델/테스트는 수정하지 않았다.

## 변경 파일과 검토

구현: `app/models/ocr.py`, `app/services/medication_guide_ocr_jobs.py`.
데이터 이전: `app/core/db/migrations/models/32_20260907220000_stage_results_envelope.py`.
회귀: `app/tests/ocr_apis/test_medication_guide_ocr_job_service.py`.
설명: 이 문서, `ocr-stage-timings-20260907.md`, `ocr-v3-schema-pipeline-summary.md`.

`ce-simplify-code`의 재사용/품질/효율 검토에서 빈 배열 보존 경계가 발견되어 별도 실패 회귀를 확인한 뒤 수정했다. 최종 독립 읽기 전용 QA는 이번 변경 범위 내 차단 이슈 없음으로 판정했다.

Code review: skipped (ce-code-review unavailable) — 브랜치 diff 전용 범위 규칙이 미추적 신규 migration을 제외하고 대량의 기존 사용자 WIP를 포함하므로 이번 변경만 안전하게 검토하는 범위를 표현할 수 없어 중단했다. 대신 신규 migration을 포함한 지정 파일의 변경 부분만 수동 검토하고 독립 QA를 완료했다.

`906/AH_05_05` 로컬 복사본에 미커밋 변경으로 남겼다. 커밋·스테이징·브랜치 작업·push·별도 Git 폴더 반영은 하지 않았다. 외부 OCR/LLM 재호출이나 과거 OCR 작업 재실행도 하지 않았다.
