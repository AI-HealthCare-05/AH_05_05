# #304 공식 챌린지 사용자 API 연결 계약

백오피스 입력과 DB 구조 유지. #303의 일일 유니크 전제. 시간대 Asia/Seoul.
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

## 구현/검증 분담

- 서버: 카탈로그, 응답 확장, 인증 날짜/중복/동시 요청 안전성, 승인 집계·배지, API 테스트.
- 프론트: 기존 레이아웃 + 실서버 공식 챌린지 연결, /dev 목업 분리, 상태/오류/인증/배지 테스트.
- 검증은 WSL만, 패키지는 pnpm만. 사용자 DB 대신 임시 MySQL 사용. 사용자 계정/볼륨 초기화 금지.
