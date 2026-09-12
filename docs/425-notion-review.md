# #425 Notion 요구 검토

최신 기준: [새 후속 요구 허브](https://app.notion.com/p/3d97226115e780839077f30699579ab6), PR #446 병합 main `4ed8c3317df7231999b1ccc619d24ac40e648325`, 기존 `feature/425@4cfc7275e4e8eef44a79f1320ff34b1afcab497f`. 승인된 RxVita clay 디자인과 병합된 #426/#428 계약을 유지한다.

| Notion 요구 | 상태 | 반영 내용 / 화면 |
| --- | --- | --- |
| [탭 디자인 : 메뉴마다 다름](https://app.notion.com/p/3d97226115e780a4a62aebcf015d9f6e) | fixed | 공통 `NavigationTabs`와 Radix `Tabs`를 같은 underline 규칙으로 맞추고, 홈의 `오늘의 복약 / 오늘의 영양제`, 영양제의 `내 영양제 / 둘러보기`, 실제·개발용 챌린지의 `/challenges`, `/challenges/browse`에 적용했다. 활성 탭은 초록 하단 ink, 비활성 탭은 중립 텍스트로 표시한다. 시간대·인증처럼 역할이 다른 선택 control은 기존 표현을 유지한다. |
| [버튼/ 탭 구분 필요](https://app.notion.com/p/3d97226115e780099edec17ac9abf5e8) | fixed / already implemented | 상위 화면 탭의 raised 배경과 그림자를 제거해 실행 버튼과 구분했다. 기존 공통 `Button`의 primary(초록), secondary(중립), danger(삭제) 계약과 44px 터치 영역은 유지했다. `aria-pressed` 선택 control은 action용 hover gradient에서 제외해 선택 상태가 hover에도 바뀌지 않는다. |
| [상단 통일 작업](https://app.notion.com/p/3d97226115e780baa285f0ffdd6c5f3c) | fixed / rendered | 운영 배지 목록·상세의 공통 Header는 병합 main에서 유지됐다. 남아 있던 development 목록·빈 상태·상세·not-found도 같은 64px shared Header, 단일 제목, 44px 뒤로가기와 dev-safe fallback을 사용한다. 375/390/1280px에서 렌더 검증했다. |
| [명암 설정 안되있음](https://app.notion.com/p/3d97226115e780298223de3ea8abe934) | already implemented / rendered | 병합 main의 `복약 메모`와 인접 toolbar control은 `shadow-card`를 사용한다. 390/1280px fixture 화면에서 계산된 `box-shadow`가 `none`이 아니며, 상태·제목 정렬과 펼친 시간표를 함께 유지하는지 확인했다. |
| [오늘의 복약 처방 전체 테두리](https://app.notion.com/p/3d97226115e780839077f30699579ab6) | already implemented / rendered | `MedicationTimeline`의 처방 article 네 면이 모두 `solid 1px`이고, 펼친 약 상세의 실제 bounds가 같은 article 안에 포함되는지 390/1280px fixture에서 확인했다. 추가 제품 스타일 변경은 하지 않았다. |

## 확인 경로

- `/dev/challenges`
- `/dev/challenges/browse`
- `/dev/home-multiple-episodes`
- `/challenges`
- `/challenges/browse`
- `/supplements?tab=browse`
- `/medications`
- Playwright 캡처: Home 375/390/1280px, challenge 375/390/1280px, supplement 390/1280px, development badge Header 375/390/1280px, prescription/memo 390/1280px

모든 브라우저 확인은 fixture-only이고 미목업 `/api`·`/media` 요청을 proxy 전에 `503`으로 막았다. 실제 API/DB, 실제 iPhone/iPad·Android 기기, 알림 전달은 이 검수 범위에서 실행하지 않았다. #429 medication-note가 소비하는 shared Tabs와 #432를 함께 합친 최종 smoke는 각 브랜치의 최신 승인 SHA가 준비된 뒤 별도 detached 통합 checkout에서만 수행한다.

## 변경 파일

- `frontend/src/shared/ui/tabs.tsx`
- `frontend/src/shared/ui/index.ts`
- `frontend/src/app/styles/index.css`
- `frontend/src/app/styles/responsive.css`
- `frontend/src/pages/home/HomePage.tsx`
- `frontend/src/pages/challenges/ChallengeHomePreviewPage.tsx`
- `frontend/src/pages/challenges/ChallengeMyPage.tsx`
- `frontend/src/pages/challenges/ChallengeBrowsePage.tsx`
- `frontend/src/pages/challenges/OfficialChallengeMyPage.tsx`
- `frontend/src/pages/challenges/OfficialChallengeBrowsePage.tsx`
- `frontend/src/pages/challenges/ChallengeBadgesPage.tsx`
- `frontend/src/pages/challenges/ChallengeBadgePage.tsx`
- `frontend/src/pages/supplements/SupplementsPage.tsx`
- `frontend/tests/e2e/425-shared-controls.spec.ts`
- `frontend/tests/e2e/369-clay-controls-followup.spec.ts`
- `frontend/tests/e2e/430-medication-followups.spec.ts`
- `frontend/tests/e2e/challenges-entry-badges.spec.ts`
- `frontend/tests/e2e/supplement-browse.spec.ts`
- `frontend/tests/harness/clay-controls.tsx`
