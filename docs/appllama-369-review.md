# feature/369 Appllama 독립 디자인 검수

상태: 동결 구현 독립 재검수 완료. 기준 커밋 `451bd86`.

## 검수 기준

요청한 `appllama-app-design-skill/SKILL.md`와 `references/simulator-loop.md`, `references/performance.md`, `references/motion.md`를 모두 읽었다. 프로젝트는 React 19 / Vite / Tailwind / Radix 모바일 웹이므로 Expo·React Native 전환이나 패키지 도입을 요구하지 않는다.

- 사용자 승인 white / mint-teal `#077A74` / navy `#002C68`와 얕은 clay 표면, 기존 로고·글꼴·내용·기능을 보존한다. navy는 제목과 구조, teal은 행동·선택·진행에 쓴다. 오류/경고 의미색은 추가 브랜드 accent가 아니다.
- 기존 radius scale(card 16, button 14, input 12, sheet 24, pill)과 간격 체계를 유지한다. 컴포넌트마다 임의 그림자·곡률을 추가하지 않는다.
- 탭 사이 화면 slide는 넣지 않는다. 자주 누르는 행은 배경 피드백, 버튼은 짧은 press, 드문 모달은 짧은 상태 전환을 사용한다.
- 챗봇 로더는 사용자 지정 Uiverse 5점과 기존 대기 문구를 유지한다. 배지의 기존 그림과 윤곽을 유지하고 신규 실제 지급당 한 번만 보상 모션을 제공한다. UI 시연을 실제 지급으로 표시하지 않는다.
- 변경한 모든 화면과 공통 CSS 소비처의 전후 이미지는 같은 데이터·시간·뷰포트·상태로 비교한다. 내용·동작 보존은 이미지뿐 아니라 DOM과 행동 검증으로 확인한다.

## 참고 자료와 한계

현재 도구 목록에 Appllama MCP는 없다. 실시간으로 20–30개 출시 앱 화면을 조회했다는 주장을 하지 않는다. 기존 `design-plans/component-audit-selection.md`의 원출처 연결 자료와 사용자 승인 `previews/home-after-390x844.png`, `chat-after-390x844.png`, `badge-award-contour-rotating-390x844.png`를 실제로 열어 표면·밀도·정보 순서·배지 윤곽을 확인했다.

Linux Chromium 390×844 실행은 모바일 웹 레이아웃 검사다. iOS 시뮬레이터, Android hardware back, 가상 키보드·safe-area 실기기, Dynamic Type, 저사양 실기기 release-build 60fps 측정과 동일하지 않다. 현재 앱은 light 토큰을 사용하며 별도의 dark theme 완성 판정은 이 범위에 없다.

## 초기 브라우저 관찰

`http://127.0.0.1:44269`의 e2e-mock UI에서 `/tmp/appllama-369-audit.mjs` 실행. 로컬 테스트 principal `appllama-qa@example.invalid`, 시스템 시간 고정 `2026-08-25T12:00:00+09:00`, 390×844, reduced motion 사용. 실제 DB를 읽거나 변경하지 않았다. 이 캡처는 작업 중 관찰이며 최종 공식 before/after 산출물과 구분한다.

| 상태 | 가로 넘침 / pageerror | 초기 관찰 |
|---|---|---|
| 홈 복수 처방, 빈 상태, 오류 상태 | 없음 | 주요 터치 대상 44px 이상 |
| 챗봇 이력 | 없음 | 입력·근거 영역 및 고정 5탭 보존 |
| 복약 | 없음 | 기존 삭제 버튼 41.8×44px |
| 영양제 | 없음 | 주요 터치 대상 44px 이상 |
| 마이 | 없음 | 스위치 시각 rect 56×32px; 실제 label hit-area 추가 확인 필요 |
| 챌린지 둘러보기 | 없음 | 기존 내부 2탭 높이 36px |
| 배지 목록 | 없음 | 주요 터치 대상 44px 이상 |
| 로그인 | 없음 | 기존 재설정 링크 35.9×21px |

텍스트 크기는 computed font-size와 line-height를 각각 1.25배 적용한 **text-only simulation**에서도 가로 넘침이 없었다. px 단위 토큰 때문에 `html{font-size:125%}`만 바꾸는 검사는 사용하지 않았다. 초기 홈·챗봇·로그인 확대 스크린샷을 직접 판독했고 명백한 겹침은 없었다. 다른 화면을 자동 측정 결과만으로 시각 합격 처리하지 않는다.

