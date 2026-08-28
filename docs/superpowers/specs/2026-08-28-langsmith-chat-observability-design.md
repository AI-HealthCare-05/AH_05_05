# LangSmith 기반 약·영양제 Chat 관측성 설계

## 1. 목표

현재 약·영양제 Chat은 LangChain의 `ChatOpenAI`, 구조화 출력,
`OpenAIEmbeddings`를 사용하지만, 한 질문이 RDBMS 조회·Qdrant 검색·LLM 생성·
안전성 검사 중 어디에서 느려지거나 잘못되었는지 하나의 실행 기록으로 확인할
수 없다.

이번 작업은 LangSmith를 다음 목적으로 연결한다.

- 사용자 질문 한 건의 전체 처리 흐름을 하나의 Trace로 묶는다.
- RDBMS, 검색, LLM, 안전성 검사, 저장 시간을 단계별 Span으로 확인한다.
- 검색 실패와 LLM 요약 실패를 구분한다.
- 모델·프롬프트·검색 설정을 결과와 함께 비교할 수 있게 한다.
- 성공 및 실패한 Assistant 메시지에서 실제 LangSmith Trace로 이동할 수 있게
  `langsmith_trace_id`를 저장한다.
- LangSmith가 꺼져 있거나 장애가 발생해도 챗봇의 기존 동작은 유지한다.

LangSmith는 관찰과 평가를 지원할 뿐 답변 품질을 자동으로 개선하지 않는다.
수집된 실행 결과를 보고 검색 쿼리, 재정렬, 프롬프트, 안전성 규칙을 변경하고
동일 평가 질문으로 다시 비교하는 것이 개선 과정이다.

## 2. 현재 상태와 문제

### 2.1 이미 구현된 LangChain 구성

- `ChatOpenAI`와 `with_structured_output()`을 이용한 답변 생성
- `OpenAIEmbeddings`를 이용한 질문·문서 임베딩
- LangChain 메시지 객체를 이용한 프롬프트 구성
- `RecursiveCharacterTextSplitter` 등 LangChain 문서 분할기

따라서 LangChain LLM 호출은 LangSmith의 자동 추적 대상이 될 수 있다.

### 2.2 아직 구현되지 않은 부분

- `LANGSMITH_TRACING`, API Key, Project 설정 계약
- Chat 요청 전체를 묶는 루트 Trace
- RDBMS·Qdrant·안전성 검사처럼 직접 구현한 함수의 Span
- Trace ID를 `ChatMessage.langsmith_trace_id`에 저장하는 코드
- 민감한 입력·출력을 외부 추적 시스템에서 숨기는 정책
- LangSmith Client 생명주기와 종료 시 buffered trace flush
- 단계별 관측성 계약과 회귀 테스트

현재 ORM과 마이그레이션에는 `langsmith_trace_id` 컬럼이 있지만 실제 값은
저장하지 않는다. 따라서 현재 컬럼명은 연동 준비용 필드이며 실제 LangSmith
연결 증거가 아니다.

## 3. 선택한 방식

### 3.1 공통 추적기 주입과 LangChain 자동 추적의 혼합

공통 `ChatTracer` 인터페이스를 애플리케이션 서비스와 Chat Core에 주입한다.
LangSmith가 꺼진 환경에서는 `NoOpChatTracer`, 켜진 환경에서는
`LangSmithChatTracer`를 사용한다.

직접 구현한 단계는 `ChatTracer.span()`으로 기록하고, Span 내부에서 실행되는
`ChatOpenAI` 같은 LangChain Runnable은 LangSmith가 자동으로 자식 실행으로
연결한다.

이 방식을 선택한 이유는 다음과 같다.

- 도메인 로직에서 LangSmith SDK 세부 구현을 분리할 수 있다.
- 테스트가 외부 LangSmith 서버 없이 실행된다.
- 추적 기능을 끄더라도 조건문이 비즈니스 코드 전체에 퍼지지 않는다.
- 향후 LangSmith를 다른 관측 도구로 교체해도 UseCase 계약을 유지할 수 있다.
- 환경변수만 켜는 방식보다 RDBMS·Qdrant·안전성 검사 구간을 명확히 비교한다.

### 3.2 제외한 방식

#### 환경변수만 활성화

LangChain LLM과 임베딩 호출은 보이지만 직접 구현한 RDBMS 조회, 쿼리 계획,
재정렬, 안전성 검사, 메시지 저장 구간이 하나의 이름 있는 단계로 나타나지 않는다.
검색 실패와 생성 실패를 구분하려는 현재 목적에 부족하다.

