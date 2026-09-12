# #429 복약 메모 Notion 검토

## 복약 메모 > 등록, 수정

- Notion: https://app.notion.com/p/3d97226115e7807583f1c3eeb909bb4d
- 상태: **fixed**
- `복용시 건강상태 변화를 기록해 보세요.`, `건강상태 기록`, 상담 활용 안내 문구로 변경했다.
- 새 메모는 처방을 고른 뒤에도 `처방 전체`가 기본값이고, 사용자가 원할 때만 개별 약을 고른다.
- 작성 폼은 같은 opt-in 처방 인벤토리의 약 목록을 사용하므로 overview 날짜 범위 밖의 활성 처방과 완료 처방도 첫 메모를 작성할 수 있다.
- 화면: `/medications/notes/new`, `/medications/notes/:noteId`

## 복약 메모 > 개선

- Notion: https://app.notion.com/p/3d97226115e78041a0dde80e422bb86a
- 상태: **fixed**
- 새 메모 작성 버튼을 헤더 우측으로 옮기고 목록 일괄삭제를 제거했다. 삭제는 수정 상세의 확인 다이얼로그에서만 제공한다.
- `메모 없는 처방`과 `메모 있는 처방` 탭을 처방별 아코디언으로 구성했다.
- `includeWithoutNotes=true` 처방 인벤토리의 `noteCount`로 분류하므로 아직 로드하지 않은 메모 페이지 때문에 무메모로 오판하지 않는다.
- 메모 본문은 아코디언을 펼칠 때 해당 `episodeId`만 조회하며, 처방별 커서 페이지네이션·빈 상태·오류·재시도를 유지한다.
- URL 딥링크 초기화는 인벤토리 세대마다 한 번만 적용해 사용자가 접은 뒤 늦게 도착한 성공·오류 응답이 아코디언을 다시 열지 않는다.
- 처방 인벤토리가 비어 있으면 `등록된 처방이 없어요.`로 안내하고, 실제 처방이 모두 기록됐을 때만 모든 처방에 기록이 있다고 안내한다.
- 화면: `/medications/notes`

## 복약 메모 > 처방 약명 표기

- Notion: https://app.notion.com/p/3d97226115e780e383ade78beb6ff7f5
- 상태: **fixed**
- 목록과 작성 폼에서 별도 용량을 덧붙이지 않고 원제품 약명만 표시해 `타이레놀정500mg 500mg` 같은 중복을 없앴다.
- 처방 전체 기록은 `처방 전체`로 명시한다.

## 복약 메모 > 처방 select

- Notion: https://app.notion.com/p/3d97226115e780f899befd25b4b79116
- 상태: **superseded**
- 최종 사용자 결정인 두 탭과 처방별 아코디언이 select 필터 요구를 대체한다. 처방 딥링크 `episodeId`와 작성·수정 후 목록 상태 복원은 유지한다.

## 기존 연결 보존

- 상태: **already implemented / preserved**
- #422 AI 복약 메모 요약의 데이터/API 경로는 변경하지 않았다.
- 기존 `/med/notes/episodes` 기본 응답은 그대로 유지하고, 새 전체 인벤토리는 opt-in 쿼리에서만 제공한다.

## 검증

- `frontend/tests/e2e/429-medication-note-tabs.spec.ts`: 권위 있는 탭 분류, 20개 초과 처방별 페이지네이션, 첫 작성/마지막 삭제 탭 전환, 완료·overview 누락 활성 처방의 첫 작성, 늦은 응답 후 접힘 유지, 빈 인벤토리, 처방 전체 기본값, 약명, 상세 삭제.
- `frontend/tests/e2e/353-note-*.spec.ts`: 폐기된 select·목록 일괄삭제 전제를 탭·아코디언·상세삭제 계약으로 이관하고 딥링크, 저장/취소/뒤로가기, 세션 세대, 오류/재시도, 중복 처방 구분을 보존한다.
- `frontend/tests/e2e/310-medication-note-collection.spec.ts`: mock 데이터의 여러 줄 본문, 처방별 페이지네이션, 늦은 응답 격리를 새 아코디언 계약으로 회귀 검증.
- `app/tests/med_apis/test_medication_note_episode_options_sqlite.py`: 기본 응답 호환, 사용자 소유권, 활성·완료 무메모 포함, 취소 무메모 제외, 메모 수와 작성 가능한 약 인벤토리 집계.
- Playwright 375px 및 1280px 스크린샷을 테스트 산출물로 검토한다.
