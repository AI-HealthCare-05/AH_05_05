# ERD125 코드 정렬·마이그레이션 39·OCR 좌표 수정

2026-09-08. 검증된 `906/AH_05_05` 변경을 `git/AH_05_05`로 파일 단위 반영했다. Git 폴더의 38번까지 이력을 보존하여 새 마이그레이션은 39번이다. 실제 서비스 DB 적용·커밋·push는 하지 않았다. 아래 검증 수치는 원본 작업 근거이며, Git 폴더 재검증은 문서 마지막에 별도로 기록한다.

## 반영 계약

- `care_episodes`: `title`, `diagnosis`, `surgery`, `discharge_date`, `started_at`, `default_end_at`, `planned_end_at` 제거. `completed_at`, `hospital_name` 유지.
- `alias`: nullable VARCHAR(255). 사용자 지정 별칭 우선, 지정하지 않은 신규 OCR 처방은 병원명을 기본 별칭으로 사용한다. 명시적인 null은 허용한다. OCR 재확정 시 기존 사용자 별칭을 보존한다. UI는 별칭이 없으면 조제일 처방, 조제일도 없는 수동 기록은 처방 번호로 표시한다.
- `care_advices`, `recovery_guides`, `recovery_guide_sources` 및 관련 chat/alarm FK·응답 필드를 제거한다. 무관한 알림 설정과 제품 `medication_guide_id`는 유지한다.
- 폐기된 환자 근거 종류·필드를 enum 및 DB CHECK에서 제거한다. `CARE_EPISODE_FIELD`는 `MEDICATION_DAYS`만 허용하며 null로 CHECK를 우회할 수 없다.
- API·프런트 별칭 길이를 255자로 통일하고, 메모의 `careEpisodeTitle` 의존성을 제거했다. 긴 별칭은 화면 폭 안에서 줄바꿈한다.
- 독립 리뷰에서 `ai_worker`의 직접 참조 누락을 찾아 함께 수정했다. 실채팅 `DbPatientContextProvider`는 더 이상 삭제 모델/임상 열을 조회하지 않고, 약·복용 시작·외래 일정만 읽는다. 공용 오프라인 `PatientContext` 스키마의 임상/권고 필드는 빈 기본값으로 남기며 OCR에서 추정하지 않는다. 호출자가 없고 삭제 테이블에만 저장하던 `RecoveryGuideRepository` 및 해당 저장 테스트는 제거했다. JSON 기반 독립 가이드 데모·생성기 계약은 DB 저장 기능과 분리해 보존했다.

## 마이그레이션 적용 전 필수 조건

대상 파일: `app/core/db/migrations/models/39_20260908000000_align_erd125_care_episodes.py`.

1. 운영 담당자가 대상 DB와 Aerich 이력(38까지), 기존 스키마와 FK/CHECK 이름을 확인한다. 코드·마이그레이션을 동일 릴리스로 배포한다. 이 문서는 실행 승인이 아니다.
2. API, OCR worker 및 해당 DB의 모든 쓰기 작업을 중지하고 유지보수 상태로 전환한다. 백업 후에도 쓰기를 재개하지 않는다. 온라인/무중단 마이그레이션이 아니다.
3. 전체 스키마·데이터·Aerich 이력을 포함한 외부 암호화 스냅샷/덤프를 만들고 별도 DB에서 복구 가능성을 검증한다. CTAS 백업만으로는 인덱스·FK·CHECK 등의 원래 DDL이 복원되지 않는다.
4. `_m39_backup_*`가 이미 있으면 실행하지 않는다. 실패한 이전 시도인지 조사하고 백업과 현재 스키마를 보존한다. 재실행을 위해 백업을 임의 삭제하거나 `IF NOT EXISTS`를 붙이지 않는다.
5. 복제/검증 DB에서 먼저 업그레이드·서비스 확인을 수행한 후, 운영 절차에 따라 기존 Aerich upgrade 경로로 적용한다. MySQL DDL은 암묵적으로 커밋되므로 SQL 트랜잭션으로 전체 변경을 되돌릴 수 없다.

## 삭제 전 보존 데이터

마이그레이션은 다음 7개 테이블에 데이터를 복사하고 건수를 대조한 뒤 앱 테이블을 변경한다.

