# #384 독립 코드·UX 회귀 검수

검수자: Astra low 독립 검수. 기준 base 451bd86, feature-384 dirty worktree. 제품 파일은 수정하지 않았다. UI/UX Pro Max와 직접 읽은 quick-reference/pro-rules의 상태 보존·접근성 기준을 적용했다. 검토는 로컬 diff, 기존 테스트 코드 및 실행 산출물에 근거하며 실기기/스크린리더/전체 시각 검증 완료를 뜻하지 않는다.

## 판정

현재 읽은 변경에서 확정된 critical/important 사용자 손상 회귀는 찾지 못했다. 아래 계정 전환 조건은 미검증 관찰로 남기며 전체 승인으로 확대하지 않는다.

## 요청별 확인

1. 처방 편집은 getMedicationSchedule(recordId)의 canonical timesPerDay를 사용한다. 정수·양수 및 해당 약 ID 존재를 검사하고, 조회 중/오류/불완전 응답에서는 선택과 저장을 차단한다. 기존 초과 선택은 자동 삭제하지 않고 명시적으로 줄인 뒤 저장하도록 한다. 닫힘은 request generation을 무효화하고 다음 조회도 generation을 증가시킨다. 저장 함수와 버튼 양쪽에 상한 검사가 있다.
2. 복약/영양제 완료 요약은 시간대의 모든 항목이 완료되고 길이가 0보다 클 때만 표시한다. 전체 완료 때 row chip만 숨기며 행의 선택/완료 의미와 undo 동작은 유지된다. 복약 실패 rollback 및 영양제 성공 응답별 records 갱신 경로도 유지된다. 새 데이터 쓰기 API는 추가되지 않았다.
3. Official participation 뒤로가기는 history idx>0이면 navigate(-1), 직접 진입이면 /challenges replace로 처리하여 push에 의한 되돌아오기 루프를 방지한다.
4. Badges는 성공/로딩/오류 상태 모두 공통 Header와 같은 back/fallback을 제공한다. 기존 제목과 본문 내용은 유지된다. custom challenge #315 파일 변경은 현재 diff에 없다.

## 테스트 근거와 한계

- 신규 384-home-completion-summary는 복약 전체 완료/선택/undo, 저장 실패 rollback, 영양제 partial/all/undo를 검증한다. test-results-384-green-final2/.last-run.json은 passed다.
- 신규 384-challenge-navigation은 Home/My 출발 왕복, participation 직접 진입, badges 공통 헤더 44px 및 직접 진입 fallback을 검증한다. 최종 분리 실행 `test-results-384-nav-final/.last-run.json`은 passed이며 5/5가 통과했다.
- medications-management-api에는 canonical 상한·시간 교체, 지연/오류/retry 차단, 기존 초과 값 보존 테스트가 추가되었다. 최신 test-results-384-med-real-green2/.last-run.json의 passed/실패 0을 직접 확인했다. lead가 11/11 통과를 보고했다. 이전 green 실패 2건은 최신 결과로 대체하며, lead 설명상 cold Vite timeout과 범위 밖 challenge read fixture 보완으로 해소됐다.
- 갤러리의 `issue2-*-baseline-complete.png`와 `issue2-*-feature-complete.png` 두 쌍은 동일 fixture·동일 전체 완료 상태를 각각 clean base `451bd86`과 feature에서 캡처한 코드 변경 전/후 증거다. 별도의 `partial.png`→`complete.png` 두 쌍은 같은 feature 코드에서 상태 전이만 보여주는 보조 증거로 구분한다.

## 미검증 관찰

### 후속 테스트 증거

- test-results-384-compression-real-green2/.last-run.json의 passed/실패 0을 직접 확인했다. lead 실행 결과는 12/12 통과다.
- test-results-384-nav-integrated-green은 전체 실행 기준 failed 1건이며, 이를 전체 PASS로 표기하지 않는다. lead 결과상 #384 신규 navigation 5/5는 통과했다. 남은 #333 baseline 테스트는 2/3이며, 기존 Header가 main 내부에 있어 banner role이 없고 x=20이므로 해당 테스트의 full-width 기대와도 불일치한다는 진단이다. #384 수정 범위와 무관한 것으로 분리했고, 진단 중 임시 locator 변경과 제품 변경은 원복했다는 lead 보고를 기록한다. 이 독립 검수에서 baseline 브라우저 재현을 별도로 수행하지는 않았다.

MedicationsPage의 principalKey 변경 effect는 목록을 초기화하지만 episodeEditing/episodeSchedule 및 episodeRequestIdRef를 초기화하지 않는다. loadEpisodeSchedule도 requestId만 검사한다. 다만 실제 signIn 호출은 AuthPage, signOut 호출은 MyPage에만 있으며 해당 이동과 인증 guard 과정에서 MedicationsPage가 unmount된다. 동일 mount에서 직접 principal을 교체하는 제품 경로는 확인되지 않았다. 따라서 확정된 사용자 손상 결함으로 분류하지 않고 향후 동일 mount 계정 교체를 도입할 경우의 방어 테스트 관찰로만 남긴다.

늦은 응답의 close/reopen, 계정 교체, 모든 empty 조합은 신규 focused 테스트에서 직접 확인하지 않았다. 테스트 코드로 확인한 부분과 실제 실행 산출물이 확인된 부분을 구분했다. 검수 중 API/DB 요청, 외부 쓰기, commit/push는 수행하지 않았다.
