# #281 챌린지 프론트 목업 검토

## 범위

- 검토 브랜치: `feature/281`
- 공식·맞춤·나만의 챌린지, 배지, 홈·마이페이지 진입 화면.
- 새 API, 서버, DB, 마이그레이션은 없습니다. 실제 복약/영양제 데이터와 연결하지 않습니다.
- 챌린지 데이터와 인증은 브라우저 내부 예시 상태입니다. 새로고침하면 초기 목업으로 돌아갑니다.
- 예시 기준일은 2026-09-13입니다. 실제 오늘 날짜나 실제 건강 기록을 의미하지 않습니다.
- 배지함은 필터 없이 전체 노출합니다.

## 실행 — WSL 전용

```bash
cd /mnt/c/dev/AH_05_05/frontend
# 현재 장비의 기존 Node 22가 필요하면:
export PATH=/home/sdh080200/.nvm/versions/node/v22.23.1/bin:$PATH
pnpm dev --host 0.0.0.0
```

로그인 없이 `/dev/challenges`에서 확인할 수 있습니다. Windows 테스트 및 npm 명령은 사용하지 않습니다.

## 주요 경로

| 화면 | 경로 |
| --- | --- |
| 챌린지 마이 | `/dev/challenges` |
| 둘러보기 | `/dev/challenges/browse` |
| 공식 참여 전 | `/dev/challenges/official/official-water-7d` |
| 공식 주간 목표 | `/dev/challenges/official/official-stretch-weekly` |
| 공식 모집 종료 | `/dev/challenges/official/official-ended` |
| 공식 진행 | `/dev/challenges/participations/part-official-active` |
| 달성 결과 | `/dev/challenges/participations/part-official-achieved` |
| 미달성 결과 | `/dev/challenges/participations/part-official-missed` |
| 맞춤 챌린지 | `/dev/challenges/tailored` |
| 맞춤 데이터 없음 | `/dev/challenges/tailored-empty` |
| 복약 대상 선택 | `/dev/challenges/tailored/medication` |
| 영양제 대상 선택 | `/dev/challenges/tailored/supplement` |
| 나만의 챌린지 | `/dev/challenges/create` |
| 기록 돌아보기 | `/dev/challenges/participations/part-review-active` |
| 진료 준비 | `/dev/challenges/participations/part-visit-active` |
| 내 배지 | `/dev/challenges/badges` |
| 배지 없음 | `/dev/challenges/badges-empty` |
| 배지 상세 | `/dev/challenges/badges/badge-walk` |

## 확인할 흐름

1. 둘러보기 → 공식 상세 → 참여하기 → 개인 수행 기간 확인.
2. 마이 카드에서 직접 했어요 → 진행 수치 갱신 → 같은 날 중복 인증 불가.
3. 복약·영양제 카드에는 기록 버튼 없이 자동 연동 안내만 표시.
4. 맞춤 챌린지 → 대상 여러 개 선택 → 선택한 대상 요약 확인.
5. 나만의 챌린지 → 매일/주 몇 회 전환 → 날짜·기간 입력 → 생성.
6. 기록 돌아보기 → 항목 열기 → 해당 기간 목업 확인 → 돌아오면 확인 표시.
7. 기록 없음/오류는 정상 열람 완료로 처리하지 않음.
8. 내 배지 → 전체 목록 → 획득/미획득 상세.
9. 홈 챌린지 요약에는 직접 인증 버튼 없음; 더보기로 마이 이동.

## 검증 명령 — WSL

```bash
pnpm exec tsc --noEmit
pnpm build
PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44284 pnpm exec playwright test tests/e2e/challenges-*.spec.ts --workers=1 --output=test-results-281-final
```

기존 WSL Playwright Chromium을 사용합니다. `PLAYWRIGHT_CHANNEL`을 지정하지 않으면 기존 테스트 설정의 Chrome이 유지됩니다.

피그마 기준: `3qUR2z0rh6aYJfeJSxiUmg`의 `722:782` 챌린지 섹션. '맞춤 챌린지' 명칭, 필터 제거, 기간별 기록 목업 연결은 사용자 후속 합의를 우선 적용합니다.

## 최종 검증 — 2026-09-07

- WSL Chromium 챌린지 E2E: 29/29 통과. 14개 화면을 320/375/390/430px에서 검사하고 390px 캡처를 남겼습니다.
- WSL 타입 검사 및 `pnpm build`: 통과. 번들 500kB 초과 경고는 남아 있습니다.
- 기존 홈·마이 회귀: 24/25 통과. `home-figma-overhaul.spec.ts:9`는 변경 전에도 실패한 `:scope > div` locator 타임아웃이 동일하게 재현됐습니다. 이번 작업에서는 기존 복약 테스트를 우회하거나 삭제하지 않았습니다.
- 독립 코드 검수에서 발견한 대상 선택 재진입 초기화와 목업 표시 누락은 수정 후 재검수 완료했습니다.
- 배지 PNG 4종은 내장 imagegen으로 생성했습니다. 파일과 프롬프트는 `public/images/challenges/README.md`를 참고하세요. 일부 미획득 배지는 같은 임시 이미지를 재사용합니다.
- 주간 공식 챌린지 상세는 별도 피그마 프레임이 없어 기존 공식 상세 구조에 주간 횟수/기간 문구를 적용했습니다. 실제 데이터 연결 전 추가 검토 대상입니다.
