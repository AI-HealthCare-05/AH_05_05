# LangSmith Chat Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 약·영양제 Chat 한 요청의 RDBMS·RAG·LLM·안전성·저장 단계를 LangSmith Trace로 연결하고, 민감정보를 기본 차단한 상태로 성공·실패 메시지에 root trace ID를 저장한다.

**Architecture:** `ChatTracer` Protocol과 No-op/LangSmith 구현을 AI Worker 관측성 계층에 두고 FastAPI 애플리케이션 서비스와 Chat UseCase에 같은 인스턴스를 주입한다. `ChatApplicationService.send()`가 root trace를 만들며, UseCase가 이름 있는 child span을 만들고 그 안의 LangChain `ChatOpenAI` 호출은 자동으로 중첩된다. LangSmith가 비활성화되거나 실패해도 `SafeChatTracer`가 오류를 격리하여 기존 Chat 동작을 유지한다.

**Tech Stack:** Python 3.13, LangSmith 0.10.x, LangChain OpenAI 1.5.x, FastAPI, Tortoise ORM, Qdrant, Pydantic Settings, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-28-langsmith-chat-observability-design.md`

## Global Constraints

- `LANGSMITH_TRACING=false`와 `LANGSMITH_CAPTURE_CONTENT=false`가 기본값이다.
- 실제 사용자 질문·답변·복약정보 원문을 기본 trace에 전송하지 않는다.
- 원문 capture는 가상 데이터 전용 환경에서만 명시적으로 활성화한다.
- 사용자 식별 metadata는 별도 salt가 있을 때만 HMAC-SHA-256 앞 16자리로 기록한다.
- LangSmith 설정·전송·종료 오류는 Chat 성공·실패 계약을 변경하지 않는다.
- 성공·실패 Assistant 메시지에 동일 root trace ID를 저장한다.
- 기존 `langsmith_trace_id` 컬럼을 사용하며 migration을 만들지 않는다.
- 현재 커밋된 프롬프트·PDF 전처리 동작을 변경하지 않는다.
- 모든 신규 동작은 테스트 실패를 먼저 확인한 뒤 최소 구현한다.

---

## File Structure

### 새 파일

- `ai_worker/observability/__init__.py`: 공개 tracer 타입과 builder export
- `ai_worker/observability/chat_tracer.py`: Protocol, No-op, LangSmith, 안전 래퍼, HMAC 구현
- `ai_worker/tests/observability/__init__.py`: 테스트 package
- `ai_worker/tests/observability/test_chat_tracer.py`: tracer 단위 테스트
- `ai_worker/tests/integration/test_langsmith_observability_integration.py`: opt-in 실연동 테스트
- `docs/langsmith-chat-observability.md`: 팀원용 설정·주의·실험 절차

### 수정 파일

- `pyproject.toml`, `uv.lock`: `langsmith` 직접 의존성
- `ai_worker/core/config.py`: LangSmith 설정 계약
- `ai_worker/tests/core/test_core_package.py`: 설정 기본값·환경 읽기 테스트
- `ai_worker/services/medication_chat_core_service.py`: 공통 tracer 생성·주입·노출
- `ai_worker/tests/services/test_medication_chat_core_service.py`: tracer 재사용 테스트
- `ai_worker/use_cases/answer_medication_question.py`: 단계별 child span
- `ai_worker/tests/use_cases/test_answer_medication_question.py`: span 이름·안전 요약 테스트
- `app/dependencies/chat.py`: core와 app service에 동일 tracer 주입
- `app/services/chat.py`: root trace, HMAC metadata, trace ID 전달
- `app/repositories/chat_repository.py`: 성공·실패 trace ID 저장
- `app/tests/chat_apis/test_chat_service.py`: 성공·실패·재사용 trace 계약
- `app/tests/chat_apis/test_chat_repository.py`: DB 저장 검증
- `app/tests/chat_apis/test_chat_api_integration.py`: API 완료 메시지 trace ID 검증
- `app/main.py`: Qdrant 이후 tracer buffer flush
- `.env.example`: 안전한 기본 설정과 빈 secret

---

### Task 1: LangSmith 설정과 공통 추적기

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `ai_worker/core/config.py`
- Modify: `ai_worker/tests/core/test_core_package.py`
- Create: `ai_worker/observability/__init__.py`
- Create: `ai_worker/observability/chat_tracer.py`
- Create: `ai_worker/tests/observability/__init__.py`
- Create: `ai_worker/tests/observability/test_chat_tracer.py`

**Interfaces:**
- Produces: `ChatTracer.span(...) -> AbstractAsyncContextManager[ChatSpan]`
- Produces: `ChatTracer.anonymize_identifier(value) -> str | None`
- Produces: `ChatTracer.capture_content: bool`
- Produces: `ChatTracer.aclose() -> None`
- Produces: `build_chat_tracer(settings: Config) -> ChatTracer`

- [ ] **Step 1: 설정 계약 실패 테스트 작성**

`test_core_package.py`에 기본 tracing/capture가 꺼져 있고 환경변수를 읽는 테스트를 추가한다.

```python
def test_config_disables_langsmith_content_capture_by_default() -> None:
    settings = Config(_env_file=None)

    assert settings.LANGSMITH_TRACING is False
    assert settings.LANGSMITH_CAPTURE_CONTENT is False
    assert settings.RUN_LANGSMITH_INTEGRATION_TESTS is False


