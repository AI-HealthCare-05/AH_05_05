# Follow-up visit reminder 21:00 rollout (#432)

This deployment procedure requires independent review; it is **not an executed migration**. The code
change alone does not correct stored reservations. Deploy the API and caption
together only after this procedure has succeeded in the target environment.
Do not execute these commands without separate target-database authorization.

New visits and date changes use 21:00 Asia/Seoul on the previous calendar day.
Medication/supplement times and notification consent retain their behavior.
Date changes preserve non-ACTIVE, previously triggered, and overdue reservations;
they do not clear dispatch history or revive an old reservation. An eligible
pending reservation moved to an elapsed reminder date is cancelled.

## Preconditions and hard stops

1. Pause visit/alarm writes, settings writes, alarm polling, recovery, manual
   retries, and alarm delivery consumers. Wait for running deliveries to finish.
   Keep them paused through verification. Do not kill an in-flight send: the
   provider may already have accepted it before completion was persisted.
2. Inventory the DB and Redis queues. Any QUEUED, RETRY_WAITING, or PROCESSING
   follow-up alarm job, or Redis delivery/retry referencing these alarms, blocks
   rollout. Resolve/drain under separate authorization, then repeat the checks.
   The worker does not compare a queued job's trigger with the alarm's new
   trigger; changing the alarm alone cannot invalidate old jobs. Never delete
   Redis keys or cancel/requeue jobs as an implicit part of this procedure.
3. Verify the storage convention before SQL. `app/core/db/databases.py` selects
   MySQL and `timezone="Asia/Seoul"`, with `use_tz` omitted (Tortoise defaults to
   false). The installed Tortoise MySQL adapter sets session time zone `+09:00`;
   datetime fields are MySQL DATETIME(6), stored as local wall-clock values.
   Compare a known reservation's raw columns to the API timestamp and inspect
   the deployed settings/schema. If UTC storage or overrides are found, stop;
   the following SQL assumes KST wall-clock storage and must not be run unchanged.
4. Take a recoverable database backup and retain the SELECT export below in the
   approved deployment record. Never include user details in public logs.

## Dry run (read-only apart from session variables)

Use one dedicated MySQL connection. These SELECTs do not contact the push provider.

```sql
SET time_zone = '+09:00';
SET @cutover_now = CURRENT_TIMESTAMP(6);

-- Must return zero rows. Keys include the alarm ID even for manual retry suffixes.
SELECT j.id, j.status, j.idempotency_key, a.id AS alarm_id
FROM background_jobs j
JOIN alarms a ON j.idempotency_key LIKE CONCAT('alarm:', a.id, ':%')
WHERE a.alarm_type = 'FOLLOW_UP_VISIT'
  AND j.job_type = 'ALARM'
  AND j.status IN ('QUEUED', 'RETRY_WAITING', 'PROCESSING');

-- Must return zero rows: do not revive overdue reservations or guess about
-- inconsistent ownership, trigger columns, recurrence, or missing dispatch markers.
SELECT a.id, a.scheduled_at, a.next_trigger_at, a.status, a.last_triggered_at
FROM alarms a
LEFT JOIN follow_up_visits v ON v.id = a.follow_up_visit_id
WHERE a.alarm_type = 'FOLLOW_UP_VISIT'
  AND a.status = 'ACTIVE' AND a.last_triggered_at IS NULL
  AND (a.scheduled_at <= @cutover_now OR a.next_trigger_at <= @cutover_now
       OR a.scheduled_at <> a.next_trigger_at OR a.recurrence_rule IS NOT NULL
       OR v.id IS NULL OR v.user_id <> a.user_id OR a.timezone <> 'Asia/Seoul'
       OR a.completed_at IS NOT NULL OR a.cancelled_at IS NOT NULL
       OR EXISTS (SELECT 1 FROM alarm_events e WHERE e.alarm_id = a.id));

-- Export all eligible rows and their proposed action. Count each action before apply.
SELECT a.*, v.visit_date,
       TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00') AS new_trigger,
       CASE WHEN TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00') <= @cutover_now
            THEN 'CANCEL_ELAPSED'
            WHEN a.scheduled_at = TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00')
            THEN 'UNCHANGED' ELSE 'MOVE_FUTURE' END AS proposed_action
FROM alarms a JOIN follow_up_visits v ON v.id = a.follow_up_visit_id AND v.user_id = a.user_id
WHERE a.alarm_type = 'FOLLOW_UP_VISIT' AND a.status = 'ACTIVE'
  AND a.last_triggered_at IS NULL AND a.completed_at IS NULL AND a.cancelled_at IS NULL
  AND a.recurrence_rule IS NULL AND a.timezone = 'Asia/Seoul'
  AND a.scheduled_at = a.next_trigger_at
  AND a.scheduled_at > @cutover_now AND a.next_trigger_at > @cutover_now
  AND NOT EXISTS (SELECT 1 FROM alarm_events e WHERE e.alarm_id = a.id)
ORDER BY a.id;

SELECT COUNT(*) AS eligible_count
FROM alarms a JOIN follow_up_visits v ON v.id = a.follow_up_visit_id AND v.user_id = a.user_id
WHERE a.alarm_type = 'FOLLOW_UP_VISIT' AND a.status = 'ACTIVE'
  AND a.last_triggered_at IS NULL AND a.completed_at IS NULL AND a.cancelled_at IS NULL
  AND a.recurrence_rule IS NULL AND a.timezone = 'Asia/Seoul'
  AND a.scheduled_at = a.next_trigger_at
  AND a.scheduled_at > @cutover_now AND a.next_trigger_at > @cutover_now
  AND NOT EXISTS (SELECT 1 FROM alarm_events e WHERE e.alarm_id = a.id);
```

