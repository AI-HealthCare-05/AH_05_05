# feature/369 UI/UX Pro Max 독립 검수

기준: `451bd86`, `/mnt/c/dev/ah_05_05/.codex-work/feature-369`. 작성자: UI/UX Pro Max 검수 에이전트. 상태: 동결 구현 독립 재검수 완료.

## 보존 계약

- 기존 white / mint `#077A74` / navy `#002C68`, 얕은 clay 표현을 따른다. 새 팔레트나 글꼴을 도입하지 않는다.
- 사용자 승인 홈·챗봇 시안, 5점 로더, 원래 로고·내용·기능·표시 순서를 보존한다. 유틸리티 필터 문구 변경만 기존 정렬 의미/방향/옵션/기본 동작 안에서 별도 대조한다.
- Radix의 dialog/checkbox/select 역할, keyboard·focus 관리, disabled 동작을 유지한다.
- 변경 화면의 전후 이미지는 동일 fixture·시간·viewport·상태로 비교해야 한다. 공유 CSS 영향 소비처도 coverage에 포함한다. `/dev` 시안, 실제 서비스 라우트의 fixture, 실제 DB 검증을 구분한다.
- 읽기 전용 UI 검사 및 fixture만 수행한다. 실제 API/DB 변이 요청, 라이브러리 설치, commit/push는 이 검수에 없다.

## 사용한 스킬과 검색 근거

`/mnt/c/Users/sdh08/.codex/skills/ui-ux-pro-max/SKILL.md`, `references/quick-reference.md`, `references/pro-rules.md`를 모두 읽었다. package.json에서 React 19 / Tailwind 4 / Radix를 확인했다. 기존 디자인 방향이 확정되어 있으므로 새 `--design-system` 생성은 하지 않았다.

| 실제 로컬 검색 | 검증된 결과 | 적용 범위 |
|---|---|---|
| `focus not obscured --domain ux` | Focus Not Obscured Enhanced/Minimum, Focus Appearance | 고정 탭·모달이 focus를 가리지 않는지. AA 최소와 AAA 전체 노출 기준은 구분 |
| `badge chip label wraps --domain ux` | Compact Label Overflow | 필수 긴 문구를 임의 생략하지 않고 집합 reflow·shrinkable layout을 검토 |
| `chip badge overflow nowrap --stack html-tailwind` | Compact label layout | flex-wrap/min-width/shrink 제약만 참고. 데이터 생략 허가로 해석하지 않음 |
| `modal focus restore --stack react` | Manage focus properly | 기존 Radix focus trap/return focus를 유지하고 실제 keyboard 동작 확인 |

검색 결과는 사용자·저장소 규칙보다 우선하지 않는다. 자료에 포함된 URL의 웹 페이지를 별도 열람한 것으로 주장하지 않는다.

## 구현 전 확인

- 원래 `Button`은 `h-control=52px`, `min-h-touch=44px`, native disabled를 사용한다.
- 원래 전역 `:focus-visible`은 2px teal outline이다. 새 box-shadow가 base layer의 outline을 지우지 않는지 최종 computed CSS로 확인한다.
- 원래 `DialogContent`는 Radix 기반이며 기본 닫기 버튼은 44px, accessible name은 `닫기`다. 변경 시 Title/Description 및 닫힘 정책을 유지한다.
- 원래 `BottomTabbar`는 64px·5개 버튼·아이콘과 라벨 상시 표시이며 활성 항목 `aria-current=page`를 사용한다.
- 폰트 크기는 다수 px 토큰이다. `html{font-size:125%}`만 적용한 결과는 실제 텍스트 확대나 iOS Dynamic Type 검증이 아니다. text-only simulation과 실제 기기 검증을 구분한다.
- 기본 shell sandbox는 bwrap 누락으로 실행하지 못했으나 읽기 전용 escalation은 성공했다. 설치된 Linux Node 22 및 기존 Chromium 경로를 확인했다. 아직 브라우저 성공 검증 결과는 없다.

## 독립 최종 실측 결과

UI/UX Low가 clean before 44268과 동결 after 44269에서 동일 /dev/my-authenticated fixture, 고정 시간 2026-08-25T12:00:00+09:00, ko-KR, Chromium으로 375/390/844/1440 × 844를 비교했다. API는 /api/v1/**만 차단했고 변이 요청 및 pageerror는 0이었다.

- Escape 이후 opener 복귀: before 4개 너비 모두 false → after 모두 true.
- MY switch 실제 root: 56×32 → 56×44px로 목표 충족.
- 알림 시트 Tab 16회 trap 이탈 0, 수평 overflow 0, focus 대상 44px 미달 0으로 보존.
- reduced-motion 시트 animation none. Button transition은 일반 모션에서 background-color 0.14s, box-shadow 0.14s, transform 0.12s이며 reduced-motion은 none/0s.
- 로그인 focus outline 민트 2px 보존. 844×390 가로 after도 trap/복귀/overflow 정상. 자기전 시/분 bottom 390.09375px의 0.094px 소수점 오차는 실질 가림으로 판정하지 않았다.

증거: /tmp/uiux-369-clean-before-a11y/report.json 및 PNG 8개, /tmp/uiux-369-final-a11y/report.json 및 PNG 8개, /tmp/uiux-369-final-landscape/report.json 및 PNG 2개. 이전 44369는 stale CSS이므로 최종 증거에서 제외한다.

실제 API 모드 44271의 /reports/new?source=medications도 독립 확인했다. 375×812, reduced-motion, HTTP hold fixture에서 pending 버튼은 disabled=true, aria-busy=true, 335×52px, spinner 존재 및 animation=none, 수평 overflow=0이었다. 대기 중 Enter/Space 추가 후에도 가로챈 POST 1회 유지. pageerror/requestfailed 0, 서버에 전달한 변이 0. 증거는 /tmp/uiux-369-final-a11y/real-report-pending.json 및 real-report-pending-375.png다. 제품 caller와 fetch를 사용했지만 외부 HTTP는 fixture로 대체했으므로 production DB end-to-end 검증은 아니다.

검사 범위에서 확정된 잔여 접근성 회귀는 없다. 제품 코드 변경 및 기능·카피 변경 요구는 없다. 전체 화면 시각 before/after coverage, 긴 사용자 문구, iOS/Android 실기기 및 screen reader는 이 독립 실측의 완료 주장에 포함하지 않는다. 별도 시각 검수와 합쳐 최종 판단해야 한다.

## 최초 판정 대기 기록

390px/큰 화면 overflow와 터치 크기, keyboard focus/close/return, reduced-motion, pending disabled·반복 탭, 긴 내용, 전후 화면별 내용 보존, 공유 CSS 영향 coverage, 새 배지 1회 모션의 실제 서버 확정 조건을 최종 변경 후 검증한다. iOS/Android 실제 기기, screen reader, production DB end-to-end는 이 문서의 검증 범위에 포함되지 않는다.
