# #392 비밀번호 재설정 화면

## 최종 승인본 및 PR 검증 (2026-09-10)

- 현재 구현은 별도 페이지가 아니라 로그인 위 공통 바텀시트이다. 아래 기존 기록의 별도 화면 설명은 이전 검수 이력이다.
- 이메일 입력 + 임시비밀번호 발송, 중복 제출 방지/실패 재시도, 로그인 값 보존 및 닫기 포커스 복귀를 유지한다.
- `/password-reset` 직접 접근은 `/login`으로 replace한 후 바텀시트를 연다.
- 최신 main `a676ce9`에 승인본을 통합했다. `AuthPage` 충돌 해결 시 main의 인증코드 재전송 중복 방지 ref/함수를 보존했다.
- 최종 트리 `tsc --noEmit`, `tsc -b`, Vite production build 통과 (기존 큰 청크 경고).
- 바텀시트 6개, main 재전송 중복 방지 1개, 기존 로그인/비밀번호 5개 회귀 테스트를 새로 실행해 통과했다.
- 44462 전용 포트와 독립 Vite 캐시를 사용했다. 모든 미처리 요청은 닫힌 127.0.0.1:9로 향하도록 설정했으며 실제 비밀번호 재설정/메일 요청은 보내지 않았다.
- 처음 넓게 선택한 회원가입 API 테스트 파일은 기존 fixture에 이메일 인증 응답이 없어 닫힌 proxy에서 실패했으며 중단했다. 이 결과는 통과로 계산하지 않았고, 충돌과 관련된 재전송 테스트만 별도 검증했다.
- 원본 승인 커밋 `43fa879`는 `codex/backup-392-approved`에 보존했다. 사용자 루트 체크아웃과 #369는 변경하지 않았다.

---

작성일: 2026-09-10

## 범위와 위치

- `feature/392`, 기준 `origin/main` / `8aedd44` (작업 전 fetch 확인).
- 작업공간: `C:/dev/AH_05_05/.codex-work/feature-392`.
- 루트 `feature/315`와 기존 사용자 서버는 전환·재시작하지 않았다.
- 로그인에서 이메일 입력 여부와 관계없이 `/password-reset`으로 이동한다.
- 로그인 이메일은 URL 대신 route state로 전달하며 새 화면에서 수정 가능하다. 비밀번호는 전달하지 않는다.
- 기존 `POST /api/v1/auth/password-reset`에 `{ email }`을 보낸다. **재설정 링크나 새 비밀번호 입력 시스템이 아니라 기존 임시 비밀번호 메일 발송 방식**을 유지한다.
- 공통 Header/Input/Button, 기존 흰색 카드와 청록색 토큰을 사용한다. 320px 제목은 단어 단위 줄바꿈한다.
- 발송 중 입력과 버튼 비활성화 + ref 중복 제출 방지, 실패 시 입력 유지·재시도, 성공 시 일반적인 요청 접수 안내를 제공한다. 202를 실제 메일 전달 완료로 표시하지 않는다.
- 돌아가기는 로그인에서 진입했으면 history pop, 직접 진입했으면 로그인으로 replace한다.
- 서버/API/마이그레이션/의존성 변경 없음.

## 검증

WSL Node 22.23.1, Playwright Chromium 사용. frontend 디렉터리에서 실행한다.

```bash
VITE_USE_MOCK=false PLAYWRIGHT_TEST_PORT=44396 PLAYWRIGHT_CHANNEL=chromium node node_modules/playwright/cli.js test tests/e2e/392-password-reset.spec.ts --output=test-results-392-final-verified
VITE_USE_MOCK=true PLAYWRIGHT_TEST_PORT=44393 PLAYWRIGHT_CHANNEL=chromium node node_modules/playwright/cli.js test tests/e2e/auth-login-figma-baseline.spec.ts tests/e2e/374-password-hangul.spec.ts --timeout=60000 --workers=1 --output=test-results-392-mock-regression
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build
```

