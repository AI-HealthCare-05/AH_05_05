# 사용자 챌린지 참여·진행·인증·배지 지급 설계

## 1. 목적과 범위

공식 챌린지와 배지 관리 기능에 사용자 참여 도메인을 추가한다. 이 설계는 다음 네 가지 책임을 분리한다.

- 사용자의 챌린지 참여 상태와 전체 진행률
- 인증 주기별 목표와 진행률
- 사용자가 제출한 개별 인증 및 관리자 검토 이력
- 챌린지 완료에 따른 배지 지급·회수 이력

동일한 사용자는 동일한 공식 챌린지에 한 번만 참여할 수 있다. 참여자 화면 구현 범위는 별도로 정하되, 데이터 모델과 서비스 규칙은 사용자 API와 관리자 검토 API를 지원할 수 있도록 설계한다.

## 2. 기존 모델과의 연결

- `user_challenges.user_id`는 `user.id`를 참조한다.
- `user_challenges.challenge_id`는 `challenges.id`를 참조한다.
- `challenges.check_type`은 `common_codes.id`를 참조하며 `CHL/CHK_TYPE` 그룹의 `SELF` 또는 `MANUAL`만 허용한다.
- `challenges.challenge_period`은 `CHL/CHL_PERIOD` 그룹의 `D7`, `D14`, `D30`을 사용한다.
- `challenges.check_frequency`는 `CHL/CHK_FREQ` 그룹의 `DAILY`, `WEEKLY_3`, `TOTAL_10`을 사용한다.
- 챌린지 완료 시 `challenges.reward_badge_id`에 연결된 배지를 지급한다.

별도의 `approval_type_id`는 만들지 않는다. `check_type=SELF`는 제출 즉시 승인, `check_type=MANUAL`은 관리자 승인 대기를 뜻한다.

## 3. 상태 정의

```dbml
Enum challenge_participation_status {
  ACTIVE
  COMPLETED
  CANCELLED
}

Enum challenge_verification_status {
  PENDING
  APPROVED
  REJECTED
}

Enum badge_award_status {
  AWARDED
  REVOKED
}
```

참여는 `ACTIVE`에서 `COMPLETED` 또는 `CANCELLED`로만 전환한다. 인증은 `PENDING`에서 `APPROVED` 또는 `REJECTED`로만 전환한다. `SELF` 인증은 생성 시 바로 `APPROVED`로 저장한다. 지급된 배지는 삭제하지 않고 필요하면 `REVOKED`로 전환한다.

## 4. 테이블 설계

### 4.1 `user_challenges`

```dbml
Table user_challenges [note: '사용자의 공식 챌린지 참여 정보'] {
  id bigint [pk, increment, note: '사용자 챌린지 참여 ID']
  user_id bigint [not null, note: '참여 사용자 ID']
  challenge_id bigint [not null, note: '공식 챌린지 ID']
  status challenge_participation_status [not null, default: 'ACTIVE', note: '참여 상태']
  joined_at datetime [not null, default: `current_timestamp`, note: '참여 신청 일시']
  started_at datetime [not null, note: '실제 챌린지 시작 일시']
  end_at datetime [not null, note: '사용자별 챌린지 종료 예정 일시']
  target_count int [not null, default: 0, note: '전체 목표 인증 횟수']
  completed_count int [not null, default: 0, note: '승인된 인증 횟수']
  progress_rate decimal(5,2) [not null, default: 0, note: '현재 진행률(0~100)']
  completed_at datetime [note: '챌린지 완료 일시']
  cancelled_at datetime [note: '참여 취소 일시']
  created_at datetime [not null, default: `current_timestamp`, note: '등록 일시']
  updated_at datetime [note: '최종 수정 일시']

  indexes {
    (user_id, challenge_id) [unique, name: 'uq_user_challenges_user_challenge']
    (user_id, status, joined_at) [name: 'idx_user_challenges_user_status']
    (challenge_id, status) [name: 'idx_user_challenges_challenge_status']
    end_at [name: 'idx_user_challenges_end_at']
  }

  checks {
    `end_at >= started_at`
    `target_count >= 0`
    `completed_count >= 0`
    `progress_rate >= 0 AND progress_rate <= 100`
  }
}
```

### 4.2 `challenge_progress`

```dbml
Table challenge_progress [note: '사용자 챌린지의 인증 주기별 진행률'] {
  id bigint [pk, increment, note: '진행률 ID']
  user_challenge_id bigint [not null, note: '사용자 챌린지 참여 ID']
  period_start date [not null, note: '진행률 집계 시작일']
  period_end date [not null, note: '진행률 집계 종료일']
  target_count int [not null, default: 0, note: '해당 기간 목표 인증 횟수']
  completed_count int [not null, default: 0, note: '해당 기간 승인 인증 횟수']
  progress_rate decimal(5,2) [not null, default: 0, note: '해당 기간 진행률(0~100)']
  is_completed boolean [not null, default: false, note: '해당 기간 목표 달성 여부']
  completed_at datetime [note: '해당 기간 목표 달성 일시']
  created_at datetime [not null, default: `current_timestamp`, note: '등록 일시']
  updated_at datetime [note: '최종 수정 일시']

  indexes {
    (user_challenge_id, period_start, period_end) [unique, name: 'uq_challenge_progress_period']
    (user_challenge_id, is_completed) [name: 'idx_challenge_progress_completed']
    period_end [name: 'idx_challenge_progress_period_end']
  }

  checks {
    `period_end >= period_start`
    `target_count >= 0`
    `completed_count >= 0`
    `progress_rate >= 0 AND progress_rate <= 100`
  }
}
```

