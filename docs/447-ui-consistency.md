# #447 UI 일관성 기준

- 기준 문서: [Notion UI/UX 허브](https://app.notion.com/p/3d97226115e780839077f30699579ab6), [GitHub issue #447](https://github.com/AI-HealthCare-05/AH_05_05/issues/447)
- 공통 `Button`은 일반 실행에 기본 52px, 카드·헤더의 compact 실행에 44px을 사용한다. primary/secondary/danger 의미와 기존 상단 반사, inset/outer shadow, pressed/disabled 표현은 유지한다.
- 복수 복용 시간 선택은 지정된 4열 소비자에서 `DoseSlotButton`이 표시와 `aria-pressed`를 소유한다. callback, 선택 횟수 제한, disabled, PRN 처리와 저장 payload는 상위 화면이 계속 소유한다.
- 정보 영역은 기존의 얇은 경계와 평면성을 유지한다. 정보 카드에 새 그림자나 토큰을 추가하지 않는다.
- 영양제 둘러보기의 검색 결과 정렬·정렬 방향은 홈 시간대와 같은 `ContinuousTabs` 트랙과 선택 필을 사용한다. 정렬 키별 기본 방향, 선택된 정렬명의 방향 표시(▲/▼), 검색 요청 계약은 상위 화면이 계속 소유한다.
- 공식 챌린지 상세·참여 화면은 loading, success, 404, load error 네 상태 모두 `Header`와 기존 뒤로 가기 목적지를 유지한다.
- 맞춤 추천 카드의 제목 행→연동 정보→대상 정보 간격은 로컬 8px, 빈 상태의 제목→설명→링크 간격은 로컬 12px이다. 공통 `Card` 구조는 변경하지 않는다.
- 처방 추가/선택과 영양제 추가/삭제·완료는 같은 secondary `Button` 테두리·라운드·52px 표면을 사용한다. 실제 삭제 실행은 danger 의미와 disabled guard를 유지한다. 최근 6개월/복약 메모 pill과 Header 취소는 별도 역할이므로 유지한다.

## 제외 및 후속 범위

- 기존 `MedicationSlotSheet`의 2열 배치는 #447의 4열 `DoseSlotButton` 지정 소비자가 아니므로 그대로 둔다.
- 챗 launcher의 가림·충돌 위치 정책은 이번 변경에서 다루지 않고 후속 결정으로 남긴다.
- API, 저장 payload, 챌린지 정책, 알림, OCR 정보 구조, V11 보고서와 전역 `Card`/radius/min-height 재설계는 범위 밖이다.
