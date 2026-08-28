# LangSmith 약·영양제 Chat 관측성 운영 가이드

## 1. 왜 연결했는가

현재 Chat은 RDBMS 환자 복용정보, 승인 상호작용 규칙, Qdrant 검색 근거,
LangChain 기반 OpenAI 답변 생성, 안전성 검사, 메시지 저장을 순서대로 수행한다.
기존 로그만으로는 답변이 느리거나 틀렸을 때 검색과 LLM 중 어느 단계가
원인인지 한 요청 단위로 구분하기 어려웠다.

LangSmith는 답변을 대신 생성하는 기능이 아니다. 한 질문의 실행 흐름과
단계별 결과·지연시간을 기록하여 검색식, 재정렬, 프롬프트, 안전성 규칙을
근거 있게 비교하는 관측 도구다.

## 2. 기록되는 흐름

한 요청은 `chat.answer` root trace 아래 다음 child span으로 기록된다.

```text
chat.answer
├─ patient_context.load
├─ query.plan
├─ interaction_rules.search
├─ rag.retrieve
├─ medication_guide.lookup
├─ answer.draft
├─ llm.generate
└─ safety.validate
```

- `patient_context.load`: 약·영양제 건수와 Context SHA-256
- `query.plan`: 추출 엔티티·검색 섹션 건수와 질문 유형 여부
- `interaction_rules.search`: 승인된 구조화 규칙 건수
- `rag.retrieve`: 채택 청크 수, 최고 유사도, Qdrant 장애 여부
- `medication_guide.lookup`: 제품 가이드 발견·모호성·후보 수
- `answer.draft`: route, 출처 수, 초안 안전성 상태
- `llm.generate`: LLM 처리 route와 출처 수
- `safety.validate`: 최종 SAFE/RESTRICTED/BLOCKED 및 reason code

LangChain의 `ChatOpenAI` 실행은 tracing이 켜진 경우 `llm.generate` 내부 실행으로
연결된다. 성공과 실패 모두 Assistant 메시지의 `langsmith_trace_id`에 root trace
ID를 저장한다.

## 3. 개인정보와 원문 수집 원칙

기본 설정은 추적과 원문 수집이 모두 꺼져 있다.

```env
LANGSMITH_TRACING=false
LANGSMITH_CAPTURE_CONTENT=false
```

`LANGSMITH_CAPTURE_CONTENT=false`이면 LangSmith Client의 입력·출력 숨김 옵션을
사용한다. 직접 만든 span에도 질문, 답변, 약명, 영양제명, 청크 본문을 넣지 않고
건수·점수·상태만 기록한다.

사용자 식별자는 `LANGSMITH_HASH_SALT`가 있을 때만 HMAC-SHA-256 앞 16자리로
기록한다. salt가 없으면 식별 metadata를 보내지 않는다. Context SHA-256은
복용정보 원문을 보내지 않고 입력 변경 여부를 비교하기 위한 checksum이다.

다음 항목은 Git, PR, ReDoc, 로그, 발표 스크린샷에 넣지 않는다.

- `LANGSMITH_API_KEY`, `LANGSMITH_HASH_SALT`
- 실제 사용자 질문·답변과 복약정보
- 원문이 보이는 LangSmith trace 화면

`LANGSMITH_CAPTURE_CONTENT=true`는 실제 사용자가 없는 별도 개발 Project에서
가상 질문과 가상 복약정보를 사용할 때만 허용한다.

## 4. 로컬 연결 방법

1. LangSmith에서 프로젝트용 API Key를 발급한다.
2. Git에서 제외된 로컬 `.env`에 다음 값을 설정한다.

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<로컬 비밀키>
LANGSMITH_PROJECT=ai-health-medication-chat-local
LANGSMITH_ENVIRONMENT=local
LANGSMITH_CAPTURE_CONTENT=false
LANGSMITH_HASH_SALT=<충분히 긴 별도 임의 문자열>
```

3. FastAPI를 재시작하고 가상 질문을 실행한다.
4. LangSmith 프로젝트에서 `chat.answer` trace와 child span 순서를 확인한다.
5. MySQL의 Assistant `chat_messages.langsmith_trace_id`와 root trace ID가 같은지
   확인한다.

API Key가 없거나 Client 구성이 실패하면 경고 후 No-op tracer로 전환한다.
LangSmith 장애가 Chat 답변이나 DB 저장을 실패시키지 않는 것이 원칙이다.

## 5. 실제 연결 테스트

기본 테스트는 외부 네트워크를 호출하지 않고 skip된다.

```bash
RUN_LANGSMITH_INTEGRATION_TESTS=0 \
  uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/integration/test_langsmith_observability_integration.py \
  -q
```

로컬 `.env`에 Key를 설정한 뒤 가상 데이터 trace 한 건만 실연동하려면 다음처럼
실행한다.

```bash
LANGSMITH_TRACING=true \
RUN_LANGSMITH_INTEGRATION_TESTS=1 \
  uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/integration/test_langsmith_observability_integration.py \
  -q
```

## 6. Trace를 보고 개선하는 방법

대표 질문을 제품 안내, 영양제 기능성, 약-약, 약-영양제, 영양제-영양제,
근거 없음으로 나눈다. 같은 질문 세트로 baseline을 만든 뒤 한 번에 하나의
설정만 변경한다.

| 관찰 결과 | 먼저 점검할 부분 |
|---|---|
| 검색 후보가 0건 | PDF 전처리, metadata, entity 추출, query 확장 |
| 관련 청크가 낮은 순위 | 후보 수, score boosting, reranking |
| 근거는 맞지만 답변이 틀림 | 답변 조립, 프롬프트, 한국어 요약 |
| 적절한 답변이 차단됨 | 안전성 규칙 오탐과 reason code |
| 부적절한 답변이 통과함 | 금지 표현, 근거 일치 검사, 출력 안전성 |
| 전체 응답이 느림 | 가장 긴 span과 OpenAI/Qdrant/RDBMS 지연 |

단일 성공 사례만 보고 채택하지 않는다. 동일 평가 세트의 Recall@K, MRR,
근거 일치율, 안전성 판정 정확도, P50/P95, 토큰 비용을 함께 비교한다.

관측성 자체의 API P95 증가 목표는 50ms 이하이다. 초과하면 기록 span 수와
metadata 크기를 줄이고 batch tracing 상태를 확인한다.

## 7. 운영 체크리스트

- [ ] 운영·실사용 환경에서 `LANGSMITH_CAPTURE_CONTENT=false`인가?
- [ ] Project 이름에 환경(local/demo/production)이 구분되는가?
- [ ] API Key와 HMAC salt가 Git에 포함되지 않았는가?
- [ ] 성공·실패 Assistant 메시지에 root trace ID가 저장되는가?
- [ ] LangSmith 장애 시 기존 Chat API가 정상 동작하는가?
- [ ] 변경 전후를 동일 질문·동일 데이터셋 버전으로 비교했는가?
- [ ] 검색 정확도와 안전성뿐 아니라 P50/P95와 비용도 함께 기록했는가?
