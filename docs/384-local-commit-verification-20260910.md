# Feature 384 local commit verification

## PR 준비 최종 재검증 (2026-09-10)

- 최신 `origin/main`의 #315 병합본 `a676ce9`를 격리된 `codex/384-pr-review` 작업 폴더에 통합했다.
- 배지 화면 충돌은 공식·맞춤 배지의 독립 로딩/오류/목록을 보존하고 공통 헤더와 뒤로가기를 모두 유지했다.
- `tsc --noEmit`, `tsc -b`, Vite production build 통과. 기존 500kB 청크 경고는 남는다.
- 목업 21개, HTTP fixture 29개를 새로 실행해 모두 통과했다. 공식·맞춤 배지와 뒤로가기를 함께 확인하는 1개 테스트를 추가했다.
- 추가 테스트의 최초 fixture는 snake_case였으나 실제 맞춤 API는 camelCase이므로 fixture를 바로잡고 HTTP 29개 전체를 재실행했다.
- 읽기 전용 별도 리뷰에서 병합 부분의 Critical/Important 지적 없음.
- 전용 44484 포트와 전용 Vite 캐시를 사용했다. 미처리 API는 127.0.0.1:9로 차단했다. 실제 사용자 DB 검증이 아니다.
- 아래 내용은 이전 검수 기록이다. 이번 PR 준비에서도 사용자 루트 체크아웃과 #369는 변경하지 않았다.

The local commit packages the existing six requested fixes: canonical medication frequency limits, medication/supplement completion summaries, challenge participation and badge back navigation, public guest ranking, and the complete medication list inside expanded prescriptions. No new product changes were made during packaging.

Fresh verification on 2026-09-10, Node 22.23.1 and Linux Chromium:

- TypeScript `tsc --noEmit` and `tsc -b`: passed.
- Vite production build: passed; the existing large bundle warning remains.
- Mock tests: 21 passed across `384-home-public-ranking`, `384-home-completion-summary`, and `home-figma-overhaul`.
- HTTP fixture tests: 28 passed across `384-challenge-navigation`, `home-medication-compression`, and `medications-management-api`.
- Staged whitespace check: passed.

Browser checks used port 44484. The HTTP fixture run set `VITE_API_PROXY_TARGET=http://127.0.0.1:9` so unmatched requests could not reach the user's backend. Local mock state and intercepted requests are not a real database integration test.

Only reviewed source, tests, and Markdown reports are included. Capture galleries, screenshots, test outputs, caches, environment files, and preview artifacts are left outside the commit and preserved in this worktree. Earlier reports describe their historical verification checkpoints; this report records the fresh packaging gate. The root checkout stays on `feature/315`; this feature worktree is detached at its resulting commit to make the branch available for manual switching. No push or merge is performed.
