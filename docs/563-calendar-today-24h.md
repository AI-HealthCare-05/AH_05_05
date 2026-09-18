# #563 공통 달력·오늘 선택·24시간 입력

## 승인 범위와 상태

- 사용자 요청: 달력 내부에 오늘 버튼, OCR·복약 메모 등 날짜 입력 화면에 공통 적용, 시간은 오전/오후 대신 00~23시.
- main `6768a8d`에서 분리한 `feature/563`. 흰색 버튼 그림자 #562는 포함하지 않는다.
- 프런트엔드 변경이며 develop 대상 PR #569, release/20260918_1 대상 PR #570을 생성했다. API·DB·복용 정책 변경, 배포·운영 데이터 조작은 하지 않았다.

## 구현

- 공통 Input의 date/datetime-local만 DateInput으로 분기. 다른 입력은 기존 BaseInput을 그대로 사용한다.
- Calendar: 연·월 이동, 날짜 그리드, 내부 오늘 버튼, min/max 제한, 방향키/주 단위/Home/End/PageUp/PageDown 이동.
- DateInput: 날짜 클릭 또는 달력 아이콘/Enter/아래 방향키로 팝업. 날짜·시간은 임시 선택이며 적용 시에만 상위 폼에 전달한다. 취소/닫기/Escape는 원래 값 유지.
- 오늘은 브라우저 로컬 날짜로 선택한다(기존 native local 입력 기준). datetime의 기존 시·분은 보존한다. 기존 서울 날짜 정책에서 전달하는 min/max도 그대로 적용한다.
- 시간은 00~23시 및 00~59분. 기존 진료 시간의 10분 간격과 알림 설정의 기존 시간 선택 정책은 변경하지 않는다.
- 날짜 필드와 달력 연도·시간 컨트롤은 16px. 확대 금지, 강제 resize/zoom 복원은 사용하지 않는다.
- API 전달값은 기존 YYYY-MM-DD / YYYY-MM-DDTHH:mm 유지. 하드웨어 키보드 부분 입력은 화면에 보존하되, 완성되지 않은 날짜는 기존 native 입력처럼 상위 폼에 빈 값으로 전달한다. 선택 영역·커서도 보존한다.
- 범위를 벗어난 연도·월 이동은 가장 가까운 허용 월로 보정하고, 범위 밖 날짜/월을 비활성화한다.

## 적용 화면

| 화면 | 유지하는 조건 |
|---|---|
| OCR 조제일 | 기존 서울 오늘 +31일 상한 |
| 복약 등록·복용 시작일 | 각 흐름의 기존 min/max |
| 복약 메모 복용 일시 | 선택 처방의 기본값·ISO 저장 형식, 24시간 선택 |
| 진료일정 | 서울 기준 내일부터 선택. 오늘 버튼은 표시하되 비활성 |
| 복약 조회 기간 | 기존 2년 범위와 시작≤종료. 선택 즉시 기간 초안에 반영, 시트의 적용으로 조회 |
| 회원가입·기본정보 생년월일 | 1900년~오늘 범위, 별도 기존 만14세 정책 유지 |
| 개발 전용 챌린지 생성 날짜 | 공통 Input 분기에 포함. 실제 서비스 제공 범위 변경 아님 |

조회용 챌린지 실천 달력은 날짜 입력이 아니므로 교체하지 않았다.

## 검증 및 제한

