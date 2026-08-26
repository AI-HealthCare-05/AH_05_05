# 약·영양제 Chat Core와 Front API 통합 설계

## 1. 목표

현재 RDBMS와 Qdrant에 저장된 근거를 이용해 약·영양제 질문에 답하고,
FastAPI와 프론트엔드를 하나의 JSON API로 연결한다.

- 일반 의약품·영양제 질문은 진료 기록이 없어도 처리한다.
- 사용자 복용 약·영양제 질문은 인증 사용자의 현재 복용 정보만 결합한다.
- 약봉투 OCR 결과를 사용자가 확인·저장한 진료 기록이 있으면 그 기록의
  제품명·복용법·주의사항을 일반 정보보다 우선해 설명한다.
- 약-약, 약-영양제, 영양제-영양제 상호작용은 승인된 구조화 규칙을
  우선하고 Qdrant 근거를 보충 설명으로 사용한다.
- 답변과 출처를 CHAT 테이블에 저장하고 실패 상태도 추적한다.
- `POST /api/v1/chat` 계약과 오류 예시를 ReDoc에 공개한다.

## 2. 현재 문제

현재 `AnswerChatMessageUseCase`는 질문을 분류하기 전에
`care_episode_id`로 환자 컨텍스트를 조회한다. 따라서 프론트의
`recordId: null`인 일반 의약품·영양제 질문은 실행할 수 없다. 또한 FastAPI에는
CHAT Router, Repository, Service와 Qdrant 생명주기 관리가 없으며,
프론트는 현재 `/api/chat`으로 요청해 백엔드의 `/api/v1` prefix와 맞지
않는다.

기존 Chat Core는 퇴원 환자의 진단·복약·생활습관 안내를 중심으로
구성되어 있다. 변경된 서비스는 현재 복용 항목, 제품 안내, 상호작용,
영양제 근거 검색을 중심으로 처리해야 한다.

## 3. 선택한 접근

### 3.1 선택: 약·영양제 전용 Core를 Adapter로 연결

FastAPI는 CHAT 세션·메시지 저장과 인증·인가를 담당하고,
`MedicationChatCoreService`는 질문 분류, RDBMS 조회, 상호작용 규칙 조회,
Qdrant 검색, 답변 생성과 안전성 검사를 담당한다. 두 계층은 요청·결과
스키마와 Protocol로만 연결한다.

이 구조를 선택한 이유는 다음과 같다.

- 일반 의약품·영양제 질문과 사용자 복용정보 질문을 같은 API에서 처리할
  수 있다.
- ORM이나 Qdrant 구현을 바꿔도 FastAPI Router 계약은 유지된다.
- 향후 SSE를 추가할 때 저장 Service와 Core를 재사용할 수 있다.
- 단위 테스트에서는 가짜 Core를 주입해 OpenAI 호출 없이 트랜잭션과
  API를 검증할 수 있다.

### 3.2 제외한 접근

- **기존 퇴원환자 Core를 Router에서 직접 호출:** `care_episode_id`가
  필수가 되어 일반 의약품·영양제 질문을 처리하지 못하고 변경된 도메인과 맞지
  않는다.
- **Router에서 ORM·Qdrant·OpenAI를 직접 조립:** 구현은 빠르지만 저장
  트랜잭션, 근거 정책, 안전성 검사와 HTTP 책임이 섞여 테스트와 확장이
  어렵다.
- **모든 채팅을 Redis Worker로 처리:** 사용자 응답에 queue와 Pub/Sub
  왕복이 추가된다. 채팅은 FastAPI에서 직접 처리하고, PDF 인덱싱처럼
  오래 걸리고 재시도가 필요한 작업만 Worker에 둔다.

## 4. 범위

### 구현 범위