스크린샷 및 DOM 측정: `/tmp/appllama-369-initial/`. 작은 터치 대상은 원래 코드에서도 존재하며 lead와 UI/UX 검수자에게 전달했다. 공통 sheet의 하단 inset 누락 가능성은 lead가 consumer padding을 확인한 후 공통 `env(safe-area-inset-bottom)` 여백을 추가했다. 실제 기기 inset 검증은 남아 있다.

## 최종 판정

clean `451bd86`의 44268과 동결 구현 44269를 동일 fixture·시간·390×844에서 비교했다. normal 및 text-only 125% 검사에서 가로 overflow와 page error는 0건이었고, 10개 fixture의 본문·control label·href가 일치했다. 확대 화면 직접 판독에서도 명백한 텍스트 겹침이나 신규 레이아웃 회귀는 없었다. 증거는 `/tmp/appllama-369-clean-before`, `/tmp/appllama-369-final`에 있다.

초기 최종본에서 MY 스위치의 44px 투명 hitbox에 회색 사각 배경이 보이는 회귀를 발견했다. 소비처의 unchecked 배경을 보이는 32px `::before` 트랙으로 옮긴 뒤 `/tmp/appllama-my-corrected.png`에서 root 투명, 56×44 hitbox, 32px track을 확인했다. 배지 목록의 초기 조각 이미지는 코드 회귀가 아니라 `img.complete=false`인 캡처였으며, decode 뒤 `/tmp/appllama-badges-decoded.png`에서 정상 원본 그림을 확인했다.

최신 영상 재검수에서 다음을 확인했다.

- `test-results-369-badge-ready-video` 5.84초 영상: 이미지 gate 중 완료 정보 유지, 이미지 준비 후 세로 1회전, 정적 끝 상태, 재방문 및 reduced-motion 정적 상태. 테스트 fixture는 1px PNG이므로 회전 lifecycle 증거이며 실제 배지 윤곽 품질의 근거로 사용하지 않는다.
- `test-results-369-controls-final-video` 7개 영상: loading 버튼의 enabled teal 복귀가 유지되고, switch 선택 끝 상태와 dialog/sheet reduced-motion 정적 재오픈이 보인다.
- 시간순 추출 프레임은 `/tmp/appllama-motion-frames/badge-ready-*.png`, `/tmp/appllama-motion-frames/control-ready-*.png`에 있다. 신규 명백한 회귀는 발견하지 않았다.

최종 water-only contour 보완도 독립 판독했다. 실제 `water-badge.png`는 alpha가 없는 RGB 원본이어서 기존 원형 CSS만으로는 청록 외곽 밖 흰 matte가 남았다. 원본 파일은 바꾸지 않고 해당 filename에만 자체 측정한 243점 CSS polygon을 적용했다. 1400×820 light/navy 확대와 product light/navy/rotation PNG에서 넓은 흰 원판 잔여나 들쭉날쭉한 절단은 없었고, 실제 water 영상의 10fps 샘플에서 회전 중 clip이 그림을 따라 유지한 뒤 정상 정면 및 재방문 정적 상태를 확인했다. 확대 최외곽의 얇은 anti-alias 선은 남는다.

근거는 `/tmp/water-contour-light-dark-1400x820.png`, `frontend/test-results-369-water-contour-final/`, `frontend/test-results-369-water-contour-video/`다. navy 배경은 contour 검사용 강제 배경이라 정식 dark-theme 대비 판정이 아니다. 마지막 reduced 영상 구간은 이미지 paint 전에 끝났으므로 reduced static-art 영상 판정에서는 제외하고 자동 lifecycle 테스트 근거와 구분한다. 다른 walk 자산은 filename 선택 조건과 `clip-path:none` 회귀 테스트로 보존을 확인했으며, 이번 보완에서 별도 walk 실물 전후 PNG는 만들지 않았다.

기존 작은 대상인 복약 삭제 약 41.8×44px, 챌린지 내부 탭 36px 높이, 로그인 재설정 35.9×21px은 이번 8개 승인 묶음 밖의 잔여다. 공통 소비처 전후 coverage는 별도 `design-plans/369/coverage.json`과 gallery 판정을 따른다. 원본 영상은 25fps이고 reviewer는 샘플 프레임을 판독했으므로 full-speed feel, 모든 프레임, 실기기 release-build 60fps를 보증하지 않는다.