- 수정 전 OCR의 공통 달력 팝업 부재로 신규 테스트 실패(RED)를 확인했다.
- 2026-09-18 최종 전용 테스트 Chromium/WebKit 총 **20/20 통과**. 320/375/393/430px, 오늘·취소·적용, 00:00/23:59, 기존 시간 보존, 윤년, 순차 입력·기존 연도 교체, 연·월 범위 보정, 진료일 제한, 기간 조회, 정상 회원가입까지 확인했다.
- OCR 조제일 수정→저장 요청의 ISO 값 및 다음 화면 이동 **1/1 통과**. VITE_USE_MOCK=false의 API 호출 코드 경로에서 Playwright가 합성 응답을 공급한 테스트이며 실제 서버·DB 통합 검증은 아니다. 초기 cold-load 30초 timeout 후 단독 90초 제한으로 재실행하여 36.9초에 통과했다.
- TypeScript `tsc --noEmit` 통과. 별도 읽기 전용 리뷰에서 찾은 직접 입력 커서 이동 및 범위 밖 월 이동 문제를 수정하고 전용 테스트에 회귀 사례를 추가했다.
- 최종 코드 기준 기존 기간 필터·진료일정 회귀 **21/21 통과**(Chromium, 1.8분). 전용20 + OCR 저장1 + 관련21 = 42건 통과이며, 전체 CI 결과가 아니다.
- 기존 테스트를 넓게 실행했을 때 30 통과 / 5 실패 / 61 API-mode 전용 skip. 실패 원인은 아래와 같다. 이를 전체 테스트 통과로 합산하지 않는다.
- 기존 account-profile 테스트 5건은 생년월일을 입력하기 전에 만14세 동의 체크를 기대하는 helper 순서에서 실패했다. main의 `applyAgeTerms`는 생년월일 검증을 먼저 요구한다. 수정 전 main 정적 데모(6768a8d)에서도 빈 생년월일→동의 클릭 시 unchecked 및 '생년월일을 입력해주세요.'를 재현했다. 이번 변경에서 가입 정책이나 이 테스트들의 순서를 바꾸지 않았다.
- 실제 아이폰의 네이티브 키보드/VoiceOver 실기기 검증은 미실시. 로컬 Chromium/WebKit 결과를 실기기 검증으로 표현하지 않는다.
- 실제 운영 API 통합 테스트, 배포 반영 검증, 전체 CI 통과는 주장하지 않는다.
- PR 충돌 해결: 두 대상 브랜치에 이미 포함된 #556(`998b273`)만 병합했다. develop/release 전체나 #562는 가져오지 않았다. #563의 Input 분기와 BaseInput 분리를 유지하면서 #556의 일반 입력 16px을 BaseInput에 보존했다.
- 충돌 해결 전 로그인 회귀 테스트에서 기대 16px 이상 / 실제 15px으로 실패하는 것을 확인했다. 단순히 #563 쪽 Input을 선택하면 확대 방지 변경이 유실되므로 분리된 렌더러에도 반영했다.
- 충돌 해결 후 재검증: `tsc --noEmit`, #556 Chromium/WebKit **32/32**, #563 Chromium/WebKit **20/20** 통과(2026-09-18). 결과는 `artifacts/calendar-563/conflict-556-verified/`, `conflict-calendar-verified/`에 보존한다. 회원가입 후 홈 이동 중 꺼진 로컬 백엔드의 챌린지 API 연결 경고가 있었으며 서버 통합 테스트 통과를 의미하지 않는다.

## 재현

frontend에서 WSL Node 22로 실행:

```bash
node node_modules/typescript/bin/tsc --noEmit
CHOKIDAR_USEPOLLING=true PLAYWRIGHT_TEST_PORT=44563 \
node node_modules/playwright/cli.js test -c playwright.calendar.config.ts \
  --output=../artifacts/calendar-563/final-verified
```

Windows 파일 변경 감지가 누락되는 WSL 환경에서는 테스트 서버를 재시작하거나 polling을 사용한다. mock/real-mode 테스트 서버를 동시에 실행하지 않는다.

## 화면 증거

`artifacts/calendar-563/screenshots/`의 실제 앱 + 합성 데이터 로컬 화면:

- `ocr-{chromium,webkit}-393.png`
- `memo-24h-{chromium,webkit}-393.png`
- `visit-{chromium,webkit}-393.png`

운영 계정·운영 데이터가 아니며 이미지는 검토용 로컬 산출물로만 보존한다.
