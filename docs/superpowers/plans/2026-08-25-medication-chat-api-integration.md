# Medication Chat API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일반 의약품·영양제 질문과 사용자 확정 복약정보 기반 질문을 처리하고 저장하는 `POST /api/v1/chat`을 구현해 프론트와 ReDoc에 연결한다.

**Architecture:** FastAPI의 `ChatApplicationService`가 인증·세션·메시지 트랜잭션을 담당하고, `MedicationChatCoreService`가 RDBMS 컨텍스트·승인 상호작용 규칙·Qdrant 근거·OpenAI 답변·안전성 검사를 조립한다. 외부 호출은 DB 트랜잭션 밖에서 실행하고 Core는 Protocol 기반 Adapter로 테스트한다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Tortoise ORM, MySQL 8, Qdrant, OpenAI API, React 19, TypeScript, pytest, Ruff, Playwright

**Spec:** `docs/superpowers/specs/2026-08-25-medication-chat-api-integration-design.md`

## Global Constraints

- 일반 의약품·영양제 질문은 `recordId=null`로 처리한다.
- `recordId`가 있으면 인증 사용자 소유이며 확인 완료된 `CareEpisode`여야 한다.
- 사용자 확정 복약정보, RDBMS 제품 가이드, Qdrant 근거 순서를 지킨다.
- `InteractionRule.review_status=APPROVED`인 규칙만 런타임에 사용한다.
- 규칙이나 검색 근거가 없다는 사실을 안전하다는 결론으로 표현하지 않는다.
- 진단·처방·복용 시작·중단·용량 변경을 지시하지 않는다.
- OpenAI·Qdrant 호출 동안 MySQL 트랜잭션과 row lock을 유지하지 않는다.
- Worker는 변경하지 않고 FastAPI가 채팅을 직접 처리한다.
- SSE는 구현하지 않고 JSON 응답을 유지한다.
- `.DS_Store`와 `.superpowers/`의 기존 사용자 변경을 수정하거나 stage하지 않는다.
- 사용자가 별도로 요청하기 전에는 commit 또는 push하지 않는다.

---

### Task 1: 약·영양제 Chat Core 계약

**Files:**
- Create: `ai_worker/schemas/medication_chat.py`
- Modify: `ai_worker/domain/interfaces.py`
- Create: `ai_worker/tests/schemas/test_medication_chat_schema.py`

**Interfaces:**
- Produces: `MedicationChatRequest`, `ActiveMedication`, `ActiveSupplement`, `ActiveIntakeContext`, `MedicationGuideFact`, `InteractionRuleFact`, `MedicationChatSource`, `MedicationChatResult`
- Produces: `ActiveIntakeContextProvider`, `MedicationGuideRepository`, `InteractionRuleRepository`, `MedicationKnowledgeRetriever`, `MedicationAnswerGenerator`, `GroundedClaimValidator` Protocol

- [ ] **Step 1: 실패하는 스키마 테스트 작성**

```python
def test_general_drug_question_accepts_missing_care_episode() -> None:
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        care_episode_id=None,
        question="타이레놀은 어떤 약인가요?",
    )
    assert request.care_episode_id is None


def test_medication_chat_request_rejects_blank_question() -> None:
    with pytest.raises(ValidationError):
        MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="  ",
        )
```

- [ ] **Step 2: 신규 모듈 부재로 실패 확인**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/schemas/test_medication_chat_schema.py -q`

Expected: `ModuleNotFoundError: ai_worker.schemas.medication_chat`

- [ ] **Step 3: 요청·컨텍스트·근거·결과 모델 구현**

```python
class MedicationChatRequest(BaseModel):
    request_id: UUID
    user_id: int = Field(ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)


class ActiveIntakeContext(BaseModel):
    user_id: int
    preferred_care_episode_id: int | None = None
    medications: list[ActiveMedication] = Field(default_factory=list)
    supplements: list[ActiveSupplement] = Field(default_factory=list)


class MedicationChatResult(BaseModel):
    answer: str
    route: str
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)
    sources: list[MedicationChatSource] = Field(default_factory=list)
    model_name: str | None = None
    prompt_version: str
    schema_version: str
    context_hash: str | None = None
