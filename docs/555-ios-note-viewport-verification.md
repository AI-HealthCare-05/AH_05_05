# #555 iPhone 복약 메모 레이아웃 조사 및 검증

기준일: 2026-09-18. 기준 코드: main `6768a8d`. 작업 브랜치: `feature/555`.

## 최신 상태: 아이폰 실측 기반 날짜 너비 개선 v2

- 사용자 피드백: 기존 원본/16px 후보 모두 날짜 입력창 넘침 동일. 따라서 #556 글자 크기 변경을 #555 해결로 보지 않는다.
- 첨부 `rxvita-555-before (2).json`의 첫 render: 화면 393px, 확대율 1, 처방/메모 폭 353px, 날짜 폭 383px, 날짜 오른쪽 403px. 포커스 이벤트 없이 이미 10px 화면 밖으로 나가 있다. 문서 scrollWidth는 기존 clipping 때문에 393px로 남아, 그것만으로 정상 판단하면 안 된다.
- 별도 붙여넣기 자료는 Android UA로, 아이폰 증거와 혼합하지 않았다. UA만으로 실제 기기 여부나 정확한 OS 버전을 추가 추정하지 않는다.
- 30px 초과는 좌우 padding 28px와 border 2px 합에 일치한다. iOS native 날짜 테마의 content-box 보정이 가장 유력한 원인이다. 원본 JSON에는 computed boxSizing이 없어 해당 속성의 실기기 직접 확인은 아직 없다.
- 공식 근거: [WebKit 버그 301648](https://bugs.webkit.org/show_bug.cgi?id=301648)에는 iOS 날짜/시간 input의 width:100% + padding 초과가 보고되어 있다. [RenderThemeIOS](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/rendering/ios/RenderThemeIOS.mm)의 `adjustInputElementButtonStyle`에는 native 날짜 컨트롤의 boxSizing을 content-box로 조정하는 코드가 있다. 자료와 실측의 일치는 원인 가설을 강하게 뒷받침하지만 수정 후 실기기 성공 증거를 대신하지 않는다.

### 변경

- `.rx-input[type=date]`, `.rx-input[type=datetime-local]`에만 `-webkit-appearance:none`, `appearance:none`, `box-sizing:border-box` 적용.
- 기본 테마의 너비 보정을 피하고, 디자인의 여백/테두리를 지정된 폭 안에 포함한다. native input type, 값 형식, 이벤트, 날짜 저장 로직은 유지한다.
- 자동 포커스, 글자 크기, 사용자 확대, 기존 clipping은 변경하지 않는다. #556 변경은 이 브랜치에 포함하지 않는다.
- 범위상 복약 메모 외 진료일정·OCR·프로필·복용 시작일의 공통 날짜 입력에도 적용된다. iOS native 피커의 열기/선택 및 빈 날짜 표시가 실제 기기에서 유지되는지 확인해야 한다.

### 검증 및 공개 비교

- 수정 전 native content-box 조건 모델 검증: Chromium/WebKit 모두 383px > 부모 353px로 실패. Linux WebKit 자체에서 iOS 결함을 재현한 것이 아니라 공식 native 테마 동작을 제한적으로 모델링한 테스트다.
- 수정 후 전용 14개 통과: 조건 모델, 진료일정 빈 값·입력·포커스·최소 높이, 메모 5개 폭의 진입·새로고침·복귀·resize/값 유지. `tsc --noEmit` 통과.
- 기존 #310 메모 목록 4개 + #532 UI 회귀 8개 = 12개 통과. 합성 정적 빌드 성공(기존 500kB 초과 bundle 경고 유지). 코드 리뷰에서 차단 결함 없음. `fill()` 검증은 실제 iPhone 피커 조작 검증이 아니다.
- 공개 HTTPS의 원본/수정본 × Chromium/Linux WebKit 4조합 확인: 수정본 appearance:none/box-sizing:border-box, 화면 내 입력 경계, 합성 메모 저장·수정 통과. 런타임 예외·실패 HTTP 리소스 없음. API/환경파일/소스 차단 및 POST 405 유지. 결과는 `artifacts/ios-note-viewport-20260918/preview-verification-date-width-v2.json`, 스크린샷은 `screens/*-date-width-v2.png`.
- 공개 비교의 1번은 main `6768a8d` 그대로, 2번은 이번 #555 날짜 너비 v2로 교체한다. 기존 16px 후보 빌드는 로컬 `preview/after-font-only-556`에 보존한다.
- 진단 v2에는 날짜 입력과 부모의 폭, appearance, boxSizing, padding, border를 추가하고, 기존 수치와 섞이지 않도록 저장 키를 구분한다. 입력값은 수집하지 않는다.
- **최종 해결 여부는 동일 아이폰에서 v2 최초 진입/날짜 선택/복귀 확인 대기. PR·원격 push·병합·운영 배포는 하지 않는다.**

아래는 v2 이전 조사 이력이다. 과거 Fix·Test Result 및 기존 공개 서버 설명을 최신 결과로 해석하지 않는다.

## 범위 분리 (2026-09-18 후속 결정)

- 사용자 요청으로 **날짜 입력 박스 가로 넘침은 #555**, **입력 포커스 자동 확대는 #556**으로 분리했다.
- #555의 제품 코드에서 16px 변경을 제외했다. 해당 수정과 글자 크기 회귀 테스트는 `feature/556`으로 이관한다.
- #555에는 넘침/초기 진입/새로고침/복귀/resize 검사와 조사 문서를 유지한다. 원래 제보는 실기기 확인 대기이며 수정 완료가 아니다.
- 아래 Fix와 20건 검증 결과는 **분리 전 조사 시점의 기록**이다. 현재 #555에 자동 확대 수정이 포함되어 있다는 의미가 아니다.
- 기존 공개 비교 주소는 main 원본과 #556의 메모 입력 16px 후보를 비교하는 용도로 유지한다. #555의 넘침 해결본으로 부르지 않는다.

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
