# #447 UI 일관성 기준

- 기준 문서: [Notion UI/UX 허브](https://app.notion.com/p/3d97226115e780839077f30699579ab6), [GitHub issue #447](https://github.com/AI-HealthCare-05/AH_05_05/issues/447)
- 공통 `Button`은 일반 실행에 기본 52px, 카드·헤더의 compact 실행에 44px을 사용한다. primary/secondary/danger 의미와 기존 상단 반사, inset/outer shadow, pressed/disabled 표현은 유지한다.
- 복수 복용 시간 선택은 지정된 4열 소비자에서 `DoseSlotButton`이 표시와 `aria-pressed`를 소유한다. callback, 선택 횟수 제한, disabled, PRN 처리와 저장 payload는 상위 화면이 계속 소유한다.
- 정보 영역은 기존의 얇은 경계와 평면성을 유지한다. 정보 카드에 새 그림자나 토큰을 추가하지 않는다.
- 영양제 둘러보기의 검색 결과 정렬은 홈 시간대와 같은 `ContinuousTabs` 트랙과 선택 필 한 줄만 사용한다. 선택한 기준을 다시 누르면 오름차순·내림차순이 전환되고, 다른 기준을 누르면 이름순은 오름차순, 등록·평점·후기순은 내림차순을 기본으로 쓴다. 선택된 정렬명의 방향 표시(▲/▼), 검색 요청 계약은 상위 화면이 계속 소유한다.
- 공식 챌린지 상세·참여 화면은 loading, success, 404, load error 네 상태 모두 `Header`와 기존 뒤로 가기 목적지를 유지한다.
- 맞춤 추천 카드의 제목 행→연동 정보→대상 정보 간격은 로컬 8px, 빈 상태의 제목→설명→링크 간격은 로컬 12px이다. 공통 `Card` 구조는 변경하지 않는다.
- 처방 추가/선택과 영양제 추가/삭제·완료는 같은 secondary `Button` 테두리·라운드·52px 표면을 사용한다. 실제 삭제 실행은 danger 의미와 disabled guard를 유지한다. 최근 6개월/복약 메모 pill과 Header 취소는 별도 역할이므로 유지한다.
- 단일 행 입력은 공용 `Input`의 52px 높이·15px 글자·`rounded-input`·`border-input`·`rx-input` 표면을 사용한다. 네이티브 `select`·`textarea`와 시간 선택을 여는 버튼은 각각의 의미·행 수·길이 제한·resize·disabled 동작을 유지하면서 `rx-input` 표면만 공유한다. 날짜는 네이티브 `type=date`와 min/max 검증을 그대로 둔다.
- MY의 재시도·로그아웃·탈퇴 진입은 실행 버튼이므로 secondary `Button`을 사용하고, 되돌릴 수 없는 탈퇴 확인 실행만 danger 단계를 유지한다. 비밀번호 변경은 화면 이동 성격의 64px navigation row이므로 chevron과 평면 카드 역할을 유지한다.
- AI 보고서의 생성 전·대기·오류·빈 결과·기본/V11 결과와 하단 CTA는 모두 최대 760px의 `rx-reading-content` 읽기 열 안에 둔다. 좁은 화면에서는 기존처럼 폭 100%를 사용한다.
- 공통 챗 launcher는 사용자가 6px을 넘겨 드래그한 위치에 가장자리 스냅 없이 남고, 버전이 있는 로컬 UI 환경설정으로 위치를 기억한다. 표시 위치는 현재 viewport의 16px 안쪽이면서 실제 하단 탭바 위 16px(말풍선 꼬리 포함)으로 제한하고, 탭바가 없는 화면에서는 기존 safe-area 하단 여백도 유지하되, 작은 화면에서 제한된 값으로 저장 위치를 덮어쓰지 않는다. 6px 이하 포인터 이동과 키보드 Enter/Space는 기존 로그인 안내·인증 채팅 이동을 그대로 실행하며, 실제 드래그가 만든 click만 억제한다. 기본 위치와 기존 캐릭터·재질은 유지하고 MY 초기 겹침을 자동으로 피하지 않으며 사용자가 직접 옮기는 정책이다.

## 제외 및 후속 범위

- 기존 `MedicationSlotSheet`의 2열 배치는 #447의 4열 `DoseSlotButton` 지정 소비자가 아니므로 그대로 둔다.
- API, 저장 payload, 챌린지 정책, 알림, OCR 정보 구조, V11 보고서와 전역 `Card`/radius/min-height 재설계는 범위 밖이다.
