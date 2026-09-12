# #425 Notion 요구 검토

기준: `fbeda80f3796b6beec63061107f63faf90732f79`, 승인된 RxVita clay 디자인 유지.

| Notion 요구 | 상태 | 반영 내용 / 화면 |
| --- | --- | --- |
| [탭 디자인 : 메뉴마다 다름](https://app.notion.com/p/3d97226115e780a4a62aebcf015d9f6e) | fixed | 공통 `NavigationTabs`와 Radix `Tabs`를 같은 underline 규칙으로 맞추고, 실제·개발용 챌린지의 `/challenges`, `/challenges/browse` 및 영양제의 `내 영양제 / 둘러보기`에 적용했다. 활성 탭은 초록 하단 ink, 비활성 탭은 중립 텍스트로 표시한다. |
| [버튼/ 탭 구분 필요](https://app.notion.com/p/3d97226115e780099edec17ac9abf5e8) | fixed / already implemented | 상위 화면 탭의 raised 배경과 그림자를 제거해 실행 버튼과 구분했다. 기존 공통 `Button`의 primary(초록), secondary(중립), danger(삭제) 계약과 44px 터치 영역은 유지했다. `aria-pressed` 선택 control은 action용 hover gradient에서 제외해 선택 상태가 hover에도 바뀌지 않는다. |
| [상단 통일 작업](https://app.notion.com/p/3d97226115e780baa285f0ffdd6c5f3c) | blocked (integration dependency) | 배지 상세 공통 Header 및 뒤로가기는 병렬 #424 navigation 담당 범위로 확정되어 이 브랜치에서는 충돌 방지를 위해 수정하지 않았다. #424 통합 후 확인이 필요하다. |
| [명암 설정 안되있음](https://app.notion.com/p/3d97226115e780298223de3ea8abe934) | blocked (integration dependency) | 390px computed-style 검수에서 인접 `최근 6개월`은 clay shadow, `복약 메모`는 `box-shadow: none`으로 재현됐다. 해당 toolbar는 병렬 #430 담당 범위라 이 브랜치에서는 충돌 방지를 위해 수정하지 않았으며, #430에서 `shadow-card` 보존/추가가 필요하다. |

## 확인 경로

- `/dev/challenges`
- `/dev/challenges/browse`
- `/challenges`
- `/challenges/browse`
- `/supplements?tab=browse`
- `/medications`
- Playwright 캡처: challenge 375/390/1280px, supplement 390/1280px

## 변경 파일

- `frontend/src/shared/ui/tabs.tsx`
- `frontend/src/shared/ui/index.ts`
- `frontend/src/app/styles/index.css`
- `frontend/src/pages/challenges/ChallengeMyPage.tsx`
- `frontend/src/pages/challenges/ChallengeBrowsePage.tsx`
- `frontend/src/pages/challenges/OfficialChallengeMyPage.tsx`
- `frontend/src/pages/challenges/OfficialChallengeBrowsePage.tsx`
- `frontend/src/pages/supplements/SupplementsPage.tsx`
- `frontend/tests/e2e/425-shared-controls.spec.ts`
- `frontend/tests/e2e/supplement-browse.spec.ts`