| `_m39_backup_` 뒤 이름 | 보존 내용 |
| --- | --- |
| `care_episode_removed` | 처방 id, 삭제 열, 변경 전 alias |
| `care_advices` | 제거 테이블 전체 행 |
| `recovery_guides` | 제거 테이블 전체 행 |
| `recovery_guide_sources` | 제거 테이블 전체 행 |
| `chat_message_sources_removed` | 폐기되는 근거 종류/필드 또는 care_advice 참조가 있는 전체 행 |
| `chat_message_guide` | chat message id와 기존 guide id |
| `alarm_source_guide` | alarm id와 기존 source guide id |

별칭은 기존 비공백 별칭의 양끝 공백을 정리해 유지하고, 없으면 비공백 `hospital_name` 원문을 복사하며, 둘 다 없으면 null로 둔다. `completed_at`과 병원명 원문은 변경하지 않는다. 폐기된 채팅 근거는 활성 테이블에서 삭제되므로 기존 답변의 해당 출처 표시가 사라질 수 있다. 답변 본문 자체는 삭제하지 않는다.

백업 테이블에는 의료·개인정보가 포함될 수 있다. 밑줄 이름은 보안 장치가 아니다. 운영 담당자는 DB 권한 최소화, 암호화, 일반 분석·export 대상 제외, 접근 감사 및 승인된 보존 기간을 적용해야 한다. 삭제 책임자와 보존 기한을 배포 전에 정하고, 복구 기간 종료 후 승인된 보안 삭제 절차로 별도 정리한다. 마이그레이션은 백업을 자동 삭제하지 않는다. 문서·로그에 실제 백업 내용이나 환자 정보를 남기지 않는다.

## 실패·복구

- SQL 중간 실패 시 API/worker를 계속 중지한다. 부분 적용 스키마, Aerich 이력, 외부 스냅샷, 7개 백업을 대조해 담당자가 복구/전진 수정을 결정한다. 자동 재시도 금지.
- `downgrade()`는 DB 접근 전에 오류를 발생시킨다. 업그레이드 이후 생성된 행, 50자 초과 별칭 및 출처 id 충돌 때문에 자동 역변환은 무손실을 보장할 수 없다.
- 복구는 먼저 별도 DB에서 원래 DDL과 외부 스냅샷을 복원한다. 업그레이드 이후 변경분을 별도 보존·대조하고, 처방/근거 id 충돌 및 긴 별칭 처리 방침을 확정한 후 검증된 DB와 구버전 코드를 함께 전환한다. 구버전 코드만 먼저 재시작하지 않는다.

## OCR 변경과 검증 범위

- 병원명은 전역 Y행 전체가 아니라 X축 간격으로 분리한 영역에서 판별한다. 왼쪽 영수증의 부담금/금액이 오른쪽 병원명에 붙는 좌표 회귀를 추가했다.
- 조제일은 라벨 자체의 bbox와 오른쪽·아래 날짜를 연결한다. 위쪽의 큰 다음 방문일이나 먼 영수증 날짜를 사용하지 않는다. `조제` / `일자`처럼 인접한 라벨 분할은 제한적으로 연결한다.
- 좌표 테스트는 원본 관찰에 근거한 합성 fixture이며 1배/3배 크기 및 방향·분할 케이스를 검증했다. 외부 OCR 제공자를 원본 이미지로 재호출한 성공 결과를 의미하지 않는다.

## 검증 근거

- OCR·관련 모델 테스트: 469 passed (`tests/ocr_v3`, `tests/ocr`, 새 episode 계약, 별칭 스키마).
- 관련 백엔드 API: 119 passed (처방·별칭 메모·일정·알람·OCR 확정·채팅 이력·알림 설정). 서비스 DB/Redis가 아닌 별도 포트의 임시 컨테이너에서 실행했다.
- Git 폴더 마이그레이션 재검증: 격리 MySQL 8.0에서 기존 이력 48개(번호 0~38, 중복 번호는 파일명 순)를 재현한 후 39를 검증했다. 백업·별칭·보존 열·제약·모델 스냅샷 일치·재시도 거부·downgrade 거부 3 passed. opt-in 실행: `ERD125_DISPOSABLE_MYSQL=1` 환경에서 `python -m pytest tests/migrations/test_erd125_care_migration.py -q`. 테스트는 고정된 localhost:43316 검증 서버에 임의 UUID DB만 생성·삭제한다.
- 긴 별칭 브라우저 회귀: 375/1280 viewport의 255자 저장·새로고침·메모 표시·가로 넘침 검사 2 passed. 양쪽 스크린샷을 직접 확인했다.
- 리뷰 보완: 메모 외 복약 목록 카드의 가로 넘침도 별도로 재현(2 failed)하고 줄바꿈 수정 후 2 passed. 카드·메모의 두 viewport 스크린샷을 다시 확인했으며 수정 후 production build도 통과했다.
- 기존 모델 메타데이터 테스트 2건은 이번 변경 이전 코드와 기대치가 충돌한다(`is_notify_*` 기본값 true 기대 vs 기존 false, `ChatSession.score` 기대 vs 기존 `is_like`). 이 변경에서 무관한 동작을 되돌리지 않았다.

