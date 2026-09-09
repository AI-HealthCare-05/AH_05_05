# #304 공식 챌린지 사용자 API 연결 계약

백오피스 입력과 API 필드 유지. 취소 후 재참여를 위해 사용자·챌린지의 1건 제한은 제거한다.
#303의 참여별 일일 유니크는 유지. 시간대 Asia/Seoul.
기존 화면 유지, 홈 인증 버튼 없음. 챌린지 마이 카드에서 SELF만 했어요.
맞춤 3종은 #315, 개인 챌린지와 예시 데이터는 /dev 미리보기로 유지.

## 신규 조회 (모두 사용자 인증 필요)

- GET `/api/v1/user/challenge-catalog?offset=0&limit=100`
  - `{items: CatalogItem[], total_count, offset, limit}`. 게시/미삭제 공식 챌린지만, id 내림차순. 모집 전/종료도 can_join=false로 반환.
- GET `/api/v1/user/challenge-catalog/{challenge_id}` → CatalogItem. 비게시/삭제 항목 404.

CatalogItem (snake_case):

```ts
type CatalogItem = {
  id: number; name: string; phrase: string; description: string | null;
  challenge_type_code: string; period_code: string; duration_days: number;
  check_type_code: string; frequency_code: string;
  recruit_start_at: string; recruit_end_at: string;
  reward_badge: { id: number; name: string; description: string | null; image_path: string } | null;
  can_join: boolean; participation_id: number | null;
};
```

이번 프론트는 SELF + 지원 기간/빈도만 새 참여 허용. 기존 MANUAL 서버 참여/검토 API는 유지하며 화면은 안내하되 버튼 인증 미지원. can_join은 모집 상태·기존 참여·지원 설정 기준, 화면은 check_type_code도 확인한다. D7/D14/D30, DAILY/WEEKLY_3/TOTAL_10 코드에 따라 표시. 프론트는 자연어를 파싱하지 않는다.
`participation_id`는 가장 최근 참여 ID이며 취소 이력도 포함한다. 최근 참여가 CANCELLED이고 모집 기간 안이면 `participation_id != null`과 `can_join = true`가 함께 반환된다. 화면은 `can_join`을 우선하여 '다시 참여하기'를 제공한다.
배지함: 카탈로그 연결 배지와 내 지급 배지 합집합. 미획득은 grayscale, 필터 없음. 지급/회수 상태는 서버 기준.

## 기존 사용자 API 유지 + 참여 응답 확장

- POST `/api/v1/user/challenges/{challenge_id}/join` (body 없음) → Participation
- GET `/api/v1/user/challenges` → `{items: Participation[], total_count}`
- GET `/api/v1/user/challenges/{participation_id}` → Participation
- POST `/api/v1/user/challenges/{participation_id}/cancel` → Participation
- POST `/api/v1/user/challenges/{participation_id}/verifications`
  - `{verification_date: YYYY-MM-DD, idempotency_key: string(16..64)}` → 기존 VerificationResponse
  - SELF 날짜는 참여 응답 today 사용. 서버가 오늘인지 검사한다. MANUAL은 기존 참여 기간 내 증빙 제출 정책을 유지한다. 같은 참여/날짜 중복은 기존 인증 응답 반환, 재집계/중복 지급 없음.
  - 요청 성공 후 참여 진행률을 갱신한다. 배지 등 보조 조회 실패를 이미 성공한 인증의 실패로 표시하지 않는다. 인증 요청 자체의 네트워크 재시도에는 동일 요청 키를 사용한다.
- GET `/api/v1/user/badges` → 기존 UserBadgeListResponse (snake_case)

Participation 기존 필드는 `app/dtos/challenges.py`의 UserChallengeResponse 참조. 추가:

```ts
type ParticipationAdditions = {
  challenge: CatalogItem; // 내 참여는 게시 중단된 정의도 표시 가능. 임의 타인 조회 불가
  today: string; // 서버 기준 YYYY-MM-DD
  today_verification: { id: number; verification_date: string; status: 'PENDING'|'APPROVED'|'REJECTED'; /* 기존 VerificationResponse 나머지 필드 */ } | null;
  can_verify: boolean; // SELF, ACTIVE, 개인 기간/집계 구간 내, 오늘 미인증, 구간 목표 미달
  verified_dates: string[]; // APPROVED 날짜
};
```

status: ACTIVE/COMPLETED/CANCELLED/EXPIRED. 프론트는 서버 progress_rate/target_count/completed_count 및 can_verify로 표시/제어한다. `end_at`은 마지막 수행일 다음 날의 Asia/Seoul 자정(배타적 종료)이다. 전체 수행기간 마지막 날짜는 `end_at - 1ms`를 Asia/Seoul 날짜로 포맷한다. 인증 집계 구간은 `progress_periods`를 그대로 표시한다. 날짜 경계/배지 지급을 프론트에서 추측하지 않는다.