#### 각 파일에 LangSmith SDK 직접 삽입

가장 빠르게 세부 Span을 추가할 수 있지만 UseCase와 Repository가 외부 관측
제품에 직접 의존한다. 테스트와 비활성화 처리가 중복되고 향후 교체 비용이 커서
선택하지 않는다.

## 4. 추적 구조

한 Chat 요청의 기본 구조는 다음과 같다.

```text
chat.answer
├─ chat.request.accept
├─ patient_context.load
├─ query.plan
├─ interaction_rules.search
├─ rag.retrieve
├─ medication_guide.lookup
├─ answer.draft
├─ llm.generate
├─ safety.validate
└─ chat.response.persist
```

### 4.1 루트 Trace `chat.answer`

`ChatApplicationService.send()`에서 시작한다. 요청 수락부터 최종 저장 또는 실패
저장까지 포함하여 API 내부 처리 전체 시간을 측정한다.

허용하는 기본 metadata는 다음과 같다.

- `request_id`: 원문 UUID 대신 SHA-256 해시 앞 16자리
- `user_key`: 사용자 ID를 서비스 전용 salt와 함께 해시한 값
- `care_episode_present`: 진료 기록 연결 여부만 boolean으로 기록
- `conversation_present`: 기존 대화 연결 여부만 boolean으로 기록
- `history_count`: 전달한 최근 메시지 개수
- `streaming`: 일반 JSON API 또는 SSE API 구분
- `environment`, `dataset_version`, `model_name`, `prompt_version`

사용자 이메일, 사용자 ID 원문, 진료 ID 원문, 질문 원문, 복약 목록은 기본
metadata에 넣지 않는다.

### 4.2 주요 자식 Span

| Span | 기록 대상 | 원문 없이 기록할 값 |
|---|---|---|
| `chat.request.accept` | 세션 확인·메시지 PENDING 저장 | 재사용 여부, history 개수 |
| `patient_context.load` | 현재 약·영양제 RDBMS 조회 | 약 개수, 영양제 개수, context hash |
| `query.plan` | 질문 유형·엔티티·검색 표현 구성 | route 후보, 기능성/상호작용 여부, 엔티티 개수 |
| `interaction_rules.search` | 승인 규칙 조회 | 규칙 개수, 위험도별 개수 |
| `rag.retrieve` | 임베딩·Qdrant 검색·재정렬 | 후보 수, 채택 수, 최고/최저 점수, 문서 유형 |
| `medication_guide.lookup` | 제품 가이드 조회 | 일치/모호/미발견 상태, 후보 수 |
| `answer.draft` | 결정론적 근거 조립 | 출처 유형별 개수, route |
| `llm.generate` | LangChain `ChatOpenAI` 실행 | 모델, 토큰, 지연시간, 오류 유형 |
| `safety.validate` | 근거·금지표현 검사 | SAFE/RESTRICTED/BLOCKED, reason code |
| `chat.response.persist` | 최종 답변·출처 트랜잭션 저장 | source 개수, 성공/실패 상태 |

검색 청크 본문과 환자 확정정보는 기본 metadata에 저장하지 않는다. Qdrant
point ID와 문서 checksum은 개인 데이터가 아닌 데이터셋 식별자로 제한하여
기록할 수 있다.

## 5. 입력·출력 및 개인정보 정책

### 5.1 기본 정책

기본값은 다음과 같다.

```env
LANGSMITH_TRACING=false
LANGSMITH_CAPTURE_CONTENT=false
```

`LANGSMITH_CAPTURE_CONTENT=false`이면 LangSmith Client를
`hide_inputs=True`, `hide_outputs=True`로 생성한다. 이 설정은 루트 Trace뿐
아니라 자동 생성되는 LangChain LLM 자식 실행에도 적용되어 프롬프트와 응답
본문 전송을 차단한다.

### 5.2 원문 기록 허용 조건

질문과 답변 원문은 다음 조건을 모두 만족할 때만 허용한다.

1. 가상 사용자와 가상 복약정보로 만든 개발·평가 데이터다.
2. 운영 사용자 데이터가 섞이지 않는 별도 환경이다.
3. `LANGSMITH_CAPTURE_CONTENT=true`를 실행자가 명시적으로 설정했다.
4. 전용 LangSmith Project를 사용한다.

실제 사용자 환경에서 원문 기록을 활성화하지 않는다. 원문 기록이 필요한 품질
실험은 대표 질문 데이터셋을 별도로 만들어 수행한다.

