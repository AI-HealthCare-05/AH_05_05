# AI Worker 챗봇 Core 안정화 기록

## 목적

FastAPI 연결 전에 챗봇 Core의 모호한 질문, 외부 서비스 장애, 의료 안전성, 장기 작업 재시도 계약을 명확히 했다. `app` 디렉토리는 변경하지 않았으며 FastAPI는 `ChatCoreService`를 조립해 호출할 수 있다.

## 문제·수정·이유

| 문제 | 수정 | 이유 |
| --- | --- | --- |
| `needs_clarification=True`여도 일반 답변 생성 흐름으로 진입 | 즉시 명확화 응답을 반환하고 `route=None`, `needs_clarification=True`, `safety_status=RESTRICTED`로 표시 | 모호한 질문으로 RAG/LLM을 호출해 잘못된 답을 만드는 것을 방지 |
| 명확화 필드 추가 후에도 응답 스키마 버전이 v1 | `chat-answer-result-v2`로 올리고 명확화 상태와 route의 불변식 검증 추가 | FastAPI·프론트가 계약 변경을 명시적으로 감지하고 모순된 응답을 거부 |
| `PATIENT_ONLY` 질문도 OpenAI 답변 LLM 호출 | RDBMS 확정정보를 `ChatAnswerAssembler`로 직접 조립 | 응답시간·비용을 줄이고 환자 확정정보가 LLM에 의해 변경되는 위험을 제거 |
| Qdrant 또는 질문 임베딩 장애가 전체 채팅 실패로 전파 | `GuidelineRetrievalError`를 잡아 환자 확정정보만 포함한 제한 응답 반환 | 공공자료 장애 중에도 확인된 환자정보를 안전하게 제공 |
| OpenAI 답변 생성 장애가 처리되지 않음 | `ChatAnswerGenerationError`로 변환하고 확정정보 제한 응답으로 대체 | 외부 API 장애를 예측 가능한 서비스 응답으로 변환 |
| 줄바꿈으로 금지 표현 우회 가능 | 안전성 정규식 적용 전에 공백·줄바꿈 정규화 | `복용을\n중단하세요` 같은 표현도 동일하게 탐지 |
| 답변에 기존 진단명이 있으면 새 진단 단정도 통과 | 답변 전체에 대한 기존 진단명 예외 제거 | `뇌졸중`을 언급하면서 `폐렴으로 진단됩니다`라고 단정하는 오류 차단 |
| 복약 검사에 건너뛰기·증량·감량·안 먹기 누락 | 출력 안전성 패턴에 해당 표현 추가 | 복약 변경 지시의 표현 변형을 차단 |
| 안전 안내문의 “복약 변경”이라는 명사도 차단 | `변경하세요/변경하십시오`처럼 지시형만 차단 | 정상 안전 문구의 오탐 방지 |
| Redis 실패 작업이 Pending에 영구 잔류 | `XAUTOCLAIM` 회수, 최대 시도 횟수, Dead Letter Stream 추가 | Worker 재시작·일시 장애 후 재처리하고 영구 실패는 조사 가능하게 보존 |
| 긴 작업이 처리 중인데 다른 Worker가 Pending을 회수할 수 있음 | 처리 중 `XCLAIM JUSTID IDLE 0` heartbeat로 lease 갱신 | 정상 장기 작업의 중복 실행과 잘못된 재시도 횟수 증가 방지 |
| 여러 Worker가 같은 문서를 동시에 재인덱싱할 수 있음 | Redis Stream 단위 분산 잠금과 heartbeat를 적용해 인덱싱 작업 직렬화 | 서로 다른 문서 버전이 Qdrant에 섞이는 경쟁 조건 방지 |
| `XAUTOCLAIM` 검색 cursor를 매번 초기화 | 응답 cursor를 다음 회수 호출에 이어서 사용 | Pending 목록 뒤쪽의 회수 가능한 작업이 굶는 현상 방지 |
| DLQ 기록과 원본 ACK가 별도 명령 | Lua로 `XADD`와 `XACK`을 원자 실행 | 중간 연결 장애로 같은 실패가 DLQ에 중복 기록되는 문제 방지 |
| 재인덱싱 시 기존 Qdrant 포인트를 먼저 삭제 | 기존 ID 조회 → 새 포인트 upsert → 성공 후 obsolete ID만 삭제 | 임베딩/upsert 실패 시 기존 검색 데이터 유실 방지 |
| FastAPI가 AI 구성요소를 직접 모두 알아야 함 | `build_chat_use_case()`와 `ChatCoreService.answer()` 제공 | 웹 계층은 요청·응답과 자원 수명주기에 집중하고 AI 조립 책임은 AI Worker에 유지 |
| 예외 타입이 `ValueError`/`RuntimeError`로 혼재 | `AIWorkerError` 기반 코드·재시도 가능 여부 계약 추가 | FastAPI가 문자열 파싱 없이 HTTP 상태와 로그 정책을 결정 가능 |
| 결정론적 답변과 장애 대체 답변의 출처 누락 | 환자·공공 출처 생성을 `ChatSourceBuilder`로 통합 | 화면에 표시된 RDBMS 확정정보를 레코드 ID까지 추적 가능 |

