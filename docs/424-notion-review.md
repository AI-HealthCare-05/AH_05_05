# #424 Notion navigation review

## 검토 결과

- [챌린지 뱃지 뒤로가기 갇김](https://app.notion.com/p/3d97226115e780578809e066d7e1c61e) — **fixed**. 배지 상세의 로딩·오류·미존재·정상 상태에 공통 `배지 상세` 헤더와 안전한 뒤로가기를 제공하고, `내 배지로 돌아가기`가 상세 화면을 히스토리에 다시 남기지 않게 했다.
- [챌린지 뒤로가기 갇힘 현상](https://app.notion.com/p/3d97226115e78018b32ffd4e32e9338b) — **fixed**. 공식/맞춤 상세에서 앱 뒤로가기는 실제 이전 둘러보기 엔트리를 사용하고, 직접 URL 진입은 둘러보기로 replace한다. 브라우저 back/forward 후에도 같은 규칙을 유지한다.
- [홈 영양제 랭킹 추가 후 홈 복귀](https://app.notion.com/p/3d97226115e78046a8cfd28bd4b9e51e) — **fixed**. 제품 등록 성공 시 상세 엔트리를 내 영양제로 replace해 다음 뒤로가기가 홈으로 바로 복귀한다.
- [맞춤 챌린지 뒤로가기가 목록 경유](https://app.notion.com/p/3d97226115e7804580cad3c038a26be7) — **fixed**. 둘러보기에서 연 맞춤 챌린지는 중간 맞춤 목록을 경유하지 않고 둘러보기로 돌아간다.
- [마이페이지 복약 메모 뒤로가기](https://app.notion.com/p/3d97226115e780a3ad46c67c7103ee53) — **fixed**. 마이 진입 경로를 내부 allowlist로 검증해 작성 취소·수정 저장·새로고침 뒤에도 마이로 복귀한다. 복약 진입과 직접 URL fallback은 기존 복약 경로를 유지한다.

## 변경 및 검증 경로

- 공통 규칙: `frontend/src/shared/lib/navigation.ts`
- 챌린지: `/challenges`, `/challenges/browse`, `/challenges/official/:id`, `/challenges/tailored/:kind`, `/challenges/badges`, `/challenges/badges/:id`
- 복약 메모: `/my` → `/medications/notes` → 작성/수정 → `/medications/notes` → `/my`
- 영양제: `/home` → `/supplements/product/:id` → 추가 완료 → `/supplements` → `/home`
- 회귀 테스트: `frontend/tests/e2e/424-navigation-history.spec.ts`
- 화면 검수: 375×812 챌린지 둘러보기, 1280×900 영양제 추가 완료 화면