- 약·영양제 Chat Core 요청·결과 계약
- 현재 복용 약·영양제 Provider
- 승인된 상호작용 Rule Repository
- 기존 Qdrant Knowledge Retriever Adapter
- 근거 기반 답변 조립과 안전성 검사
- CHAT Repository와 Service
- `POST /api/v1/chat`
- 프론트 API 경로와 요청 ID 연결
- Qdrant/OpenAI 의존성 생명주기와 앱 실행 설정
- 통합 테스트, OpenAPI/ReDoc 설명과 예시

### 제외 범위

- SSE 스트리밍
- 채팅 목록·상세·삭제 API
- 관리자 상호작용 규칙 승인 UI/API
- 사용자 직접 입력 영양제 ORM 확장
- PENDING 상호작용 규칙 자동 승인
- 대규모 인덱싱 및 검색 품질 고도화

PENDING 규칙은 이번 런타임에서 사용하지 않는다. 관리자가 검수해
`APPROVED`가 된 규칙만 결정론적 상호작용 결과에 포함한다.

## 5. 계층과 컴포넌트

```text
Frontend
  -> POST /api/v1/chat
  -> FastAPI Chat Router
  -> ChatApplicationService
       -> ChatRepository (세션·메시지·출처 트랜잭션)
       -> MedicationChatCoreService
            -> QuestionClassifier
            -> ActiveIntakeContextProvider (MySQL)
            -> MedicationGuideRepository (MySQL)
            -> InteractionRuleRepository (MySQL, APPROVED only)
            -> KnowledgeRetriever (Qdrant)
            -> AnswerGenerator (OpenAI)
            -> GroundedClaimValidator
  <- 저장된 답변과 출처 JSON
```

### 5.1 `MedicationChatCoreService`

HTTP와 ORM 모델을 모르는 애플리케이션 진입점이다. 입력은 인증 사용자
ID, 선택 진료 기록 ID, 질문과 최근 대화이며 출력은 답변, 라우트,
안전성 상태, 출처와 버전 정보다.

### 5.2 `ActiveIntakeContextProvider`

- 인증 사용자의 활성 `CareEpisode`에 속한 약을 조회한다.
- 처방 시작일과 처방 일수가 있는 약은 계산된 종료일이 지나지 않은
  항목만 현재 복용 후보로 사용한다.
- 활성 `UserSupplementNutrient`를 조회한다.
- `recordId`가 있으면 사용자 소유 `CareEpisode.id`인지 검증하고 해당
  기록을 우선 컨텍스트로 표시한다.
- 상호작용 검사는 선택 기록에 한정하지 않고 사용자의 전체 현재 복용
  후보를 사용한다.
- 과거·삭제·비활성 항목은 현재 상호작용 검사에서 제외한다.

### 5.3 `MedicationGuideRepository`

`MedicationProductGuide`에서 제품 기본 안내를 조회한다. 제품명이 정확히
일치하지 않을 때는 확정 매핑이 있는 항목만 사용하며 LLM이 제품을
임의로 연결하지 않는다.

### 5.4 `InteractionRuleRepository`

- `review_status=APPROVED`인 규칙만 반환한다.
- 입력 순서와 무관한 `pair_key` 또는 양쪽 entity ID로 조회한다.
- 구조화 규칙의 위험도와 원문 효과를 결정론적 결과로 사용한다.
- 승인 규칙이 없다는 사실을 `안전함`으로 해석하지 않는다.

### 5.5 `KnowledgeRetriever`

현재 `medication_knowledge_baseline_v1` Qdrant 컬렉션과 기존 Knowledge
검색 스키마를 재사용한다. 질문 의도와 확인된 약·영양제 이름으로 검색
표현을 만들고, 데이터셋·문서 유형·상호작용 유형 metadata filter를
적용할 수 있는 Adapter로 감싼다.

### 5.6 분류와 생성