- D30 + WEEKLY_3은 기존 정책대로 7일 구간 4개·목표 12회이며 마지막 2일은 인증 집계 대상이 아니다. 전체 수행기간 30일과 인증 구간 28일을 혼동하지 않는다.
- 참여·인증 동시 요청을 잠금과 유일조건으로 보호한다. 동일 참여/날짜는 다른 요청 키라도 한 번만 집계하고 배지도 한 번만 지급한다.
- 취소된 참여에 대기 중 인증이 뒤늦게 승인되어도 CANCELLED를 유지하며 완료/배지를 지급하지 않는다.
- MANUAL 승인 상태와 진행률·배지 재계산은 하나의 트랜잭션이다. 집계 실패 시 PENDING으로 롤백되어 재시도할 수 있다.
- 동시에 승인해도 참여 잠금을 획득한 뒤의 최신 상태로 집계한다. 잠금 대기 전에 읽은 DB 스냅샷으로 승인 건수를 덮어쓰지 않는다.
- D7 + TOTAL_10처럼 하루 한 번 인증으로 달성 불가능한 설정은 새 참여를 거부한다.

## 취소 후 재참여

- 기존 취소 기록을 삭제하거나 초기화하지 않고, 같은 `challenge_id`에 새로운 참여 ID를 생성한다.
- 모집 시작·종료 시각을 포함한 기간 안에서만 허용한다. 실제 처리 시 잠금 대기가 끝난 뒤 서버 시각으로 다시 검사한다.
- 새 참여는 재참여일부터 수행 기간과 목표 구간을 계산하고 0%부터 시작한다. 이전 인증은 새 진행률에 합산하지 않는다.
- 같은 날 취소·재참여해도 새 참여의 당일 인증은 별개다. 인증 중복 방지 단위는 계속 `(user_challenge_id, verification_date)`이다.
- ACTIVE, COMPLETED, EXPIRED 상태의 최근 참여가 있으면 새 참여를 만들지 않는다. 취소를 여러 번 반복해도 최근 참여를 기준으로 판단한다.
- 사용자 행 잠금으로 최초 참여와 재참여의 동시 요청을 직렬화한다. 응답을 잃은 클라이언트는 카탈로그/참여 조회로 최신 ID를 확인한다.
- 지난 취소 상세는 원래 기록을 보여주되, 중첩 `challenge.participation_id`는 최신 참여를 가리킨다. 새 도전이 진행 중이면 '진행 보기'로 연결한다.

### 마이그레이션·배포 주의

- 신규 `41_20260909120000_challenge_rejoin_attempts.py`는 사용자·챌린지 유니크를 조회 인덱스로 바꾼다. 기존 참여/인증 데이터는 삭제하지 않는다.
- 재참여 기록이 생긴 뒤에는 이전 유니크를 복원할 수 없어 downgrade를 중단한다. 이력을 삭제해서 강제로 되돌리지 않는다.
- #315에서는 맞춤 챌린지 모델 3종, 타입 enum, 모델 등록 및 변경하지 않은 #40 마이그레이션만 스키마 의존성으로 포함한다. 맞춤 챌린지 API·화면·백오피스 기능 전체를 통합한 것은 아니다.
- 아직 공개·적용하지 않은 #41 스냅샷을 불변 #40 기준으로 정합화했다. 맞춤 모델·필드·관계·인덱스를 보존하며, 공식 참여의 유니크/조회 인덱스 변경만 반영한다. #41 스냅샷은 등록된 런타임 ORM 전체 메타데이터와 일치한다. 이미 공개/적용한 #40은 수정하지 않는다.
- 적용된 최신 Aerich 스냅샷이 예상 #40 또는 #41 전체 메타데이터와 다르면 DDL 전에 중단한다. 모델 이름뿐 아니라 필드·관계·인덱스 변경도 검사한다. 불일치를 우회하거나 기존 이력을 삭제하지 않는다.
- 임시 MySQL에서 실제 Aerich의 39→40→41 및 40→41 실행, 이전 이력·맞춤 데이터 보존과 재실행을 검증한다. 이미 #40인 DB에는 대기 마이그레이션이 #41 하나인지 확인한 뒤 적용한다. 같은 번호의 과거 #39 적용 기록도 보존한다.
- 배포 전 DB 백업과 적용 이력을 확인하고, 구버전 백엔드의 참여 요청을 중단한 뒤 정합화된 #304 코드에서 #41을 적용한다. 적용 확인 후 새 백엔드를 시작한다. 처음 재참여한 뒤에는 동일 사용자·챌린지에 여러 행이 존재하므로 단일 행만 예상하는 구버전을 함께 실행하지 않는다.
- #40 downgrade는 맞춤 테이블을 삭제하므로 재참여 배포의 복구 수단으로 사용하지 않는다. #41 downgrade도 중복 이력이 있으면 중단한다. 데이터 삭제나 강제 유니크 복원 대신 서비스를 중단하고 보존된 데이터에 맞는 전진 복구를 검토한다.

## 구현/검증 분담

- 서버: 카탈로그, 응답 확장, 인증 날짜/중복/동시 요청 안전성, 승인 집계·배지, API 테스트.
- 프론트: 기존 레이아웃 + 실서버 공식 챌린지 연결, /dev 목업 분리, 상태/오류/인증/배지 테스트.
- 검증은 WSL만, 패키지는 pnpm만. 사용자 DB 대신 임시 MySQL 사용. 사용자 계정/볼륨 초기화 금지.