def test_config_reads_langsmith_settings(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "ai-health-test")
    monkeypatch.setenv("LANGSMITH_ENVIRONMENT", "test")
    monkeypatch.setenv("LANGSMITH_CAPTURE_CONTENT", "true")
    monkeypatch.setenv("LANGSMITH_HASH_SALT", "test-observability-salt")

    settings = Config(_env_file=None)

    assert settings.LANGSMITH_TRACING is True
    assert settings.LANGSMITH_API_KEY.get_secret_value() == "test-langsmith-key"
    assert settings.LANGSMITH_PROJECT == "ai-health-test"
    assert settings.LANGSMITH_ENVIRONMENT == "test"
    assert settings.LANGSMITH_CAPTURE_CONTENT is True
```

- [ ] **Step 2: 설정 테스트가 올바르게 실패하는지 실행**

Run:

```bash
uv run --group ai --group dev \
  python -m pytest \
  ai_worker/tests/core/test_core_package.py \
  -q
```

Expected: `Config`에 `LANGSMITH_TRACING`이 없어 FAIL.

- [ ] **Step 3: Config 필드와 직접 의존성 추가**

`Config`에 다음 타입과 기본값을 추가한다.

```python
LANGSMITH_TRACING: bool = False
LANGSMITH_API_KEY: SecretStr | None = None
LANGSMITH_PROJECT: str = "ai-health-medication-chat"
LANGSMITH_ENVIRONMENT: str = "local"
LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
LANGSMITH_WORKSPACE_ID: str | None = None
LANGSMITH_CAPTURE_CONTENT: bool = False
LANGSMITH_HASH_SALT: SecretStr | None = None
LANGSMITH_CLOSE_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)
RUN_LANGSMITH_INTEGRATION_TESTS: bool = False
```

`pyproject.toml`의 공통 dependencies에 설치된 lock 버전과 호환되는
`langsmith>=0.10.18`을 직접 선언하고 `uv lock`으로 lockfile을 갱신한다.

- [ ] **Step 4: Tracer API 실패 테스트 작성**

`test_chat_tracer.py`에 다음 동작을 테스트한다.

```python
async def test_noop_tracer_returns_no_trace_id() -> None:
    tracer = NoOpChatTracer()

    async with tracer.span("chat.answer", root=True) as span:
        span.end({"status": "SAFE"})

    assert span.trace_id is None
    assert tracer.anonymize_identifier(1) is None


def test_anonymize_identifier_is_stable_and_does_not_expose_id() -> None:
    tracer = NoOpChatTracer(hash_salt="test-salt")

    first = tracer.anonymize_identifier(1)
    second = tracer.anonymize_identifier(1)

    assert first == second
    assert first != "1"
    assert len(first) == 16


def test_builder_falls_back_to_noop_without_api_key() -> None:
    settings = Config(
        LANGSMITH_TRACING=True,
        LANGSMITH_API_KEY=None,
        _env_file=None,
    )

    tracer = build_chat_tracer(settings)

    assert isinstance(tracer, NoOpChatTracer)
```

Fake LangSmith Client factory를 주입하여 capture가 꺼졌을 때
`hide_inputs=True`, `hide_outputs=True`로 생성되는 것도 검증한다.

- [ ] **Step 5: Tracer 테스트가 import 오류로 실패하는지 실행**

Run:

```bash
uv run --group ai --group dev \
  python -m pytest \
  ai_worker/tests/observability/test_chat_tracer.py \
  -q