## FastAPI 연결 계약

FastAPI 애플리케이션 시작 시 `AsyncQdrantClient`를 한 번 만들고, 같은 클라이언트를 `build_chat_core_service()` 또는 `build_chat_use_case()`에 주입한다. 종료 시 FastAPI가 클라이언트를 닫는다.

```python
service = build_chat_core_service(
    settings=Config(),
    qdrant_client=qdrant_client,
)

result = await service.answer(
    request=chat_answer_request,
    limit=5,
)
```

일반 사용자 채팅은 FastAPI가 이 서비스를 직접 호출한다. 공공 PDF 인덱싱은 기존 Redis Stream Worker가 담당한다.

## 예외 계약

| 예외 | code | retryable | 처리 기준 |
| --- | --- | --- | --- |
| `AIConfigurationError` | `AI_CONFIGURATION_ERROR` | `False` | 서버 설정 수정 필요 |
| `PatientContextNotFoundError` | `PATIENT_CONTEXT_NOT_FOUND` | `False` | 잘못된 사용자/케어 에피소드 요청 |
| `UnconfirmedPatientContextError` | `PATIENT_CONTEXT_UNCONFIRMED` | `False` | OCR 확인·저장 완료 후 재요청 |
| `ChatClassificationError` | `CHAT_CLASSIFICATION_FAILED` | `True` | Core가 제한 응답으로 대체 |
| `ChatAnswerGenerationError` | `CHAT_ANSWER_GENERATION_FAILED` | `True` | Core가 확정정보 제한 응답으로 대체 |
| `GuidelineRetrievalError` | `GUIDELINE_RETRIEVAL_FAILED` | `True` | Core가 확정정보 제한 응답으로 대체 |

## Worker 및 인덱싱 설정

- `REDIS_CLAIM_IDLE_MS`: Pending 메시지를 다른 Consumer가 회수할 최소 유휴시간
- `REDIS_MAX_ATTEMPTS`: Dead Letter Stream 이동 전 최대 처리 횟수
- `REDIS_DEAD_LETTER_STREAM`: 영구 실패 메시지 보관 Stream
- `OPENAI_TIMEOUT_SECONDS`: OpenAI 요청 제한시간
- `OPENAI_MAX_RETRIES`: OpenAI SDK 내부 재시도 횟수

Qdrant 교체 과정에서 새 포인트 upsert 직후 obsolete 포인트 삭제 전까지 짧은 시간 동안 같은 문서의 구·신 버전이 함께 존재할 수 있다. 데이터 유실보다 일시적 중복을 선택한 MVP 안전 전략이다. Worker 경로는 Redis 분산 잠금으로 인덱싱을 직렬화한다. CLI 인덱싱 명령을 여러 프로세스에서 동시에 실행하는 방식은 지원하지 않는다.

## 검증 범위

- 명확화 응답이 RAG·답변 LLM·출력 안전성 호출을 건너뛰는지 확인
- `PATIENT_ONLY`가 Qdrant·답변 LLM을 호출하지 않는지 확인
- Qdrant/OpenAI 장애 시 확정정보 제한 응답으로 대체되는지 확인
- 줄바꿈·증량·감량·건너뛰기·새 진단 단정을 차단하는지 확인
- Redis Pending 회수와 최대 횟수 초과 DLQ 이동 확인
- Qdrant upsert 실패 시 기존 포인트가 삭제되지 않는지 확인
- FastAPI 재사용 서비스 조립과 위임 확인
- 예외 code·retryable·원인 예외 보존 확인
- 응답 스키마 v2와 명확화 상태 불변식 확인
- 환자 진단·생활관리·추적진료 출처 생성 확인