### 4.3 `challenge_verifications`

```dbml
Table challenge_verifications [note: '사용자가 제출한 챌린지 인증 기록'] {
  id bigint [pk, increment, note: '챌린지 인증 ID']
  user_challenge_id bigint [not null, note: '사용자 챌린지 참여 ID']
  progress_id bigint [not null, note: '인증이 반영될 진행률 ID']
  verification_date date [not null, note: '사용자 기준 인증일']
  content varchar(500) [note: '사용자 인증 내용']
  image_path varchar(500) [note: '인증 이미지 상대 경로(media/challenges/)']
  status challenge_verification_status [not null, default: 'PENDING', note: '인증 처리 상태']
  rejection_reason varchar(500) [note: '인증 반려 사유']
  reviewed_by_admin_id bigint [note: '수동 인증 검토 관리자 ID']
  reviewed_at datetime [note: '승인 또는 반려 처리 일시']
  idempotency_key varchar(64) [not null, unique, note: '인증 중복 등록 방지 키']
  submitted_at datetime [not null, default: `current_timestamp`, note: '인증 제출 일시']
  created_at datetime [not null, default: `current_timestamp`, note: '등록 일시']
  updated_at datetime [note: '최종 수정 일시']

  indexes {
    (user_challenge_id, verification_date) [name: 'idx_challenge_verifications_date']
    (status, submitted_at) [name: 'idx_challenge_verifications_review']
    progress_id [name: 'idx_challenge_verifications_progress']
    reviewed_by_admin_id [name: 'idx_challenge_verifications_admin']
  }
}
```

### 4.4 `user_badges`

```dbml
Table user_badges [note: '챌린지 완료에 따른 사용자 배지 지급 이력'] {
  id bigint [pk, increment, note: '사용자 배지 지급 ID']
  user_id bigint [not null, note: '배지 지급 사용자 ID']
  badge_id bigint [not null, note: '지급 배지 ID']
  challenge_id bigint [not null, note: '배지 지급 기준 챌린지 ID']
  user_challenge_id bigint [not null, note: '완료한 사용자 챌린지 참여 ID']
  status badge_award_status [not null, default: 'AWARDED', note: '배지 지급 상태']
  badge_name varchar(100) [not null, note: '지급 당시 배지 이름 스냅샷']
  badge_image_path varchar(500) [not null, note: '지급 당시 활성 배지 이미지 경로']
  awarded_at datetime [not null, default: `current_timestamp`, note: '배지 지급 일시']
  revoked_at datetime [note: '배지 회수 일시']
  revoke_reason varchar(500) [note: '배지 회수 사유']
  created_at datetime [not null, default: `current_timestamp`, note: '등록 일시']
  updated_at datetime [note: '최종 수정 일시']

  indexes {
    (user_challenge_id, badge_id) [unique, name: 'uq_user_badges_participation_badge']
    (user_id, status, awarded_at) [name: 'idx_user_badges_user_status']
    (challenge_id, awarded_at) [name: 'idx_user_badges_challenge']
  }
}
```

### 4.5 참조 관계

```dbml
Ref: user_challenges.user_id > user.id
Ref: user_challenges.challenge_id > challenges.id
Ref: challenge_progress.user_challenge_id > user_challenges.id
Ref: challenge_verifications.user_challenge_id > user_challenges.id
Ref: challenge_verifications.progress_id > challenge_progress.id
Ref: challenge_verifications.reviewed_by_admin_id > admin.id
Ref: user_badges.user_id > user.id
Ref: user_badges.badge_id > badges.id
Ref: user_badges.challenge_id > challenges.id
Ref: user_badges.user_challenge_id > user_challenges.id
```

관리자 FK는 `SET NULL`, 그 외 핵심 FK는 이력 보호를 위해 `RESTRICT`를 적용한다. 참여·인증·지급 이력은 물리 삭제하지 않는다.

## 5. 기간과 목표 계산

참여 시작 시 공통코드의 상세코드를 읽어 진행 구간을 생성한다.

| 인증 빈도 | 구간 생성 | 목표 계산 |
|---|---|---|
| `DAILY` | 하루마다 한 구간 | 구간별 1회 |
| `WEEKLY_3` | 참여 시작일부터 완전한 7일마다 한 구간 | 구간별 3회 |
| `TOTAL_10` | 전체 기간을 한 구간 | 전체 10회 |

