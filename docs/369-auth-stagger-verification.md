# Authentication visual followup for #369

Based on `feature/369` at `386c222`, implemented in isolated `codex/auth-stagger369`.

Login now uses the signup background. An empty, aria-hidden block reserves the
signup progress area, placing both headings at Y=192 at 320, 390 and 1280px.
The login tab no longer places a white inner surface over the selected clay tab,
which previously rendered white text against white.

Each mode/step entrance reveals the title, existing description (when present),
then each complete input group. Motion moves upward 8px over 280ms with 80ms
stagger intervals. Step four retains its existing title without new copy.
The gender and required-consent groups follow its three text/date fields.

Existing input nodes stay mounted during typing and validation. Focusing a group
cancels its entrance immediately. Reduced motion skips entrances and switching
that preference while an entrance is running cancels it. Mode reset, validation,
navigation, request functions and password-reset behavior are unchanged.

## Verification

Run from `frontend` using Node 22.23.1 and Playwright Chromium:

```sh
node node_modules/playwright/cli.js test -c tests/auth-stagger.config.ts 369-auth-stagger.spec.ts auth-login-figma-baseline.spec.ts
node node_modules/typescript/bin/tsc --noEmit
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build --config tests/auth-stagger.vite.config.ts
```

- Existing login baseline: 1 passed before implementation.
- RED: 4 failures, 2 passes. Selected login text was white-on-white and no
  entrance existed. A separate 390px RED run also measured white vs signup's
  `rgb(247, 249, 249)` background and heading Y=164 vs signup's Y=192.
- GREEN: 7 passed, including the existing baseline. New checks cover all signup
  steps, rendered opacity order, input/error preservation, back navigation,
  signup request payload, focused-field visibility and reduced motion.
- TypeScript and production build passed. The existing bundle-size warning
  remains (main JS exceeds Vite's 500kB advisory threshold).
- Screenshots inspected: login at 390px, signup at 320px, and signup step four.
  Login/signup screenshots at all three widths are written under
  `frontend/test-results/auth-stagger/` by the tests.

The dedicated test server uses port 44420, a worktree-local dependency cache in
`test-results/.vite-auth-stagger`, and a dead API/media proxy at `127.0.0.1:9`.
Every `/api/` pathname in the new suite is intercepted, including a fallback.
This avoids accidentally intercepting Vite source URLs containing `/api/` and
prevents real email or database operations.

## Integration

Only `AuthPage.tsx` and new test/documentation files are changed. No shared button
tokens are modified. Preserve #392's separately developed reset action when
merging the overlapping AuthPage change. Signup privacy disclosure markup is
unchanged and remains available for the separate accordion migration.