- 신규 흐름 **6 passed (20.4s)**: 빈 로그인 이메일 진입/뒤로가기, 이메일 수정·형식 검증, pending 중 추가 submit 차단, 실패 후 재시도, 직접 진입 fallback, 320/390/1280px 가로 넘침·버튼 접근.
- 기존 로그인/비밀번호 입력 목업 회귀 **5 passed (24.3s)**.
- 구현 전 신규 진입 테스트가 `/login`에 남는 원인으로 실패하는 RED를 확인했다.
- 최초 validity 검사에서 DOM 객체의 비열거 속성이 빈 객체로 직렬화되어 실패했다. 브라우저 안에서 `validity.valid`를 직접 읽는 검사로 수정했으며 제품 검증 조건은 바꾸지 않았다.
- 네트워크 차단 최초 glob이 `/src/shared/api/client.ts`까지 막아 중간 실행을 중단했다. URL pathname이 `/api/`로 시작하는 경우만 차단하도록 수정했고 최종 실행은 통과했다.
- 타입 검사·production 빌드 통과. 기존 500KB 초과 청크 경고만 남음.
- 로컬 커밋 직전 재검증: `tsc -b`, Vite build, 포트 `44492`의 위 신규 흐름 6개 모두 통과 (1.3m). `VITE_USE_MOCK=false`에서 API 요청을 전부 가로채는 #392 파일만 실행했으며 결과는 `frontend/test-results-392-commit-verification/`에 보관한다.
- 독립 정적 리뷰: blocking finding 없음. 실기기 IME, 실제 메일 전달, 서버 worker 처리와 사용자 비밀번호 변경은 최종 검증 범위가 아니다.

### 실행 실수와 영향 범위

처음 기존 목업용 #374 테스트를 신규 API-fixture 테스트와 함께 `VITE_USE_MOCK=false`로 실행했다. 기존 테스트는 API interception이 없어 `new-patient@example.com`이라는 테스트 주소에 대해 로컬 회원가입 인증 요청이 발생했다. 화면 오류에는 실제 인증번호 불일치가 확인된다. 해당 실행은 4 failed / 7 passed였으며 정상 회귀 결과로 계산하지 않았다. 이후 #374는 목업 모드로 분리했다. #392 테스트의 비밀번호 재설정 요청은 처음부터 가로채었고 사용자 비밀번호를 변경하지 않았다. 최종 #392 테스트는 미지정 API 요청도 차단한다. 테스트 인증 요청으로 생긴 로컬 기록/메일 작업은 임의 삭제하지 않았다.

## 수동 확인

1. 로그인 이메일을 비운 채 재설정 → 별도 화면 진입.
2. 로그인에 이메일을 적고 재설정 → 같은 이메일 표시, 수정 가능.
3. 빈 값은 발송 불가, 잘못된 이메일은 발송하지 않음.
4. 발송 중 여러 번 눌러도 중복 요청 없음.
5. 성공 후 요청 접수 안내 → 로그인으로 돌아가기. 뒤로가기로 두 화면이 반복되지 않음.
6. 실패 시 이메일 유지 후 다시 발송 가능.
7. `/password-reset` 직접 진입·새로고침 후 뒤로가기 → 로그인.
8. 모바일 320/390px에서 입력창 양옆과 버튼이 잘리지 않음.

캡처: `frontend/test-results-392-final-verified/392-password-reset-reset-fields-and-actions-fit-{320,390,1280}px/password-reset-{320,390,1280}.png`.

## 이후 통합 주의

- `router.tsx` 추가 경로는 #315·#390 변경을 덮어쓰지 말고 한 줄 단위로 결합한다.
- #390 전역 챗봇 런처의 인증 화면 제외 경로에 `/password-reset`도 포함해야 한다. 현재 이 브랜치에는 #390 런처가 없다.
- #369 공통 토큰/반응형 변경을 결합한 후 새 페이지도 확인한다. 해당 디자인 브랜치를 이 작업에서 병합하지 않았다.
- page/test/docs는 명시적으로 커밋하고 test-results 산출물은 로컬에 보관한다.