```

Expected: `ai_worker.observability.chat_tracer`가 없어 collection ERROR.

- [ ] **Step 6: 최소 추적기 구현**

다음 공개 계약을 구현한다.

```python
class ChatSpan(Protocol):
    trace_id: str | None

    def end(self, outputs: Mapping[str, Any] | None = None) -> None: ...


class ChatTracer(Protocol):
    capture_content: bool

    def span(
        self,
        name: str,
        *,
        run_type: str = "chain",
        inputs: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        root: bool = False,
    ) -> AbstractAsyncContextManager[ChatSpan]: ...

    def anonymize_identifier(self, value: str | int) -> str | None: ...

    async def aclose(self) -> None: ...
```

구현 구성은 다음으로 고정한다.

- `_IdentifierAnonymizer`: HMAC-SHA-256 앞 16자리 반환
- `NoOpChatTracer`: 네트워크와 trace ID 없음
- `LangSmithChatTracer`: programmatic `Client`와 `tracing_context`, `trace` 사용
- `SafeChatTracer`: delegate의 span 시작·종료·close 오류를 경고로 격리
- `build_chat_tracer`: 설정 검증과 Client 생성

`LangSmithChatTracer`는 root span에만 새 UUID를 주고, child span은 현재
tracing context의 parent를 자동 상속한다. `ChatSpan.end()`는 RunTree에 안전한
요약 output만 추가한다.

- [ ] **Step 7: Tracer·Config 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  ai_worker/core/config.py \
  ai_worker/observability \
  ai_worker/tests/core/test_core_package.py \
  ai_worker/tests/observability

uv run --group ai --group dev \
  python -m pytest \
  ai_worker/tests/core/test_core_package.py \
  ai_worker/tests/observability/test_chat_tracer.py \
  -q
```

Expected: Ruff 0 errors, 모든 대상 테스트 PASS.

---

### Task 2: Root Trace와 성공·실패 Trace ID 저장

**Files:**
- Modify: `app/services/chat.py`
- Modify: `app/repositories/chat_repository.py`
- Modify: `app/tests/chat_apis/test_chat_service.py`
- Modify: `app/tests/chat_apis/test_chat_repository.py`

**Interfaces:**
- Consumes: `ChatTracer`, `ChatSpan`
- Changes: `ChatApplicationService(..., tracer: ChatTracer | None = None)`
- Changes: `ChatRepository.complete_request(..., langsmith_trace_id: str | None = None)`
- Changes: `ChatRepository.fail_request(..., langsmith_trace_id: str | None = None)`

- [ ] **Step 1: Service Trace ID 전달 실패 테스트 작성**

테스트용 `RecordingChatTracer`가 고정 trace ID와 span 이름을 기록하도록 만들고
성공·AI 오류·예상 외 오류·취소에 같은 ID가 Repository 인자로 전달되는지
검증한다.

```python
async def test_send_persists_root_trace_id_on_success() -> None:
    repository = FakeRepository()
    tracer = RecordingChatTracer(trace_id="11111111-1111-4111-8111-111111111111")
    service = ChatApplicationService(
        repository=repository,
        core_service=FakeCore(result=build_result()),
        tracer=tracer,
    )

    await service.send(user=SimpleNamespace(id=1), command=build_command())

    assert repository.completed["langsmith_trace_id"] == tracer.trace_id
    assert tracer.names[0] == "chat.answer"
```

실패 테스트의 기존 expected dict에도 `langsmith_trace_id`를 포함한다.

- [ ] **Step 2: Service 테스트 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev \
  python -m pytest \
  app/tests/chat_apis/test_chat_service.py \
  -q
```

Expected: `ChatApplicationService`가 `tracer`를 받지 않아 FAIL.

- [ ] **Step 3: Repository DB 저장 실패 테스트 작성**

성공과 실패 각각 고정 UUID를 전달하고 저장된 Assistant 메시지의
`langsmith_trace_id`가 같은지 검증한다.

```python
assert completed.langsmith_trace_id == trace_id
assert failed.langsmith_trace_id == trace_id
```

- [ ] **Step 4: Repository 테스트 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev \
  python -m pytest \
  app/tests/chat_apis/test_chat_repository.py \
  -q
```

Expected: Repository 메서드가 `langsmith_trace_id`를 받지 않아 FAIL.

- [ ] **Step 5: Root Trace와 저장 최소 구현**