명확한 제품 안내·상호작용 키워드는 결정론적으로 먼저 분류한다.
모호한 질문만 OpenAI 분류기로 보낸다. 답변 생성 LLM은 RDBMS 결과와
검색된 Qdrant 청크 안의 정보만 자연스러운 한국어로 정리한다.

## 6. 답변 정책

| 질문 유형 | 우선 근거 | 보충 근거 | 근거가 없을 때 |
|---|---|---|---|
| 약 기본 정보(진료 기록 없음) | RDBMS 제품 가이드 | Qdrant | 확인 가능한 자료가 없다고 안내 |
| 복용 중인 약 설명(진료 기록 있음) | 사용자 확정 복약정보 | RDBMS 제품 가이드, Qdrant | 확정정보와 일반정보를 구분해 안내 |
| 영양제 기본 정보 | Qdrant | 검토된 생활습관 원칙 | 자료 범위 밖이라고 안내 |
| 약-약 | 승인된 RDBMS 규칙 | Qdrant | 확인되지 않았으며 안전하다는 뜻은 아니라고 안내 |
| 약-영양제 | 승인된 RDBMS 규칙 | Qdrant | 같은 제한 문구 사용 |
| 영양제-영양제 | 승인된 RDBMS 규칙 | Qdrant | 같은 제한 문구 사용 |
| 일반 생활습관 | 검토된 원칙 파일 | 관련 Qdrant 근거 | 일반적 범위만 설명 |

상호작용 우선순위는 약-약, 약-영양제, 영양제-영양제 순으로 표시한다.
답변은 복용 시작·중단, 용량 증감, 진단 또는 처방 결정을 하지 않는다.
모든 의료 관련 답변 끝에는 참고 정보이며 의료진의 진료를 대체하지
않는다는 문구를 포함한다.

## 7. API 계약

### 7.1 요청

`POST /api/v1/chat`

```json
{
  "requestId": "6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
  "recordId": null,
  "conversationId": null,
  "message": "타이레놀은 어떤 약이고 복용할 때 무엇을 주의해야 하나요?"
}
```

- `requestId`: 프론트가 생성하는 UUID. 재전송 식별에 사용한다.
- `recordId`: 약봉투 OCR 결과를 사용자가 확인·저장한
  `CareEpisode.id`. 일반 의약품·영양제 질문은 `null`이다.
- `conversationId`: 기존 `ChatSession.id`. 첫 질문은 `null`이다.
- `message`: 1~2,000자의 사용자 질문이다.
- `user_id`와 대화 history는 클라이언트에서 받지 않는다. JWT 사용자와
  DB의 최근 대화에서 결정한다.

`recordId=null`인 일반 의약품 질문은 제품명 또는 성분명을 기준으로
`MedicationProductGuide`와 Qdrant 근거를 조회한다. 이름이 여러 제품을
가리켜 특정할 수 없으면 LLM이 임의로 고르지 않고 제품명·성분명 확인을
요청한다.

`recordId`가 있으면 해당 기록이 인증 사용자 소유이고 사용자 확인이
완료되었는지 검증한다. 이후 답변은 다음 순서를 지킨다.

1. 사용자 확정 복약정보: 실제 저장된 제품명, 복용량, 횟수, 기간
2. RDBMS 제품 가이드: 효능, 사용법, 주의사항, 상호작용, 이상반응, 보관법
3. Qdrant 공공 근거: 필요한 추가 설명

사용자 확정정보와 일반 제품 설명은 답변과 출처에서 구분한다. 일반
제품 가이드가 사용자의 처방 지시를 덮어쓰지 않는다.

### 7.2 응답

```json
{
  "conversationId": 42,
  "messageId": 108,
  "answer": "확인된 근거를 기준으로 설명드리면 ...",
  "sources": [
    {
      "scope": "official",
      "title": "e약은요 · 제품 사용 안내",
      "organization": "식품의약품안전처",
      "url": "https://example.org/source"
    }
  ]
}
```