```

- [ ] **Step 4: Protocol을 정확한 async signature로 추가**

```python
class ActiveIntakeContextProvider(Protocol):
    async def get_active_context(
        self, *, user_id: int, care_episode_id: int | None
    ) -> ActiveIntakeContext:
        pass


class InteractionRuleRepository(Protocol):
    async def find_approved_rules(
        self, *, context: ActiveIntakeContext
    ) -> list[InteractionRuleFact]:
        pass
```

- [ ] **Step 5: 대상 테스트와 정적 검사 통과**

Run: `uv run --group dev ruff check ai_worker/schemas/medication_chat.py ai_worker/domain/interfaces.py ai_worker/tests/schemas/test_medication_chat_schema.py`

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/schemas/test_medication_chat_schema.py -q`

Expected: all pass.

---

### Task 2: 현재 복용정보와 승인 규칙 RDBMS Adapter

**Files:**
- Create: `ai_worker/providers/db_active_intake_context_provider.py`
- Create: `ai_worker/repositories/medication_product_guide_repository.py`
- Create: `ai_worker/repositories/interaction_rule_repository.py`
- Create: `ai_worker/tests/providers/test_db_active_intake_context_provider.py`
- Create: `ai_worker/tests/repositories/test_medication_product_guide_repository.py`
- Create: `ai_worker/tests/repositories/test_interaction_rule_repository.py`

**Interfaces:**
- Consumes: Task 1의 `ActiveIntakeContextProvider`, `MedicationGuideRepository`, `InteractionRuleRepository`
- Produces: `DbActiveIntakeContextProvider`, `DbMedicationProductGuideRepository`, `DbInteractionRuleRepository`

- [ ] **Step 1: Provider 실패 테스트 작성**

```python
async def test_provider_returns_only_current_user_active_intakes(initialized_db) -> None:
    context = await DbActiveIntakeContextProvider().get_active_context(
        user_id=1,
        care_episode_id=None,
    )
    assert [item.name for item in context.medications] == ["아스피린"]
    assert [item.name for item in context.supplements] == ["오메가3"]


async def test_provider_rejects_unowned_episode(initialized_db) -> None:
    with pytest.raises(PatientContextNotFoundError):
        await DbActiveIntakeContextProvider().get_active_context(
            user_id=1,
            care_episode_id=999,
        )
```

- [ ] **Step 2: Repository 실패 테스트 작성**

```python
async def test_interaction_repository_returns_only_approved_rules(initialized_db) -> None:
    rules = await DbInteractionRuleRepository().find_approved_rules(
        context=build_active_context(),
    )
    assert [rule.review_status for rule in rules] == ["APPROVED"]


async def test_product_guide_repository_does_not_guess_ambiguous_name(initialized_db) -> None:
    result = await DbMedicationProductGuideRepository().find_by_name("타이레놀")
    assert result.is_ambiguous is True
    assert result.guide is None
```

- [ ] **Step 3: 신규 Adapter 부재 실패 확인**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/repositories/test_medication_product_guide_repository.py ai_worker/tests/repositories/test_interaction_rule_repository.py -q`

- [ ] **Step 4: 현재 복용정보 조회 구현**

`DbActiveIntakeContextProvider`는 사용자 소유·확정 episode를 검증하고 다음 조건을 적용한다.

```python
is_current = (
    episode.status == CareEpisodeStatus.ACTIVE
    and (
        medication.prescribed_at is None
        or medication.days is None
        or medication.prescribed_at + timedelta(days=medication.days) >= today
    )
)
```

영양제는 `UserSupplementNutrient.status == SupplementStatus.ACTIVE`만 조회하며 `supplement_nutrient`를 prefetch한다.

- [ ] **Step 5: 제품 가이드와 승인 규칙 조회 구현**

제품 가이드는 정규화한 제품명의 exact match를 먼저 사용한다. exact match가 여러 건이거나 부분 검색 결과가 여러 건이면 `is_ambiguous=True`를 반환한다. 상호작용 규칙은 context에 매핑된 entity ID 조합과 `APPROVED` 조건을 DB 쿼리에 포함하고 source/evidence 관계를 prefetch한다.

- [ ] **Step 6: 대상 테스트와 정적 검사 통과**

Run: `uv run --group dev ruff check ai_worker/providers ai_worker/repositories ai_worker/tests/providers ai_worker/tests/repositories`

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/providers/test_db_active_intake_context_provider.py ai_worker/tests/repositories/test_medication_product_guide_repository.py ai_worker/tests/repositories/test_interaction_rule_repository.py -q`