`ChatApplicationService.send()`를 root span으로 감싸고 기존 코드를 private
`_send_in_trace()`로 이동한다. root inputs는 capture가 켜졌을 때만 질문 원문을,
꺼졌을 때는 문자 수만 전달한다.

```python
inputs = (
    {"question": command.message}
    if self._tracer.capture_content
    else {"question_length": len(command.message)}
)
async with self._tracer.span(
    "chat.answer",
    root=True,
    inputs=inputs,
    metadata={
        "request_key": self._tracer.anonymize_identifier(command.request_id),
        "user_key": self._tracer.anonymize_identifier(user.id),
        "care_episode_present": command.record_id is not None,
        "conversation_present": command.conversation_id is not None,
        "streaming": progress_callback is not None,
    },
) as root_span:
    return await self._send_in_trace(..., trace_id=root_span.trace_id)
```

`complete_request()`와 세 실패 경로에 `trace_id`를 전달한다. Repository는
성공·실패 update에 `langsmith_trace_id`를 포함한다. 완료 메시지 재사용 경로는
기존 DB trace ID를 갱신하지 않고 root span output에 `cache_hit=True`만 기록한다.

- [ ] **Step 6: Service·Repository 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  app/services/chat.py \
  app/repositories/chat_repository.py \
  app/tests/chat_apis/test_chat_service.py \
  app/tests/chat_apis/test_chat_repository.py

uv run --group ai --group app --group dev \
  python -m pytest \
  app/tests/chat_apis/test_chat_service.py \
  app/tests/chat_apis/test_chat_repository.py \
  -q
```

Expected: Ruff 0 errors, 대상 테스트 PASS.

---

### Task 3: Chat Core 단계별 Child Span

**Files:**
- Modify: `ai_worker/use_cases/answer_medication_question.py`
- Modify: `ai_worker/services/medication_chat_core_service.py`
- Modify: `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Modify: `ai_worker/tests/services/test_medication_chat_core_service.py`

**Interfaces:**
- Consumes: `ChatTracer`
- Changes: `AnswerMedicationQuestionUseCase(..., tracer: ChatTracer | None = None)`
- Changes: `MedicationChatCoreService(..., tracer: ChatTracer | None = None)`
- Changes: `build_medication_chat_core_service(..., tracer: ChatTracer | None = None)`
- Produces: `MedicationChatCoreService.tracer -> ChatTracer`

- [ ] **Step 1: Builder tracer 재사용 실패 테스트 작성**

```python
def test_builder_reuses_injected_chat_tracer() -> None:
    tracer = NoOpChatTracer(hash_salt="test")

    service = build_medication_chat_core_service(
        settings=Config(OPENAI_API_KEY="test-key", _env_file=None),
        qdrant_client=object(),
        tracer=tracer,
    )

    assert service.tracer is tracer
```

OpenAI/Qdrant 실제 연결은 생성자 단계에서 호출되지 않는 기존 구조를 유지한다.

- [ ] **Step 2: UseCase span 이름 실패 테스트 작성**

기존 fake 의존성을 사용해 성공 경로를 실행하고 다음 이름이 순서대로 포함되는지
검증한다.

```python
assert tracer.names == [
    "patient_context.load",
    "query.plan",
    "interaction_rules.search",
    "rag.retrieve",
    "medication_guide.lookup",
    "answer.draft",
    "llm.generate",
    "safety.validate",
]
```

Span output에는 원문 대신 개수·route·score·safety status만 들어가는지 검증한다.

- [ ] **Step 3: Core 테스트 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/services/test_medication_chat_core_service.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py \
  -q
```

Expected: tracer 인자와 child span이 없어 FAIL.

- [ ] **Step 4: Builder·UseCase에 tracer 주입**

builder는 주입된 tracer를 우선하고 없으면 `build_chat_tracer(settings)`를 한 번
호출한다. 동일 인스턴스를 Core Service와 UseCase가 사용한다.

UseCase의 기존 진행상태 callback 순서는 변경하지 않고 각 작업만 span으로
감싼다. 각 span은 다음 안전 output을 기록한다.

```python
context_span.end({
    "medication_count": len(context.medications),
    "supplement_count": len(context.supplements),
    "context_hash": self._context_hash(context),
})
rag_span.end({
    "accepted_count": len(chunks),
    "rag_unavailable": rag_unavailable,
    "max_score": max(
        (chunk.similarity_score for chunk in chunks),
        default=None,
    ),
})
safety_span.end({
    "status": validated.safety_status.value,
    "reason_codes": validated.safety_reason_codes,
})
```

질문, 환자명, 약명·영양제명, 청크 본문은 metadata/output에 넣지 않는다.
기존 LLM generate 호출은 `llm.generate` span 안에 두어 자동 LangChain 실행이
자식으로 연결되게 한다.

- [ ] **Step 5: Core 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  ai_worker/use_cases/answer_medication_question.py \
  ai_worker/services/medication_chat_core_service.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py \
  ai_worker/tests/services/test_medication_chat_core_service.py

uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/services/test_medication_chat_core_service.py \
  ai_worker/tests/use_cases/test_answer_medication_question.py \
  -q
```

