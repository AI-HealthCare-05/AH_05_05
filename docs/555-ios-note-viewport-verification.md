# #555 iPhone 복약 메모 레이아웃 조사 및 검증

기준일: 2026-09-18. 기준 코드: main `6768a8d`. 작업 브랜치: `feature/555`.

## Root Cause

- **제보된 최초 진입 확대/넘침의 원인은 미확정**이다. Chromium과 Linux Playwright WebKit 26.5에서 375·390·393·414·430px를 조사했으나 재현하지 못했다. 실제 iPhone Safari 결과로 간주하지 않는다.
- 메모 작성 컴포넌트에는 `window.innerWidth`, `screen.width`, resize listener, 고정 페이지 폭, 페이지 scale/zoom 계산이 없다. 따라서 최초 mount 시 JS 폭 계산이 빠졌다고 판단할 근거는 없다.
- 별개의 확인된 위험 조건: 처방 select와 복용 일시 input의 실제 글자 크기가 15px이다. WebKit iOS의 포커스 확대 계산은 표준 글자 크기 16과 입력 글자 크기의 비율을 사용한다. 단, 이 조건이 제보된 **포커스 이전** 증상의 원인이라는 증거는 아직 없다.

## Evidence

- `frontend/index.html`: `width=device-width, initial-scale=1.0` 설정 존재. 사용자 확대를 제한하지 않음.
- `frontend/src/pages/medications/MedicationNoteFormPage.tsx`: 처방 select 및 Input의 기본 control 토큰 사용.
- `frontend/src/app/styles/index.css`: `--text-control: 15px`; root의 기존 overflow-x clip 존재.
- root와 main의 clipping을 진단 중 해제하고 긴 합성 처방명도 넣어 측정했다. baseline 70개 표본에서 가로 넘침 또는 resize 전후 폭 차이가 발견되지 않았다. 시점은 첫 DOM 관측, 선택 후, 날짜 포커스, 텍스트 포커스, clipping 해제, 긴 이름 새로고침, resize 복귀이다. 첫 DOM 관측이 OS의 최초 페인트를 완전히 대체하지는 않는다.
- 측정 원문: `artifacts/ios-note-viewport-20260918/baseline.json`.
- WebKit 근거: https://github.com/WebKit/WebKit/blob/main/Source/WebKit/UIProcess/API/ios/WKWebViewIOS.mm 의 `_zoomToFocusRect` (`webViewStandardFontSize = 16`, `standardFontSize / fontSize`). 이는 구현 근거이며 사용자 단말 실측이 아니다.

## Fix

- 메모 작성/수정 화면의 처방 select와 복용 일시 input에 `text-base`를 적용해 16px로 통일했다. 건강상태 textarea는 기존 16px를 유지한다.
- 전역 토큰, 다른 화면, 알림/기록 정책, 저장 payload, DB는 변경하지 않았다.
- 가로 넘침 숨김, 강제 resize, 타이머로 레이아웃 보정, `user-scalable=no`는 추가하지 않았다. 기존 main의 전역 clipping은 변경하지 않았으며 테스트에서는 이를 해제하고 검사한다.

## Regression Risk

- 글자가 1px 커져 매우 긴 처방명의 표시 길이가 달라질 수 있다. 긴 합성 처방명 및 5개 viewport에서 컴포넌트가 페이지 폭 안에 들어오는지 검사했다.
- 모바일뿐 아니라 데스크톱에서도 해당 두 입력은 16px가 된다. 공통 Input 및 다른 페이지의 글꼴 규격에는 영향이 없다.
- Linux WebKit은 iOS UIKit 키보드·날짜 피커·Safari 주소창을 재현하지 않는다. 실제 iPhone 확인이 필요하다.

## Test Result

1. 변경 전 393px 렌더링 글자 크기 회귀 테스트: 실패 (15px, 최소 기준 16px). **초기 진입 결함을 재현한 테스트가 아니라 입력 글자 크기 조건 테스트**다.
2. `playwright.ios-note.config.ts`: Chromium 10 + WebKit 10 = **20건 통과**. 5개 폭에서 포커스, unclipped 폭 검사, 새로고침, 목록으로 이동 후 재진입, resize와 작성 값 보존.
3. 기존 `532-ui-regressions.spec.ts` + `310-medication-note-collection.spec.ts`: **12건 통과**.
4. `tsc --noEmit`: 통과 (프로젝트 설정상 src 대상).
5. main 원본 및 수정본 정적 mock 빌드: 성공. 기존 500kB 초과 bundle 경고는 남아 있으며 이번 CSS 변경 범위와 별개다.
6. 공개 HTTPS 주소에서 Chromium/WebKit으로 원본/수정본 4조합 검사. 런타임 예외 및 HTTP 4xx/5xx 리소스 응답 없음. 수정본에서 합성 메모 저장·다시 열기·수정 저장 확인. 실제 API/DB 통합 검증은 아님.
7. API, 환경파일, 소스 및 service worker 경로 404, 경로 변조 400/404, POST 405 확인. 네트워크 CSP `connect-src 'none'`, 백엔드 프록시 없음.

실행 예:

```sh
# frontend/, Node 22+, 필요한 Playwright 브라우저 설치 후
PLAYWRIGHT_TEST_PORT=44555 node node_modules/playwright/cli.js test -c playwright.ios-note.config.ts
PLAYWRIGHT_CHANNEL=chromium PLAYWRIGHT_TEST_PORT=44555 node node_modules/playwright/cli.js test tests/e2e/532-ui-regressions.spec.ts tests/e2e/310-medication-note-collection.spec.ts --workers=1
node node_modules/typescript/bin/tsc --noEmit
```

전체 저장소 테스트/백엔드 테스트, 실제 iPhone, 운영 배포 검증은 수행하지 않았다. 테스트 설정 과정의 Chrome 채널 상속 오류와 WSL 개발 서버의 이전 소스 캐시는 수정/재시작 후 위 결과로 재검증했다.

## 실기기 확인 대기

1. 비교 안내에서 main 원본을 Safari 새 탭으로 열고, 첫 화면을 확대·회전 없이 촬영한다.
2. 처방 → 복용 일시 → 건강상태 기록을 선택/입력한다. 키보드 및 피커를 닫는다.
3. 새로고침, 목록으로 복귀 후 재진입을 확인한다.
4. 마지막에 가로/세로 회전 전후를 확인한다.
5. 왼쪽 아래 검증 패널에서 기록을 복사/다운로드한다. 수정본도 같은 순서로 확인한다.
6. 실제 OS 버전, Safari/PWA 여부, 재현 단계, 화면과 두 검증 기록을 회신받아 원인을 확정한다. 이번 수정만으로 원본 제보를 해결했다고 표시하지 않는다.

진단 기록은 화면 폭·확대율·컨트롤 크기·경로·시각만 기기 sessionStorage에 보관한다. 메모 내용/처방 값은 수집하지 않고 서버로 전송하지 않는다. 합성 데이터 외 실제 건강정보를 입력하지 않도록 안내한다.
