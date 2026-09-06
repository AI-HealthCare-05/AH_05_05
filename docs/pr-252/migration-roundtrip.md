# F 2.2 · Migration downgrade/upgrade verification

2026-09-05 · feature/252 · verification only, no application edits

## Result: FAIL — migration 29 cannot re-upgrade after downgrade

Executed the actual repository migration `upgrade`/`downgrade` SQL through the existing asyncmy driver against an isolated MySQL schema: `pr252_migrationcheck_20260905_f22`.

The scratch schema was newly created after confirming it did not exist. All 47 current `ai_health` table definitions were copied with `SHOW CREATE TABLE`; no data was copied. Foreign-key checking was disabled only while cloning definitions, then enabled for the migration test. All migration SQL used the verified scratch database. Neither `ai_health` nor `test` was modified.

This verifies the migration SQL itself, not Aerich's history-table bookkeeping or CLI operation. No package installation was performed.

```text
Created scratch schema: pr252_migrationcheck_20260905_f22
Cloned 47 table definitions, zero data rows
downgrade 30 PASS
downgrade 29 PASS
downgrade 28 PASS
downgrade 27 PASS
upgrade 27 PASS
upgrade 28 PASS
upgrade 29 FAIL OperationalError (1091, "Can't DROP 'uid_medication__user_dose_slot'; check that column/key exists")
```

Migration 29's downgrade drops the new unique index, foreign key, episode/date index and episode column, but does not recreate `uid_medication__user_dose_slot`. Its upgrade unconditionally drops that old unique index, causing MySQL error 1091 during re-upgrade. Migration 30 re-upgrade was not reached.

MySQL DDL commits implicitly. The failed re-upgrade already re-added `care_episode_id BIGINT NOT NULL`, so the scratch table was left partially migrated:

```sql
CREATE TABLE `medication_doses` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dose_date` date NOT NULL,
  `slot` varchar(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
  `taken_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `user_id` bigint NOT NULL,
  `care_episode_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_medication__user_date` (`user_id`,`dose_date`),
  CONSTRAINT `fk_medicati_user_2b519a1e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```

The scratch schema is retained for inspection. No cleanup deletion was performed. The local reproduction script is `.codex-work/pr-252/migration_roundtrip_check.py` (ignored diagnostic artifact, not included in this PR); it refuses to reuse an existing scratch schema. Run via PowerShell on the verification host:

```powershell
Get-Content .codex-work/pr-252/migration_roundtrip_check.py -Raw | docker compose exec -T fastapi uv run --no-sync python -
```

This is a release verification blocker under F 2.2. No fix was applied because F authorizes verification rather than feature/schema changes. A future fix must consider that multiple per-episode records can share the old `(user_id, dose_date, slot)` key; simply restoring that unique index on populated data can itself fail. Deleted dose rows are not restored by downgrade.
