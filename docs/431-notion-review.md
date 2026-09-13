# #431 Notion 요구 검토

기준 커밋: `fbeda80f3796b6beec63061107f63faf90732f79`

## 판정

| Notion 요구 | 판정 | 확인 내용 | 화면 경로 |
| --- | --- | --- | --- |
| [채팅 최근 대화(웹 모드)](https://app.notion.com/p/3d97226115e78024806cea80c8504e5c) | fixed (원본 세로 잘림 재검증) | 최초 한 행·가로 overflow 검증만으로 already implemented라 한 판정은 잘못됐다. 원본 증상은 여러 대화의 제목/미리보기 세로 잘림이다. 20행의 PC 1280×600·1440×600·1440×900에서 각 행이 44px로 눌려 두 줄이 사라지는 실패를 재현했다. 목록 컨테이너에 `shrink-0`를 추가하여 본문 스크롤이 길이를 담당하게 했다. 가로 truncate는 그대로이며 보기/삭제 선택 모드 모두 줄 높이·글자 범위와 마지막 행 접근을 검증했다. | `/chat` |
| [챗봇 대화창의 이미지도 캐릭터로 통일](https://app.notion.com/p/3d97226115e78052848fc3b006e9fde1) | fixed | 기존 답변과 답변 대기 상태의 아바타를 플로팅 챗봇이 사용하는 `/images/default-profile.png`로 통일했다. 원본 여백을 확대·클리핑해 32px 프레임 안에서도 병아리 알약 캐릭터가 식별되도록 했다. | `/chat` 대화방 |
| [AI 보고서 생성 화면](https://app.notion.com/p/3d97226115e780b8b824d271c9527094) | fixed (사용자 검토 보완) | 최초 구현은 문구만 바꿔 참고 이미지의 말풍선과 애니메이션을 누락했다. 검토 후 챗봇과 공유하는 둥근 테두리·그림자 박스에 `보고서 생성 중 (최대 2분 소요)`와 움직이는 청록색 5점을 표시한다. 동작 줄이기 설정은 점을 정지한다. 버튼 내부 spinner는 제거한 상태를 유지하며 `disabled`, `aria-busy`, `inFlight` 중복 요청 차단도 유지했다. | `/reports/new?source=medications`, `/reports/new?source=supplements` |

## 검증

- 검토 보완 회귀: `frontend/tests/e2e/431-chat-report-ui.spec.ts` — 4 passed. 두 보고서 진입 경로에서 실제 border/background/shadow, 5점, 경과 시간과 transform 변화, reduced-motion 정지, 중복 요청 차단과 오류 후 대기 제거를 확인했다.
- 기존 보고서 pending 회귀: `frontend/tests/e2e/309-ai-report-api.spec.ts`의 확정 문구·spinner 부재 기대를 갱신했다.
- 모바일/PC 캡처: `frontend/test-results/431-bubble-green/`에 375px·1280px 대화방, 두 경로 각각 375px·390px·1280px 보고서 loading, 1440px 최근 대화. fixture만 사용했고 화면/컨테이너 가로 넘침이 없음을 확인했다. 정지 이미지는 표면을 보여 주며 실제 애니메이션은 런타임 assertion으로 검증했다.
- `tsc --noEmit`: exit 0.
- 기존 보고서 retry/EMPTY/401/entry 회귀: #309에서 해당 4개 모두 통과. 이전에 확인한 이메일 기준선 불일치 항목은 이번 loading 보완 범위에서도 수정하지 않았다.
- 세로 잘림 보완: `431-chat-list-height.spec.ts` 3개 + 기존 #431 UI 4개 + `chat-session-list-api.spec.ts` 6개 = **13 passed**. `tsc --noEmit` exit 0. 원래 한 행 가로 overflow 테스트도 유지한다.
- 세로 캡처: `frontend/test-results/431-height-red/`는 수정 전 날짜만 보이는 상태, `frontend/test-results/431-height-green/`는 각 PC 크기에서 보기/선택 목록과 마지막 20번째 항목까지 접근한 상태를 담는다. 모든 데이터는 fixture다.
- 채팅 세션 API 회귀 6개가 통과해 #422 채팅 동작을 변경하지 않았고, 새로운 의료 기능이나 말풍선 내용은 추가하지 않았다.

## 기준선 주의사항

정확한 `fbeda80` detached worktree에서 #309 대표 1개와 #310 이메일 대표 1개를 실행했을 때도, 생성 후 이메일 버튼이 비활성인 현재 구현과 테스트 기대가 달라 실패했다. #431 worktree의 통합 실행에서도 같은 원인으로 5개가 실패했다. 이 문제는 #431의 `AiReportRequestPage.tsx loading only` 소유 범위 밖이므로 이메일 UI는 수정하지 않았다.
