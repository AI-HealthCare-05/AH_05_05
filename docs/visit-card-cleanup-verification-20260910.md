# 진료일정 카드 병원명 중복 제거 검증

- 브랜치: `codex/visit-card-cleanup`
- 기준 커밋: `8aedd440c64ca6c97b5296e763a8bdb258d24aab`
- 변경: `FollowUpVisitsPage.tsx`의 다가오는 일정 카드에서 병원명을 반복하던 하단 행을 제거하고, 카드 높이를 내용에 맞추며 긴 병원명 줄바꿈을 허용했다.
- 날짜, 남은 일수, 병원·시간 요약과 기존 편집 진입 동작을 유지한다.

## 2026-09-10 선별 커밋 전 재검증

WSL Node `v22.23.1`에서 다음 검사를 새로 실행했다.

- `node node_modules/typescript/bin/tsc --noEmit`: 통과.
- `node node_modules/typescript/bin/tsc -b && node node_modules/vite/bin/vite.js build`: 통과. 기존 500 kB 초과 번들 권고 경고만 남는다.
- `follow-up-visit-card.spec.ts`와 `follow-up-visits-api.spec.ts`: 4개 통과. 320/390 px에서 병원명 1회 표시, 긴 영문 병원명 수평 넘침 없음, 원래 일정 편집창과 등록·수정 요청 payload를 확인했다.
- `follow-up-visits.spec.ts` mock 회귀: 10개 통과. 미정 값, 한국 날짜 경계, 시간 선택, 등록·수정·삭제와 좁은 화면 입력 안내를 확인했다.

브라우저 검사는 `PLAYWRIGHT_TEST_PORT=44403`, `PLAYWRIGHT_CHANNEL=chromium`, `--workers=1 --timeout=60000`을 사용했다. API 요청은 테스트 fixture로 처리하며 나머지 API 요청은 abort한다. 추가로 `VITE_API_BASE_URL=/api`, `VITE_API_PROXY_TARGET=http://127.0.0.1:9`를 지정하여 실제 백엔드·DB 접근을 차단했다.

초기 병렬 빌드 중 기본 10초 제한에서 페이지 로딩 시간 초과가 발생하여 해당 실행은 중단했다. 빌드 완료 후 60초 제한으로 새로 실행한 위 4개 검사가 통과했다. 로컬 실행 결과와 스크린샷은 `frontend/test-results-visit-*`에 보존하며 커밋에서 제외한다.

루트 `feature/315`, 백엔드, DB, 워커, 마이그레이션은 이 변경 범위에 포함하지 않는다. 원격 push, PR 생성 및 병합은 실행하지 않는다.
