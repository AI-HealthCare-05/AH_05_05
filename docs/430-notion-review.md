# #430 Notion 요구사항 검수

기준: 2026-09-12 확정 사용자 결정이 이전 Notion 제안보다 우선한다. 이후 사용자가 `복약 체크 표시 기능이 애매함`, `OCR 약정보 UI` 두 항목을 취소했다. 일부 복용 선택은 기존 동작을 유지하고, 복약 시간대는 표로 재설계하지 않는다.

## 링크별 처리 결과

1. [복약 체크 표시 기능이 애매함](https://app.notion.com/p/3d97226115e78021ad04e4f4307f10b5) — **cancelled**
   - 해당 항목 취소에 따라 미완료 복약 버튼 문구를 기준 동작인 `먹었어요`로 복원했다.
   - 기존 일부 복용 선택, 선택/전체 대상 기록, 완료 상태의 `복약 기록 되돌리기` 동작은 유지했다.
2. [홈 오늘의 복약/영양제 빈 상태 UI 통일](https://app.notion.com/p/3d97226115e780a1bf0af0b0ac1e702a) — **fixed**
   - 두 빈 상태를 같은 카드 배경·간격·패딩 구조로 맞췄다.
   - 영양제 빈 상태에 `영양제 살펴보기` 버튼과 탐색 연결을 추가했다.
3. [홈 오늘의 복약 펼치기](https://app.notion.com/p/3d97226115e780099e7ce233f83c1523) — **fixed**
   - 펼친 처방의 상세 약명을 보통 굵기로 변경했다.
4. [약봉투 미리보기](https://app.notion.com/p/3d97226115e78025b6a3f20ac3411f9a) — **fixed**
   - OCR 약봉투 미리보기에 100/150/200/300% 확대·축소와 이동 가능한 스크롤 영역을 추가했다.
   - 키보드 버튼 조작, Escape/명시적 닫기, 이미지 클릭 닫기, 터치 pinch-zoom을 유지·검증했다.
5. [복약 상단 버튼 영역](https://app.notion.com/p/3d97226115e78040862fd97600c127a8) — **fixed**
   - `AI 보고서 받기`는 주 동작, `처방 추가`는 보조 동작으로 시각적으로 구분했다.
   - 유휴 `선택`, 선택 중 `삭제`, 헤더 `취소` 경로를 제공하고 삭제 버튼은 항목 선택 전 비활성화했다.
   - 상단 `복약 메모` 버튼의 카드 그림자를 보존했다.
6. [복약 아침/점심/저녁 색상](https://app.notion.com/p/3d97226115e780588f8feab165166ef6) — **fixed / superseded**
   - 확정안대로 50:50 중간톤 시간대 점, 헤더 범례, `복용 중` 스티커를 유지했다.
   - 연필은 화살표와 세로 정렬되는 독립 우측 헤더 동작으로 옮기고 44px 이상 터치 영역을 유지했다.
   - 상세 표 제안은 최신 사용자 결정으로 **superseded**되어 구현하지 않았다.
7. [OCR 약정보 UI](https://app.notion.com/p/3d97226115e780a4a4c4c00de107da5f) — **cancelled**
   - 함량/횟수 줄바꿈과 접기·펼치기 제안은 취소되었다. 이번 #430 제품 diff에는 이 항목의 신규 변경이 없어 되돌릴 코드가 없다.
   - 기존 승인 상태인 항상 펼침·연필만·약명 옆 `확인 필요` 표시는 유지한다. 별도 4번 `약봉투 미리보기` 확대·축소도 취소 대상이 아니다.

## 변경 파일

- 홈: `frontend/src/pages/home/MedicationTimeline.tsx`, `SupplementTodayCard.tsx`
- 복약: `frontend/src/pages/medications/MedicationEpisodeCard.tsx`, `MedicationsPage.tsx`
- OCR: `frontend/src/pages/ocr-review/OcrReviewPage.tsx`
- 검증: `frontend/tests/e2e/430-medication-followups.spec.ts` 및 변경 문구를 사용하는 기존 관련 E2E 테스트

`HomeChallengeSummary` 제품 코드는 #428 소유 범위이므로 수정하지 않았다.

## 검증과 화면

- #430 전용 E2E: 375/390/1280px 포함 9개 통과
- 복약/OCR 실 API 모드 집중 회귀: 18개 통과
- 선택/보고서 목업 모드 집중 회귀: 6개 통과
- 기존 #353 편집·선택 회귀: 1개 통과
- TypeScript `tsc --noEmit` 통과
- 화면: `frontend/test-results/430-green/*/home-*.png`, `medication-*.png`, `ocr-preview-zoom-*.png`

화면 캡처는 테스트 fixture만 사용하며 커밋하지 않는다.