### 5.3 해시 주의사항

단순 SHA-256만 사용하면 작은 범위의 숫자 ID를 대입해 원본을 추측할 수 있다.
따라서 사용자 식별 metadata는 `SECRET_KEY`와 분리된 관측 전용 salt를 사용한
HMAC-SHA-256으로 생성한다. salt가 없으면 사용자 식별 metadata 자체를
기록하지 않는다.

## 6. 설정 계약

`ai_worker.core.config.Config`에 다음 설정을 추가한다.

| 설정 | 기본값 | 설명 |
|---|---:|---|
| `LANGSMITH_TRACING` | `false` | 전체 추적 활성화 |
| `LANGSMITH_API_KEY` | 없음 | LangSmith 비밀키 |
| `LANGSMITH_PROJECT` | `ai-health-medication-chat` | Trace 프로젝트명 |
| `LANGSMITH_ENVIRONMENT` | `local` | local·test·demo·production 구분 |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | API endpoint |
| `LANGSMITH_WORKSPACE_ID` | 없음 | 복수 workspace key일 때 지정 |
| `LANGSMITH_CAPTURE_CONTENT` | `false` | 가상 데이터 원문 기록 허용 |
| `LANGSMITH_HASH_SALT` | 없음 | 사용자 식별자 HMAC용 별도 salt |
| `LANGSMITH_CLOSE_TIMEOUT_SECONDS` | `2.0` | 종료 시 trace buffer flush 제한시간 |
| `RUN_LANGSMITH_INTEGRATION_TESTS` | `false` | 실제 API 연결 테스트 opt-in |

추적이 켜졌는데 API Key가 없으면 앱 전체를 실패시키지 않는다. 명확한 경고를
남기고 `NoOpChatTracer`로 전환한다. API Key와 hash salt는 로그, metadata,
ReDoc, 응답에 노출하지 않는다.

LangSmith를 코드에서 직접 import하므로 transitive dependency에 기대지 않고
`pyproject.toml`에 직접 의존성을 선언한다.

## 7. Trace ID 저장 계약

- Trace를 시작할 때 루트 `run_id`를 UUID로 생성한다.
- LangSmith에서는 이 root run ID가 trace ID가 된다.
- 정상 완료 시 `ChatRepository.complete_request()`가 Assistant 메시지의
  `langsmith_trace_id`에 저장한다.
- 예외와 취소 시에도 `ChatRepository.fail_request()`가 같은 값을 저장한다.
- LangSmith가 비활성화되었거나 Trace 생성 자체가 실패하면 `null`을 저장한다.
- 완료된 동일 `requestId`를 재사용할 때 기존 메시지의 Trace ID를 덮어쓰지
  않는다. 새 요청 Trace에는 `cache_hit=true`만 남긴다.

기존 DB 컬럼을 사용하므로 이번 작업에는 Aerich migration이 필요하지 않다.

## 8. 장애와 성능 정책

### 8.1 장애 격리

- LangSmith Client 생성 실패는 경고 후 No-op으로 대체한다.
- Span 시작·종료·전송 실패는 실제 Chat 예외로 변환하지 않는다.
- OpenAI, Qdrant, RDBMS의 실제 오류는 기존 예외 계약대로 처리한다.
- 추적 오류 메시지에는 질문·답변·복약정보를 포함하지 않는다.

### 8.2 지연시간

LangSmith Client는 auto batch tracing을 사용한다. 요청 경로에서 trace 전송
완료를 기다리지 않는다. 애플리케이션 종료 시 `Client.close(timeout=...)`를
호출하여 남은 buffer를 제한 시간 동안 flush한다.

연동 전후 같은 대표 질문으로 P50/P95를 비교한다. 관측성 추가로 인한 API P95
증가 목표는 50ms 이하이며, 이를 넘으면 Span 수와 metadata 크기를 줄인다.

## 9. 코드 경계

### 새 파일

- `ai_worker/observability/chat_tracer.py`
  - `ChatTracer`, `ChatSpan` Protocol
  - `NoOpChatTracer`
  - `LangSmithChatTracer`
  - HMAC 식별자 유틸리티
- `ai_worker/tests/observability/test_chat_tracer.py`
  - 비활성화, 마스킹, ID, 장애 격리 단위 테스트
- `docs/langsmith-chat-observability.md`
  - 팀원용 설정·주의사항·조회·실험 절차

### 수정 파일