Expected: all pass.

---

### Task 3: 약·영양제 Core 실행 흐름과 Qdrant 대체 정책

**Files:**
- Create: `ai_worker/rag/retrievers/medication_knowledge_retriever.py`
- Create: `ai_worker/llm/assemblers/medication_answer_assembler.py`
- Create: `ai_worker/llm/prompts/medication_chat_prompt.py`
- Create: `ai_worker/llm/generators/medication_answer_generator.py`
- Create: `ai_worker/safety/grounded_claim_validator.py`
- Create: `ai_worker/use_cases/answer_medication_question.py`
- Create: `ai_worker/services/medication_chat_core_service.py`
- Modify: `ai_worker/core/config.py`
- Create: `ai_worker/tests/use_cases/test_answer_medication_question.py`
- Create: `ai_worker/tests/services/test_medication_chat_core_service.py`

**Interfaces:**
- Consumes: Task 1 계약과 Task 2 Adapter
- Produces: `AnswerMedicationQuestionUseCase.execute(request) -> MedicationChatResult`
- Produces: `MedicationChatCoreService.answer(request) -> MedicationChatResult`
- Produces: `build_medication_chat_core_service(settings, qdrant_client)`

- [ ] **Step 1: 일반 의약품·영양제와 확정정보 우선순위 실패 테스트 작성**

```python
async def test_general_drug_question_runs_without_episode() -> None:
    result = await build_use_case().execute(build_request(care_episode_id=None))
    assert result.route == "MEDICATION_GUIDE"


async def test_confirmed_medication_precedes_general_guide_and_rag() -> None:
    result = await build_use_case().execute(build_record_based_request())
    assert result.answer.index("사용자 확정 복약정보") < result.answer.index("일반 제품 안내")
    assert result.answer.index("일반 제품 안내") < result.answer.index("공공자료 추가 설명")
```

- [ ] **Step 2: 상호작용과 안전 대체 실패 테스트 작성**

```python
async def test_no_interaction_evidence_never_claims_safe() -> None:
    result = await build_use_case(rules=[], chunks=[]).execute(build_interaction_request())
    assert "안전" not in result.answer
    assert "확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다" in result.answer


async def test_qdrant_failure_falls_back_to_rdbms_facts() -> None:
    result = await build_use_case(retriever=FailingRetriever()).execute(build_record_based_request())
    assert "사용자 확정 복약정보" in result.answer
    assert result.safety_status == SafetyStatus.RESTRICTED
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/services/test_medication_chat_core_service.py -q`

- [ ] **Step 4: Query Adapter와 결정론적 Assembler 구현**

`MedicationKnowledgeRetriever`는 `KnowledgeSearchQuery`를 직접 만들어 현재 컬렉션을 재사용한다. `MedicationAnswerAssembler`는 섹션 순서를 고정한다.

```python
SECTION_ORDER = (
    "사용자 확정 복약정보",
    "확인된 상호작용",
    "일반 제품 안내",
    "공공자료 추가 설명",
)
```

각 source는 patient/medication guide/interaction rule/public chunk 식별자를 유지한다.

- [ ] **Step 5: UseCase와 안전성 처리 구현**

명확한 약·영양제·상호작용 키워드는 규칙 기반으로 route를 선택하고 모호한 경우에만 기존 OpenAI 분류기를 호출한다. Qdrant 오류는 잡아 빈 chunk로 처리하되 `RAG_UNAVAILABLE` reason code를 남긴다. 생성 결과가 근거에 없는 제품명·복용량·위험도를 추가하거나 금지 표현을 포함하면 안전 안내로 교체한다.

- [ ] **Step 6: 재사용 가능한 Service Builder 구현**

