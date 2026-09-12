# #427 노션 요구 검토

## 영양제 성분합계

- 원문: https://app.notion.com/p/3d97226115e78059bfa5e71690d5168b
- 상태: **fixed**
- 성분명 옆에 하루 합계와 단위를 배치했습니다.
- 서버 섭취기준으로 계산하던 기존 판정 문구를 그래프 오른쪽 위로 옮겼습니다. `권장량/충분섭취량의 N%예요`, `권장 범위예요`, `상한 초과`의 판정 조건과 계산은 변경하지 않았습니다.
- `성분 포함 제품 N개`를 누르면 합산에 사용된 제품명을 확인할 수 있도록 기본 접힘 상세를 추가했습니다.

## 내 영양제 목록

- 원문: https://app.notion.com/p/3d97226115e780dd8a82fe8bb9700175
- 상태: **fixed** (성분 합계 범위)
- `기준 · 2025 한국인 영양소 섭취기준 · 만 N세 성별` 표기를 유지했습니다.
- 검색 등록 제품만 합산하며 직접 입력 제품, 음식, 의약품 섭취량은 제외한다는 세 문장을 명시했습니다.
- 제품 목록의 `성분 정보 없음` 배지 제거는 같은 파일의 제품 목록을 소유한 #426 담당자에게 전달했습니다. 이 브랜치에서는 충돌 방지를 위해 해당 목록 코드를 수정하지 않았습니다.

## 확인 경로

- 화면: `/dev/supplements`
- 신규 테스트: `frontend/tests/e2e/427-nutrient-totals.spec.ts`
- 기존 회귀: `frontend/tests/e2e/supplements.spec.ts`, `frontend/tests/e2e/307-supplement-empty.spec.ts`, `frontend/tests/e2e/supplements-real-api.spec.ts`
- fixture 스크린샷: Playwright `test-results/427-green` 아래 375px, 390px, 1280px 결과
