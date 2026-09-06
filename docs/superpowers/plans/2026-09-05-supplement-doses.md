# 영양제 일일 복용 기록

승인 범위: 홈 영양제 선택·복용·되돌리기 실제 저장, 별도 등록/date/slot 모델과 migration 30 추가. 기존 테이블 용도 변경, DB 초기화, migration 적용은 하지 않는다.

계약은 `GET /api/v1/med/supplement-doses?date=YYYY-MM-DD`, `PUT /api/v1/med/supplement-doses`의 `{supplementId, date, slot, taken}`이다. slot은 기존 프론트와 같은 소문자다. 등록 소유권은 404, 같은 등록/날짜/시간대 기록은 unique, true는 멱등 생성, false는 멱등 삭제다. 저장은 오늘까지 최근 366일과 등록 기간·시간대를 검증한다. 삭제는 변경된 등록 시간대에 막히지 않는다.

홈은 등록 시간대별 모든 제품을 보여준다. 개별 선택을 켜면 미완료 선택은 N개 먹었어요, 완료 선택은 N개 되돌리기로 처리하며 두 상태를 함께 고르지 않는다. 미선택 상태의 다 먹었어요는 해당 시간대 미완료만 저장한다. 서버 성공 항목만 완료 표시하고 실패 항목만 재시도한다. 영양제 탭의 관리·제품 정보·후기는 유지한다.

- [x] 새 mock E2E로 기존 비대화형 UI 실패 확인(아침 영양제 선택 그룹 없음).
- [x] 모델·DTO·service·router·migration 30과 소유권/멱등/되돌리기 API 테스트 6개 추가.
- [x] 공용 영양제 dose API 및 계정별 목업, 실제 슬롯 시각 매핑 추가.
- [x] 홈 컴포넌트를 분리해 조회/선택/저장/실패 재시도/되돌리기 연결.
- [x] 집중 mock/real E2E, 상세·후기 회귀, tsc/build/diff-check 실행.

검증: focused mock 9 passed/5 real-only skipped, focused real 복용 6 passed/1 mock-only skipped, 실 API 상세/후기 2건 통과. migration 표준 라이브러리 정적 테스트 3건과 Python compileall 통과. tsc/build/diff-check 통과. 기존 bundle 크기 경고는 남아 있다.

제한: backend API 테스트는 WSL Python에 pytest와 FastAPI가 없어 실행하지 못했다. 프론트 real 검증은 서버 실기동이 아닌 HTTP 경로/메서드/payload/실패 응답 계약 검증이다. migration은 적용하지 않았다. 전체 홈 mock 회귀는 21 passed/4 skipped/1 failed(58초): 기존 처방 테스트 `home-figma-overhaul.spec.ts:184`가 펼친 뒤 이름이 접기로 바뀐 버튼을 이전 펼치기 locator로 찾는 실패이며 영양제 변경 범위 밖이라 수정하지 않았다.
