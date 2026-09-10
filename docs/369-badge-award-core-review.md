# Shared badge award presenter

Built from feature/369 `23f28e8` in the isolated `codex/badge-award369` worktree. This core has no official/custom API dependency; adapters must supply actual server awards. It mounts once under SessionProvider and waits for existing Radix or native dialogs without closing them or navigating.

## Public adapter contract

```ts
import { captureBadgeAwardScope, observeBadgeAwards, enqueueBadgeAward, type BadgeAward } from '@/shared/lib/badgeAwards';
// Capture BEFORE the request. The coordinator rejects old account/auth generations.
const scope = captureBadgeAwardScope(principalKey);
// Normalized award: {source:'official'|'custom', awardId, participationId, name, imageUrl}.
// imageUrl must come from the actual server award (resolved with apiAssetUrl as needed).
observeBadgeAwards(scope, historicalAwards); // Silent initial history; never queues.
enqueueBadgeAward(scope, newServerAward); // Returns false for observed/presented duplicates.
enqueueBadgeAward(scope, currentServerAward, { confirmedTransition: true });
// The last option is ONLY for a confirmed current ACTIVE→COMPLETED transition race:
// it promotes silent-observed history but never replays an already presented/queued award.
```

Identity is account + source + award ID + participation ID. Observation and presentation claims are stored separately in browser localStorage, with in-memory fallback when storage is unavailable. This prevents duplicate callback/StrictMode/remount/reload celebrations in the same browser; it is not server-side or cross-device exactly-once delivery. Claims happen when enqueued, so dismissing or reloading during the intro does not replay it.

## Artwork and motion

The actual server artwork is fetched with explicit CORS handling, decoded, reduced to at most 512px per edge and processed once per URL using a cached Blob promise. A four-neighbour flood fill removes only edge-connected near-white pixels (each RGB >224, spread <18); enclosed white remains unchanged. The existing award art elsewhere in the app is untouched. Temporary decoding/display Blob URLs are revoked on cleanup; failed processing promises are removed for explicit retry. An image error shows text/retry/confirmation, never the known opaque source as a fallback.

Normal presentation decodes first, uses a restrained 900ms tilt/settle, one 450ms gloss sweep clipped to the processed image alpha, then reveals the title and confirmation. Reduced motion shows title/confirmation immediately and removes 3D/gloss. Close/Escape remain available during preparation and motion. The existing shared 44px+ Button and dialog focus behavior are reused; no dependency or global Button/CSS changes.

## Verification

Core suite: **11 passed (31.6s)**. It covers StrictMode/duplicate/remount/reload dedupe, different participations/accounts, stale authentication generation, historical seeding, confirmed-transition promotion, native-dialog waiting, exact internal-white preservation, bounded decoded image/cache/object-URL cleanup, image errors/retry, CORS rejection/Escape, reduced motion/focus/44px button, and normal 320/390px tilt/gloss/ready sequence screenshots. The 390px ready screenshot was visually inspected with the user's explicit medication PNG fixture: transparent outer area and preserved white capsule detail, teal clay styling, one clear confirmation.

TDD: official My-page award success first failed because no celebration dialog existed. Two stronger core regressions reproduced silent-observation promotion loss and missing native-dialog detection, then passed after fixes. An intermediate animation screenshot test missed the brief gloss phase; deterministic inspection of the real WAAPI timelines now captures each stage without changing production duration.

TypeScript baseline and current `tsc -b --pretty false` passed. Browser runs use Node22, Chromium, private ignored cache `frontend/.codex-work/node_modules/.vite-badge369`, port44426, and API/media proxy hardwired to `127.0.0.1:9`. The user-owned demo and PNG were read as references only and are not included in this commit. Tests use tracked water artwork by default or the explicit `BADGE_ART_FIXTURE_PATH` environment override. Official wiring and custom315 adapter are separate commits/tasks.

One-shot motion follow-up: changing reduced-motion back to no-preference after either a normal or initially reduced presentation reproduced a second tilt (two intentional RED regressions). A per-dialog presentation guard now keeps the settled state and never replays the gloss on preference changes. The full core suite subsequently passed **13 tests (38.8s)**, and TypeScript passed again.