Expected: Ruff 0 errors, 대상 테스트 PASS.

---

### Task 4: FastAPI 생명주기와 실제 API 저장 연결

**Files:**
- Modify: `app/dependencies/chat.py`
- Modify: `app/main.py`
- Modify: `app/tests/chat_apis/test_chat_api_integration.py`

**Interfaces:**
- Consumes: `MedicationChatCoreService.tracer`
- Changes: app state `chat_tracer`
- Consumes: `ChatTracer.aclose()`

- [ ] **Step 1: API 통합 실패 테스트 작성**

고정 trace ID를 내는 tracer로 `ChatApplicationService`를 구성하고 POST 완료 후
Assistant 메시지에 값이 저장되었는지 확인한다. JSON과 SSE 경로를 각각 검증한다.

```python
assistant = await ChatMessage.get(
    chat_session_id=body["conversationId"],
    role=ChatMessageRole.ASSISTANT,
)
assert assistant.langsmith_trace_id == "11111111-1111-4111-8111-111111111111"
```

- [ ] **Step 2: API 통합 테스트 실패 확인**

Run:

```bash
uv run --group ai --group app --group dev \
  python -m pytest \
  app/tests/chat_apis/test_chat_api_integration.py \
  -q
```

Expected: 현재 Service/Repository가 trace ID를 저장하지 않아 FAIL.

- [ ] **Step 3: 동일 tracer 의존성 조립과 종료 구현**

`get_chat_application_service()`에서 Core builder가 가진 tracer를 application
service에 주입하고 `request.app.state.chat_tracer`에도 저장한다.

```python
service = ChatApplicationService(
    repository=ChatRepository(),
    core_service=core_service,
    tracer=core_service.tracer,
)
request.app.state.chat_tracer = core_service.tracer
```

FastAPI lifespan 종료 시 Qdrant를 먼저 닫고 tracer를 닫는다. tracer close 오류는
`SafeChatTracer` 내부에서 격리한다.

```python
chat_tracer = getattr(app.state, "chat_tracer", None)
if chat_tracer is not None:
    await chat_tracer.aclose()
```

- [ ] **Step 4: API 통합 테스트 통과 확인**

Run:

```bash
uv run --group dev ruff check \
  app/dependencies/chat.py \
  app/main.py \
  app/tests/chat_apis/test_chat_api_integration.py

uv run --group ai --group app --group dev \
  python -m pytest \
  app/tests/chat_apis/test_chat_api_integration.py \
  -q
```

Expected: Ruff 0 errors, JSON·SSE 통합 테스트 PASS.

---

### Task 5: 환경 예시, 운영 문서, opt-in 실연동 테스트

**Files:**
- Modify: `.env.example`
- Create: `docs/langsmith-chat-observability.md`
- Create: `ai_worker/tests/integration/test_langsmith_observability_integration.py`

**Interfaces:**
- Consumes: `build_chat_tracer`, `Config`
- Produces: `RUN_LANGSMITH_INTEGRATION_TESTS=1` opt-in 검증 명령

- [ ] **Step 1: `.env.example`에 안전한 기본값 추가**

비밀값은 비워 두고 다음 설정을 추가한다.

```env
# LangSmith observability (synthetic/demo data only for content capture)
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ai-health-medication-chat
LANGSMITH_ENVIRONMENT=local
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=
LANGSMITH_CAPTURE_CONTENT=false
LANGSMITH_HASH_SALT=
LANGSMITH_CLOSE_TIMEOUT_SECONDS=2
RUN_LANGSMITH_INTEGRATION_TESTS=false
```

- [ ] **Step 2: 팀원 사용 문서 작성**

문서는 다음 내용을 구체적으로 포함한다.

