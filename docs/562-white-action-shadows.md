# #562 — 흰색 실행 버튼 그림자 축소

사용자 승인 범위: 흰색 실행 버튼이 초록 버튼보다 커 보이는 깊이감을 줄이되 실제 크기와 터치 영역, 초록/위험 버튼 스타일은 유지한다.

## 변경

- 공통 `Button`의 활성 secondary 기본/hover/pressed 그림자만 축소. 기존 테두리, radius, 높이, padding, transform, 비활성 스타일 유지.
- `shadow-white-action` 토큰: 바깥 그림자 `0 1px 2px / 6%`, 하단 inset `0 -1px 1px / 5%`.
- 별도 실행 버튼 적용: 복용약 기간 필터·복약 메모, 영양제 기본정보 입력 안내·복용 정보 수정, OCR 이미지 확대뷰 닫기.
- `shadow-card`와 공통 Card는 유지. 처방/제품/프로필 등의 큰 정보 카드는 변경하지 않음. 원래 그림자가 없는 흰색 컨트롤에도 새 그림자를 추가하지 않음.
- 입력·날짜·달력에는 변경 없음.

## 검증

새 회귀 테스트는 실제 `/dev/gallery`, `/dev/medications`, `/dev/supplements` mock 데이터 화면을 방문한다. HTML 재구성이나 screenshot용 CSS 대체는 사용하지 않았다.

- RED: 변경 전 390px·1280px 두 케이스 모두 그림자 깊이 조건에서 실패. 공통 흰색 바깥 그림자 offset+blur는 9px, 카드 그림자를 쓰던 실행 버튼은 26px.
- GREEN: 변경 후 둘 다 3px 이하. 기존 control 회귀 9개 포함 총 11개 통과.
- `tsc --noEmit` 및 `git diff --check` 통과. 테스트용 44562 서버 종료 확인, 기존 44556/44559 서버 유지.
- 전후 JSON 비교: 모든 측정 버튼의 width/height 동일, primary/report/danger 및 gallery 정보 카드 스타일 완전 동일.
- 390px gallery 흰색/초록 버튼 각각 348×52px. 1280px에서는 각각 1054×52px. 기간 필터는 높이 44px 유지.
- 기존 369 테스트의 흰색/초록 그림자 동등 조건만 승인한 디자인 변경에 맞춰 제거하고 테두리·radius·height·pressed transform 동등 및 disabled 입력 차단 검사는 유지.
- 최초 기존 테스트 cold-load 10초 timeout 1건은 `--timeout=30000`으로 재실행하여 통과. worker는 1개.

재현 명령(WSL, frontend 디렉터리):

```bash
PLAYWRIGHT_TEST_PORT=44562 PLAYWRIGHT_CHANNEL=chromium \
UI562_SCREENSHOT_DIR=/mnt/c/dev/AH_05_05/artifacts/562-white-buttons/after \
UI562_BASELINE_DIR=/mnt/c/dev/AH_05_05/artifacts/562-white-buttons/before \
node node_modules/playwright/cli.js test \
  tests/e2e/562-white-action-shadows.spec.ts \
  tests/e2e/369-clay-controls-followup.spec.ts \
  --workers=1 --timeout=30000 --output=../artifacts/562-white-buttons/test-results
```

## 스크린샷

`artifacts/562-white-buttons/{before,after}/`에 390·1280px 동일 viewport 결과를 보존했다. screenshot은 finite animation 종료 후 촬영한다.

- `gallery-390.png`, `gallery-1280.png`: 흰색/초록 공통 버튼과 그대로인 정보 카드.
- `medications-390.png`, `medications-1280.png`: 복약 실제 목록과 기간 필터·초록 보고서 버튼.
- `medication-dialog-390.png`, `medication-dialog-1280.png`: 취소·삭제 버튼 비교.
- `supplement-detail-390.png`, `supplement-detail-1280.png`: 영양제 복용 정보 수정 버튼과 그대로인 제품/기록 카드.
- `metrics-390.json`, `metrics-1280.json`: 전후 geometry와 computed style.

스크린샷은 로컬 검토용 산출물이며 커밋에는 코드·테스트·이 문서만 포함한다.