```python
class MedicationChatCoreService:
    async def answer(self, request: MedicationChatRequest) -> MedicationChatResult:
        return await self._use_case.execute(request)


def build_medication_chat_core_service(
    *, settings: Config, qdrant_client: AsyncQdrantClient
) -> MedicationChatCoreService:
    use_case = AnswerMedicationQuestionUseCase(
        context_provider=DbActiveIntakeContextProvider(),
        guide_repository=DbMedicationProductGuideRepository(),
        interaction_rule_repository=DbInteractionRuleRepository(),
        knowledge_retriever=build_medication_knowledge_retriever(
            settings=settings,
            qdrant_client=qdrant_client,
        ),
        answer_generator=OpenAIMedicationAnswerGenerator.from_settings(settings),
        grounded_claim_validator=RuleBasedGroundedClaimValidator(),
    )
    return MedicationChatCoreService(use_case=use_case)
```

Builder는 client를 생성하지 않고 주입받아 프로세스 생명주기와 분리한다.

- [ ] **Step 7: 대상 테스트와 기존 AI 회귀 테스트 통과**

Run: `uv run --group dev ruff check ai_worker`

Run: `uv run --group ai --group app --group dev python -m pytest ai_worker/tests/use_cases/test_answer_medication_question.py ai_worker/tests/services/test_medication_chat_core_service.py ai_worker/tests/services/test_chat_core_service.py -q`

Expected: all pass.

---

### Task 4: CHAT Repository와 두 단계 저장 트랜잭션

**Files:**
- Create: `app/repositories/chat_repository.py`
- Create: `app/tests/chat_apis/test_chat_repository.py`
- Modify: `app/repositories/__init__.py`

**Interfaces:**
- Produces: `AcceptedChatRequest(session, user_message, assistant_message, history)`
- Produces: `ChatRepository.accept_request(*, user_id, care_episode_id, conversation_id, request_id, content) -> AcceptedChatRequest`
- Produces: `ChatRepository.complete_request(*, assistant_message_id, result, duration_ms) -> ChatMessage`
- Produces: `ChatRepository.fail_request(*, assistant_message_id, error_code, duration_ms) -> None`
- Produces: `ChatRepository.get_completed_result_by_request_id(*, chat_session_id, request_id) -> SendChatResult | None`

- [ ] **Step 1: 요청 수락 트랜잭션 실패 테스트 작성**

```python
async def test_accept_request_creates_ordered_user_and_pending_assistant_messages() -> None:
    accepted = await ChatRepository().accept_request(
        user_id=1,
        care_episode_id=None,
        conversation_id=None,
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        content="마그네슘은 어떤 영양제인가요?",
    )
    assert accepted.user_message.sequence_no == 1
    assert accepted.assistant_message.sequence_no == 2
    assert accepted.assistant_message.status == ChatMessageStatus.PENDING
```

- [ ] **Step 2: 결과 확정·실패·history 실패 테스트 작성**

```python
async def test_complete_request_saves_sources_in_citation_order() -> None:
    await repository.complete_request(assistant_message_id=2, result=build_core_result())
    sources = await ChatMessageSource.filter(chat_message_id=2).order_by("citation_order")
    assert [source.citation_order for source in sources] == [1, 2]


async def test_fail_request_never_leaves_pending_message() -> None:
    await repository.fail_request(assistant_message_id=2, error_code="CHAT_UPSTREAM_UNAVAILABLE", duration_ms=1200)
    message = await ChatMessage.get(id=2)
    assert message.status == ChatMessageStatus.FAILED
```

- [ ] **Step 3: 신규 Repository 부재 실패 확인**

Run: `uv run --group app --group ai --group dev python -m pytest app/tests/chat_apis/test_chat_repository.py -q`

- [ ] **Step 4: 세션 잠금과 sequence 할당 구현**

```python
async with in_transaction() as connection:
    session = await self._get_or_create_owned_session(
        user_id=user_id,
        care_episode_id=care_episode_id,
        conversation_id=conversation_id,
        connection=connection,
    )
    locked = await ChatSession.filter(id=session.id).using_db(connection).select_for_update().get()
    last_sequence = await ChatMessage.filter(chat_session=locked).using_db(connection).max("sequence_no") or 0
    user_message = await ChatMessage.create(
        chat_session=locked,
        sequence_no=last_sequence + 1,
        role=ChatMessageRole.USER,
        content=content,
        status=ChatMessageStatus.COMPLETED,
        safety_status=ChatSafetyStatus.SAFE,
        using_db=connection,
    )
    assistant_message = await ChatMessage.create(
        chat_session=locked,
        reply_to_message=user_message,
        request_id=request_id,
        sequence_no=last_sequence + 2,
        role=ChatMessageRole.ASSISTANT,
        content="",
        status=ChatMessageStatus.PENDING,
        safety_status=ChatSafetyStatus.PENDING,
        using_db=connection,
    )
```