- 현재 LangChain 사용 위치와 LangSmith가 추가하는 역할
- 로컬 연결 순서와 project 생성
- 기본 마스킹 상태 확인법
- 가상 데이터에서만 원문 capture를 켜는 절차
- Trace 단계별 의미와 검색/LLM/안전성 문제 구분법
- 대표 질문 baseline과 변경 후 비교 절차
- API Key, trace 화면, 사용자 데이터의 Git·PR·스크린샷 금지
- 실제 사용자 환경에서는 content capture 금지

- [ ] **Step 3: opt-in 통합 테스트 작성**

```python
@pytest.mark.skipif(
    not Config().RUN_LANGSMITH_INTEGRATION_TESTS,
    reason="LangSmith integration tests are disabled",
)
async def test_langsmith_accepts_synthetic_chat_trace() -> None:
    settings = Config()
    tracer = build_chat_tracer(settings)

    async with tracer.span(
        "chat.observability.integration",
        root=True,
        inputs={"question": "가상 데이터 기반 테스트 질문"},
        metadata={"synthetic": True},
    ) as span:
        span.end({"status": "SAFE"})

    trace_id = span.trace_id
    await tracer.aclose()

    assert trace_id is not None

    client = Client(
        api_url=settings.LANGSMITH_ENDPOINT,
        api_key=settings.LANGSMITH_API_KEY.get_secret_value(),
        workspace_id=settings.LANGSMITH_WORKSPACE_ID,
    )
    saved_run = await asyncio.to_thread(client.read_run, trace_id)
    client.close(timeout=settings.LANGSMITH_CLOSE_TIMEOUT_SECONDS)

    assert str(saved_run.trace_id) == trace_id
    assert saved_run.name == "chat.observability.integration"
```

실연동 테스트는 API Key가 없으면 명확히 skip하고 CI에서 기본적으로 실행하지
않는다. 로컬 수동 실행 후 LangSmith UI에서 project와 trace를 확인한다.

- [ ] **Step 4: 문서·통합 테스트 정적 검증**

Run:

```bash
uv run --group dev ruff check \
  ai_worker/tests/integration/test_langsmith_observability_integration.py

RUN_LANGSMITH_INTEGRATION_TESTS=0 \
  uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/integration/test_langsmith_observability_integration.py \
  -q
```

Expected: Ruff 0 errors, 실제 네트워크 호출 없이 1 skipped.

---

### Task 6: 전체 회귀·품질 검증

**Files:**
- Verify only: all files changed by Tasks 1–5

**Interfaces:**
- Verifies: 기존 Chat JSON/SSE, RAG, LLM, Repository 계약 유지

- [ ] **Step 1: 전체 Ruff 검사**

Run:

```bash
uv run --group dev ruff check ai_worker app
```

Expected: `All checks passed!`

- [ ] **Step 2: AI Worker와 Chat API 전체 테스트**

Run:

```bash
RUN_OPENAI_INTEGRATION_TESTS=0 \
RUN_LANGSMITH_INTEGRATION_TESTS=0 \
  uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests \
  app/tests/chat_apis \
  -q
```

Expected: 0 failed, OpenAI/LangSmith 실제 연동 테스트만 skip.

- [ ] **Step 3: 전체 app 회귀 테스트**

Run:

```bash
RUN_OPENAI_INTEGRATION_TESTS=0 \
RUN_LANGSMITH_INTEGRATION_TESTS=0 \
  uv run --group ai --group app --group dev \
  python -m pytest app/tests -q
```

Expected: 0 failed.

- [ ] **Step 4: 변경 품질과 작업 트리 확인**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected:

- whitespace 오류 없음
- 기존 로컬 생성물은 staging되지 않음
- 프롬프트·PDF 전처리 파일에 LangSmith 추가 변경 없음
- migration 파일 생성 없음

- [ ] **Step 5: 실제 LangSmith 연결은 사용자 Key로 별도 검증**

로컬 `.env`에 다음을 설정한 뒤 opt-in 테스트를 한 번 실행한다.

```bash
RUN_LANGSMITH_INTEGRATION_TESTS=1 \
  uv run --group ai --group app --group dev \
  python -m pytest \
  ai_worker/tests/integration/test_langsmith_observability_integration.py \
  -q
```

Expected: 1 passed, LangSmith UI의 `ai-health-medication-chat` project에
`chat.observability.integration` root trace가 표시됨.

API Key가 제공되지 않은 구현 세션에서는 이 단계만 미실행으로 명시하고,
나머지 단위·통합·회귀 검증 결과와 분리해 보고한다.
