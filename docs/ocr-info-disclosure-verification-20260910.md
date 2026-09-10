# OCR 약 정보 줄바꿈·접기 검증

- 작업 브랜치: `codex/ocr-info-disclosure`
- 작업공간: `C:/dev/AH_05_05/.codex-work/ocr-info-disclosure`
- 기준: fetched `origin/main` `8aedd440c64ca6c97b5296e763a8bdb258d24aab`
- 루트 `feature/315`, API, DB, 워커, 마이그레이션은 변경하지 않았다. 이 문서는 기능별 로컬 선별 커밋에 포함하며 원격 push는 실행하지 않는다.

## 구현 범위

`frontend/src/pages/ocr-review/OcrReviewPage.tsx`의 OCR 결과 약 카드만 변경했다.

- 긴 약 이름은 전체 줄바꿈하며 신뢰도 배지는 접힘 여부와 관계없이 표시한다.
- 카드 제목과 오른쪽 꺾쇠는 상세를 접고 펼친다. 기본은 접힘이다.
- 펼친 상세는 함량 / 1회 투약량 / 1일 횟수 / 투약일수를 각각 한 행에 표시한다.
- 기존 함량·투약량 표시 정규화와 `미추출`, `필요 시`, 일수 의미를 유지한다.
- 별도 연필 `수정` 버튼에서 기존 편집 다이얼로그를 연다. 버튼 중첩은 없다.
- 확정된 읽기 전용 결과도 정보를 펼칠 수 있지만 수정 버튼은 없다.
- 기존 `확인 필요` 경고 및 저장 전 검토 확인, 저장 payload, 직접 추가/삭제/재촬영 흐름은 유지한다.
- 기존 안내 중 ‘아무 항목이나 눌러 고칠 수 있어요’만 새 편집 진입점에 맞게 정정했다.

## 자동 검증

- 변경 전 OCR 표시 회귀 6개 통과.
- 신규 테스트 4개를 먼저 실행하여 상세 토글 및 수정 버튼 부재로 RED 확인.
- 실제 API 모드의 요청 경계를 fixture로 대체한 E2E 53개 통과(2.4분):
  - `ocr-info-disclosure.spec.ts`
  - `ocr-strength-display.spec.ts`
  - `medication-registration-flow.spec.ts`
- mock 모드의 기존 저신뢰 OCR 수정 회귀 1개 통과(27.9초).
- 타입 검사 통과.
- 프로덕션 빌드 통과(56.51초). 기존 주 번들 500KB 초과 권고 경고만 남는다.
- `git diff --check` 통과.

기존 테스트의 ‘약명 + 함량’ 한 줄 기대값을 현재 main의 약명 단독 정책에 맞추고,
홈 직접 진입 3개 테스트에서 미목킹 부가 API 요청이 실제 서버로 나가지 않도록 fixture를 보완했다.
해당 시간 설정/홈 운영 코드는 변경하지 않았다.

## 스크린샷

아래는 생성 이미지가 아니라 API fixture를 사용한 실제 앱 브라우저 렌더다.

- `frontend/test-results-ocr-disclosure/ocr-collapsed-320.png`
- `frontend/test-results-ocr-disclosure/ocr-expanded-320.png`
- `frontend/test-results-ocr-disclosure/ocr-collapsed-390.png`
- `frontend/test-results-ocr-disclosure/ocr-expanded-390.png`

320/390px 모두 수평 넘침 없이 긴 이름, 경고, 네 정보행과 수정 버튼을 확인했다.
기존 추적 스크린샷 `frontend/test-results-ocr-display/ocr-strength-dedup-{375,1280}.png`도 새 UI로 갱신되었다.
RED/중간 실행 로그 폴더는 로컬 검증 자료이며 제출 코드가 아니다.

## 사용자 확인 순서

1. OCR 결과에서 긴 약 이름과 `확인 필요`가 접힌 상태에서도 전부 보이는지 확인한다.
2. 제목 또는 꺾쇠를 눌러 네 상세행을 확인하고 다시 접는다. Enter로도 토글할 수 있다.
3. `수정`을 눌러 기존 원본 값으로 편집창이 열리는지, 저장하면 바뀐 값이 상세에 반영되는지 확인한다.
4. 빈 추출값은 `미추출`, 필요 시 복용은 `필요 시`로 구분되는지 확인한다.
5. 저장된 확정 결과는 펼칠 수 있고 수정할 수 없는지 확인한다.
6. 직접 추가/삭제, 저신뢰 검토 확인, OCR 저장 후 복약 시간 설정 이동이 기존처럼 동작하는지 확인한다.

실제 사진 OCR 엔진 재판독 및 실 DB 저장은 이번 표시 변경 검증에서 실행하지 않았다.

## 2026-09-10 선별 커밋 전 재검증

WSL Node `v22.23.1`에서 타입 검사와 프로덕션 빌드를 새로 실행하여 통과했다. 빌드는 1분 44초이며 기존 500 kB 초과 번들 권고 경고만 남는다.

위 세 API fixture E2E 파일을 새로 실행한 결과 52개 통과, 기존 polling 간격 검사 1개 실패였다. 실패값이 `-693 ms`로 나타나 호스트 시계 보정에 영향을 받는 `Date.now()` 기반 경과 시간 측정을 `performance.now()`로 변경했다. 해당 검사만 다시 실행하여 1개 통과했다. 최종적으로 53개 검사의 통과 근거를 확보했으며 polling 주기와 UI 운영 코드는 변경하지 않았다.

`medication-feature-252.spec.ts`의 저신뢰 OCR 수정 mock 회귀도 별도로 새로 실행하여 1개 통과했다(19.7초).

API fixture 실행은 `PLAYWRIGHT_TEST_PORT=44402`, `PLAYWRIGHT_CHANNEL=chromium`, `--workers=1 --timeout=60000`을 사용했다. `VITE_API_BASE_URL=/api`, `VITE_API_PROXY_TARGET=http://127.0.0.1:9`를 강제하여 누락된 fixture 요청도 실제 백엔드·DB로 나가지 않도록 했다. 최초 10초 제한 실행은 cold start 로딩에서 중단했고, 다음 실행에서 이전 runner의 서버 정리로 연결이 끊겨 별도 수명의 fixture 서버를 띄운 뒤 최종 검증을 수행했다.

스크린샷, `test-results-ocr-*` 실행 폴더와 기존 추적 PNG 2개의 변경은 로컬에 보존하고 커밋에서 제외한다. 운영 코드, 관련 테스트 4개 파일 및 이 검증 문서만 선별 커밋한다.