기존 세션에서 같은 request ID가 완료됐으면 저장 응답을 재구성한다.
PENDING이면 `ChatRequestInProgressError`를 발생시킨다. 최근 완료 메시지는
최신 10개를 가져온 뒤 오름차순으로 뒤집는다.

- [ ] **Step 5: 결과와 출처 저장 구현**

`complete_request`는 AI 메시지 필드와 `ChatMessageSource` 전체를 한 트랜잭션으로 저장한다. `fail_request`는 별도 트랜잭션에서 `FAILED`, `error_code`, `duration_ms`, `completed_at`을 확정한다.

- [ ] **Step 6: MySQL Repository 테스트 통과**

Run: `uv run --group app --group ai --group dev python -m pytest app/tests/chat_apis/test_chat_repository.py -q`

Expected: all pass including ownership, idempotency, history and concurrent sequence cases.

---

### Task 5: Chat Application Service와 오류 계약

**Files:**
- Create: `app/services/chat.py`
- Modify: `app/core/exceptions.py`
- Create: `app/tests/chat_apis/test_chat_service.py`
- Modify: `app/services/__init__.py`

**Interfaces:**
- Consumes: Task 3 `MedicationChatCoreService`, Task 4 `ChatRepository`
- Produces: `ChatApplicationService.send(user, command) -> SendChatResult`
- Produces: `ChatSessionNotFoundError`, `CareEpisodeNotFoundError`, `ChatContextMismatchError`, `ChatRequestInProgressError`, `ChatUpstreamUnavailableError`, `ChatProcessingFailedError`

- [ ] **Step 1: Service 성공과 최근 history 전달 실패 테스트 작성**

```python
async def test_send_passes_server_loaded_history_to_core() -> None:
    result = await service.send(user=user, command=build_command())
    assert fake_core.requests[0].history == expected_last_ten_messages
    assert result.answer == "근거 기반 답변"
```

- [ ] **Step 2: Core 실패 상태 확정 테스트 작성**

```python
async def test_send_marks_assistant_failed_before_raising_503() -> None:
    with pytest.raises(ChatUpstreamUnavailableError):
        await failing_service.send(user=user, command=build_command())
    assert repository.failed_error_code == "CHAT_UPSTREAM_UNAVAILABLE"
```

- [ ] **Step 3: Service와 오류 구현**

Service는 monotonic clock으로 전체 duration을 측정한다. Repository의 트랜잭션 1을 완료한 뒤 Core를 호출하고, 성공하면 트랜잭션 2로 완료한다. AI configuration/timeout/rate-limit 오류는 503, 예상하지 못한 오류는 500으로 변환하기 전에 `fail_request`를 반드시 호출한다.

- [ ] **Step 4: 대상 테스트 통과**

Run: `uv run --group dev ruff check app/services/chat.py app/core/exceptions.py app/tests/chat_apis/test_chat_service.py`

Run: `uv run --group app --group ai --group dev python -m pytest app/tests/chat_apis/test_chat_service.py -q`

Expected: all pass.

---

### Task 6: FastAPI Router, 의존성 생명주기와 ReDoc

**Files:**
- Create: `app/dtos/chat.py`
- Create: `app/dependencies/chat.py`
- Create: `app/apis/v1/chat_router.py`
- Modify: `app/apis/v1/__init__.py`
- Modify: `app/main.py`
- Create: `app/tests/chat_apis/__init__.py`
- Create: `app/tests/chat_apis/test_chat_api.py`
- Create: `app/tests/chat_apis/test_chat_openapi_docs.py`

**Interfaces:**
- Produces: `SendChatRequest`, `ChatSourceResponse`, `SendChatResponse`
- Produces: `get_chat_application_service(request: Request)`
- Produces: `POST /api/v1/chat`

- [ ] **Step 1: API DTO와 인증 실패 테스트 작성**

