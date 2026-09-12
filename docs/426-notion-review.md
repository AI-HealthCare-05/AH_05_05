# #426 노션 검수 반영

## 노션 항목별 결과

| 노션 원문 | 상태 | 반영 내용 |
| --- | --- | --- |
| [영양제 필터](https://app.notion.com/p/3d97226115e780158b11f08682bf5240) | fixed | 선택한 정렬명에 오름차순 `▲`, 내림차순 `▼`를 표시하고 평점 옆 수치를 `후기: N개`로 명시했습니다. |
| [영양제 복용 정보 줄바꿈](https://app.notion.com/p/3d97226115e780e1b1ebe2260008892f) | fixed | 정상 목록과 삭제 선택 목록 모두 제품명, `하루 N회 · 1회 N단위`, 시간대를 각각 독립된 줄로 표시합니다. |
| [마지막 선택 버튼 색상](https://app.notion.com/p/3d97226115e780258d05f9f02334c71c) | fixed | 선택 슬롯에 기존 primary clay gradient와 안쪽·바깥쪽 그림자를 재사용합니다. 영양제 추가·편집 및 사용자 추가 요청인 복약 처방·개별 약 편집 모두 마지막 선택에 포인터가 남아도 색과 입체감이 같고, 기존 focus outline은 유지됩니다. |
| [둘러보기 등록됨 문구](https://app.notion.com/p/3d97226115e780d59ddad00261e9c6f2) | fixed | 현재 복용 목록은 `status=ACTIVE`로 조회되는 계약을 검증하고 해당 제품 배지를 `복용 중`으로 변경했습니다. 과거 등록 이력에는 이 배지를 사용하지 않습니다. |
| [등록 시 제품 칸 clipping](https://app.notion.com/p/3d97226115e7804d893fe11b098befca) | fixed | 검색 결과 행의 flex 축소를 막고 선택 후 카드를 scroll viewport 안으로 이동하며, 작은 화면에서 확장 카드가 들어오도록 sheet 최대 높이를 조정했습니다. |
| [내 영양제 별점·메모](https://app.notion.com/p/3d97226115e78009a431e4cf49b88178) | fixed / already implemented | 요약의 중복 별점과 `메모 있음`을 제거했습니다. 메모 100자 제한은 이미 구현되어 있었고, 긴 무공백 문자열의 강제 줄바꿈을 회귀 검증했습니다. |
| [추가 안내 문구](https://app.notion.com/p/3d97226115e780e3b673dc7d7ff36e83) | fixed | `제품 정보의 복용 권장사항을 참고하세요.`로 변경했습니다. |
| [제품 정보](https://app.notion.com/p/3d97226115e780e9aed5d13ec4a2cfd0) | fixed | 없는 정보는 행 자체를 숨기고, 중복 복용 정보는 제거했으며, 제품 정보는 그림자와 둥근 모서리가 없는 `dl` 영역으로 표시합니다. 공백 없는 긴 영문·숫자 값도 375px 화면 경계 안에서 줄바꿈합니다. |
| [랭킹 폰트·긴 이름](https://app.notion.com/p/3d97226115e780ab83c5fe26bf429f70) | fixed | 랭킹 번호와 제품명을 한 단계 줄이고 한 줄 말줄임했습니다. 전체 제품명은 버튼 접근성 이름과 `title`로 유지됩니다. |
| [영양제 추가 버튼 중복](https://app.notion.com/p/3d97226115e780809dafd4cb5bf78506) | fixed | 정상 목록은 제목 옆 추가 버튼 하나만 유지하고, 빈 목록의 안내 CTA는 그대로 유지했습니다. |

`superseded` 또는 `blocked` 항목은 없습니다.

## 변경 화면

- 내 영양제 목록 및 편집 sheet
- 둘러보기 랭킹·검색·정렬
- 영양제 추가 sheet
- 제품 상세
- 홈 영양제 랭킹
- 복약 처방 편집 및 개별 약 복용 시간 sheet

성분 합계 영역과 영양제 화면 navigation handler는 변경하지 않았습니다.

## 검증

- RED: `426-supplement-ui.spec.ts` 4개 최초 실패, 슬롯 배경·작은 화면 clipping을 각각 별도 재현
- GREEN: `426-supplement-ui.spec.ts` 6/6
- 리뷰 1차 RED: 375px 삭제 목록의 `하루 N회 · 1회 N단위` 누락과 긴 영문 제품정보 overflow를 각각 재현
- 리뷰 1차 GREEN: 집중 회귀 2/2, `426-supplement-ui.spec.ts` 8/8
- 기존 mock 회귀: 45 passed, 10 mode-specific skipped
- 기존 real-API 영향 회귀: 18 passed 후 환경성 1건을 단독 재실행하여 1 passed
- TypeScript: `tsc --noEmit`

## 화면 캡처

- `frontend/test-results/426-green/.../426-add-sheet-375-green.png`
- `frontend/test-results/426-green/.../426-browse-390-green.png`
- `frontend/test-results/426-green/.../426-product-1280-green.png`
- `frontend/test-results/426-review-suite-green/.../426-delete-list-375-green.png`

화면 캡처는 테스트 fixture만 사용했으며 커밋 대상이 아닙니다.

## 선택 버튼 입체감 후속 검증

- 원인: 영양제의 arbitrary primary 배경에는 기존 `button.bg-primary` clay 규칙이 적용되지 않았고, 복약의 `bg-primary`는 generic hover gradient로 마지막 선택만 진해졌습니다.
- 수정: 세 런타임 소비자의 `rx-dose-slot`을 선택 상태에 직접 연결하고 기존 primary gradient·shadow 선언을 공유했습니다. 별도 색상값은 추가하지 않았습니다. 복약도 arbitrary primary 배경을 사용하므로 generic hover와 #425의 `:not([aria-pressed])` 제외 규칙에 의존하지 않습니다.
- RED: 기존 소스에서 영양제 computed gradient `none`, 복약 hover 선택 surface 종류 2개를 각각 재현했습니다.
- GREEN: 추가·편집 및 복약 두 편집 화면의 입체감·선택색·focus outline·선택 해제 검증 20/20. 편집 화면은 375/390/1280px에서 포인터와 실제 tap 입력을 확인했습니다.
- 기존 회귀: #426 전체 11개와 복약 일일 횟수 제한·조회 실패/재시도·잘못된 저장값, 영양제 최소 선택/추가 저장·편집 저장 5개가 모두 통과했습니다(16/16).
- 기존 mock 회귀: 권장 슬롯 표시·최소 선택·추가 저장·편집 저장 4/4 통과.
- TypeScript `tsc --noEmit` 및 `git diff --check` 통과.
- 검증 실행은 detached 작업 폴더, 포트 45526, 독립 Vite cache를 사용했습니다. API 경계 회귀는 fixture만 사용하며 테스트 서버가 미목업 API 요청을 proxy 이전에 차단합니다.
- 390px 시각 검증: `frontend/test-results/426-depth-green/` 아래 `426-supplement-edit-depth-390.png`, `426-medication-prescription-depth-390.png`, `426-medication-individual-depth-390.png`(각 desktop/touch 디렉터리). 선택 controls가 보이도록 스크롤한 캡처입니다.
