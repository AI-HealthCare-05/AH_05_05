# #426 노션 검수 반영

## 노션 항목별 결과

| 노션 원문 | 상태 | 반영 내용 |
| --- | --- | --- |
| [영양제 필터](https://app.notion.com/p/3d97226115e780158b11f08682bf5240) | fixed | 선택한 정렬명에 오름차순 `▲`, 내림차순 `▼`를 표시하고 평점 옆 수치를 `후기: N개`로 명시했습니다. |
| [영양제 복용 정보 줄바꿈](https://app.notion.com/p/3d97226115e780e1b1ebe2260008892f) | fixed | 제품명, `하루 N회 · 1회 N단위`, 시간대를 각각 독립된 줄로 표시합니다. |
| [마지막 선택 버튼 색상](https://app.notion.com/p/3d97226115e780258d05f9f02334c71c) | fixed | 선택 슬롯이 공통 토큰 배경을 사용해 포인터가 마지막 선택 슬롯에 남아도 색이 같고, 기존 focus outline은 유지됩니다. |
| [둘러보기 등록됨 문구](https://app.notion.com/p/3d97226115e780d59ddad00261e9c6f2) | fixed | 현재 복용 목록은 `status=ACTIVE`로 조회되는 계약을 검증하고 해당 제품 배지를 `복용 중`으로 변경했습니다. 과거 등록 이력에는 이 배지를 사용하지 않습니다. |
| [등록 시 제품 칸 clipping](https://app.notion.com/p/3d97226115e7804d893fe11b098befca) | fixed | 검색 결과 행의 flex 축소를 막고 선택 후 카드를 scroll viewport 안으로 이동하며, 작은 화면에서 확장 카드가 들어오도록 sheet 최대 높이를 조정했습니다. |
| [내 영양제 별점·메모](https://app.notion.com/p/3d97226115e78009a431e4cf49b88178) | fixed / already implemented | 요약의 중복 별점과 `메모 있음`을 제거했습니다. 메모 100자 제한은 이미 구현되어 있었고, 긴 무공백 문자열의 강제 줄바꿈을 회귀 검증했습니다. |
| [추가 안내 문구](https://app.notion.com/p/3d97226115e780e3b673dc7d7ff36e83) | fixed | `제품 정보의 복용 권장사항을 참고하세요.`로 변경했습니다. |
| [제품 정보](https://app.notion.com/p/3d97226115e780e9aed5d13ec4a2cfd0) | fixed | 없는 정보는 행 자체를 숨기고, 중복 복용 정보는 제거했으며, 제품 정보는 그림자와 둥근 모서리가 없는 `dl` 영역으로 표시합니다. |
| [랭킹 폰트·긴 이름](https://app.notion.com/p/3d97226115e780ab83c5fe26bf429f70) | fixed | 랭킹 번호와 제품명을 한 단계 줄이고 한 줄 말줄임했습니다. 전체 제품명은 버튼 접근성 이름과 `title`로 유지됩니다. |
| [영양제 추가 버튼 중복](https://app.notion.com/p/3d97226115e780809dafd4cb5bf78506) | fixed | 정상 목록은 제목 옆 추가 버튼 하나만 유지하고, 빈 목록의 안내 CTA는 그대로 유지했습니다. |

`superseded` 또는 `blocked` 항목은 없습니다.

## 변경 화면

- 내 영양제 목록 및 편집 sheet
- 둘러보기 랭킹·검색·정렬
- 영양제 추가 sheet
- 제품 상세
- 홈 영양제 랭킹

성분 합계 영역과 영양제 화면 navigation handler는 변경하지 않았습니다.

## 검증

- RED: `426-supplement-ui.spec.ts` 4개 최초 실패, 슬롯 배경·작은 화면 clipping을 각각 별도 재현
- GREEN: `426-supplement-ui.spec.ts` 6/6
- 기존 mock 회귀: 45 passed, 10 mode-specific skipped
- 기존 real-API 영향 회귀: 18 passed 후 환경성 1건을 단독 재실행하여 1 passed
- TypeScript: `tsc --noEmit`

## 화면 캡처

- `frontend/test-results/426-green/.../426-add-sheet-375-green.png`
- `frontend/test-results/426-green/.../426-browse-390-green.png`
- `frontend/test-results/426-green/.../426-product-1280-green.png`

화면 캡처는 테스트 fixture만 사용했으며 커밋 대상이 아닙니다.