프론트의 기존 `SendChatResult`를 유지한다. 내부 route, 안전성 상태,
모델·프롬프트 버전과 실행 시간은 DB에 저장하되 초기 화면 응답에는
노출하지 않는다.

### 7.3 인증과 소유권

- JWT 인증이 없으면 `401`이다.
- `conversationId`가 다른 사용자의 세션이면 존재 여부를 노출하지 않고
  `404 CHAT_SESSION_NOT_FOUND`를 반환한다.
- `recordId`가 다른 사용자의 기록이면 `404 CARE_EPISODE_NOT_FOUND`를
  반환한다.
- 기존 세션을 이어갈 때 요청의 `recordId`와 세션 기록이 충돌하면
  `409 CHAT_CONTEXT_MISMATCH`를 반환한다.

## 8. 저장 트랜잭션

MySQL 트랜잭션을 OpenAI·Qdrant 호출 동안 유지하지 않는다.

### 트랜잭션 1: 요청 수락

1. 기존 세션을 `SELECT FOR UPDATE`로 잠그거나 새 세션을 생성한다.
2. 최근 sequence 번호를 확인한다.
3. 사용자 메시지를 `COMPLETED`로 저장한다.
4. 사용자 메시지를 참조하는 AI `PENDING` 메시지를 저장한다.
5. 커밋한다.

`requestId`는 AI 메시지에 저장한다. 같은 세션에서 동일한 `requestId`가
이미 완료되었다면 저장된 응답을 반환하고, 처리 중이면
`409 CHAT_REQUEST_IN_PROGRESS`를 반환한다. 세션 잠금과
`(chat_session_id, sequence_no)` 고유키로 순서 충돌을 방지한다.

### 트랜잭션 밖: Core 실행

최근 완료 메시지 최대 10개를 시간 순서로 읽어 Core에 전달한다.
RDBMS, Qdrant와 OpenAI 호출은 DB 잠금 없이 실행한다.

### 트랜잭션 2: 결과 확정

- 성공: AI 메시지를 `COMPLETED`로 바꾸고 답변·route·안전성·버전·
  `duration_ms`를 저장한 뒤 출처를 citation 순서대로 저장한다.
- 실패: AI 메시지를 `FAILED`로 바꾸고 `error_code`, `duration_ms`,
  `completed_at`을 저장한다.
- 세션의 `last_message_at`을 갱신한다.

이 구조는 외부 호출 실패로 `PENDING` 메시지가 영구히 남는 것을 막고,
긴 외부 호출로 다른 채팅 저장이 막히는 것을 방지한다.

## 9. 오류와 대체 응답

FastAPI 오류 본문은 기존 앱 계약을 따른다.

```json
{
  "code": "CHAT_UPSTREAM_UNAVAILABLE",
  "message": "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
}
```

- Qdrant 장애 + RDBMS 근거 존재: RDBMS 근거만으로 제한된 답변을 만든다.
- Qdrant 장애 + RDBMS 근거 없음: 검색 근거를 확인할 수 없다고 답하며
  임의의 안전 결론을 만들지 않는다.
- OpenAI timeout/rate limit/일시 장애: 메시지를 `FAILED`로 확정하고
  `503 CHAT_UPSTREAM_UNAVAILABLE`을 반환한다.
- 근거 위반 또는 금지된 복약 결정 표현: 원 답변을 저장하지 않고 안전한
  제한 안내로 교체해 `COMPLETED`로 저장한다.
- 예상하지 못한 오류: 내부 상세를 노출하지 않고
  `500 CHAT_PROCESSING_FAILED`로 변환한다.

## 10. 프로세스 생명주기와 배포

- FastAPI 프로세스당 Qdrant async client와 OpenAI client를 한 번만
  생성해 재사용하고 종료 시 닫는다.
- 요청마다 client나 Core 전체를 다시 생성하지 않는다.
- FastAPI 이미지가 `ai_worker`를 import할 수 있도록 소스 복사와 최소
  chat runtime dependency group을 추가한다.
