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

## 다중 처방·목업 홈 추가 검토

- `/dev/challenges` 하단 **홈** → `/dev/home-challenges`: 2026-09-13 저녁으로 고정한 검토 전용 홈입니다. 일반 `/challenges`의 홈 이동 및 실제 홈의 API·저장 동작은 변경하지 않았습니다.
- 기존 홈 복약 UI를 재사용합니다. 감기약과 9월 7일 처방이 보이며, 행을 선택한 다음 `먹었어요`로 해당 처방만 기록합니다. 선택하지 않고 누르면 두 처방을 함께 기록합니다.
- 기본 챌린지 대상은 감기약만입니다. 6/9회(67%) → 감기약 저녁 기록 → 7/9회(78%). 선택 대상이 아닌 다른 처방 기록은 달성률을 바꾸지 않습니다.
- `복약 챌린지 참여 처방 확인`에서 두 처방을 선택하면 9회 + 14회 = 23회로 합산합니다. 처음 6/23회(26%), 한 처방씩 기록하면 7/23회(30%) → 8/23회(35%)입니다.
- 같은 처방의 같은 날짜·시간대는 약이 여러 개여도 1회입니다. 반복 저장은 중복 집계하지 않으며, 완료한 행 선택 후 `복약 기록 되돌리기`로 취소할 수 있습니다.
- 상세에는 선택한 처방별 진행률과 전체 수치가 표시됩니다. 신규 처방을 자동 선택하지 않습니다. 복약에는 하루 한 번 인증으로 오해할 수 있는 일별 인증표를 표시하지 않습니다.
- 지난 기록은 처음에는 접히고, 펼치기/접기 가능합니다. 화면 재진입 시 다시 접힙니다.
- 복약과 챌린지 연동은 이 검토용 홈의 메모리 상태에만 적용됩니다. 실제 복약/영양제 API 연동은 없으며, 영양제 탭은 표시용입니다. 새로고침하면 모두 초기화됩니다.

추가 검증: WSL 타입 검사 및 챌린지 35/35 통과(52.5초). 기존 홈 회귀는 알려진 `:scope > div` 실패 1건을 제외한 14/14 통과(30초 테스트 한도, 39.9초). 처음 실행에서는 초기 로딩 타임아웃 1건이 있었고 위 조건으로 재실행했습니다. WSL 빌드 통과(번들 크기 경고 유지). 독립 검수에서 일반 홈 이동이 목업 경로로 바뀌는 문제를 발견해 dev 경로에만 적용하도록 수정하고 회귀 테스트/재검수했습니다.

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
