# #100 홈 리뉴얼·회원가입 기본정보 설계

## 목표

회원가입과 기본정보 수정에서 이름·전화번호를 수집하고, 여러 care episode가 동시에 존재해도 홈의 복약 시간표와 기록이 길어지거나 서로 어긋나지 않게 표시한다. 복약 탭은 약봉투 이미지 중심 화면에서 care episode별 처방 기록 탐색 화면으로 바꾼다.

## 범위

- 회원가입 필드 순서: 이메일 → 비밀번호 → 비밀번호 확인 → 이름 → 전화번호 → 생년월일 → 성별 → 필수 약관 2건.
- 이름과 전화번호는 필수다. 전화번호는 화면에서 `010-1234-5678` 형태로 읽히게 하고 API payload에는 숫자만 보낸다.
- 마이페이지 기본정보 수정에서 이름·전화번호·생년월일·성별을 함께 수정한다.
- 로그인 홈은 항상 `PokeFeatureCarousel`을 먼저 표시한다.
- 등록한 care episode가 없으면 배너 아래에 약봉투 등록 카드를 표시한다.
- 등록 기록이 있으면 모든 활성 care episode의 약을 시간대별로 합친다.
- 시간대 행은 기본으로 접혀 있고 `아침약 5개 · 08:00`처럼 시간대·개수·시각만 보인다. 사용자가 `자세히 보기`를 누르면 약 이름·용량·소속 처방을 같은 행 안에 펼친다.
- `N개 먹었어요`는 그 날짜·시간대에 약이 있는 모든 care episode의 복용 기록을 함께 저장한다.
- 홈의 통합 복약 기록 칸은 대상 episode가 모두 기록됐을 때만 `먹은 기록`으로 표시한다. 일부만 기록된 상태를 완료로 표시하지 않는다.
- 복약 탭에서 약봉투 원본 이미지와 이미지 뷰어를 제거한다.
- 복약 탭 첫 화면은 care episode 목록이며, 각 항목은 처방 기간·상태·약 개수를 표시한다.
- care episode를 누르면 `/medications/:recordId`에서 해당 회차의 알림 시간과 약 목록을 본다.

## 데이터 계약

`MedicationOverview` 한 건의 구조는 유지한다. 목록 경계만 다음처럼 확장한다.

```ts
getMedicationOverviews(): Promise<MedicationOverview[]>
getMedicationOverview(recordId?: number): Promise<MedicationOverview>

interface DoseRecord {
  recordId: number;
  date: string;
  slot: MealSlot;
  taken: boolean;
}

interface DoseRecordRange {
  recordId: number;
  from: string;
  to: string;
}
```

실서버 어댑터는 전환 기간 동안 `GET /v1/medications`의 단일 `MedicationOverview`와 `{ episodes: MedicationOverview[] }`를 모두 받아 배열로 정규화한다. 화면은 단일 응답 여부를 알지 못한다. 복용 기록 조회·저장에는 반드시 `recordId`를 포함한다.

목업에는 기간과 약 구성이 다른 활성 episode 두 개를 둔다. 신규 가입 목업은 빈 배열을 반환한다.

## 홈 집계 규칙

- 오늘 활성 약: `start.date <= 오늘 <= start.date + medication.days - 1`이고 `asNeeded === false`인 약.
- 시간대 시각: 사용자 공통 시각이라는 기존 전제에 따라 첫 활성 episode의 `mealTimes[slot]`을 표시한다.
- 시간대 개수: 해당 슬롯의 모든 활성 약 개수.
- 저장 대상: 해당 날짜·슬롯에 활성 약이 하나 이상인 episode의 `recordId` 목록.
- 완료: 저장 대상 모든 `recordId`에 `(recordId, date, slot, taken=true)` 기록이 존재.
- 통합 기록 기간: 전체 episode 중 가장 이른 `start.date`부터 가장 늦은 `endDate`까지.
- 통합 기록 칸 존재: 해당 날짜·슬롯에 활성 약이 있는 episode가 하나 이상.
- 통합 기록 칸 완료: 칸이 존재하는 모든 episode의 기록이 완료.

## 화면 방향

기존 흰 카드·민트 primary·따뜻한 배경과 Noto Sans KR 조판을 유지한다. 색·임의 px를 새로 만들지 않고 토큰 클래스만 쓴다. 접힌 시간대 행은 44px 이상의 터치 영역을 보장하고, 상세 내용은 행 아래로 펼친다. 여러 행을 각각 열고 닫을 수 있으며 기본은 모두 접힘이다. 장식적 애니메이션은 추가하지 않는다.

## 오류와 저장

- 목록 또는 기록 조회 실패는 홈 안의 실패 카드로 표시하고 팝업을 띄우지 않는다.
- 여러 episode 저장은 entity 함수가 담당한다. 하나라도 실패하면 화면의 낙관적 갱신 전체를 원복하고 기존 `ErrorDialog`를 띄운다.
- 되돌리기도 같은 recordId 집합에 적용한다.
- 마이페이지 저장 성공은 기존처럼 토스트, 실패는 `ErrorDialog`다.

## 제외

- 백엔드 DB·라우터 구현.
- 약봉투 OCR 확인 화면의 원본 미리보기 제거. 제거 범위는 복약 탭뿐이다.
- care episode 이름 수정·삭제·정렬 UI.
- 시간대별 개별 약 복용 체크.