Old overdue reservations are left unchanged and **block worker restart** until
separately resolved; they are never moved forward to create a replay. Non-ACTIVE
or `last_triggered_at IS NOT NULL` rows remain unchanged, including already sent
reservations. An old 22:00 reservation with an elapsed new 21:00 is cancelled,
not emitted late. A 19:00 reservation already attempted is not repeated at 21:00.

## Authorized apply and verification

While all producers/consumers remain paused, start a transaction, refresh the
cutover time, and repeat **both hard-stop SELECTs** plus the candidate export
with `FOR UPDATE`. Compare counts by proposed_action with the reviewed dry run.
If any blocker or unexplained change appears, `ROLLBACK` and stop. Do not proceed
across the 21:00 boundary without repeating the review at the new cutover time.

```sql
START TRANSACTION;
SET @cutover_now = CURRENT_TIMESTAMP(6);
-- Repeat the hard-stop checks and lock/export eligible rows as described above.

UPDATE alarms a
JOIN follow_up_visits v ON v.id = a.follow_up_visit_id AND v.user_id = a.user_id
SET a.status = 'CANCELLED', a.cancelled_at = @cutover_now, a.updated_at = @cutover_now
WHERE a.alarm_type = 'FOLLOW_UP_VISIT' AND a.status = 'ACTIVE'
  AND a.last_triggered_at IS NULL AND a.completed_at IS NULL AND a.cancelled_at IS NULL
  AND a.recurrence_rule IS NULL AND a.timezone = 'Asia/Seoul'
  AND a.scheduled_at = a.next_trigger_at
  AND a.scheduled_at > @cutover_now AND a.next_trigger_at > @cutover_now
  AND TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00') <= @cutover_now
  AND NOT EXISTS (SELECT 1 FROM alarm_events e WHERE e.alarm_id = a.id)
  AND NOT EXISTS (SELECT 1 FROM background_jobs j
      WHERE j.idempotency_key LIKE CONCAT('alarm:', a.id, ':%') AND j.job_type = 'ALARM'
        AND j.status IN ('QUEUED', 'RETRY_WAITING', 'PROCESSING'));
SELECT ROW_COUNT() AS cancelled_count;

UPDATE alarms a
JOIN follow_up_visits v ON v.id = a.follow_up_visit_id AND v.user_id = a.user_id
SET a.scheduled_at = TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00'),
    a.next_trigger_at = TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00'),
    a.updated_at = @cutover_now
WHERE a.alarm_type = 'FOLLOW_UP_VISIT' AND a.status = 'ACTIVE'
  AND a.last_triggered_at IS NULL AND a.completed_at IS NULL AND a.cancelled_at IS NULL
  AND a.recurrence_rule IS NULL AND a.timezone = 'Asia/Seoul'
  AND a.scheduled_at = a.next_trigger_at
  AND a.scheduled_at > @cutover_now AND a.next_trigger_at > @cutover_now
  AND TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00') > @cutover_now
  AND a.scheduled_at <> TIMESTAMP(DATE_SUB(v.visit_date, INTERVAL 1 DAY), '21:00:00')
  AND NOT EXISTS (SELECT 1 FROM alarm_events e WHERE e.alarm_id = a.id)
  AND NOT EXISTS (SELECT 1 FROM background_jobs j
      WHERE j.idempotency_key LIKE CONCAT('alarm:', a.id, ':%') AND j.job_type = 'ALARM'
        AND j.status IN ('QUEUED', 'RETRY_WAITING', 'PROCESSING'));
SELECT ROW_COUNT() AS moved_count;
-- Re-run the candidate SELECT: every remaining candidate must be UNCHANGED.
-- Compare exact changed IDs/fields to the preimage; verify all protected rows unchanged.
-- If counts, IDs, jobs, storage, or time-boundary checks disagree: ROLLBACK.
COMMIT;
```

Keep workers paused while deploying the fixed API and caption. Verify new visits,
date edits, setting independence, and consent on an isolated test account with a
stub push provider, then repeat pending/job checks before restart. If a stored
trigger became overdue during the pause, stop and obtain a reviewed resolution;
do not permit a catch-up send as part of rollout. This procedure does not create
missing alarms and is idempotent for successfully converted pending rows.

## Rollback limits

Before COMMIT, use ROLLBACK. After COMMIT, restoring the preimage is safe only
while all writers/workers remain paused, the exact rows are unchanged, no job or
event has appeared, and both the old and restored triggers remain in the future.
Elapsed cancellations cannot be reactivated automatically. Once consumers resume
or a provider accepts a push, rollback cannot unsend it; never reset
`last_triggered_at`, delivery events, terminal jobs, or idempotency keys.
Reverting application code alone would restore medication-time coupling and can
alter already migrated rows. A rollback after restart needs a separately reviewed
data and delivery plan. This change does not authorize that operation.
