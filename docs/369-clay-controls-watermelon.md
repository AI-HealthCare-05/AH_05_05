# Common button depth and Watermelon Continuous Tabs

Based on `feature/369` at `23f28e8`; implemented only in isolated
`codex/clay-controls369`. The root user-review checkout was not changed.

## Source and adaptation

The exact `continuous-tabs` registry component was retrieved through Watermelon
`get_component`, including its installable source:

- Preview: https://ui.watermelon.sh/animated-components/continuous-tabs
- Registry: https://registry.watermelon.sh/r/continuous-tabs.json
- Original registry file: `components/watermelon/continuous-tabs.tsx`
- Source dependency: `motion`; spring stiffness `380`, damping `30`, mass `0.9`.

The adaptation preserves the source's recessed rounded track and one continuously
sliding active pill, using the existing RxVita light-clay/teal palette. A native
Web Animations implementation samples that damped spring over 600ms; there is no
new dependency. On interruption it starts at the currently rendered position,
retains spring velocity, and heads toward the latest controlled selection.

The pill is persistent and belongs to its own component instance. A ResizeObserver
aligns it to the actual selected button after resizing. Reduced motion places it
immediately, including when the preference changes during an animation.

The source changes selected text color while its background is still moving.
Here the dark labels stay on the light track, and an aria-hidden white label layer
is clipped by the moving pill. Its counter-translation keeps labels exactly over
the real buttons, so text remains legible during the crossing. Both animation
layers share a timeline start; only native buttons participate in focus or the
accessibility tree. No control or panel is remounted by the slider.

## Shared API and consumers

`ContinuousTabs<T>` is imported directly from `shared/ui/ContinuousTabs`:

```tsx
<ContinuousTabs
  label="Accessible group name"
  role="tablist" // or "group" for independent pressed mode buttons
  items={[{ value: 'first', label: 'First', id: 'tab-first', controls: 'panel-first' }]}
  value={selected}
  onChange={setSelected}
/>
```

`id` and `controls` are optional. Instances without explicit IDs use `useId`.
Tablists retain roving focus, clamped ArrowLeft/ArrowRight, Home/End and existing
tab/panel associations. Group mode retains ordinary pressed buttons. Each button
has a minimum 44px hit area and a visible focus outline.

Applied to Home's medication/supplement tabs, login/signup mode buttons, and both
Home time-slot navigators. Auth reset/intro behavior and all time-slot panel state,
swipe, recording, navigation and API behavior remain with their existing owners.
The shared track is 52px tall (44px button + rim/padding); auth headings still align
with each other, now four pixels below their prior position.

Common action buttons now use a 1px rim for every variant, identical 1px upper
highlight / 2px lower shade / 3px external drop geometry, and the same pressed
and disabled depth. Primary/danger colors and their readable existing gradients
are retained. Card surfaces and shared palette tokens are unchanged.

## Verification

Before implementation, the seven initial new cases failed for the expected
missing slider and unequal 0px/1px primary/secondary rims. A separate before-state
interaction sequence passed and recorded the original components. The final pack
passed **38 tests in 57.2s**:

| Suite | Cases |
| --- | ---: |
| `369-clay-controls-followup.spec.ts` | 9 |
| `369-controls-motion.spec.ts` | 12 |
| `369-auth-stagger.spec.ts` | 6 |
| `auth-login-figma-baseline.spec.ts` | 1 |
| `home-slot-swipe.spec.ts` | 10 |

New checks cover equal rest/focus/pressed/disabled button geometry; visible-surface
contrast of at least 4.5:1; actual intermediate pill positions and aligned text;
rapid reversal from the current position; independent instances; resize alignment;
320/390/1280px containment; reduced motion; and auth mode reset/value preservation.
Existing tests additionally verify signup steps/validation/payloads, request
loading, dialogs, slot selection, saves resolving after navigation, supplement
undo, real horizontal swipes and vertical touch scrolling.

The auth intro test's animation capture now selects only `auth-enter` elements so
it continues measuring that feature independently of the new shared pill.

Run from `frontend` with WSL Node 22.23.1 and Chromium:

```sh
VITE_USE_MOCK=false node node_modules/playwright/cli.js test -c tests/clay-controls.config.ts 369-clay-controls-followup.spec.ts 369-controls-motion.spec.ts 369-auth-stagger.spec.ts auth-login-figma-baseline.spec.ts home-slot-swipe.spec.ts
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build --config tests/clay-controls.vite.config.ts
```

TypeScript and production build passed; Vite retains its existing 500kB advisory
(main JS 890.51kB). `git diff --check` passed. Port 44422 and the worktree-private
cache `.codex-work/clay-controls/node_modules/.vite` prevent cache conflicts with
other agents. API/media proxies are hardwired to `127.0.0.1:9`; the API-backed
tests intercept `/api/` pathnames. No real backend, email or database is used.

Before/after screenshots and videos remain in ignored local test results:

- Before: `frontend/test-results/clay-controls-before-sequence/369-clay-controls-followup-1a481--home-and-slot-interactions/`
- After: `frontend/test-results/clay-controls/369-clay-controls-followup-1a481--home-and-slot-interactions/`
- Each sequence directory contains start/moving/end PNGs and `video.webm`.
- The final pack also records actual auth and Home slot regression videos.

Inspected before/after resting controls, the synchronized intermediate pill,
320px controls, and auth entrance screenshots. Only owned files are packaged;
selection cards, accordion source, dependency manifests and the root checkout are
outside this change.
