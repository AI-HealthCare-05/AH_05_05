# #315 CI migration-head correction

## Reproduced failure

GitHub run `34461514409` reported 3 failures, 1,935 passes and 1 skip.
The same three failures reproduced in an isolated MySQL 8 instance:

- Both real Aerich 39/40 upgrade chains attempted to remove the old custom participation table while the newly generated award table still referenced it.
- The last main migration (44) described the therapeutic-classification models but did not include the independent custom finalization changes from migration 43.

## Correction

- Keep every existing migration unchanged. Add migration 45, merging the frozen 44 state with the five custom model descriptions from frozen 43. Its SQL is `SELECT 1`; it does not remove or rewrite application rows.
- In the disposable migration test database only, remove the newly generated empty child award table before constructing the historical schema.
- Seed historical custom rows using the columns actually present at version 40, rather than the current ORM with post-43 fields.
- Exercise the full upgrade/downgrade/re-upgrade chain, compare original columns and row values, check additive defaults, preserve official verification history, and retain the duplicate-rejoin rollback guard.
- Compare the final migration snapshot with all 58 registered runtime model descriptions. Historical 43 remains frozen instead of being regenerated from today's unrelated models.
- Exercise upgrading an existing main-44 ledger where the custom-43 migration has not been applied yet; Aerich must apply both missing custom-43 and final-45 entries.

## Deployment boundary

Use the usual reviewed Aerich upgrade process for unapplied migrations, including 45. The previously reported 43-only requirement is superseded when integrating with current main. Migration 45 only reconciles migration metadata; the schema-changing custom migration 43 is still required where it has not been applied.

No migration or data repair was run against the user's development database. The root feature/384 checkout was left unchanged. The separately deferred 'no goals today' issue is outside this correction.

## Verification

- Before correction: the original 3 CI failures reproduced locally (3 failed, 3 passed).
- After correction: the same two test files passed all 6 cases, including actual MySQL upgrade chains.
- Repository Ruff check and format check passed (856 Python files).
- CI-style model/custom-challenge/service regression run with the normal app fixture and disposable MySQL: **202 passed**.
- Standalone MySQL migration suite, in a separate process: **5 passed**.
- An initial mixed `--noconftest` run had 201 passes and 6 fixture-initialization failures because it included tests requiring the app initializer. The commands were corrected and separated; no product change was made for those harness failures.
- These are scoped local results. The full backend suite is verified separately by GitHub CI.