`D30 + WEEKLY_3`은 7일 구간 네 개와 전체 목표 12회를 만든다. 마지막 2일은 인증 목표와 진행률 집계에서 제외한다. `started_at`은 참여 시각이며 `end_at`은 `started_at + 7/14/30일`인 배타적 종료 시각이다. 따라서 인증 가능 범위는 `started_at <= 인증 시각 < end_at`이다. 날짜 구간은 기존 `Config.TIMEZONE` 기준으로 계산하며 `DAILY`는 시작일을 포함해 D7/D14/D30 각각 7개, 14개, 30개의 일별 구간을 만든다.

## 6. 인증과 진행률 처리

1. 참여 생성과 모든 `challenge_progress` 생성은 한 트랜잭션에서 처리한다.
2. 인증일을 기준으로 서버가 진행 구간을 찾는다. 클라이언트는 `progress_id`를 지정하지 않는다.
3. `SELF`는 생성 즉시 `APPROVED` 처리하고 진행률을 갱신한다.
4. `MANUAL`은 `PENDING`으로 생성하며 내용 또는 이미지 중 하나 이상을 요구한다.
5. 관리자 승인 시 해당 진행 구간과 참여 행을 잠그고 승인 횟수 및 진행률을 갱신한다.
6. 반려된 인증은 집계하지 않으며 사용자는 새 인증으로 다시 제출할 수 있다.
7. 모든 필수 진행 구간이 완료되면 참여를 `COMPLETED`로 전환한다.
8. 완료 트랜잭션에서 활성 배지를 멱등하게 한 번 지급한다.

참여가 `COMPLETED` 또는 `CANCELLED`이면 새 인증을 받지 않는다. 인증 승인·반려는 한 번만 가능하다.

## 7. API 경계

사용자 API는 참여, 내 참여 목록·상세·진행률 조회, 인증 제출, 참여 취소, 보유 배지 조회를 담당한다. 관리자 API는 수동 인증 대기 목록, 승인·반려, 참여·완료 현황, 배지 회수를 담당한다.

승인과 반려는 하나의 액션 API를 사용한다.

```http
POST /api/v1/admin/challenge-verifications/{verification_id}/actions
```

```json
{
  "action": "APPROVE",
  "rejection_reason": null
}
```

## 8. 오류 처리

- 모집 기간 외 참여: `409 CHALLENGE_NOT_RECRUITING`
- 삭제 또는 미전시 챌린지: `404 CHALLENGE_NOT_FOUND`
- 중복 참여: `409 CHALLENGE_ALREADY_JOINED`
- 챌린지 종료 후 인증: `409 CHALLENGE_PERIOD_ENDED`
- 인증 집계 대상이 아닌 날짜: `409 VERIFICATION_PERIOD_NOT_FOUND`
- 수동 인증 증빙 누락: `422 VERIFICATION_EVIDENCE_REQUIRED`
- 이미 처리한 인증 재처리: `409 VERIFICATION_ALREADY_REVIEWED`
- 다른 사용자의 참여 정보 접근: `404`

인증 제출은 `idempotency_key`로 중복 요청을 차단하고 같은 요청이면 기존 결과를 반환한다. 배지 지급도 유일 인덱스를 이용해 멱등하게 처리한다.

## 9. 검증 범위

- 모델 필드, FK, 인덱스, 유일조건 및 체크 제약
- `D7`, `D14`, `D30` 기간 계산
- `DAILY`, `WEEKLY_3`, `TOTAL_10` 진행 구간 생성
- `D30 + WEEKLY_3`의 마지막 2일 제외
- `SELF` 즉시 승인과 `MANUAL` 승인 대기
- 승인·반려 상태 전이 및 재처리 차단
- 동시 승인에서도 진행률이 한 번만 증가하는지 확인
- 모든 필수 구간 완료 시 참여 완료와 배지 1회 지급
- 완료 또는 취소 이후 인증 차단
- 비활성 배지와 소프트 삭제된 챌린지의 기존 이력 유지

## 10. 구현 범위

- 기존 설계가 아직 소스에 없는 `badges`, `challenges` Tortoise ORM 모델과 관리자 CRUD API
- 배지 이미지 업로드(PNG/JPG/WebP, 최대 2MB, `media/badges/` 상대 경로 저장)
- `챌린지관리 > 공식챌린지`, `챌린지관리 > 배지관리` 사이드바와 관리자 관리 화면
- Tortoise ORM 모델과 enum 등록
- Aerich 마이그레이션 생성 및 기존 Docker MySQL에 업그레이드 적용
- 사용자 참여·진행률·인증·보유 배지 API
- 관리자 수동 인증 조회·승인·반려 API
- 저장소·서비스·DTO·예외 처리
- OpenAPI 용도 설명 및 관련 단위·API 테스트

사용자 참여 화면 UI는 이번 구현 범위에서 제외한다.
