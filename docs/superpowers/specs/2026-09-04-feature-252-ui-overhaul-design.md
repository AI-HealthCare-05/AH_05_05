# Feature 252 UI Overhaul Design

## Authority

- Issue: `#252 UI 전면 수정`
- Figma file: `3qUR2z0rh6aYJfeJSxiUmg`
- Approved section: `614:161` — `09 Main 기준 재작성 / 2026.09.04`
- Platform: mobile web app only, 390×844 reference viewport, light theme.
- This document records implementation scope. Figma remains the visual source of truth.

## Product-wide rules

- Reuse the current React 19, React Router 7, Tailwind 4, Radix, Lucide, entity APIs, session context, and page components.
- Preserve existing API payloads, error handling, authentication guards, and mock/real API switching. Do not invent a server contract where no endpoint exists.
- Use the existing semantic tokens in `frontend/src/app/styles/index.css`; no raw color literals in page TSX.
- Use one `BottomTabbar` with labels `홈 / 복약 / 영양제 / 챗봇 / 마이` on all root tab screens.
- Interactive targets are at least 44×44 CSS pixels. Forms keep labels, inline errors, password-manager support, paste support, and keyboard operation.
- Fixed headers, bottom navigation, sheets, and CTAs must not cover scroll content.
- The Figma state frames are interaction states of real pages, not separate production pages.
- Existing APIs are wired wherever available. Purely new UI with no backend contract may use in-memory state only for `/dev/*` verification; it must not fabricate a production HTTP endpoint.

## Domain requirements

### Authentication and tutorial

- Frames: `616:161`, `616:167`, `616:188`, `617:167`, `617:189`, `617:214`, `618:176`, `618:213`, `618:239`, `619:183`, `619:198`, `619:213`, `619:228`.
- Keep the approved login screen. Change signup to four steps: email → six-digit verification UI → password → existing profile and consent fields.
- Email remains the immutable account identifier. Existing account creation and login APIs execute only after the final step.
- Add four tutorial states with skip and completion navigation; show once per session using browser session storage.

### Home

- Frames: `622:183`, `622:271`, `622:361`, `623:198`, `630:214`, `630:256`, `630:298`, `631:218`.
- Medication is grouped by episode inside the meal-time category. Episode completion is one action for all medicines in that episode.
- Collapsed episode shows compact medicine summaries; expand/collapse stays at the lower right.
- Primary action row is split between `복약 메모 쓰기` and `먹었어요`.
- Guest home uses the compact three-banner auto carousel without vertical overflow; rankings remain public.

### Medication registration, prescriptions, and notes

- Frames: `633:223`, `633:248`, `633:262`, `641:239`, `641:283`, `636:289`, `643:239`, `643:278`, `643:309`, `644:241`, `647:239`, `647:276`, `647:311`, `647:362`, `648:257`, `648:291`, `648:313`, `683:877`, `683:906`, `683:929`, `683:954`.
- Registration is five steps: image/OCR → OCR confirmation and episode alias → per-medicine meal slots → first intake date/time → alarm time → completion. The progress indicator uses `n / 5`.
- Preserve the current upload, OCR polling, confirmation, schedule, and alarm APIs.
- Medication list top action is `삭제`; tapping an active episode opens the existing edit sheet directly. Completed prescriptions are view-only.
- Medication notes are reachable from the medication list and home. Notes capture prescription, medicine, taken time, and experience; list/create/edit/delete states are required. With no backend contract, production UI must clearly isolate persistence behind a local adapter rather than call an invented URL.

### Supplements

- Frames: `650:268`, `650:317`, `650:347`, `650:372`, `658:603`, `658:667`, `658:725`, `658:752`, `675:877`, `675:901`, `675:940`.
- Keep `내 영양제 / 둘러보기`, public ranking/search/product information, nutrient totals, add/edit/stop APIs.
- Tapping a registered supplement opens `내 영양제 상세`, showing the user's rating, memo, and review. Rating is editable there; product information is a secondary action.
- Rating stars use the approved accent/status palette, never the old teal star color.

### Chatbot

- Frames: `672:709`, `672:742`, `672:772`, `672:809`, `672:860`, `672:912`, `693:877`, `693:939`.
- All visible navigation labels use `챗봇`, not `AI 상담`.
- Keep list/start/answer flows and the existing chatbot profile icon.
- Add `채팅 종료`; it opens content-height feedback. Positive and negative reason choices submit/end or allow skip/end.
- Add list deletion selection and confirmation using the existing session-delete API.
- The final assistant response metadata reads `오늘 · 근거 n개`.

### My page

- Frames: `665:663`, `665:719`, `665:742`, `665:762`, `667:700`, `667:722`, `667:741`.
- My page includes medication, supplements, follow-up visits, medication/supplement/follow-up notifications, notification times, and logout.
- Basic information does not display or edit email. Add password change. Put account withdrawal at the bottom of basic information behind confirmation.
- Preserve account, visit, notification, password, logout, and withdrawal behavior already implemented.

## Verification

- Each domain adds focused Playwright coverage that first fails against the pre-change branch and then passes.
- Run focused tests, `pnpm run typecheck`, and `pnpm run build` per domain.
- Final integration runs the complete Playwright suite at 390×844 plus visual smoke checks at 375px and a landscape viewport.
