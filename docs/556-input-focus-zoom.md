# #556 iOS 화면 최초 진입 및 입력 포커스 시 확대 현상 개선

2026-09-18 사용자 요청으로 #555 날짜 입력 박스 가로 넘침과 분리했다.

## 이관한 변경

- 최신 main `6768a8d`에서 분기한 `feature/556`.
- 메모 처방 select, 복용 일시 input의 실제 글자 크기 15→16px.
- 375·390·393·414·430px에서 위 컨트롤과 textarea의 렌더링 글자 크기를 검증하는 테스트.
- WebKit 기준: https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/ios/WKWebViewIOS.mm 의 `_zoomToFocusRect` 글자 크기 기반 확대 계산.

## 추가 조사와 변경 (2026-09-18)

- 공통 `Input`과 챗봇 textarea가 `--text-control: 15px`를 사용함을 코드와 실제 렌더링으로 확인했다. 로그인, 영양제 검색·추가, 내 정보, 진료일정, OCR 결과, 복용 일정, 챗봇을 조사했다.
- 공통 `Input`과 챗봇 textarea를 `text-base`(16px)로 변경했다. 전역 `--text-control` 토큰은 유지하여 버튼·설명 글자 크기를 함께 바꾸지 않았다.
- 메모 select와 복용 일시의 기존 16px 이관 변경은 유지한다. 영양제 메모 textarea는 이미 16px였다. 나머지 native input은 파일·라디오·체크박스·배율 슬라이더로, 텍스트 편집 입력과 구분했다.
- 팝업의 기본 포커스, 영양제 직접 입력의 자동 포커스, 챗봇 전송 후 포커스를 유지했다. 확대 금지, 강제 resize, 타이머, 가로 넘침 숨김은 추가하지 않았다.
- 사전 조사 자료: `artifacts/ios-input-zoom-556/investigation.md`, `rendered-controls.json` (로컬 자료, 커밋 대상 아님).

## 검증 결과와 한계

- 수정 전 신규 화면 검증에서 16px 이상 조건이 실제 15px로 실패하는 것을 확인한 뒤 변경했다.
- Chromium·Linux WebKit: 전용 검증 32개 통과. 렌더링 글자 크기, 주요 입력 경계, 자동 포커스, 긴 검색어·챗봇 초안을 확인했다.
- 메모 너비 375·390·393·414·430px, 기타 주요 화면 393px, 긴 입력 375·430·1280px를 검증했다. 모든 화면을 모든 너비에서 검증한 것은 아니다.
- 기존 채팅 입력 3개 및 #532 UI 회귀 8개: 총 11개 통과. 5줄 자동 높이, 전송 후 높이 복구, 한글 IME, 검색 포커스 링 등을 확인했다.
- 별도 채팅 전송·포커스 회귀 3개 통과(응답은 테스트에서 대체). 첫 실행은 10초 제한에서 최초 페이지 로딩이 시간 초과되어 1개 실패·2개 통과했다. 코드 변경 없이 30초 제한으로 재실행해 3개 통과했다. 세션 목록은 로컬 백엔드 미실행으로 연결 오류가 남아, 이 결과는 목록 API 정상 동작을 증명하지 않는다.
- `tsc --noEmit` 통과. 저장소 전체 테스트 및 실제 백엔드 통합 검증은 수행하지 않았다.

## 실기기 확인 및 수정 방향 확정 (2026-09-18)

- 사용자가 iPhone 테스트 결과를 전달했다: 기준본에서 확대가 재현되었고 입력 글자 16px 비교본에서는 해결되었다.
- 이어서 사용자는 입력 중 확대된 상태가 입력 종료 후 초기화되지 않는다고 설명했다. 이에 따라 화면 진입 시 별도로 폭이 잘못 계산된다고 단정하지 않고, **입력 포커스 확대가 남아 이후 화면에서도 커 보이는 흐름**으로 증상을 정리한다.
- 대응은 기존 `feature/556`의 공통 Input·복약 메모 select/date·챗봇 textarea 16px 적용을 유지한다. 이미 16px인 복약·영양제 메모 textarea는 변경하지 않는다. 라디오·체크박스·파일·배율 슬라이더는 텍스트 입력과 구분한다.
- 최상위 부모에 기기 폭을 강제로 지정하거나 blur/탭 이동 시 배율을 강제 초기화하지 않는다. 사용자 핀치 확대, 입력 포커스, IME 동작을 유지한다.
- 이 실기기 결과는 사용자 전달 기준이다. 해당 테스트의 기종·iOS 버전·브라우저 버전·배율 시계열 원본은 아직 받지 않았으며, 모든 iOS 기기에서 검증했다고 확대 해석하지 않는다.
- 기존 자동 테스트는 실제 렌더링 글자 크기·레이아웃·입력 동작을 검증한다. Linux WebKit이 실제 iOS 키보드 자동 확대를 재현했다고 간주하지 않는다.
- 수정 방향 확정 후 재검증: 전용 Chromium/WebKit 32개 및 기존 채팅 입력·#532 UI 회귀 11개, 총 43개 통과. `tsc --noEmit`도 통과했다. 추가 제품 코드 변경은 필요하지 않았으며, 기존 16px 수정 커밋을 유지했다.

## 남은 범위

- 기존에 열린 탭의 확대 상태를 소급해서 초기화하는 변경은 아니다. 새 수정본을 다시 연 뒤 입력 → 키보드 닫기 → 탭 이동 흐름으로 확인한다.
- 실기기 재현/해결은 위 사용자 전달 결과와 구분해서 기록하며, 자동 테스트만으로 판정하지 않는다.
- 날짜 입력 박스 가로 넘침은 #555에 남기며 이 변경으로 해결했다고 표시하지 않는다.

## 검증 실행

```sh
node node_modules/playwright/cli.js test -c playwright.ios-input.config.ts
PLAYWRIGHT_CHANNEL=chromium node node_modules/playwright/cli.js test tests/e2e/456-chat-input.spec.ts tests/e2e/532-ui-regressions.spec.ts --workers=1
VITE_USE_MOCK=false PLAYWRIGHT_CHANNEL=chromium node node_modules/playwright/cli.js test tests/e2e/chat-composer-focus.spec.ts --workers=1 --timeout=30000
node node_modules/typescript/bin/tsc --noEmit
```

실행은 WSL에서 수행했다. 각 명령은 해당 모드의 별도 포트를 `PLAYWRIGHT_TEST_PORT`로 지정하고 서버 종료 후 실행한다. 기존 서버를 재사용할 경우 mock/real 모드가 다르면 안 된다.

최초 공개 비교 서버는 이후 #555 날짜 너비/정렬 검증 전용으로 분리했다. #556은 별도의 합성 데이터 정적 서버에서 main 기준본과 공통 Input·챗봇을 포함한 16px 비교본을 제공했다. 임시 주소와 실행 정보는 로컬 `artifacts/ios-input-zoom-556/server-status.md`에 보관한다. 운영 데이터와 연결하지 않으며 PR·병합·운영 배포는 하지 않았다.
