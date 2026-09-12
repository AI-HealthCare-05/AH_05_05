# #428 챌린지 정책 및 표시 검토

기준: `fbeda80f3796b6beec63061107f63faf90732f79`, 사용자 확정 결정 2026-09-12. 기존 참여는 보존하며, 동일 영양제 등록 ID가 하나라도 겹치는 새로운 ACTIVE 참여를 차단한다. 같은 상품의 별도 등록 ID를 합치는 정책은 추가하지 않았다.

| Notion 원문 | 판정 | 반영 내용 |
| --- | --- | --- |
| [홈 미참여 안내](https://app.notion.com/p/3d97226115e78047a029d36f244a7ec5) | fixed | 미참여 시 생활습관 개선 참여 안내, ACTIVE 참여는 있으나 오늘 일정이 없는 경우 별도 안내 |
| [지난 기록 진행 보기](https://app.notion.com/p/3d97226115e7808e9450e5d9889a43b4) | fixed | 지난 참여 상세의 다른 참여로 가는 하단 진행 보기 삭제. 과거 기록과 가능한 재참여 유지 |
| [마이·카드·구분 표시](https://app.notion.com/p/3d97226115e780158e43f329b445ccaa) | fixed / 별도 담당 | 공식·맞춤을 브랜드 청록·복숭아색으로 구분. 카드 전체 링크, 버튼 독립 동작, ACTIVE 카드의 중복 상태 문구 제거. 탭명 `나의 챌린지`는 #425 담당 |
| [홈 화살표·달성률·오늘 상태](https://app.notion.com/p/3d97226115e780a4ac6dcbc8e7c48275) | fixed / superseded | 화살표를 카드 아래로 배치. 공식 홈·목록·상세는 같은 진행률 함수, 맞춤은 기존 `customChallengeDayProgress` 공유. 일 단위 완료/목표 표시. 사용자가 확정한 `완료/미완료` 구분 적용, 완료 카드는 유지. 원문의 달성을 미완료로 바꾸는 문구는 확정 결정으로 대체 |
| [영양제 중복 선택](https://app.notion.com/p/3d97226115e78070ba67ef6d9c5adccd) | fixed | 이미 참여 중인 영양제 선택 비활성화, 기존 참여 링크 유지. 추천의 참여 가능 개수와 둘러보기 참여 중 판정도 같은 정책 적용 |
| [둘러보기 유형](https://app.notion.com/p/3d97226115e780f698d9d1cb3e47b214) | fixed | 각 항목 오른쪽에 공식·맞춤 표시 |
| [재참여 버튼 위치](https://app.notion.com/p/3d97226115e780c8a0fad8aa403fe9cc) | superseded / already implemented | 최신 결정은 하단 돌아가기 삭제이므로 재도입하지 않음. 취소 참여의 재참여 버튼 및 확인 흐름은 유지 |
| [영양제 부분 중복](https://app.notion.com/p/3d97226115e7800bbb10e0e942db36a7) | fixed | 서버의 완전 동일 집합 비교를 교집합 검사로 변경. 기존 User → source → settings 행 잠금과 요청 키 선확인 유지 |
| [모집기간·공식 상세 구분](https://app.notion.com/p/3d97226115e780288ea2cbb788399969) | already implemented / fixed | 모집기간은 이미 년월일 표기, 목록은 제목과 모집기간 구조. 공식·맞춤 참여 안내에 유형 박스 적용 |

## 검증

- TDD: 부분 중복 생성이 허용되는 API 실패 2건과 UI 미구현 실패를 확인한 뒤 수정했다.
- `python -m pytest --confcutdir=app/tests/custom_challenge_apis app/tests/custom_challenge_apis -q`: 94 passed. 인메모리 SQLite로 실행하며 실제 사용자 DB는 사용하지 않는다.
- 새 UI 테스트 `frontend/tests/e2e/428-challenge-policy.spec.ts` 9 passed. 기존 `304-official-challenges-api.spec.ts`와 `315-custom-challenges-api.spec.ts`에서 변경 관련 회귀 18개 passed. 변경된 정책 기대도 갱신했다.
- TypeScript `tsc --noEmit` 통과. 최종 브라우저 실행 결과와 명령은 외부 작업 보고서 `428-report.md`에 기록한다.
- 화면 캡처: `frontend/test-results/428-final/428-challenge-policy-home--7630c-y-s-completed-card-at-375px/{home-375,detail-375}.png`, `...home--d963b-y-s-completed-card-at-390px/{home-390,detail-390}.png`, `...home--2e5c8--s-completed-card-at-1280px/{home-1280,detail-1280}.png`. fixture 데이터만 사용하며 이미지는 커밋하지 않는다.

## 범위와 제한

- 공식 DAILY 인증은 일 단위, WEEKLY/TOTAL 인증은 서버 목표에 맞는 회 단위를 유지한다. 횟수 목표를 임의로 날짜 목표로 환산하지 않는다.
- SQLite 동시 요청 회귀는 한 요청만 성공함을 확인한다. MySQL 실제 행 잠금 동시성 통합 검사는 로컬 MySQL 서버가 없어 실행하지 못했다. 기존 트랜잭션 잠금 순서와 키 확인 순서는 변경하지 않았다.
- 날짜 스트립과 상세 뒤로 가기 동작, 공통 탭 스타일은 별도 이슈 소유 범위여서 변경하지 않았다.
- WSL Vite 테스트는 작업트리별 임시 캐시와 `CHOKIDAR_USEPOLLING=true`를 사용한다. 공유 캐시 충돌 및 Windows 편집 감지 실패를 제품 회귀와 구분했다.

## 사용자 추가 요청: 둘러보기 공식·맞춤 아코디언 (2026-09-12)

- 사용자 대화와 첨부 화면의 명시 요청이다. 별도 Notion 원본 링크는 제공되지 않았으며 추정하지 않는다. 실행 계획: `design-plans/428-browse-accordions.md`.
- 기존 종류 Select를 공식 챌린지·맞춤 챌린지의 독립 `ChallengeAccordion` 두 개로 대체했다. 기존 컴포넌트의 기본 접힘을 유지하고, 두 그룹을 동시에 펼칠 수 있다.
- 그룹별 개수·로딩·실패·빈 목록·재시도를 표시한다. 카드 렌더링은 공유하며, 그룹 안의 참여 중 하단 정렬·비활성화·모집기간·유형·목적지와 기존 계정 응답 guard를 유지했다. 공통 탭 및 이동 핸들러는 변경하지 않았다.
- 새 아코디언 5개 테스트를 기존 화면에서 RED로 확인했다. 구현 후 전체 관련 102개 실행은 101 passed / 1 failed: 기존 홈 테스트 1개가 승인된 일 단위 표시 대신 옛 퍼센트 링크명을 기대했다. 기대만 수정한 뒤 해당 회귀와 최종 아코디언 5개를 재실행하여 6 passed (13.3s), TypeScript exit 0을 확인했다.
- 375·390·1280px 각각 접힘/펼침 6개 fixture 캡처를 `frontend/test-results/428-browse-confirmed/`에 보관했다. 가로 넘침, 긴 제목 줄바꿈, 키보드 토글, 두 그룹 동시 펼침, 참여 중 카드 비활성화를 검증했다. 실제 사용자 데이터는 사용하지 않았다.
- 이미 참여 중인 영양제는 기존 `cc4c08e`에서 초기 선택 차단을 완료했다. fresh 서버 집중 테스트 1 passed 및 390px 전체 점유 fixture의 모든 체크박스·CTA 비활성화, API 쓰기 0회를 확인했다. 중복 구현은 하지 않았다.
- 후속 로컬 커밋은 독립 리뷰 대기(`REVIEW_PENDING`). push/PR/main 병합은 수행하지 않는다.

## 직접 요청 전수 감사 후속: 종료된 맞춤 상세 하단 복귀 제거

- `direct-request-audit.md` D03에서 기존 `ba021727`의 완료·만료·취소 상세에 `내 챌린지로 돌아가기`가 남아 있음을 확인했다. 정상 상세의 non-ACTIVE 분기만 제거했다.
- 헤더 뒤로가기와 실제 404 복귀, ACTIVE 참여 취소 버튼, 취소 확인창의 돌아가기, 지난 기록 및 공식 재참여는 유지했다. #424의 헤더 이동 구현은 수정하지 않았다.
- TDD RED: 종료 3상태 × 390/1280px 6개 모두 남은 footer로 실패, 보존 대상 2개는 통과. GREEN: 새 8개와 기존 취소·헤더·달성 스냅샷·공식 재참여 회귀를 합한 14개 통과 (55.6s). `tsc --noEmit` 및 `git diff --check` 통과.
- 화면: `frontend/test-results/428-footer-green/`에 상태별 390/1280px 상단·하단 fixture 캡처 12개 보관. 사용자 데이터/실제 서버 쓰기는 사용하지 않았다.
- 작업은 `ba021727`에서 분리된 HEAD로 수행했다. 실제 `feature/428` ref와 사용자 기본 작업 폴더는 변경하지 않았으며, 독립 리뷰 및 부모 작업의 안전한 ref 갱신 전까지 전달 대기다.