- `ai_worker/core/config.py`: LangSmith 설정 계약
- `ai_worker/services/medication_chat_core_service.py`: tracer 조립·주입
- `ai_worker/use_cases/answer_medication_question.py`: Core 세부 Span
- `app/dependencies/chat.py`: tracer 한 번 생성·재사용
- `app/services/chat.py`: 루트 Trace와 성공·실패 Trace ID 전달
- `app/repositories/chat_repository.py`: Trace ID 저장
- `app/main.py`: LangSmith Client 종료 flush
- 관련 ai_worker/app 테스트
- `.env.example`, `pyproject.toml`, `uv.lock`

현재 사용자가 수정 중인 다음 파일은 이번 작업에서 변경하지 않는다.

- `ai_worker/llm/generators/medication_answer_generator.py`
- `ai_worker/llm/prompts/medication_chat_prompt.py`
- PDF loader·normalizer 및 해당 테스트

## 10. 테스트 전략

### 10.1 단위 테스트

- tracing 기본값은 꺼져 있고 content capture 기본값도 꺼져 있다.
- API Key 없이 tracing을 켜도 No-op으로 안전하게 대체된다.
- content capture가 꺼지면 Client가 입력·출력을 숨긴다.
- hash salt가 있을 때 원문 ID와 다른 안정적인 HMAC key를 만든다.
- Trace가 활성화되면 root trace ID가 성공 저장 인자로 전달된다.
- AI 오류, 예상하지 못한 오류, 요청 취소에도 trace ID가 실패 저장 인자로 전달된다.
- 완료 답변 재사용 시 기존 Trace ID를 덮어쓰지 않는다.
- UseCase 단계가 정해진 Span 이름으로 기록된다.
- tracer 내부 오류가 Chat 결과를 실패시키지 않는다.

### 10.2 통합 테스트

- 기존 Chat API 통합 테스트에서 Assistant 메시지 Trace ID 저장을 검증한다.
- LangSmith 비활성 환경의 모든 테스트는 네트워크 없이 실행된다.
- 실제 LangSmith API 테스트는 별도 opt-in 플래그와 가상 질문으로만 실행한다.
- opt-in 테스트는 Trace 생성 후 project에서 root run을 조회할 수 있는지 확인한다.

### 10.3 회귀 검증

```bash
uv run --group dev ruff check ai_worker app
RUN_OPENAI_INTEGRATION_TESTS=0 \
  uv run --group ai --group app --group dev \
  python -m pytest ai_worker/tests app/tests/chat_apis -q
git diff --check
```

실제 LangSmith 연결 검증은 API Key를 로컬 환경에만 설정하고 가상 데이터 질문
한 건으로 수행한다. Key와 원문 Trace는 Git, CI 출력, 스크린샷에 포함하지 않는다.

## 11. 결과를 보고 개선하는 방법

1. 대표 질문을 기능성, 제품 안내, 약-약, 약-영양제, 영양제-영양제,
   근거 없음으로 구분한다.
2. 같은 질문 세트를 현재 설정으로 실행해 baseline Trace를 저장한다.
3. 다음 원인을 구분한다.
   - 검색 후보가 없음: 전처리·metadata·query 확장 문제
   - 관련 청크가 낮은 순위: boosting·reranking 문제
   - 근거는 올바르나 답변이 부정확: prompt·출력 조립 문제
   - 답변은 적절하나 차단: 안전성 규칙 오탐 문제
   - 결과는 적절하나 느림: 단계별 latency 문제
4. 한 번에 한 설정만 바꾸고 같은 dataset으로 재실행한다.
5. 정확도 지표와 latency·token·안전성 지표를 함께 비교한다.

LangSmith 화면의 단일 성공 사례만 보고 설정을 채택하지 않는다. 대표 질문 전체의
Recall@K, MRR, 근거 일치율, 안전성 통과·차단 정확도, P50/P95를 함께 기록한다.

## 12. 완료 기준

- tracing 비활성 상태에서 기존 Chat 동작과 테스트가 유지된다.
- tracing 활성 상태에서 한 질문이 이름 있는 root/child Span으로 표시된다.
- LangChain LLM 실행이 `llm.generate` 아래에서 확인된다.
- 성공·실패 Assistant 메시지에 실제 root trace ID가 저장된다.
- 기본 설정에서는 질문·답변·환자정보 원문이 LangSmith에 보이지 않는다.
- 가상 데이터 전용 설정에서만 원문 기반 품질 분석을 할 수 있다.
- LangSmith 장애가 API 결과와 저장 트랜잭션을 실패시키지 않는다.
- 설정법, 주의사항, 평가 절차가 팀 문서에 남아 있다.
