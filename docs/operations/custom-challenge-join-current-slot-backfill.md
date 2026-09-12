# #428: 기존 맞춤 챌린지의 참여일 현재 시간대 목표 복구

상태: **실행하지 않은 운영 검토용 런북**. 새 참여 로직 배포와 기존 데이터 복구는 별도 작업이다. 이 문서는 SQL 실행, 데이터 변경, 운영 승인 또는 복구 완료를 의미하지 않는다.

관련 이슈: [#428](https://github.com/AI-HealthCare-05/AH_05_05/issues/428)

## 범위와 실행 금지 조건

새 정책은 참여 시각을 KST로 바꾼 뒤 **네 시간대 설정 전체 중 참여 시각 이하인 가장 늦은 시각**을 현재 시간대로 삼는다. 선택된 복약 처방/영양제의 그 시간대가 당시 유효하고 아직 복용하지 않았으면 포함한다. 이후 목표는 기존 기간 안에서 유지한다. 현재 시간대가 선택 대상에 없거나 이미 복용했으면 더 이른 시간대로 되돌아가지 않는다. 첫 시간대 전에는 지난날 목표를 가져오지 않는다. 같은 시각으로 설정된 시간대들은 같은 경계에 속하되 각 source의 실제 slot만 해당한다.

이 런북은 정확히 허용된 사용자 한 명, 기존 참여 한 건의 **참여일 경계 시각 목표 중 누락된 키만 추가**하는 절차다. 기존 목표를 재계산·삭제·수정하거나 미래 목표를 복구하지 않는다. MEDICATION과 SUPPLEMENT만 해당한다. 진료 일정, 목표가 전혀 생성되지 않아 참여 자체가 없는 경우, 대상 추가/삭제, 기간 연장, 상태 재개, 완료 결과/배지 변경은 범위 밖이다.

다음 중 하나라도 해당하면 **STOP: 수정 없이 종료**한다.

- 별도의 사용자/운영 담당자 승인과 정확한 대상 allowlist가 없다. 코드 변경 승인은 실데이터 복구 승인이 아니다.
- 참여가 ACTIVE가 아니거나 `finalized_at`/`completed_at`이 있거나 이미 종료 시각이 지났다. 배지 지급 이력이 있는 경우도 중단한다.
- source가 삭제되었거나 target의 FK가 null이거나 소유권/`source_id_snapshot`이 일치하지 않는다.
- 가입 당시 네 시간대 설정, 선택 source의 당시 기간/slot, **가입 트랜잭션이 관측했을 당시 복용 상태**를 입증할 수 없다.
- 가입 전 복용 후 취소(행 삭제), 이후 설정/처방/영양제 기간 변경, 중간 reconciliation/수동 수정 이력이 누락되거나 모호하다. 현재 DB 상태가 당시와 같아 보인다는 이유로 통과시키지 않는다.
- 누락 원인이 기존 `joined_at <= scheduled_at` 경계 때문이라는 근거가 없다. 이미 존재하는 키의 시각/완료값이 예상과 달라도 덮어쓰지 않고 중단한다.
- 실행 환경의 DATETIME 저장/세션 시간대 변환, 마이크로초 정밀도, MySQL 트랜잭션/잠금 동작을 검증하지 못했다.
- 동일 사용자 잠금을 공유하지 않는 쓰기 경로가 동시 실행될 수 있거나, 만료/취소/일정 변경과의 안전한 직렬화를 보장할 수 없다.

**현재 스키마만으로 과거의 미복용을 일반적으로 증명할 수 없다.** `custom_challenge_targets`에는 source ID/이름만 snapshot으로 남는다. 당시 시간 설정/기간/slot/복용 상태 snapshot은 저장하지 않는다. `taken_at`이 남은 행만 조회하는 방법은 취소로 삭제된 기록을 복원하지 못한다. 설정의 현재 값이나 `updated_at`, 복용 행의 부재만으로 역사적 증거를 대신하지 않는다. 증거가 없다면 기존 참여를 그대로 두고 새 정책은 새 참여에만 적용한다.

## 기존 도구 확인 결과

`scripts/`, 서비스와 관련 문서에서 이 목표를 안전하게 복구하는 기존 backfill CLI/관리 API는 확인되지 않았다. `CustomChallengeScheduleReconciler.reconcile`은 변경 시점 이전 목표를 보존하는 일정 동기화이며 누락된 과거 목표 backfill 용도가 아니다. 조회 API나 재참여 호출로 복구하지 않는다. lifecycle/finalization 호출은 결과를 고정할 수 있으므로 복구 절차에서 호출하지 않는다.

아래는 **별도 검토가 필요한 일회성 수동 트랜잭션 템플릿**이다. SQL을 실행하지 않았고 대상 MySQL 버전/드라이버에서 문법·잠금 동작을 검증하지 않았다. 새 migration, 실행 helper, 범용 복구 프레임워크, schema 추가는 만들지 않는다. 이 템플릿을 그대로 운영 콘솔에 붙여 넣지 않는다.

## 실행 전에 승인받을 증거 묶음

실제 개인정보/의료정보를 Git 문서에 적지 말고 접근 제한된 운영 기록에 보관한다.

| 필수 항목 | 검증 내용 |
| --- | --- |
| 환경/코드 | DB 인스턴스 식별자, 배포 SHA, schema 버전, DB/세션 시간대, ORM 시간 변환 확인 |
| 정확한 대상 | `user_id`, `participation_id`, MEDICATION/SUPPLEMENT, 정확한 `joined_at`와 `end_at` 원시 DB 값 및 KST 값 |
| 참여 당시 설정 | MORNING/LUNCH/EVENING/BEDTIME 네 시각 전체와 근거 시점; 설정이 없었다면 당시 기본값을 썼다는 근거 |
| 참여 당시 source | target ID, source ID snapshot와 FK, 소유 사용자, 당시 유효 상태/기간/slot, 이후 변경 이력 |
| 복용 이력 | 참여 직전의 해당 source/참여일/slot 복용 상태 및 트랜잭션 순서, 이후 복용/취소의 완전한 이력; 같은 타임스탬프에서 순서 불명확하면 중단 |
| 기존 목표 | 해당 참여 전체 occurrence의 ID/키/시각/완료값, 참여/target/배지 상태의 일관된 before snapshot |
| 수정 manifest | 정확한 `(target_id, scheduled_date, slot, scheduled_at)` allowlist, 각 키의 판정 근거, 예상 INSERT 수 N, 예상 목표 수/고유 날짜 수/진행률 변화 |
| 승인 | 대상별 변경 승인자, 작업자/검토자, 허용 실행 시간, 중단/복구 책임자 |

`medication_goal_windows`는 개별 약의 days 또는 처방 days, 시작일/시작 slot, 약별 slot을 합쳐 처방 단위 목표를 만든다. 임의로 약 수만큼 목표를 만들지 않는다. `supplement_goal_windows`는 등록 기간/slot을 따른다. 이 함수에 현재 ORM 객체를 넣어 과거 상태인 것처럼 계산하지 말고 검증된 당시 snapshot으로 계산한다.

참여일을 D, 참여 시각을 J, 네 설정 중 J 이하의 가장 늦은 시각을 T라고 하면 추가 후보는 다음 조건을 모두 만족해야 한다.

1. 기존 target이며 `(D, slot)`이 검증된 당시 source window 안에 있다.
2. slot의 설정 시각이 T이고 `D@T < J < end_at`이다. `D@T == J`는 기존 정책도 포함하므로 이 누락 수정의 대상이 아니다.
3. 해당 키는 참여 당시 미복용이었다. 참여 전 이미 먹은 키는 이후 취소했어도 추가하지 않는다.
4. 키가 현재 occurrence에 없고 이후 의도적으로 제거된 목표가 아니다.

N은 승인된 고유 키 수이고 `0 < N <= 4 × 승인된 기존 target 수`여야 한다. 보통 source별 한 키지만 같은 시각 설정을 고려한다. N을 맞추려고 앞 시간대/미래/다른 source를 채우지 않는다. 이미 정확한 키가 모두 존재하면 재실행은 **0건/no-op**으로 종료한다. 일부만 존재하면 새 manifest와 예상 수를 다시 승인받고 기존 행은 보존한다.

## Dry-run 및 수동 트랜잭션 템플릿

먼저 격리된 비식별 fixture DB에서 원본 구조와 같은 경계 사례/중단 조건/재실행을 확인한다. 실제 환경은 조회·잠금까지도 별도 승인 범위 안에서만 수행한다. 하나의 검토된 DB 세션으로 **한 사용자/한 참여만** 처리한다. 값은 드라이버 parameter binding으로 전달하며 문자열 조합·와일드카드·전체 사용자 스캔은 사용하지 않는다.

아래 `:name`은 실제 값이 없는 설명용 placeholder다. GUARD는 SQL 문법이 아니라 작업자가 결과를 검증한 뒤 통과해야 하는 중단 지점이다. 자동 COMMIT을 포함한 스크립트로 변환하지 않는다. transaction 시작 후 대기/승인 요청을 하지 않는다. 잠금 대기는 최대 5초, 전체 transaction은 최대 30초를 운영 도구에서 제한하며 종료까지 최소 5분이 남아 있지 않으면 시작하지 않는다. timeout/lock 실패/접속 오류는 즉시 ROLLBACK 후 새 dry-run부터 재검토한다.

```sql
START TRANSACTION;

-- 애플리케이션과 같은 잠금 순서: User 먼저, 참여 다음.
SELECT id FROM `user` WHERE id = :user_id FOR UPDATE;
SELECT * FROM custom_challenge_participations
WHERE id = :participation_id AND user_id = :user_id FOR UPDATE;

-- GUARD: 각각 정확히 1행. 승인한 joined_at/end_at/type과 byte/정밀도 일치.
-- ACTIVE, finalized_at IS NULL, completed_at IS NULL, 아직 종료 전.
-- 서버 현재 시각과 종료 시각을 같은 검증된 시간대에서 비교한다.

SELECT * FROM custom_challenge_targets
WHERE participation_id = :participation_id ORDER BY id FOR UPDATE;
SELECT o.* FROM custom_challenge_occurrences o
JOIN custom_challenge_targets t ON t.id = o.target_id
WHERE t.participation_id = :participation_id ORDER BY o.id FOR UPDATE;
SELECT * FROM custom_challenge_badge_awards
WHERE participation_id = :participation_id;

-- GUARD: target/source 소유권 및 양쪽 snapshot/FK 동일, 배지 없음.
-- source 행/관련 slot/설정과 관련 dose 행도 승인한 ID로 조회·검증한다.
-- 정확한 참여 전체 before snapshot 및 dose snapshot을 기록한다.
-- 승인 manifest 외 수정 0건, 현재 없는 키 수 == N 확인.

-- 아래 문장은 manifest의 각 키에 대해 한 번씩만 수행한다.
-- NOT EXISTS는 기존 키를 보존하는 보조장치다. 앞선 GUARD를 대체하지 않는다.
INSERT INTO custom_challenge_occurrences
    (target_id, scheduled_date, slot, scheduled_at, is_completed)
SELECT t.id, :join_date_kst, :slot, :scheduled_at_db, FALSE
FROM custom_challenge_targets t
JOIN custom_challenge_participations p ON p.id = t.participation_id
WHERE t.id = :target_id
  AND t.participation_id = :participation_id
  AND t.source_id_snapshot = :source_id
  AND p.user_id = :user_id
  AND p.challenge_type = :challenge_type
  AND p.joined_at = :expected_joined_at_db
  AND p.end_at = :expected_end_at_db
  AND p.status = 'ACTIVE'
  AND p.finalized_at IS NULL AND p.completed_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM custom_challenge_occurrences o
      WHERE o.target_id = :target_id
        AND o.scheduled_date = :join_date_kst AND o.slot = :slot
  );

-- GUARD: 각 INSERT affected rows == 1, 전체 합계 == N.
-- 기존 행/dose/participation/target/badge는 before snapshot과 완전히 일치.
-- 추가 행의 정확한 ID/키/시각 및 목표 수/일수 변화를 다시 대조한다.

ROLLBACK; -- dry-run 기본값. 승인 후 실제 실행도 모든 GUARD를 재검증한다.
```

실제 작업에서는 위 마지막 세 주석의 의미대로 **각 INSERT 영향 행 수 1, 총 N, 기존 행 완전 보존**을 확인한다. 유일 키 `(target_id, scheduled_date, slot)` 충돌은 재시도/무시로 넘기지 말고 전체 ROLLBACK한다. `INSERT IGNORE`, `REPLACE`, `ON DUPLICATE KEY UPDATE`는 사용하지 않는다.

source별 조회 경로는 MEDICATION이면 `care_episodes` 소유권과 `medication_doses(user_id, care_episode_id, dose_date, slot)`이고, SUPPLEMENT이면 `user_suppl_nutrient` 소유권과 `supplement_doses(registration_id, dose_date, slot)`이다. 정확한 원본/추가 키뿐 아니라 승인한 참여의 source에 해당하는 dose 전체의 ID/값을 같은 잠금 구간에서 비교해 **복용 기록 변경 0건**을 확인한다. 잠금을 공유하는 복용 저장/취소가 대기하더라도 작업은 30초 내 종료한다.

실행 승인은 dry-run 보고서와 별도로 받는다. 승인된 작업 창에서 모든 조회/GUARD를 다시 통과했을 때만 최종 ROLLBACK 대신 COMMIT을 선택한다. 성공 응답을 잃으면 커밋 실패로 추정하거나 무작정 재실행하지 말고 정확한 키/추가 ID와 transaction 결과를 조회해 확인한다.

## 결과 검증과 롤백 한계

- 추가한 occurrence만 N건 존재하고 기존 occurrence의 ID/키/시각/완료값, 참여/target/배지/dose 값이 그대로여야 한다. 새 행 `is_completed=FALSE`는 일반 신규 목표와 같은 저장 기본값이다.
- ACTIVE 참여의 응답 목표 수/완료 수/일수는 서비스가 occurrence와 dose로 계산한다. `target_count`, `completed_count`, `progress_rate`, `completed_at`, `finalized_at`, status나 배지를 직접 고치지 않는다.
- 참여 당시 미복용이었다가 **참여 후** 정상적으로 복용한 키라면 조회 시 완료로 보이는 것이 맞다. 미달성으로 보이게 하려고 dose를 삭제하거나 생성 시각을 바꾸지 않는다. 참여 전 완료 키를 추가하여 소급 달성시키면 안 된다.
- API 조회도 lifecycle/finalization이 선행될 수 있으므로 transaction 전후 검증을 위해 함부로 호출하지 않는다. 우선 정확한 DB snapshot 비교와 로컬 순수 계산으로 검증하고, 정상 UI 검토는 COMMIT 후 별도 승인 범위에서 한다.
- ROLLBACK으로 끝낸 dry-run을 반복하면, 다른 상태 변화가 없는 한 동일한 N건이 다시 후보로 나와야 한다. 동일 키 0건/no-op 검증은 승인된 COMMIT이 성공한 뒤의 재검사 또는 격리 fixture에서 COMMIT한 뒤에만 적용한다. 미래 날짜, 다른 사용자, 허용하지 않은 target의 변경은 모두 0건이어야 한다.
- COMMIT 전 실패는 즉시 전체 ROLLBACK한다. COMMIT 후 일반적인 원복은 보장하지 않는다. 사용자 복용/취소·일정 변경·완료 고정·배지 지급이 뒤따를 수 있다. 코드 롤백은 추가 목표를 지우지 않는다.
- COMMIT 후 되돌림은 **별도 승인된 작업**이다. 작업이 기록한 정확한 신규 occurrence ID와 값만 대상으로, User→참여 잠금을 다시 얻고 ACTIVE/미고정/미만료 및 모든 관련 상태가 post-commit snapshot과 같음을 입증한 경우에만 삭제 여부를 검토한다. 후속 변경이 하나라도 있거나 이력이 불명확하면 STOP하고 별도 데이터 복구 판단을 요청한다. 기존 목표/dose/배지/최종 결과를 자동으로 되돌리는 명령은 제공하지 않는다.

운영 보고서는 승인 번호, 실행 SHA/환경, 비식별 대상 식별자, 증거 출처, dry-run 예상 N/실제 N, 신규 행 ID와 정확한 키, 보존 검증, 실행/COMMIT 시각, 중단 또는 no-op 사유를 남긴다. 이 런북 작성 단계에서는 실제 대상의 복구 가능성이나 실행 성공을 검증하지 않았다.

## 근거 코드

- `app/services/custom_challenge_goal_planner.py`: KST 경계, `include_join_slot`, 제외 키, 고유 목표 키.
- `app/services/custom_challenges.py`: 당시 설정 해석/window 규칙, User 선행 잠금, 신규 목표 저장 및 ACTIVE 진행률 계산.
- `app/services/custom_challenge_schedule_reconciler.py`: 변경 시점 이전 이력 보존; 소급 backfill 도구가 아님.
- `app/services/custom_challenge_lifecycle.py`: User→참여 잠금과 최종 결과 고정.
- `app/models/custom_challenges.py`, `app/models/medications.py`, `app/models/supplement_nutrients.py`: 유일 키, FK, dose 저장 구조와 snapshot 한계.