```python
async def test_post_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json=valid_payload())
    assert response.status_code == 401


async def test_post_chat_accepts_general_drug_question_without_record(client, auth_headers) -> None:
    response = await client.post(
        "/api/v1/chat",
        headers=auth_headers,
        json={
            "requestId": "6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            "recordId": None,
            "conversationId": None,
            "message": "타이레놀은 어떤 약인가요?",
        },
    )
    assert response.status_code == 200
```

- [ ] **Step 2: OpenAPI 실패 테스트 작성**

```python
def test_chat_openapi_contains_redoc_contract() -> None:
    operation = app.openapi()["paths"]["/api/v1/chat"]["post"]
    assert operation["summary"] == "약·영양제 챗봇 답변 생성"
    assert "일반 의약품" in operation["description"]
    assert {"200", "401", "404", "409", "422", "503"} <= set(operation["responses"])
```

- [ ] **Step 3: camelCase DTO 구현**

```python
class SendChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: UUID = Field(alias="requestId")
    record_id: int | None = Field(default=None, alias="recordId", ge=1)
    conversation_id: int | None = Field(default=None, alias="conversationId", ge=1)
    message: str = Field(min_length=1, max_length=2000)
```

- [ ] **Step 4: lifespan과 Dependency 구현**

FastAPI lifespan에서 `AsyncQdrantClient`와 `MedicationChatCoreService`를 한 번 생성해 `app.state`에 넣고 종료 시 client를 닫는다. 테스트는 `app.dependency_overrides[get_chat_application_service]`로 가짜 Service를 주입한다.

- [ ] **Step 5: Router와 ReDoc metadata 구현**

Router prefix는 `/chat`, tags는 `chat`으로 하고 `v1_routers`에 include한다. endpoint는 JWT `User`를 Service에 전달하며 request/response 예시와 401·404·409·422·503 모델을 decorator의 `responses`에 등록한다.

- [ ] **Step 6: API와 OpenAPI 통합 테스트 통과**

Run: `uv run --group app --group ai --group dev python -m pytest app/tests/chat_apis/test_chat_api.py app/tests/chat_apis/test_chat_openapi_docs.py -q`

Expected: all pass; `/api/openapi.json`에 `/api/v1/chat`이 존재한다.

---

### Task 7: 프론트 API 경로와 request ID

**Files:**
- Modify: `frontend/src/entities/chat/types.ts`
- Modify: `frontend/src/entities/chat/api.ts`
- Modify: `frontend/src/entities/chat/api.mock.ts`
- Modify: `frontend/src/pages/chat/ChatPage.tsx`
- Create: `frontend/tests/e2e/chat-api-contract.spec.ts`

**Interfaces:**
- Consumes: Task 6의 camelCase JSON 계약
- Produces: `sendChat(payload)`가 `/api/v1/chat`으로 요청

- [ ] **Step 1: Playwright 계약 테스트 작성**

```typescript
test('chat sends the v1 contract with a request id', async ({ page }) => {
  const request = page.waitForRequest(
    req => req.url().endsWith('/api/v1/chat') && req.method() === 'POST',
  );
  await page.goto('/chat');
  await page.getByRole('textbox').fill('타이레놀은 어떤 약인가요?');
  await page.getByRole('button', { name: '전송' }).click();
  const payload = (await request).postDataJSON();
  expect(payload.requestId).toMatch(/^[0-9a-f-]{36}$/);
  expect(payload.recordId).toBeNull();
});
```

- [ ] **Step 2: 타입과 API 구현**

`SendChatPayload`에 `requestId: string`을 추가하고 `sendChat`은 `http.post('/v1/chat', payload)`를 호출한다. 화면은 질문 제출 시 `crypto.randomUUID()`를 한 번 만들며 같은 사용자 재시도에는 같은 payload를 재사용한다.

- [ ] **Step 3: mock 응답 호환과 정적 검증**

Run: `npm run typecheck`

Run: `npm run build`

Workdir: `frontend`

Expected: both pass.

---

### Task 8: FastAPI 컨테이너의 Chat Runtime 의존성

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `app/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.github/workflows/checks.yml`
- Create: `app/tests/test_chat_runtime_packaging.py`