- 개발 compose에는 FastAPI 컨테이너의 `ai_worker` bind mount를 추가한다.
- PDF 인덱싱 Worker 구성은 변경하지 않는다.

## 11. ReDoc 문서

Router에는 다음을 명시한다.

- summary: `약·영양제 챗봇 답변 생성`
- description: 인증, 일반 질문, 복용정보 결합, RDBMS/Qdrant 우선순위,
  의료적 제한, 동기 JSON 응답을 설명한다.
- 요청 예시: 일반 의약품, 일반 영양제, 복용 약 상호작용, 기존 대화 이어가기
- 성공 예시: 개인 출처와 공공 출처가 각각 있는 응답
- 오류 응답: 401, 404, 409, 422, 503
- `recordId`와 `conversationId`의 의미를 필드 설명에 포함한다.

`/redoc`과 `/openapi.json`에서 실제 `/api/v1/chat` 경로와 모든 예시가
노출되어야 한다.

## 12. 테스트 전략

### Core 단위 테스트

- 일반 의약품·영양제 질문은 care episode 없이 실행된다.
- 현재 복용 약·영양제만 Provider가 반환한다.
- APPROVED 규칙만 조회된다.
- 상호작용 순서와 근거 우선순위가 유지된다.
- 근거 없음이 안전함으로 표현되지 않는다.
- Qdrant 장애 시 RDBMS-only 대체 응답을 사용한다.
- 금지된 진단·처방·복약 변경 표현을 차단한다.

### Repository·Service 통합 테스트

- 새 세션과 사용자/AI 메시지 순서 저장
- 기존 세션 최근 10개 history의 시간 순서 전달
- 세션·진료 기록 소유권 검증
- 성공 시 답변과 출처의 원자적 저장
- Core 실패 시 AI 메시지 `FAILED` 확정
- 동일 request ID 완료 응답 재사용과 처리 중 충돌
- 동시 요청 sequence 충돌 방지

SQLite는 비즈니스 로직을 빠르게 검증하고, MySQL 통합 테스트는 Enum,
Decimal, FK, row lock과 트랜잭션 호환성을 별도로 검증한다.

### API·문서 통합 테스트

- 인증 없는 요청 `401`
- 새 대화와 이어가기 `200`
- 잘못된 payload `422`
- Core 장애 `503`과 DB 실패 상태
- 응답 source DTO 매핑
- OpenAPI에 경로, summary, description, 예시와 오류 스키마 존재

### 프론트 검증

- 실제 요청 경로가 `/api/v1/chat`으로 조합된다.
- UUID `requestId`가 요청마다 생성되고 재시도 시 같은 값을 재사용할 수
  있다.
- TypeScript 타입 검사, 단위 테스트와 production build를 통과한다.

실제 OpenAI 통합 테스트는 환경 플래그가 있을 때만 실행하고 기본 CI는
가짜 Core/client를 사용해 결정론적으로 동작한다.

## 13. 완료 기준

- `POST /api/v1/chat`이 인증 사용자 기준으로 새 대화와 이어가기를
  처리한다.
- 일반 의약품·영양제 질문은 `recordId=null`로 동작한다.
- 확정 진료 기록이 있는 약 질문은 사용자 복약정보를 먼저 설명하고
  일반 제품 정보와 Qdrant 근거를 보충한다.
- 사용자 복용정보, 승인 규칙, Qdrant 출처가 정책에 맞게 사용·저장된다.
- 외부 호출 중 DB 트랜잭션을 유지하지 않는다.
- 실패한 AI 메시지가 `PENDING`에 남지 않는다.
- `/redoc`과 `/openapi.json`에서 완전한 계약을 확인할 수 있다.
- Ruff, Python 테스트, 프론트 테스트·build, Docker Compose config와
  `git diff --check`가 통과한다.