- 최종 프런트 검증: `tsc -b` 및 Vite production build 통과. 기존 단일 JS chunk 500 kB 초과 경고는 남아 있다.
- 브라우저: `medication-feature-252.spec.ts` 21 passed, `chat-session-list-api.spec.ts` 6 passed. 후자는 `VITE_USE_MOCK=false`에서 테스트가 가로챈 API 응답을 사용하며 운영 서버 통합 검증은 아니다.
- AI worker 관련 65 passed: DB/JSON 환자정보 제공자, ChatCoreService, 채팅 유스케이스·근거·생성기·안전 검증, PatientContext, 독립 가이드 유스케이스. 처음 확인된 삭제 모델 import 오류를 재현한 뒤 수정·재검증했다.
- AI worker 전체 비통합 테스트 수집은 622건까지 수집했으나 PDF/RAG의 선택 의존성 `pypdf`, `langchain_text_splitters` 미설치로 12개 모듈 수집 오류가 남는다. 해당 경로는 이번 변경 범위가 아니며 전체 AI worker 통과를 주장하지 않는다.
- 변경 범위 Ruff 검사 통과, `git diff --check` 공백 오류 없음. 독립 읽기 전용 최종 리뷰는 보완 2건 확인 후 전달 가능 판정이며 ERD125 범위의 잔여 P0~P2 지적은 없다. 운영 적용 승인을 의미하지 않는다.
- 검증 종료 후 이번 작업에서 만든 MySQL/Redis 컨테이너 2개만 제거하고 잔존하지 않음을 확인했다. 기존 서비스 컨테이너와 DB는 변경하지 않았다.

## Git 폴더 반영 검증

- 대상: `git/AH_05_05`, 시작 HEAD `f80d6a2`. 시작 시 미커밋 변경 없음. 원본 변경을 파일 단위 반영했으며 merge/cherry-pick, 브랜치 변경, stage/commit/push는 실행하지 않았다.
- 기존 이메일 인증·챌린지 모델/enum/등록과 마이그레이션 0~38을 보존했다. 39의 `MODELS_STATE`는 대상 모델에서 재생성했고 51개 모델이 등록된다. 백업 테이블 이름도 `_m39_backup_*`로 구분한다.
- 대상에만 추가된 메모 필터·페이지네이션 응답 보호·다시 시도·전체 본문 표시, 이메일 인증 signup helper, 기존 envelope 마이그레이션 import 경로를 유지했다.
- OCR·모델·현재 AI worker 제공자/채팅 서비스: 486 passed, 1 skipped. skip은 Git에 없는 로컬 OCR-16 고정 증거 묶음이다.
- 격리 API 119 passed, 마이그레이션 3 passed. 실제 서비스 DB에는 적용하지 않았다.
- 브라우저 32 passed: 복약 21, 기존 메모 모아보기/필터 회귀 5, 채팅 목록 API 응답 연동 6. 긴 별칭 카드·메모 화면도 직접 확인했다.
- `tsc -b`, Vite production build, 전체 Ruff check/format 통과. 기존 대형 JS chunk 경고는 유지한다.
- 별도 읽기 전용 체인 감사에서 기존 FK·CHECK·인덱스 및 seed와 충돌 없음, 원본 SQL 대비 번호/백업 접두사 이외 동작 변경 없음 확인. 파일 이동 자체는 검증된 코드의 기계적 반영이며 새 기능을 추가하지 않았다.
- 대상 전용 ‘처방 메모만 보기’ 버튼의 긴 별칭 잘림은 화면 확인으로 발견해 줄바꿈을 추가했다. 2건 실패 재현 후 별칭/메모 필터 회귀 7 passed, 빌드 재통과 및 375/1280 화면 재확인.
- 시작 시 해시와 대조하여 범위 밖 추적 파일 1,360개의 바이트가 동일하고 HEAD·index가 바뀌지 않았음을 확인했다. 최종 변경은 기존 파일 43개(삭제 3개 포함)와 새 파일 4개이며 모두 미커밋 상태다.