**Interfaces:**
- Produces: `chat-api` dependency group containing `qdrant-client`, `langchain-openai`, `tiktoken`, `pyyaml`
- Produces: FastAPI image에서 `app`과 `ai_worker` import 가능

- [ ] **Step 1: 현재 CI workflow 경로 확인**

Run: `rg --files .github | sort`

현재 실제 workflow 파일만 수정 대상으로 확정한다. 존재하지 않는 `.github/workflows/ci.yml`을 새로 만들지 않는다.

- [ ] **Step 2: Packaging 실패 테스트 작성**

```python
def test_fastapi_dockerfile_installs_chat_runtime_and_copies_ai_worker() -> None:
    dockerfile = Path("app/Dockerfile").read_text()
    assert "--group chat-api" in dockerfile
    assert "COPY ./ai_worker ./ai_worker" in dockerfile
```

- [ ] **Step 3: 최소 dependency group과 이미지 수정**

`chat-api`에는 FastAPI 채팅 실행에 필요한 네 패키지만 넣고 torch, torchvision, sentence-transformers는 포함하지 않는다. Dockerfile은 `uv sync --group app --group chat-api --no-dev --frozen`을 실행하고 `ai_worker`를 복사한다. 개발 compose의 FastAPI volumes에는 `./ai_worker:/app/ai_worker`를 추가한다.

- [ ] **Step 4: lockfile과 CI 수정**

Run: `uv lock`

App 테스트 job이 `--group app --group chat-api --group dev`를 설치하도록 바꾼다. 기존 AI job은 유지한다.

- [ ] **Step 5: 패키징과 compose 검증**

Run: `uv run --group app --group chat-api --group dev python -m pytest app/tests/test_chat_runtime_packaging.py -q`

Run: `docker compose config --quiet`

Expected: both pass.

---

### Task 9: 전체 통합 검증과 결과 기록

**Files:**
- Create: `app/tests/chat_apis/test_chat_mysql_integration.py`
- Create: `docs/testing/medication-chat-api-verification.md`

**Interfaces:**
- Consumes: Tasks 1~8 전체
- Produces: MySQL 저장 흐름과 ReDoc 계약의 검증 증빙

- [ ] **Step 1: MySQL 통합 테스트 작성**

가짜 Core를 주입하고 실제 Tortoise MySQL test database에 다음을 검증한다.

```python
async def test_chat_api_persists_success_and_sources_in_mysql(client, auth_headers) -> None:
    response = await client.post("/api/v1/chat", headers=auth_headers, json=valid_payload())
    assistant = await ChatMessage.get(id=response.json()["messageId"])
    assert assistant.status == ChatMessageStatus.COMPLETED
    assert await ChatMessageSource.filter(chat_message=assistant).count() == 2


async def test_chat_api_persists_failed_state_when_core_fails(client, auth_headers) -> None:
    response = await client.post("/api/v1/chat", headers=auth_headers, json=valid_payload())
    assert response.status_code == 503
    assert await ChatMessage.filter(status=ChatMessageStatus.FAILED).count() == 1
```

- [ ] **Step 2: 전체 Python 정적 검사와 테스트**

Run: `uv run --group dev ruff check app ai_worker tests`

Run: `RUN_OPENAI_INTEGRATION_TESTS=0 uv run --group app --group ai --group chat-api --group dev python -m pytest app/tests ai_worker/tests tests -q`

Expected: all pass except explicitly marked integration skips.

- [ ] **Step 3: 프론트와 Docker 검증**

Run: `npm run typecheck`

Run: `npm run build`

Workdir: `frontend`

Run: `docker compose config --quiet`

Expected: all pass.

- [ ] **Step 4: diff 품질과 변경 범위 확인**

Run: `git diff --check`

Run: `git status --short`

Expected: whitespace errors 없음. `.DS_Store`와 `.superpowers/`는 기존 상태 그대로이며 구현 파일만 추가·수정된다.

- [ ] **Step 5: 검증 문서 작성**

`docs/testing/medication-chat-api-verification.md`에 실행 명령, pass/skip 수, 테스트 DB 종류, OpenAI 실호출 제외 사실, 검증된 API 예시와 남은 배포 전 확인 사항을 기록한다. 성능 수치는 실제 OpenAI/Qdrant 환경에서 별도 측정 전에는 작성하지 않는다.
